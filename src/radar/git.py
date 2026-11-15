"""Thin wrapper around the git CLI.

This is the only module allowed to call git. It uses subprocess without a
shell, decodes output as UTF-8, and returns plain Python data (or the models
from ``radar.models``). Failures raise :class:`GitError` unless a caller opts
out with ``check=False``.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import time
from typing import Iterator, List, Optional, Sequence, Tuple

from .models import Branch, FileChange

# Directories whose contents are noise for every radar signal.
IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "vendor",
        "dist",
        "build",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".tox",
        ".eggs",
        "site-packages",
        "bower_components",
        "third_party",
    }
)

# Generated files: lockfiles, bundles, source maps, bytecode.
IGNORED_FILES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lockb",
        "poetry.lock",
        "Pipfile.lock",
        "uv.lock",
        "Gemfile.lock",
        "composer.lock",
        "Cargo.lock",
        "go.sum",
        "mix.lock",
        "pubspec.lock",
        "Podfile.lock",
        "flake.lock",
    }
)

IGNORED_SUFFIXES = (
    ".lock",
    ".min.js",
    ".min.css",
    ".map",
    ".pyc",
    ".pyo",
    ".class",
)

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class GitError(RuntimeError):
    """Raised when a git invocation exits non-zero."""

    def __init__(self, cmd: Sequence[str], returncode: int, stderr: str) -> None:
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stderr = stderr
        detail = stderr.strip() or f"exit code {returncode}"
        super().__init__(f"{' '.join(self.cmd)}: {detail}")


def is_ignored(path: str) -> bool:
    """Return True for lockfiles, vendored code, build output, and similar.

    Matching is on path components, so ``vendor/lib.js`` is skipped while
    ``src/vendor.py`` is kept.
    """
    normalized = path.replace("\\", "/").strip()
    if not normalized:
        return False

    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts:
        return False

    # Check every component: untracked directories arrive as "node_modules/".
    for part in parts:
        if part.lower() in IGNORED_DIRS:
            return True

    name = parts[-1].lower()
    if name in IGNORED_FILES:
        return True
    return name.endswith(IGNORED_SUFFIXES)


def run(
    args: Sequence[str],
    cwd: os.PathLike[str] | str,
    check: bool = True,
) -> str:
    """Run ``git <args>`` in *cwd* and return stdout.

    No shell is involved. With ``check=True`` a non-zero exit raises
    :class:`GitError`; with ``check=False`` stdout is returned regardless.
    """
    cmd = ["git", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=os.fspath(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError(cmd, 127, "git executable not found") from exc

    if check and proc.returncode != 0:
        raise GitError(cmd, proc.returncode, proc.stderr)
    return proc.stdout


def is_repo(cwd: os.PathLike[str] | str) -> bool:
    """Return True when *cwd* is inside a git working tree."""
    try:
        out = run(["rev-parse", "--is-inside-work-tree"], cwd, check=False)
    except GitError:
        return False
    return out.strip() == "true"


def _unquote(path: str) -> str:
    """Undo git's C-style quoting when ``core.quotePath`` is in play."""
    if len(path) >= 2 and path.startswith('"') and path.endswith('"'):
        try:
            value = ast.literal_eval(path)
        except (ValueError, SyntaxError):
            return path[1:-1]
        if isinstance(value, str):
            return value
    return path


def status_porcelain(cwd: os.PathLike[str] | str) -> List[FileChange]:
    """Parse ``git status --porcelain`` into :class:`FileChange` objects."""
    try:
        out = run(
            ["status", "--porcelain=v1", "-z", "--untracked-files=normal"],
            cwd,
        )
    except GitError:
        return []

    changes: List[FileChange] = []
    fields = out.split("\0")
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue

        code = entry[:2]
        path = _unquote(entry[3:])

        # Renames/copies carry the original path as the next -z field.
        if code[0] in ("R", "C") and i < len(fields):
            i += 1

        if is_ignored(path):
            continue

        if code == "??":
            status = "?"
        elif code[0] != " ":
            status = code[0]
        else:
            status = code[1]
        changes.append(FileChange(path=path, status=status))

    return changes


def branches(cwd: os.PathLike[str] | str) -> List[Branch]:
    """Return local branches with the age of their last commit in days."""
    try:
        out = run(
            [
                "for-each-ref",
                "--format=%(refname:short)%00%(committerdate:unix)",
                "refs/heads",
            ],
            cwd,
        )
    except GitError:
        return []

    now = int(time.time())
    result: List[Branch] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\0")
        if len(parts) < 2 or not parts[1].strip():
            continue
        name = parts[0]
        try:
            committed_at = int(parts[1])
        except ValueError:
            continue
        days_old = max(0, (now - committed_at) // 86400)
        result.append(Branch(name=name, days_old=int(days_old)))

    # Oldest first: the most neglected work bubbles to the top.
    result.sort(key=lambda b: (-b.days_old, b.name))
    return result


def log(
    cwd: os.PathLike[str] | str, n: int
) -> List[Tuple[str, str, str]]:
    """Return ``(sha7, iso_date, subject)`` for the last *n* commits."""
    if n <= 0:
        return []

    try:
        out = run(["log", f"-n{n}", "--format=%H%x00%aI%x00%s"], cwd)
    except GitError:
        # No commits yet, or not a repository.
        return []

    commits: List[Tuple[str, str, str]] = []
    for line in out.splitlines():
        parts = line.split("\0")
        if len(parts) < 3:
            continue
        commits.append((parts[0][:7], parts[1], parts[2]))
    return commits


def added_lines(
    cwd: os.PathLike[str] | str, n_commits: int
) -> Iterator[Tuple[str, str, int, str]]:
    """Yield added lines from the diffs of the last *n_commits* commits.

    Each item is ``(sha7, path, line_no, text)``. ``line_no`` is the line
    number in the file *after* the commit, tracked from ``@@`` hunk headers.
    Removed lines are never yielded.
    """
    for sha, _date, _subject in log(cwd, n_commits):
        try:
            diff = run(
                [
                    "-c",
                    "core.quotePath=false",
                    "show",
                    "--format=",
                    "--no-color",
                    "--no-ext-diff",
                    "--unified=0",
                    sha,
                ],
                cwd,
            )
        except GitError:
            continue

        path: Optional[str] = None
        line_no = 0
        in_hunk = False

        for raw in diff.splitlines():
            if raw.startswith("diff --git "):
                in_hunk = False
                path = None
                continue

            if raw.startswith("+++ ") and not in_hunk:
                target = raw[4:].split("\t", 1)[0]
                if target == "/dev/null":
                    path = None
                elif target.startswith("b/"):
                    path = _unquote(target[2:])
                else:
                    path = _unquote(target)
                continue

            match = _HUNK_RE.match(raw)
            if match:
                in_hunk = True
                line_no = int(match.group(1))
                continue

            # Outside a hunk only file headers matter.
            if not in_hunk:
                continue

            if raw.startswith("+"):
                if path is not None:
                    yield sha, path, line_no, raw[1:]
                line_no += 1
            elif raw.startswith(" "):
                line_no += 1
            # "-" lines are removals; "\ No newline..." is metadata.


_NUMSTAT_RE = re.compile(r"^(\d+|-)\t(\d+|-)\t(.*)$")


def _numstat_path(raw: str) -> str:
    """Return a usable path from a numstat entry.

    Renames appear as ``old => new`` or ``dir/{old => new}/file``; use the
    destination path so signals see the file that exists after the commit.
    """
    path = raw.strip()
    if " => " not in path:
        return path
    if "{" in path and "}" in path:
        start = path.index("{")
        end = path.rindex("}")
        inner = path[start + 1 : end]
        if " => " in inner:
            destination = inner.split(" => ", 1)[1]
            return path[:start] + destination + path[end + 1 :]
    return path.split(" => ", 1)[1]


def _split_numstat_tail(tail: str) -> Tuple[str, List[Tuple[int, int, str]]]:
    """Split a log field into ``(body, [(added, deleted, path)])``."""
    body_lines: List[str] = []
    stats: List[Tuple[int, int, str]] = []
    in_stats = False

    for line in tail.splitlines():
        match = _NUMSTAT_RE.match(line)
        if match:
            in_stats = True
            added = 0 if match.group(1) == "-" else int(match.group(1))
            deleted = 0 if match.group(2) == "-" else int(match.group(2))
            path = _numstat_path(match.group(3))
            if path:
                stats.append((added, deleted, path))
        elif in_stats:
            # A blank line closes the numstat block.
            continue
        else:
            body_lines.append(line)

    return "\n".join(body_lines).strip(), stats


def commits_numstat(
    cwd: os.PathLike[str] | str, n: int = 200
) -> List[Tuple[str, str, str, str, List[Tuple[int, int, str]]]]:
    """Return commit metadata plus per-file line counts in one git call.

    Each item is ``(sha7, iso_date, subject, body, [(added, deleted, path)])``
    for the last *n* non-merge commits, oldest last. Binary files report
    ``-`` in numstat and are normalized to zero.
    """
    if n <= 0:
        return []

    try:
        out = run(
            [
                "-c",
                "core.quotePath=false",
                "log",
                "--no-merges",
                f"-n{n}",
                "--numstat",
                "--format=%x00%H%x00%aI%x00%s%x00%b",
            ],
            cwd,
        )
    except GitError:
        return []

    fields = out.split("\0")
    commits: List[Tuple[str, str, str, str, List[Tuple[int, int, str]]]] = []

    # fields[0] is the empty prefix before the first commit's NUL marker.
    for index in range(1, len(fields) - 3, 4):
        sha, date, subject, tail = fields[index : index + 4]
        if len(sha) < 7 or not all(ch in "0123456789abcdef" for ch in sha):
            continue
        body, stats = _split_numstat_tail(tail)
        commits.append((sha[:7], date, subject, body, stats))

    return commits


def parent_sha(
    cwd: os.PathLike[str] | str, sha: str
) -> Optional[str]:
    """Return the first parent of *sha*, or None for a root commit."""
    try:
        out = run(["rev-parse", "--verify", "--quiet", f"{sha}^"], cwd)
    except GitError:
        return None
    parent = out.strip()
    return parent or None


def file_at(
    cwd: os.PathLike[str] | str, sha: str, path: str
) -> Optional[str]:
    """Return the contents of *path* at *sha*, or None if it is absent."""
    try:
        return run(["show", f"{sha}:{path}"], cwd)
    except GitError:
        return None

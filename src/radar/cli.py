"""Command line entry point: print the terminal radar and export a prompt."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
from typing import List, Optional, Sequence

from . import __version__, cache
from .budget import FULL, HARD_MAX, TARGET, est_tokens, fit, trimmed
from .export import render_md, render_xml
from .git import (
    branches,
    current_branch,
    is_repo,
    log,
    status_porcelain,
    toplevel,
)
from .models import Report
from .render_ascii import render_terminal
from .signals.cochange import find_hotspots
from .signals.deletions import find_large_deletions
from .signals.deps import find_dep_changes
from .signals.env import find_env_issues
from .signals.reverts import find_reverts
from .signals.todos import find_todos
from .tests_artifacts import find_failing
from .timeline import build_timeline

try:
    import pyperclip
except ImportError:  # pragma: no cover - depends on the environment

    class _MissingClipboard:
        @staticmethod
        def copy(text: str) -> None:
            raise RuntimeError("pyperclip is not installed")

    pyperclip = _MissingClipboard()

STALE_DAYS = 30
DEFAULT_COMMITS = 30
DEFAULT_BRANCHES = frozenset({"main", "master", "trunk"})
TEST_TIMEOUT = 120
PYTEST_FAILED_RE = re.compile(r"^\s*FAILED\s+(\S+)", re.MULTILINE)


def _mtime(cwd: os.PathLike[str] | str, path: str) -> float:
    try:
        return os.path.getmtime(os.path.join(os.fspath(cwd), path))
    except OSError:
        return -1.0


def _has_pytest(cwd: str) -> bool:
    return any(
        os.path.isfile(os.path.join(cwd, name))
        for name in ("pyproject.toml", "pytest.ini")
    ) or os.path.isdir(os.path.join(cwd, "tests"))


def _has_npm_test(cwd: str) -> bool:
    try:
        with open(os.path.join(cwd, "package.json"), encoding="utf-8") as handle:
            package = json.load(handle)
    except (OSError, ValueError):
        return False
    scripts = package.get("scripts") if isinstance(package, dict) else None
    if not isinstance(scripts, dict):
        return False
    test_script = scripts.get("test")
    return isinstance(test_script, str) and bool(test_script.strip())


def _detect_test_command(cwd: str):
    if _has_pytest(cwd):
        return "pytest", [sys.executable, "-m", "pytest", "-q", "--tb=no"]
    if _has_npm_test(cwd):
        return "npm", ["npm", "test"]
    return None


def run_repo_tests(cwd: str) -> List[str]:
    """Run one detected test command and return failures; never writes files."""
    detected = _detect_test_command(cwd)
    if detected is None:
        print("radar: no test runner detected")
        return []

    kind, command = detected
    print("running tests...")
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TEST_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [f"{kind} (timed out after {TEST_TIMEOUT}s)"]
    except OSError as exc:
        return [f"{kind} (could not run: {exc.__class__.__name__})"]

    output = re.sub(r"\x1b\[[0-9;]*m", "", proc.stdout or "")
    if kind == "pytest":
        failures = sorted(set(PYTEST_FAILED_RE.findall(output)))
        if failures:
            return failures
        if proc.returncode != 0:
            return [f"pytest (exit code {proc.returncode})"]
        return []

    if proc.returncode != 0:
        return [f"npm test (exit code {proc.returncode})"]
    return []


def build_report(
    cwd: os.PathLike[str] | str, n_commits: int = DEFAULT_COMMITS
) -> Report:
    """Collect the resume and decision signals for *cwd*."""
    report = Report()
    if not is_repo(cwd):
        return report

    report.uncommitted = status_porcelain(cwd)
    report.failing_tests = find_failing(cwd)
    report.todos = find_todos(cwd, n_commits)
    current = current_branch(cwd)
    report.stale_branches = [
        branch
        for branch in branches(cwd)
        if branch.days_old > STALE_DAYS
        and branch.name not in DEFAULT_BRANCHES
        and branch.name != current
    ]

    commits = log(cwd, 1)
    last_subject = commits[0][2] if commits else None
    if commits:
        report.last_commit_date = commits[0][1][:10]

    archaeology = (
        find_reverts(cwd) + find_large_deletions(cwd) + find_dep_changes(cwd)
    )
    dirty_by_mtime = sorted(
        report.uncommitted,
        key=lambda change: _mtime(cwd, change.path),
        reverse=True,
    )
    report.events = build_timeline(
        archaeology,
        report.last_commit_date,
        dirty_by_mtime,
        last_subject,
    )
    report.hotspots = find_hotspots(cwd)
    report.env_issues = find_env_issues(cwd)

    return report


def _copy_summary(
    size: int,
    cap: int,
    trimmed_items: List[str],
    label: str = "Copied",
    cached: bool = False,
) -> str:
    line = f"{label}: ~{size} tokens (cap {cap:,})"
    if trimmed_items:
        line += " | trimmed: " + ", ".join(trimmed_items)
    if cached:
        line += " (cached)"
    return line


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Legacy Windows consoles cannot encode every path or TODO character.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="radar",
        description="Show where work stopped in a git repository.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="repository to inspect (default: current directory)",
    )
    parser.add_argument(
        "--commits",
        type=int,
        default=DEFAULT_COMMITS,
        help=f"commits to scan for TODOs (default: {DEFAULT_COMMITS})",
    )
    parser.add_argument(
        "--md",
        action="store_true",
        help="use a Markdown briefing instead of XML",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=None,
        metavar="N",
        help=f"token cap (default: {TARGET}, hard maximum {HARD_MAX})",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="skip trimming and print a size warning",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        dest="no_copy",
        help="do not copy the prompt to the clipboard",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        dest="no_cache",
        help="skip reading and writing the report cache",
    )
    parser.add_argument(
        "--diagram",
        action="store_true",
        help="include a plain-ASCII timeline diagram in the prompt",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        dest="run_tests",
        help="run the project's test suite and include failures",
    )
    args = parser.parse_args(argv)

    cwd = os.path.abspath(args.path)
    if not is_repo(cwd):
        print(f"radar: not a git repository: {cwd}", file=sys.stderr)
        return 1
    if args.commits < 0:
        parser.error("--commits must be zero or greater")

    test_failures: List[str] = []
    if args.run_tests:
        test_failures = run_repo_tests(cwd)

    key: Optional[str] = None
    cached_report: Optional[Report] = None
    if not args.no_cache and not args.run_tests:
        try:
            key = cache.compute_key(cwd)
            if args.commits != DEFAULT_COMMITS:
                key = f"{key}:{args.commits}"
        except Exception:
            key = None
        if key is not None:
            try:
                cached_report = cache.load(cwd, key)
            except Exception:
                cached_report = None

    cached = cached_report is not None
    if cached_report is not None:
        report = cached_report
    else:
        report = build_report(cwd, args.commits)
        if key is not None:
            try:
                cache.save(cwd, key, report)
            except Exception:
                pass
    if test_failures:
        report.failing_tests = sorted(set(report.failing_tests) | set(test_failures))

    root = toplevel(cwd) or cwd
    repo_name = os.path.basename(os.path.normpath(root)) or os.path.basename(
        os.path.normpath(cwd)
    )
    print(render_terminal(report, repo_name=repo_name))

    render = render_md if args.md else render_xml
    requested = args.budget or TARGET
    cap = min(requested, HARD_MAX)

    if args.full:
        full_limits = dataclasses.replace(FULL, diagram=args.diagram)
        text = render(report, full_limits)
        size = est_tokens(text)
        trimmed_items: List[str] = []
        print(
            f"warning: --full bypasses the budget: "
            f"~{size} tokens (cap {cap:,})"
        )
    else:
        text, limits = fit(
            report, render, budget=requested, diagram=args.diagram
        )
        size = est_tokens(text)
        trimmed_items = trimmed(report, limits)
        if args.diagram and not limits.diagram:
            trimmed_items.append("diagram")
        if size > cap:
            print("warning: budget below minimum size")

    if args.no_copy:
        print(_copy_summary(size, cap, trimmed_items, label="Prompt", cached=cached))
        return 0

    try:
        pyperclip.copy(text)
    except Exception:
        print("clipboard unavailable, printing prompt:")
        print(text)
        print(
            _copy_summary(size, cap, trimmed_items, label="Prompt", cached=cached)
        )
        return 0

    print(_copy_summary(size, cap, trimmed_items, cached=cached))
    return 0


if __name__ == "__main__":
    sys.exit(main())

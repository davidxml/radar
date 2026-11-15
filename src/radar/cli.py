"""Command line entry point: print the terminal radar and export a prompt."""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Sequence

from . import __version__, cache
from .budget import FULL, HARD_MAX, TARGET, est_tokens, fit, trimmed
from .export import render_md, render_xml
from .git import branches, is_repo, log, status_porcelain, toplevel
from .models import Report
from .render_ascii import render_terminal
from .signals.deletions import find_large_deletions
from .signals.deps import find_dep_changes
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


def _mtime(cwd: os.PathLike[str] | str, path: str) -> float:
    try:
        return os.path.getmtime(os.path.join(os.fspath(cwd), path))
    except OSError:
        return -1.0


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
    report.stale_branches = [
        branch for branch in branches(cwd) if branch.days_old > STALE_DAYS
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
    args = parser.parse_args(argv)

    cwd = os.path.abspath(args.path)
    if not is_repo(cwd):
        print(f"radar: not a git repository: {cwd}", file=sys.stderr)
        return 1
    if args.commits < 0:
        parser.error("--commits must be zero or greater")

    key: Optional[str] = None
    cached_report: Optional[Report] = None
    if not args.no_cache:
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

    root = toplevel(cwd) or cwd
    repo_name = os.path.basename(os.path.normpath(root)) or os.path.basename(
        os.path.normpath(cwd)
    )
    print(render_terminal(report, repo_name=repo_name))

    render = render_md if args.md else render_xml
    requested = args.budget or TARGET
    cap = min(requested, HARD_MAX)

    if args.full:
        text = render(report, FULL)
        size = est_tokens(text)
        trimmed_items: List[str] = []
        print(
            f"warning: --full bypasses the budget: "
            f"~{size} tokens (cap {cap:,})"
        )
    else:
        text, limits = fit(report, render, budget=requested)
        size = est_tokens(text)
        trimmed_items = trimmed(report, limits)
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

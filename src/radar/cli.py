"""Command line entry point: print a plain-text Resume Here list."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence

from .git import branches, is_repo, log, status_porcelain
from .models import Report
from .signals.todos import find_todos

STALE_DAYS = 30
DEFAULT_COMMITS = 30


def build_report(
    cwd: os.PathLike[str] | str, n_commits: int = DEFAULT_COMMITS
) -> Report:
    """Collect the block 1 signals for *cwd*."""
    report = Report()
    if not is_repo(cwd):
        return report

    report.uncommitted = status_porcelain(cwd)
    report.todos = find_todos(cwd, n_commits)
    report.stale_branches = [
        branch for branch in branches(cwd) if branch.days_old > STALE_DAYS
    ]

    commits = log(cwd, 1)
    if commits:
        report.last_commit_date = commits[0][1][:10]

    return report


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def render_resume(report: Report) -> str:
    """Render the Resume Here block as plain text."""
    lines = ["Resume Here"]

    if report.last_commit_date:
        lines.append(f"  Last commit: {report.last_commit_date}")

    lines.append("")
    if report.uncommitted:
        lines.append(f"  Uncommitted ({_plural(len(report.uncommitted), 'file')})")
        for change in report.uncommitted:
            lines.append(f"    {change.status}  {change.path}")
    else:
        lines.append("  Uncommitted: clean")

    lines.append("")
    if report.todos:
        lines.append(f"  TODO / FIXME ({len(report.todos)})")
        for todo in report.todos:
            ref = f"  [{todo.ref}]" if todo.ref else ""
            lines.append(f"    {todo.path}:{todo.line}  {todo.text}{ref}")
    else:
        lines.append("  TODO / FIXME: none in recent commits")

    lines.append("")
    if report.stale_branches:
        lines.append(
            f"  Stale branches (older than {STALE_DAYS} days)"
        )
        for branch in report.stale_branches:
            lines.append(
                f"    {branch.name}  ({_plural(branch.days_old, 'day')})"
            )
    else:
        lines.append(f"  Stale branches: none older than {STALE_DAYS} days")

    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="radar",
        description="Show where work stopped in a git repository.",
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
    args = parser.parse_args(argv)

    cwd = os.path.abspath(args.path)
    if not is_repo(cwd):
        print(f"radar: not a git repository: {cwd}", file=sys.stderr)
        return 1
    if args.commits < 0:
        parser.error("--commits must be zero or greater")

    report = build_report(cwd, args.commits)
    print(render_resume(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

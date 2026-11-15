"""Command line entry point: print a plain-text Resume Here list."""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Sequence

from .git import branches, is_repo, log, status_porcelain
from .models import Event, Report
from .signals.deletions import find_large_deletions
from .signals.deps import find_dep_changes
from .signals.reverts import find_reverts
from .signals.todos import find_todos
from .timeline import build_timeline

STALE_DAYS = 30
DEFAULT_COMMITS = 30
MAX_DECISIONS = 15


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


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _shown_events(events: List[Event]) -> List[Event]:
    """Keep the highest-weight events, then show them chronologically."""
    ranked = sorted(events, key=lambda event: (-event.weight, event.date))
    chosen = ranked[:MAX_DECISIONS]
    return sorted(chosen, key=lambda event: event.date)


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

    lines.append("")
    lines.append("  Decisions")
    if report.events:
        for event in _shown_events(report.events):
            lines.append(
                f"    {event.date} | {event.kind}: {event.text} "
                f"[{event.conf}] | {event.ref or '-'}"
            )
    else:
        lines.append("    none yet")

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

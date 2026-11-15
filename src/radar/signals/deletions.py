"""Flag commits that delete a large share of the lines they touch."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

from ..git import commits_numstat, is_ignored
from ..models import Event

MIN_NET = 200
MIN_NET_WITH_RATIO = 50
DELETION_RATIO = 0.3


@dataclass
class _DeletionGroup:
    """Flagged commits that share a calendar date."""

    date: str
    total_net: int = 0
    commits: int = 0
    best_net: int = -1
    ref: str = ""
    per_file: Dict[str, int] = field(default_factory=dict)


def _count(value: int, singular: str, plural: str) -> str:
    return f"{value:,} {singular if value == 1 else plural}"


def find_large_deletions(
    cwd: os.PathLike[str] | str, n: int = 200
) -> List[Event]:
    """Return ``deletion`` events for commits that mostly remove code.

    A commit qualifies when its net deletion count (deleted minus added) is at
    least 200, or at least 50 while net deletions are 30% or more of all
    changed lines. Ignored paths (lockfiles, vendored code, build output) are
    not counted. Commits from the same day are merged into one event.
    """
    groups: Dict[str, _DeletionGroup] = {}

    for sha, date, _subject, _body, stats in commits_numstat(cwd, n):
        added_total = 0
        deleted_total = 0
        per_file: Dict[str, int] = {}

        for added, deleted, path in stats:
            if is_ignored(path):
                continue
            added_total += added
            deleted_total += deleted
            if deleted:
                per_file[path] = per_file.get(path, 0) + deleted

        changed = added_total + deleted_total
        if changed == 0:
            continue

        net = deleted_total - added_total
        ratio = net / float(changed)
        qualifies = net >= MIN_NET or (
            net >= MIN_NET_WITH_RATIO and ratio >= DELETION_RATIO
        )
        if not qualifies:
            continue

        day = date[:10]
        group = groups.get(day)
        if group is None:
            group = _DeletionGroup(date=day)
            groups[day] = group

        group.total_net += net
        group.commits += 1
        if net > group.best_net:
            group.best_net = net
            group.ref = sha
        for path, deleted in per_file.items():
            group.per_file[path] = group.per_file.get(path, 0) + deleted

    events: List[Event] = []
    for group in groups.values():
        top_path = max(
            group.per_file.items(), key=lambda item: (item[1], item[0])
        )[0]
        if group.commits == 1:
            text = (
                f"-{group.total_net:,} net lines in "
                f"{_count(len(group.per_file), 'file', 'files')} "
                f"(top: {top_path})"
            )
        else:
            text = (
                f"-{group.total_net:,} net lines across "
                f"{_count(group.commits, 'commit', 'commits')} "
                f"(top: {top_path})"
            )
        events.append(
            Event(
                date=group.date,
                kind="deletion",
                text=text,
                conf="e",
                ref=group.ref,
            )
        )

    return events

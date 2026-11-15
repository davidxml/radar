"""Flag commits that delete a large share of the lines they touch."""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

from ..git import commits_numstat, is_ignored
from ..models import Event

MIN_DELETED = 200
MIN_DELETED_WITH_RATIO = 50
DELETION_RATIO = 0.3


def find_large_deletions(
    cwd: os.PathLike[str] | str, n: int = 200
) -> List[Event]:
    """Return ``deletion`` events for commits that mostly remove code.

    A commit qualifies when it deletes at least 200 lines, or at least 50
    lines while deletions are 30% or more of all changed lines. Ignored
    paths (lockfiles, vendored code, build output) are not counted.
    """
    events: List[Event] = []

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

        if deleted_total == 0:
            continue

        ratio = deleted_total / float(added_total + deleted_total)
        qualifies = deleted_total >= MIN_DELETED or (
            deleted_total >= MIN_DELETED_WITH_RATIO and ratio >= DELETION_RATIO
        )
        if not qualifies:
            continue

        top_path = max(
            per_file.items(), key=lambda item: (item[1], item[0])
        )[0]
        file_count = len(per_file)
        events.append(
            Event(
                date=date[:10],
                kind="deletion",
                text=(
                    f"-{deleted_total} lines in {file_count} files "
                    f"(top: {top_path})"
                ),
                conf="e",
                ref=sha,
            )
        )

    return events

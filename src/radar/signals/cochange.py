"""Find file pairs that tend to change together."""

from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Tuple

from ..git import commits_numstat, is_ignored
from ..models import Hotspot

MAX_HOTSPOTS = 5


def find_hotspots(
    cwd,
    n: int = 200,
    min_count: int = 4,
    max_files_per_commit: int = 30,
) -> List[Hotspot]:
    """Return the strongest co-change pairs in the last *n* commits.

    Commits touching more than ``max_files_per_commit`` files are skipped:
    a sweeping rename or generated-code commit says little about coupling.
    """
    counts: Dict[Tuple[str, str], int] = {}

    for _sha, _date, _subject, _body, stats in commits_numstat(cwd, n):
        files = []
        seen = set()
        for _added, _deleted, path in stats:
            if is_ignored(path) or path in seen:
                continue
            seen.add(path)
            files.append(path)

        if not (2 <= len(files) <= max_files_per_commit):
            continue

        for a, b in combinations(sorted(files), 2):
            key = (a, b)
            counts[key] = counts.get(key, 0) + 1

    hotspots = [
        Hotspot(a=a, b=b, count=count)
        for (a, b), count in counts.items()
        if count >= min_count
    ]
    hotspots.sort(key=lambda item: (-item.count, item.a, item.b))
    return hotspots[:MAX_HOTSPOTS]

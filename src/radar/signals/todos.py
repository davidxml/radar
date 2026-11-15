"""Find TODO/FIXME/HACK/XXX markers on lines added in recent commits."""

from __future__ import annotations

import os
import re
from typing import List, Set, Tuple

from ..git import added_lines, is_ignored
from ..models import Todo

MARKER_RE = re.compile(r"\b(?:TODO|FIXME|HACK|XXX)\b")
MAX_TEXT = 80


def _truncate(text: str, limit: int = MAX_TEXT) -> str:
    return text.strip()[:limit]


def find_todos(
    cwd: os.PathLike[str] | str, n_commits: int = 30
) -> List[Todo]:
    """Return markers from added diff lines in the last *n_commits* commits.

    Only ``+`` lines are scanned, so deleting a TODO does not report one.
    ``line`` is the line number in the file after the commit. Text is
    truncated to :data:`MAX_TEXT` characters and ignored paths are skipped.
    """
    todos: List[Todo] = []
    seen: Set[Tuple[str, int, str]] = set()

    for ref, path, line_no, text in added_lines(cwd, n_commits):
        if is_ignored(path) or not MARKER_RE.search(text):
            continue

        body = _truncate(text)
        if not body:
            continue

        key = (path, line_no, body)
        if key in seen:
            continue
        seen.add(key)

        todos.append(Todo(path=path, line=line_no, text=body, ref=ref))

    return todos

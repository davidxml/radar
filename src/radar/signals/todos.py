"""Find TODO/FIXME/HACK/XXX markers on lines added in recent commits."""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Set, Tuple

from ..git import added_lines, is_ignored
from ..models import Todo

MARKER_RE = re.compile(r"\b(?:TODO|FIXME|HACK|XXX)\b")
MAX_TEXT = 80


def _truncate(text: str, limit: int = MAX_TEXT) -> str:
    return text.strip()[:limit]


def _read_lines(path: str) -> Optional[List[str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()
    except OSError:
        return None


def _anchor(
    cwd: str, todos: List[Todo]
) -> List[Todo]:
    """Re-anchor historical todos to the current working-tree files.

    A todo survives only if the file still exists and still contains a line
    with the same marker and text. Its line number becomes the current one.
    """
    cache: Dict[str, Optional[List[str]]] = {}
    seen: Set[Tuple[str, int, str]] = set()
    anchored: List[Todo] = []

    for todo in todos:
        if todo.path not in cache:
            cache[todo.path] = _read_lines(os.path.join(cwd, todo.path))
        lines = cache[todo.path]
        if lines is None:
            # File was deleted or renamed away: the todo is stale.
            continue

        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped[:MAX_TEXT] != todo.text:
                continue
            if not MARKER_RE.search(stripped):
                continue

            key = (todo.path, number, todo.text)
            if key in seen:
                break
            seen.add(key)
            anchored.append(
                Todo(
                    path=todo.path,
                    line=number,
                    text=todo.text,
                    ref=todo.ref,
                )
            )
            break

    return anchored


def find_todos(
    cwd: os.PathLike[str] | str, n_commits: int = 30
) -> List[Todo]:
    """Return markers from added diff lines that still exist on disk.

    Only ``+`` lines are scanned, so deleting a TODO does not report one.
    Every hit is then re-anchored to the current working tree: removed or
    renamed markers are dropped and moved markers get their current line
    number. Text is truncated to :data:`MAX_TEXT` characters and ignored
    paths are skipped.
    """
    root = os.fspath(cwd)
    candidates: List[Todo] = []
    seen: Set[Tuple[str, str]] = set()

    for ref, path, line_no, text in added_lines(root, n_commits):
        if is_ignored(path) or not MARKER_RE.search(text):
            continue

        body = _truncate(text)
        if not body:
            continue

        # The same marker may show up in several commits; keep the newest.
        key = (path, body)
        if key in seen:
            continue
        seen.add(key)

        candidates.append(
            Todo(path=path, line=line_no, text=body, ref=ref)
        )

    return _anchor(root, candidates)

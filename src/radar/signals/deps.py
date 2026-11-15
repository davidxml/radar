"""Detect dependency changes by diffing manifests across commits."""

from __future__ import annotations

import os
from typing import Callable, Iterable, List, Optional, Set

from ..git import commits_numstat, file_at, is_ignored, parent_sha
from ..models import Event
from .manifests import package_json, requirements

MAX_NAMES = 3

Parser = Callable[[str], Optional[Set[str]]]


def _parser_for(path: str) -> Optional[Parser]:
    name = path.rsplit("/", 1)[-1].lower()
    if name == "package.json":
        return package_json.parse
    if name == "requirements.txt":
        return requirements.parse
    return None


def _format_names(prefix: str, names: Iterable[str]) -> str:
    ordered = sorted(names)
    shown = ordered[:MAX_NAMES]
    parts = [f"{prefix}{name}" for name in shown]
    remaining = len(ordered) - len(shown)
    if remaining > 0:
        parts.append(f"{prefix}{remaining} more")
    return " ".join(parts)


def _manifest_paths(stats) -> List[str]:
    paths: List[str] = []
    for _added, _deleted, path in stats:
        if path in paths or is_ignored(path):
            continue
        if _parser_for(path) is None:
            continue
        paths.append(path)
    return paths


def find_dep_changes(
    cwd: os.PathLike[str] | str, n: int = 200
) -> List[Event]:
    """Return events for dependency-set changes in recent commits.

    Commits touching ``package.json`` or ``requirements.txt`` anywhere in the
    tree are compared against their first parent. A commit that adds and
    removes names is a ``swap`` (inferred); one-sided changes are ``other``
    (evidence). Invalid or missing manifests are skipped, never fatal.
    """
    events: List[Event] = []

    for sha, date, _subject, _body, stats in commits_numstat(cwd, n):
        paths = _manifest_paths(stats)
        if not paths:
            continue

        parent = parent_sha(cwd, sha)
        if parent is None:
            continue

        added: Set[str] = set()
        removed: Set[str] = set()

        for path in paths:
            parser = _parser_for(path)
            if parser is None:
                continue

            before_text = file_at(cwd, parent, path)
            after_text = file_at(cwd, sha, path)
            if before_text is None or after_text is None:
                continue

            before = parser(before_text)
            after = parser(after_text)
            if before is None or after is None:
                continue

            added.update(after - before)
            removed.update(before - after)

        if not added and not removed:
            continue

        if added and removed:
            kind, conf = "swap", "i"
            text = f"{_format_names('-', removed)} {_format_names('+', added)}"
        elif added:
            kind, conf = "other", "e"
            text = _format_names("+", added)
        else:
            kind, conf = "other", "e"
            text = _format_names("-", removed)

        events.append(
            Event(date=date[:10], kind=kind, text=text, conf=conf, ref=sha)
        )

    return events

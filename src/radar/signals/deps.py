"""Detect dependency changes by diffing manifests across commits."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from ..git import commits_numstat, file_at, is_ignored, parent_sha
from ..models import Event
from .manifests import (
    cargo_toml,
    composer,
    gemfile,
    go_mod,
    gradle,
    mix,
    package_json,
    pom,
    pubspec,
    pyproject,
    requirements,
)

MAX_NAMES = 3

Parser = Callable[[str], Optional[Set[str]]]

_PARSERS: Dict[str, Parser] = {
    "package.json": package_json.parse,
    "requirements.txt": requirements.parse,
    "pyproject.toml": pyproject.parse,
    "go.mod": go_mod.parse,
    "cargo.toml": cargo_toml.parse,
    "gemfile": gemfile.parse,
    "composer.json": composer.parse,
    "pom.xml": pom.parse,
    "build.gradle": gradle.parse,
    "build.gradle.kts": gradle.parse,
    "pubspec.yaml": pubspec.parse,
    "mix.exs": mix.parse,
}


@dataclass
class _OtherGroup:
    """One-sided dependency changes that share a calendar date."""

    first_date: str
    ref: str
    order: int
    added: Set[str] = field(default_factory=set)
    removed: Set[str] = field(default_factory=set)


def _parser_for(path: str) -> Optional[Parser]:
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return _PARSERS.get(name)


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


def _merged_text(added: Set[str], removed: Set[str]) -> str:
    parts: List[str] = []
    if removed:
        parts.append(_format_names("-", removed))
    if added:
        parts.append(_format_names("+", added))
    return " ".join(parts)


def find_dep_changes(
    cwd: os.PathLike[str] | str, n: int = 200
) -> List[Event]:
    """Return events for dependency-set changes in recent commits.

    Commits touching a supported manifest anywhere in the tree are compared
    against their first parent. A commit that adds and removes names is a
    ``swap`` (inferred) and stays separate. One-sided changes are ``other``
    (evidence); changes from the same day are merged, with duplicates removed
    and at most three names shown per side.
    """
    swaps: List[Tuple[int, Event]] = []
    other_groups: Dict[str, _OtherGroup] = {}

    for order, (sha, date, _subject, _body, stats) in enumerate(
        commits_numstat(cwd, n)
    ):
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
            swaps.append(
                (
                    order,
                    Event(
                        date=date[:10],
                        kind="swap",
                        text=(
                            f"{_format_names('-', removed)} "
                            f"{_format_names('+', added)}"
                        ),
                        conf="i",
                        ref=sha,
                    ),
                )
            )
            continue

        day = date[:10]
        group = other_groups.get(day)
        if group is None:
            group = _OtherGroup(first_date=date, ref=sha, order=order)
            other_groups[day] = group
        elif date < group.first_date:
            group.first_date = date
            group.ref = sha

        group.added.update(added)
        group.removed.update(removed)

    ordered: List[Tuple[int, Event]] = list(swaps)
    for day, group in other_groups.items():
        ordered.append(
            (
                group.order,
                Event(
                    date=day,
                    kind="other",
                    text=_merged_text(group.added, group.removed),
                    conf="e",
                    ref=group.ref,
                ),
            )
        )

    ordered.sort(key=lambda item: item[0])
    return [event for _order, event in ordered]

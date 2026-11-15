"""Order events into a timeline and group them into activity phases."""

from __future__ import annotations

import os
from datetime import date
from typing import Iterable, List, Optional, Sequence, Union

from .budget import shorten
from .models import Event, FileChange

MAX_STOP_TEXT = 99
STOP_SUBJECT_CHARS = 40
GAP_DAYS = 14

Uncommitted = Union[FileChange, str]


def _path_of(item: Uncommitted) -> str:
    return item.path if isinstance(item, FileChange) else str(item)


def _today() -> str:
    return date.today().isoformat()


def _newest_uncommitted(uncommitted: Sequence[Uncommitted]) -> str:
    """Pick the uncommitted file with the most recent mtime.

    Relative paths may not resolve from the process working directory; in
    that case fall back to the first entry, which callers order by mtime.
    """
    newest: Optional[str] = None
    newest_mtime: Optional[float] = None

    for item in uncommitted:
        path = _path_of(item)
        try:
            mtime: Optional[float] = os.path.getmtime(path)
        except OSError:
            mtime = None

        if mtime is not None and (
            newest_mtime is None or mtime > newest_mtime
        ):
            newest = path
            newest_mtime = mtime

    if newest is None and uncommitted:
        newest = _path_of(uncommitted[0])
    return newest or ""


def build_timeline(
    events: Iterable[Event],
    last_commit_date: Optional[str],
    uncommitted: Sequence[Uncommitted],
    last_subject: Optional[str],
) -> List[Event]:
    """Return chronological, deduped events with a synthetic ``stop`` event.

    When the working tree is dirty, the stop event names the most recently
    modified uncommitted file, includes the last commit subject, and is dated
    today. Otherwise it records the last commit subject on the last commit
    date. The stop text stays under 100 characters.
    """
    items: List[Event] = list(events)

    if uncommitted:
        newest = _newest_uncommitted(uncommitted)
        subject = (last_subject or "no commits yet")[:STOP_SUBJECT_CHARS]
        newest = newest or "working tree"
        suffix = f" uncommitted changes (last commit: {subject})"
        available = max(0, MAX_STOP_TEXT - len(suffix))
        path = (
            newest
            if len(newest) <= available
            else shorten(newest, available)
        )
        stop_text = f"{path}{suffix}"[:MAX_STOP_TEXT]
        stop_date = _today()
    else:
        stop_text = (last_subject or "no commits yet")[:MAX_STOP_TEXT]
        stop_date = last_commit_date or _today()

    items.append(Event(date=stop_date, kind="stop", text=stop_text, conf="e"))

    timeline: List[Event] = []
    seen = set()
    for event in sorted(items, key=lambda item: item.date):
        key = (event.date, event.kind, event.text)
        if key in seen:
            continue
        seen.add(key)
        timeline.append(event)

    return timeline


def phases(
    events: Iterable[Event], gap_days: int = GAP_DAYS
) -> List[List[Event]]:
    """Group events into phases separated by *gap_days* or more of silence."""
    ordered = sorted(events, key=lambda item: item.date)
    groups: List[List[Event]] = []
    previous: Optional[date] = None

    for event in ordered:
        try:
            current: Optional[date] = date.fromisoformat(event.date[:10])
        except ValueError:
            current = None

        starts_new = not groups or (
            previous is not None
            and current is not None
            and (current - previous).days >= gap_days
        )
        if starts_new:
            groups.append([])
        groups[-1].append(event)

        if current is not None:
            previous = current

    return groups

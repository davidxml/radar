"""Detect revert commits from their message bodies or subjects."""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

from ..git import commits_numstat
from ..models import Event

REVERT_SUBJECT_PREFIX = 'Revert "'
REVERT_BODY_RE = re.compile(r"This reverts commit ([0-9a-f]{7,40})")
MAX_TEXT = 60


def _resolve_subject(
    target: str, subjects: Dict[str, str]
) -> Optional[str]:
    """Look up a reverted commit's subject by its abbreviated sha."""
    for sha, subject in subjects.items():
        if target.startswith(sha) or sha.startswith(target[:7]):
            return subject
    return None


def _original_subject(
    subject: str, body: str, subjects: Dict[str, str]
) -> Optional[str]:
    if subject.startswith(REVERT_SUBJECT_PREFIX):
        original = subject[len(REVERT_SUBJECT_PREFIX) :]
        if original.endswith('"'):
            original = original[:-1]
        return original

    match = REVERT_BODY_RE.search(body or "")
    if not match:
        return None

    return _resolve_subject(match.group(1), subjects) or match.group(1)


def find_reverts(
    cwd: os.PathLike[str] | str, n: int = 200
) -> List[Event]:
    """Return one ``revert`` event for each revert commit in the last *n*."""
    commits = commits_numstat(cwd, n)
    subjects = {sha: subject for sha, _d, subject, _b, _s in commits}

    events: List[Event] = []
    for sha, date, subject, body, _stats in commits:
        original = _original_subject(subject, body, subjects)
        if original is None:
            continue
        events.append(
            Event(
                date=date[:10],
                kind="revert",
                text=f"reverted: {original[:MAX_TEXT]}",
                conf="e",
                ref=sha,
            )
        )
    return events

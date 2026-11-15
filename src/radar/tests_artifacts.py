"""Read test failures from artifacts that already exist on disk.

Nothing here runs a test command or touches the network: a missing or broken
artifact is simply one less source of evidence.
"""

from __future__ import annotations

import json
import os
import time
import xml.etree.ElementTree as ET
from typing import List, Set

MAX_FAILURES = 50
STALE_SECONDS = 30 * 24 * 60 * 60

LASTFAILED = ".pytest_cache/v/cache/lastfailed"
JUNIT_FILES = (
    "junit.xml",
    "test-results.xml",
    "reports/junit.xml",
    "test-reports/junit.xml",
)
ARTIFACTS = (LASTFAILED, *JUNIT_FILES)


def _path(cwd: os.PathLike[str] | str, relpath: str) -> str:
    return os.path.join(os.fspath(cwd), relpath)


def _is_fresh(path: str, now: float) -> bool:
    try:
        age = now - os.stat(path).st_mtime
    except OSError:
        return False
    return age <= STALE_SECONDS


def _read_lastfailed(path: str) -> Set[str]:
    with open(path, encoding="utf-8", errors="replace") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return set()
    return {str(node) for node in data if str(node).strip()}


def _read_junit(path: str) -> Set[str]:
    root = ET.parse(path).getroot()
    failures: Set[str] = set()
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        classname = case.get("classname") or ""
        name = case.get("name") or ""
        if classname and name:
            failures.add(f"{classname}::{name}")
        elif name:
            failures.add(name)
        elif classname:
            failures.add(classname)
    return failures


def find_failing(cwd: os.PathLike[str] | str) -> List[str]:
    """Return node ids that existing test artifacts record as failing."""
    now = time.time()
    found: Set[str] = set()

    for relpath in ARTIFACTS:
        path = _path(cwd, relpath)
        if not os.path.isfile(path) or not _is_fresh(path, now):
            continue
        try:
            if relpath == LASTFAILED:
                found.update(_read_lastfailed(path))
            else:
                found.update(_read_junit(path))
        except Exception:
            # A malformed artifact is skipped; the rest are still useful.
            continue

    return sorted(found)[:MAX_FAILURES]


def fingerprint(cwd: os.PathLike[str] | str) -> str:
    """Return a stable signature of the artifact files that exist."""
    parts: List[str] = []
    for relpath in ARTIFACTS:
        path = _path(cwd, relpath)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        parts.append(f"{relpath}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)

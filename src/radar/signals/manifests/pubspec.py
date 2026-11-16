"""Parse dependency names out of a pubspec.yaml without a YAML library."""

from __future__ import annotations

import re
from typing import Optional, Set

_DEPENDENCY_LINE_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$")
_SECTIONS = {"dependencies", "dev_dependencies"}


def parse(text: str) -> Set[str]:
    """Return names from top-level ``dependencies`` sections.

    Children are expected at two-space indentation. ``flutter`` and packages
    whose value block is an SDK dependency are skipped.
    """
    names: Set[str] = set()
    in_section = False
    pending_name: Optional[str] = None
    pending_skip = False

    def finish() -> None:
        nonlocal pending_name, pending_skip
        if pending_name is not None and not pending_skip:
            names.add(pending_name)
        pending_name = None
        pending_skip = False

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        indent = len(line) - len(line.lstrip(" "))

        if indent == 0:
            finish()
            in_section = stripped in {f"{name}:" for name in _SECTIONS}
            continue

        if not in_section:
            continue

        if indent == 2:
            finish()
            match = _DEPENDENCY_LINE_RE.match(stripped)
            if not match:
                continue

            pending_name = match.group(1)
            remainder = match.group(2).strip()
            pending_skip = (
                pending_name == "flutter"
                or bool(re.match(r"^\{?\s*sdk\s*:", remainder))
            )
        elif indent > 2 and pending_name is not None:
            if re.match(r"^sdk\s*:", stripped):
                pending_skip = True

    finish()
    return names

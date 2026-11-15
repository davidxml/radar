"""Parse dependency names out of a package.json."""

from __future__ import annotations

import json
from typing import Optional, Set

SECTIONS = ("dependencies", "devDependencies", "peerDependencies")


def parse(text: str) -> Optional[Set[str]]:
    """Return dependency names, or None when the file is not valid JSON."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    names: Set[str] = set()
    for section in SECTIONS:
        dependencies = data.get(section)
        if isinstance(dependencies, dict):
            names.update(
                name for name in dependencies if isinstance(name, str)
            )
    return names

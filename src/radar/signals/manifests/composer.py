"""Parse package names out of a composer.json."""

from __future__ import annotations

import json
from typing import Set


def parse(text: str) -> Set[str]:
    """Return package names from ``require`` and ``require-dev``.

    The platform package ``php`` and PHP extension/library pseudo-packages
    (``ext-*`` and ``lib-*``) are skipped.
    """
    names: Set[str] = set()

    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return names

    if not isinstance(data, dict):
        return names

    for section in ("require", "require-dev"):
        table = data.get(section)
        if not isinstance(table, dict):
            continue

        for key in table:
            if not isinstance(key, str) or not key.strip():
                continue

            lowered = key.lower()
            if lowered == "php":
                continue
            if lowered.startswith("ext-") or lowered.startswith("lib-"):
                continue

            names.add(key)

    return names

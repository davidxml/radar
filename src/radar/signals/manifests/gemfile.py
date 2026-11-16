"""Parse gem names out of a Gemfile."""

from __future__ import annotations

import re
from typing import Set

_GEM_RE = re.compile(r"^\s*gem\s+['\"]([^'\"]+)['\"]")


def parse(text: str) -> Set[str]:
    """Return names from ``gem "name"`` and ``gem 'name'`` lines."""
    names: Set[str] = set()

    for raw in text.splitlines():
        line = raw.split("#", 1)[0]
        match = _GEM_RE.match(line)
        if match and match.group(1).strip():
            names.add(match.group(1).strip())

    return names

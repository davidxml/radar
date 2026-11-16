"""Parse dependency atoms out of a mix.exs."""

from __future__ import annotations

import re
from typing import Set

# Match dependency-looking tuples: {:name, "~> 1.0"} or
# {:name, github: "owner/repo"}. Requiring a quoted version or a source/option
# key avoids treating ordinary tuples such as {:ok, result} as dependencies.
_DEP_RE = re.compile(
    r"\{\s*:([A-Za-z_][A-Za-z0-9_]*[!?]?)\s*,\s*(?:"
    r"['\"]|(?:github|git|path|hex|branch|tag|ref|only|runtime|optional|"
    r"targets|compile|app|manager|organization)\s*:)"
)


def parse(text: str) -> Set[str]:
    """Return dependency atom names from mix.exs tuples."""
    names: Set[str] = set()

    # Keep newlines so a tuple split over several lines still matches.
    cleaned = "\n".join(
        raw.split("#", 1)[0] for raw in text.splitlines()
    )
    for match in _DEP_RE.finditer(cleaned):
        names.add(match.group(1))

    return names

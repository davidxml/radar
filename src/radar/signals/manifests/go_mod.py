"""Parse module paths out of a go.mod."""

from __future__ import annotations

import re
from typing import Set

_INDIRECT_RE = re.compile(r"//\s*indirect\s*$")
_REQUIRE_RE = re.compile(r"^require(?:\s|\(|$)")


def _add_require_line(line: str, names: Set[str]) -> None:
    if _INDIRECT_RE.search(line):
        return

    content = line.split("//", 1)[0].strip()
    if not content or content.startswith(")"):
        return

    fields = content.split()
    if len(fields) < 2:
        return

    module = fields[0].strip()
    if not module or module in {"(", ")", "require"}:
        return
    if module.startswith("//"):
        return

    names.add(module)


def parse(text: str) -> Set[str]:
    """Return module paths from ``require`` directives.

    Both single-line and parenthesized block forms are supported. Indirect
    requirements, ``replace``/``exclude`` directives, and all other go.mod
    statements are ignored.
    """
    names: Set[str] = set()
    in_require_block = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        if in_require_block:
            if line.startswith(")"):
                in_require_block = False
                continue
            _add_require_line(line, names)
            continue

        if not _REQUIRE_RE.match(line):
            continue

        rest = line[len("require") :].strip()
        if rest.startswith("("):
            in_require_block = True
            continue
        _add_require_line(rest, names)

    return names

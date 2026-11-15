"""Parse dependency names out of a requirements.txt."""

from __future__ import annotations

import re
from typing import Set

# Everything that can terminate a package name: specifiers, extras, markers,
# direct-reference URLs, and whitespace.
_NAME_RE = re.compile(r"[<>=!~;,\s\[@]")


def parse(text: str) -> Set[str]:
    """Return normalized requirement names.

    Comments, blank lines, option lines (``-r``, ``-e``, ``--``), extras,
    version specifiers, and environment markers are discarded. Names are
    lowercased and ``_`` is treated the same as ``-``.
    """
    names: Set[str] = set()

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue

        # Direct references can be separated by whitespace: "pkg @ url".
        token = line.split()[0] if line.split() else ""
        if not token:
            continue

        name = _NAME_RE.split(token, 1)[0]
        if not name or name.startswith("-"):
            continue

        names.add(name.lower().replace("_", "-"))

    return names

"""Parse dependency coordinates out of Gradle build files."""

from __future__ import annotations

import re
from typing import Set

_CONFIGURATIONS = (
    "annotationProcessor",
    "testImplementation",
    "testRuntimeOnly",
    "implementation",
    "compileOnly",
    "runtimeOnly",
    "kapt",
    "api",
)

_CONFIG_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(name) for name in _CONFIGURATIONS)
    + r")\s*\(?\s*(['\"])([^'\"]+)\1"
)


def parse(text: str) -> Set[str]:
    """Return ``group:artifact`` names from common Gradle configurations.

    Groovy and Kotlin DSL string forms are supported. ``project(...)`` and
    ``files(...)`` declarations do not match because their argument is not a
    quoted coordinate immediately following the configuration name.
    """
    names: Set[str] = set()

    # Remove block comments, then line comments, before looking for
    # declarations. Preserve newlines so multi-line Kotlin calls still work.
    cleaned = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    cleaned = re.sub(r"//[^\n]*", "", cleaned)

    for match in _CONFIG_RE.finditer(cleaned):
        coordinate = match.group(2).strip()
        if not coordinate:
            continue

        parts = coordinate.split(":")
        if len(parts) < 2:
            continue

        group = parts[0].strip()
        artifact = parts[1].strip()
        if group and artifact:
            names.add(f"{group}:{artifact}")

    return names

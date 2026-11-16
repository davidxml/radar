"""Parse dependency names out of a pyproject.toml."""

from __future__ import annotations

import re
from typing import Any, Optional, Set

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib

# Everything that can terminate a PEP 508 package name.
_NAME_RE = re.compile(r"[<>=!~;,\s\[@(]")
_NAME_TOKEN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


def _normalize_pep508(value: str) -> Optional[str]:
    """Return the normalized project name from a PEP 508 requirement."""
    token = value.strip()
    if not token:
        return None

    name = _NAME_RE.split(token, 1)[0]
    if not name or not _NAME_TOKEN_RE.match(name):
        return None
    return name.lower().replace("_", "-")


def _add_pep508(value: Any, names: Set[str]) -> None:
    if not isinstance(value, str):
        return
    name = _normalize_pep508(value)
    if name is not None:
        names.add(name)


def _add_pep508_list(values: Any, names: Set[str]) -> None:
    if not isinstance(values, list):
        return
    for value in values:
        _add_pep508(value, names)


def _add_poetry_table(table: Any, names: Set[str]) -> None:
    if not isinstance(table, dict):
        return
    for key in table:
        if not isinstance(key, str):
            continue
        if key.strip().lower() == "python":
            continue
        name = _normalize_pep508(key)
        if name is not None:
            names.add(name)


def parse(text: str) -> Set[str]:
    """Return normalized dependency names from the supported TOML tables.

    Invalid or unrecognized documents yield an empty set. PEP 508 strings have
    extras, specifiers, and markers stripped, and the usual Python name
    normalization (lowercase, ``_`` equivalent to ``-``) is applied.
    """
    names: Set[str] = set()

    try:
        data = tomllib.loads(text)
    except Exception:
        return names

    if not isinstance(data, dict):
        return names

    try:
        project = data.get("project")
        if isinstance(project, dict):
            _add_pep508_list(project.get("dependencies"), names)

            optional = project.get("optional-dependencies")
            if isinstance(optional, dict):
                for group in optional.values():
                    _add_pep508_list(group, names)

        tool = data.get("tool")
        if isinstance(tool, dict):
            poetry = tool.get("poetry")
            if isinstance(poetry, dict):
                _add_poetry_table(poetry.get("dependencies"), names)

                groups = poetry.get("group")
                if isinstance(groups, dict):
                    for group in groups.values():
                        if isinstance(group, dict):
                            _add_poetry_table(
                                group.get("dependencies"), names
                            )

        dependency_groups = data.get("dependency-groups")
        if isinstance(dependency_groups, dict):
            for entries in dependency_groups.values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    # ``{include-group = "..."}`` entries are not packages.
                    if isinstance(entry, str):
                        _add_pep508(entry, names)
    except Exception:
        return set()

    return names

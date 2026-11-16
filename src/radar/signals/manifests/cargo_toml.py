"""Parse dependency names out of a Cargo.toml."""

from __future__ import annotations

from typing import Any, Optional, Set

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib


def _add_dependencies(table: Any, names: Set[str]) -> None:
    if not isinstance(table, dict):
        return

    for key, value in table.items():
        if not isinstance(key, str) or not key:
            continue

        name: Optional[str] = key
        if isinstance(value, dict):
            package = value.get("package")
            if isinstance(package, str) and package.strip():
                name = package.strip()

        if name:
            names.add(name)


def parse(text: str) -> Set[str]:
    """Return crate names from Cargo dependency tables.

    Invalid or unrecognized documents yield an empty set. A dependency table
    with ``package = "real-name"`` contributes the real package name.
    """
    names: Set[str] = set()

    try:
        data = tomllib.loads(text)
    except Exception:
        return names

    if not isinstance(data, dict):
        return names

    try:
        for section in (
            "dependencies",
            "dev-dependencies",
            "build-dependencies",
        ):
            _add_dependencies(data.get(section), names)

        workspace = data.get("workspace")
        if isinstance(workspace, dict):
            _add_dependencies(workspace.get("dependencies"), names)

        target = data.get("target")
        if isinstance(target, dict):
            for target_table in target.values():
                if isinstance(target_table, dict):
                    _add_dependencies(
                        target_table.get("dependencies"), names
                    )
    except Exception:
        return set()

    return names

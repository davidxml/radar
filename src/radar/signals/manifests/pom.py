"""Parse Maven coordinates out of a pom.xml."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional, Set


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> Optional[str]:
    for child in element:
        if _local_name(child.tag) == name:
            text = (child.text or "").strip()
            return text
    return None


def _walk(
    element: ET.Element,
    names: Set[str],
    in_dependencies: bool = False,
    in_plugin: bool = False,
) -> None:
    tag = _local_name(element.tag)

    if tag == "plugin":
        in_plugin = True
    if tag == "dependencies":
        in_dependencies = True

    if tag == "dependency" and in_dependencies and not in_plugin:
        group = _child_text(element, "groupId")
        artifact = _child_text(element, "artifactId")
        if group and artifact:
            names.add(f"{group}:{artifact}")

    for child in element:
        _walk(child, names, in_dependencies, in_plugin)


def parse(text: str) -> Set[str]:
    """Return ``groupId:artifactId`` for dependencies outside plugin blocks.

    The parser is namespace-agnostic and includes dependencies nested under
    ``dependencyManagement``. Property placeholders are kept verbatim.
    """
    names: Set[str] = set()

    try:
        root = ET.fromstring(text)
    except Exception:
        return names

    try:
        _walk(root, names)
    except Exception:
        return set()

    return names

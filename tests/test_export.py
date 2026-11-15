"""Tests for XML/Markdown export."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from radar.budget import FULL
from radar.export import event_line, pick_events, render_md, render_xml
from radar.models import Branch, Event, FileChange, Report, Todo

TRICKY = "A & B < C > D \"quoted\" 'single' café 日本語"


def _full_report() -> Report:
    return Report(
        uncommitted=[
            FileChange(path=f"src/{TRICKY}.py", status="M", lines_changed=3)
        ],
        todos=[
            Todo(
                path=f"docs/{TRICKY}.md",
                line=7,
                text=TRICKY,
                ref="abc1234",
            )
        ],
        failing_tests=[f"tests/test_{TRICKY}.py::case"],
        stale_branches=[Branch(name=TRICKY, days_old=42)],
        events=[
            Event(
                date="2026-01-02",
                kind="revert",
                text=TRICKY,
                conf="e",
                ref="abc1234",
            )
        ],
    )


def test_render_xml_escapes_special_characters_and_parses():
    report = _full_report()

    root = ET.fromstring(render_xml(report, FULL))

    assert root.tag == "project_handoff"

    file_node = root.find(".//file")
    assert file_node is not None
    assert file_node.get("path") == report.uncommitted[0].path
    assert file_node.get("status") == "M"

    todo_node = root.find(".//todo")
    assert todo_node is not None
    assert todo_node.get("path") == report.todos[0].path
    assert todo_node.get("line") == "7"
    assert todo_node.text == TRICKY

    test_node = root.find(".//test")
    assert test_node is not None
    assert test_node.text == report.failing_tests[0]

    branch_node = root.find(".//branch")
    assert branch_node is not None
    assert branch_node.get("age_days") == "42"
    assert TRICKY.startswith(branch_node.get("name"))

    timeline_node = root.find(".//timeline")
    assert timeline_node is not None
    assert event_line(report.events[0]) in (timeline_node.text or "")


def test_render_xml_handles_an_empty_report():
    root = ET.fromstring(render_xml(Report(), FULL))

    assert root.tag == "project_handoff"
    assert root.find(".//timeline") is None
    assert root.find("instructions") is not None


def test_render_md_includes_every_populated_section():
    md = render_md(_full_report(), FULL)

    assert "# Project handoff" in md
    assert "## Uncommitted" in md
    assert "## TODOs" in md
    assert "## Failing tests" in md
    assert "## Stale branches" in md
    assert "## Timeline" in md
    assert "## Instructions" in md


def test_render_md_omits_empty_sections():
    md = render_md(Report(), FULL)

    assert "# Project handoff" in md
    assert "## Instructions" in md
    assert "## Uncommitted" not in md
    assert "## TODOs" not in md
    assert "## Failing tests" not in md
    assert "## Stale branches" not in md
    assert "## Timeline" not in md


def test_pick_events_keeps_stop_when_the_cap_is_one():
    stop = Event(date="2026-01-01", kind="stop", text="stopped", conf="e")
    revert = Event(
        date="2026-02-01",
        kind="revert",
        text="revert",
        conf="e",
        ref="abc1234",
    )

    assert pick_events([revert, stop], 1) == [stop]


def test_pick_events_returns_chronological_order():
    stop = Event(date="2026-01-01", kind="stop", text="stopped", conf="e")
    revert = Event(
        date="2026-02-01",
        kind="revert",
        text="revert",
        conf="e",
        ref="abc1234",
    )

    assert pick_events([revert, stop], 2) == [stop, revert]

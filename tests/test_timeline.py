"""Tests for timeline ordering, the stop event, and phase grouping."""

from __future__ import annotations

import os
from datetime import date

from radar.models import Event, FileChange
from radar.timeline import build_timeline, phases


def _event(day: str, kind: str = "other", text: str = "change") -> Event:
    return Event(date=day, kind=kind, text=text, conf="e", ref="abc1234")


def test_build_timeline_sorts_and_dedupes_then_adds_stop():
    events = [
        _event("2026-03-01", "deletion", "removed old code"),
        _event("2026-01-01", "revert", "reverted: bad idea"),
        _event("2026-01-01", "revert", "reverted: bad idea"),
    ]

    timeline = build_timeline(events, "2026-03-02", [], "last work")

    assert [event.date for event in timeline] == [
        "2026-01-01",
        "2026-03-01",
        "2026-03-02",
    ]
    assert [event.kind for event in timeline].count("revert") == 1
    stop = timeline[-1]
    assert stop.kind == "stop"
    assert stop.conf == "e"
    assert stop.text == "last work"


def test_stop_uses_today_and_the_newest_uncommitted_file(
    tmp_path, monkeypatch
):
    old = tmp_path / "old.py"
    new = tmp_path / "new.py"
    old.write_text("old\n", encoding="utf-8")
    new.write_text("new\n", encoding="utf-8")
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))
    monkeypatch.chdir(tmp_path)

    changes = [
        FileChange(path="old.py", status="M"),
        FileChange(path="new.py", status="M"),
    ]

    timeline = build_timeline([], "2026-01-01", changes, "ignored")

    stop = timeline[-1]
    assert stop.text == "new.py uncommitted changes (last commit: ignored)"
    assert stop.date == date.today().isoformat()


def test_stop_falls_back_to_first_change_for_relative_paths():
    changes = [
        FileChange(path="missing-a.py", status="?"),
        FileChange(path="missing-b.py", status="?"),
    ]

    timeline = build_timeline([], "2026-01-01", changes, "ignored")

    assert timeline[-1].text == (
        "missing-a.py uncommitted changes (last commit: ignored)"
    )


def test_stop_without_commits_uses_today():
    timeline = build_timeline([], None, [], None)

    assert timeline[-1].kind == "stop"
    assert timeline[-1].text == "no commits yet"
    assert timeline[-1].date == date.today().isoformat()


def test_stop_truncates_long_last_subject():
    timeline = build_timeline([], "2026-01-01", [], "x" * 100)

    assert timeline[-1].text == "x" * 99
    assert len(timeline[-1].text) < 100


def test_stop_includes_last_commit_subject_and_stays_under_100(tmp_path):
    dirty = tmp_path / ("very-long-file-name-" + "x" * 80 + ".py")
    dirty.write_text("x\n", encoding="utf-8")
    subject = "subject " + "y" * 100

    timeline = build_timeline(
        [],
        "2026-01-01",
        [FileChange(path=str(dirty), status="M")],
        subject,
    )

    stop = timeline[-1]
    assert "(last commit: " + subject[:40] + ")" in stop.text
    assert len(stop.text) < 100


def test_phases_split_after_fourteen_days():
    events = [
        _event("2026-01-01"),
        _event("2026-01-10"),
        _event("2026-01-24"),
        _event("2026-01-25"),
    ]

    groups = phases(events, gap_days=14)

    assert [[event.date for event in group] for group in groups] == [
        ["2026-01-01", "2026-01-10"],
        ["2026-01-24", "2026-01-25"],
    ]


def test_phases_of_empty_timeline_is_empty():
    assert phases([]) == []

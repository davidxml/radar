"""Tests for the plain-ASCII terminal radar."""

from __future__ import annotations

from datetime import date

from radar.models import Branch, EnvIssue, Event, FileChange, Hotspot, Report, Todo
from radar.render_ascii import render_terminal


def _small_report() -> Report:
    return Report(
        uncommitted=[FileChange(path="src/app.py", status="M")],
        todos=[Todo(path="src/app.py", line=3, text="# TODO: finish", ref="abc1234")],
        failing_tests=["tests.test_app::test_finish"],
        stale_branches=[Branch(name="wip/old", days_old=41)],
        events=[
            Event(date="2026-01-01", kind="revert", text="reverted parser", conf="e", ref="abc1234"),
            Event(date="2026-01-02", kind="stop", text="parser WIP", conf="e"),
        ],
        last_commit_date="2026-01-02",
    )


def test_output_is_plain_ascii():
    out = render_terminal(_small_report(), "demo", today=date(2026, 1, 3))

    assert out.isascii()


def test_clean_repo_says_nothing_pending():
    out = render_terminal(
        Report(last_commit_date="2026-01-01"), "demo", today=date(2026, 1, 2)
    )

    assert "Nothing pending" in out
    assert "Uncommitted" not in out
    assert "TIMELINE" not in out


def test_empty_sections_are_omitted():
    report = Report(
        uncommitted=[FileChange(path="app.py", status="M")],
        last_commit_date="2026-01-01",
    )

    out = render_terminal(report, "demo", today=date(2026, 1, 2))

    assert "Uncommitted (1)" in out
    assert "TODO / FIXME" not in out
    assert "Failing tests" not in out
    assert "Stale branches" not in out
    assert "TIMELINE" not in out
    assert "Nothing pending" not in out


def test_a_long_gap_between_events_prints_days_quiet():
    report = Report(
        events=[
            Event(date="2026-01-01", kind="other", text="first", conf="e"),
            Event(date="2026-01-22", kind="other", text="second", conf="e"),
        ]
    )

    out = render_terminal(report, "demo", today=date(2026, 1, 23))

    assert "21 days quiet" in out


def test_long_paths_and_many_events_stay_within_caps():
    report = Report(
        uncommitted=[
            FileChange(path="src/" + "a" * 200 + f"/file{index}.py", status="M")
            for index in range(50)
        ],
        todos=[
            Todo(
                path="src/" + "b" * 200 + f"/todo{index}.py",
                line=index + 1,
                text="# TODO: " + "c" * 200,
            )
            for index in range(50)
        ],
        failing_tests=[
            f"tests/test_{index}.py::test_" + "d" * 200 for index in range(50)
        ],
        stale_branches=[
            Branch(name="branch-" + "e" * 200 + str(index), days_old=index + 1)
            for index in range(50)
        ],
        events=[
            Event(
                date="2026-01-01",
                kind="other",
                text="event " + "f" * 200,
                conf="e",
                ref="abc1234",
            )
            for _ in range(500)
        ],
        last_commit_date="2026-01-01",
    )

    out = render_terminal(report, "demo", today=date(2026, 1, 2))
    lines = out.splitlines()

    assert out.isascii()
    assert len([line for line in lines if line.startswith("  2026-01-01")]) == 15
    assert out.count("+40 more") == 2
    assert out.count("+45 more") == 2
    assert "..." in out


def test_a_report_without_events_or_last_commit_does_not_crash():
    out = render_terminal(Report(), "demo")

    assert "last commit unknown" in out
    assert "Nothing pending" in out
    assert "TIMELINE" not in out


def test_terminal_renders_hotspots_and_env_blockers():
    report = Report(
        hotspots=[Hotspot(a="src/a.py", b="src/b.py", count=4)],
        env_issues=[EnvIssue(kind="missing_key", detail="API_KEY is missing or empty in .env")],
    )

    out = render_terminal(report, "demo")

    assert "Hotspots (1)" in out
    assert "src/a.py + src/b.py" in out
    assert "Env blockers (1)" in out
    assert "API_KEY" in out
    assert "Nothing pending" not in out

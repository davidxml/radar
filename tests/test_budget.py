"""Tests for the token budget ladder and trimming."""

from __future__ import annotations

import pytest

from radar.budget import (
    FULL,
    HARD_MAX,
    LADDER,
    TARGET,
    est_tokens,
    fit,
    trimmed,
)
from radar.export import render_md, render_xml
from radar.models import Branch, Event, FileChange, Report, Todo

RENDERERS = [render_xml, render_md]
RENDER_IDS = ["xml", "md"]


def _long_path(index: int) -> str:
    return (f"dir{index}/" + "x" * 120)[:120]


def _huge_report() -> Report:
    events = [
        Event(
            date="2026-01-01",
            kind=("revert", "swap", "deletion", "other")[index % 4],
            text=f"event {index} " + "e" * 150,
            conf="e" if index % 2 else "i",
            ref=f"{index:07x}"[:7],
        )
        for index in range(1000)
    ]
    todos = [
        Todo(
            path=_long_path(index),
            line=index + 1,
            text="# TODO: " + "t" * 200,
            ref="abc1234",
        )
        for index in range(500)
    ]
    uncommitted = [
        FileChange(path=_long_path(index), status="M", lines_changed=index)
        for index in range(300)
    ]
    branches = [
        Branch(name=f"branch-{index}-" + "b" * 100, days_old=index + 1)
        for index in range(40)
    ]
    failing_tests = [
        f"tests/test_{index}.py::test_case_" + "f" * 150
        for index in range(30)
    ]
    return Report(
        uncommitted=uncommitted,
        todos=todos,
        failing_tests=failing_tests,
        stale_branches=branches,
        events=events,
    )


@pytest.fixture
def huge_report() -> Report:
    return _huge_report()


@pytest.mark.parametrize("render", RENDERERS, ids=RENDER_IDS)
def test_fit_caps_a_huge_report_at_the_hard_max(huge_report, render):
    text, _limits = fit(huge_report, render)

    assert est_tokens(text) <= HARD_MAX


@pytest.mark.parametrize("render", RENDERERS, ids=RENDER_IDS)
def test_an_oversized_budget_is_clamped_to_the_hard_max(huge_report, render):
    text, _limits = fit(huge_report, render, budget=99999)

    assert est_tokens(text) <= HARD_MAX


@pytest.mark.parametrize("render", RENDERERS, ids=RENDER_IDS)
def test_every_ladder_rung_is_no_larger_than_the_previous(huge_report, render):
    sizes = [est_tokens(render(huge_report, limits)) for limits in LADDER]

    assert all(later <= earlier for earlier, later in zip(sizes, sizes[1:])), sizes


def test_a_small_report_is_returned_untrimmed():
    report = Report(
        uncommitted=[FileChange(path="app.py", status="M")],
        todos=[Todo(path="app.py", line=1, text="# TODO: one")],
        failing_tests=["tests/test_app.py::test_one"],
        stale_branches=[Branch(name="old-work", days_old=40)],
        events=[Event(date="2026-01-01", kind="stop", text="stopped", conf="e")],
    )

    for render in RENDERERS:
        text, limits = fit(report, render)

        assert limits == LADDER[0]
        assert trimmed(report, limits) == []
        assert est_tokens(text) < TARGET
        assert "# TODO: one" in text


def test_full_limits_do_not_trim_a_huge_report(huge_report):
    text = render_xml(huge_report, FULL)

    assert est_tokens(text) > HARD_MAX

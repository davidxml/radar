"""Tests for the terminal radar CLI output."""

from __future__ import annotations

import pytest

from radar import cli
from radar.cli import STALE_DAYS, build_report, main
from radar.models import Event, FileChange, Report, Todo
from radar.render_ascii import render_terminal


def test_main_prints_resume_here(repo, capsys):
    repo.commit("add a todo", files={"app.py": "# TODO: finish the parser\n"})
    repo.write("dirty.py", "x = 1\n")

    code = main([str(repo.path), "--no-copy"])
    out = capsys.readouterr().out

    assert code == 0
    assert "RESUME HERE" in out
    assert "Uncommitted (1)" in out
    assert "?  dirty.py" in out
    assert "TODO / FIXME (1)" in out
    assert "app.py:1  # TODO: finish the parser" in out


def test_version_prints_package_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "radar 0.1.0"


def test_build_report_keeps_only_stale_branches(repo):
    repo.git("checkout", "-q", "-b", "wip/old")
    repo.commit(
        "old work",
        files={"old.py": "x = 1\n"},
        date="2020-01-01T00:00:00+0000",
    )
    repo.git("checkout", "-q", "main")

    report = build_report(repo.path)

    assert [branch.name for branch in report.stale_branches] == ["wip/old"]
    assert report.stale_branches[0].days_old > STALE_DAYS
    assert report.last_commit_date is not None

    out = render_terminal(report, "repo")
    assert out.count("Stale branches") == 1
    assert "wip/old" in out


def test_main_reports_non_repository(tmp_path, capsys):
    code = main([str(tmp_path)])
    captured = capsys.readouterr()

    assert code == 1
    assert captured.out == ""
    assert "not a git repository" in captured.err


def test_main_rejects_negative_commit_count(repo):
    try:
        main([str(repo.path), "--commits", "-1"])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - argparse always exits
        raise AssertionError("expected argparse to exit")


def test_build_report_collects_decisions(repo):
    original = repo.commit("add feature", files={"feature.py": "x = 1\n"})
    repo.git("revert", "--no-edit", original)

    report = build_report(repo.path)

    kinds = [event.kind for event in report.events]
    assert "revert" in kinds
    assert "stop" in kinds


def test_timeline_section_renders_one_line_per_event(repo, capsys):
    original = repo.commit("add feature", files={"feature.py": "x = 1\n"})
    repo.git("revert", "--no-edit", original)
    revert_sha = repo.git("rev-parse", "HEAD").strip()[:7]

    assert main([str(repo.path), "--no-copy"]) == 0
    out = capsys.readouterr().out

    assert "TIMELINE" in out
    assert "revert" in out
    assert "reverted: add feature" in out
    assert revert_sha in out


def test_timeline_shows_at_most_fifteen_and_keeps_heaviest():
    events = [
        Event(
            date=f"2026-01-{day:02d}",
            kind="other",
            text=f"change {day}",
            conf="e",
            ref="abc1234",
        )
        for day in range(1, 21)
    ]
    events.append(
        Event(date="2026-02-01", kind="stop", text="stopped here", conf="e")
    )

    out = render_terminal(Report(events=events), "repo")
    shown = [
        line
        for line in out.splitlines()
        if line.startswith("  2026-") and " [e]" in line
    ]

    assert len(shown) == 15
    assert "change 20" in out
    assert "change 1 [e]" not in out
    assert "stopped here" in shown[-1]


def test_full_prints_a_size_warning(repo, capsys):
    repo.commit("work", files={"app.py": "x = 1\n"})

    code = main([str(repo.path), "--full", "--no-copy"])
    out = capsys.readouterr().out

    assert code == 0
    assert "warning:" in out
    assert "--full" in out
    assert "tokens" in out


def test_clipboard_failure_falls_back_to_printing(repo, capsys, monkeypatch):
    def unavailable(text):
        raise RuntimeError("no clipboard backend")

    monkeypatch.setattr(cli.pyperclip, "copy", unavailable)

    code = main([str(repo.path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "clipboard unavailable, printing prompt:" in out
    assert "<project_handoff>" in out


def test_successful_copy_prints_the_token_summary(repo, capsys, monkeypatch):
    copied = []
    monkeypatch.setattr(cli.pyperclip, "copy", copied.append)

    code = main([str(repo.path)])
    out = capsys.readouterr().out

    assert code == 0
    assert copied
    assert "Copied: ~" in out
    assert "(cap 1,400)" in out


def test_trimmed_items_appear_in_the_summary(repo, capsys, monkeypatch):
    huge = Report(
        uncommitted=[
            FileChange(path=f"src/file{i}.py", status="M")
            for i in range(100)
        ],
        todos=[
            Todo(
                path=f"src/file{i}.py",
                line=i + 1,
                text="# TODO: " + "x" * 200,
            )
            for i in range(100)
        ],
    )
    monkeypatch.setattr(cli, "build_report", lambda cwd, n: huge)
    monkeypatch.setattr(cli.pyperclip, "copy", lambda text: None)

    code = main([str(repo.path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "| trimmed:" in out
    assert "TODOs" in out


def test_budget_above_the_hard_max_is_reported_as_clamped(repo, capsys, monkeypatch):
    monkeypatch.setattr(cli.pyperclip, "copy", lambda text: None)

    code = main([str(repo.path), "--budget", "99999"])
    out = capsys.readouterr().out

    assert code == 0
    assert "(cap 1,450)" in out

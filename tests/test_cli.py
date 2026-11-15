"""Tests for the Resume Here CLI output."""

from __future__ import annotations

from radar import cli
from radar.cli import (
    MAX_DECISIONS,
    STALE_DAYS,
    build_report,
    main,
    render_resume,
)
from radar.models import Event, FileChange, Report, Todo


def test_main_prints_resume_here(repo, capsys):
    repo.commit("add a todo", files={"app.py": "# TODO: finish the parser\n"})
    repo.write("dirty.py", "x = 1\n")

    code = main([str(repo.path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "Resume Here" in out
    assert "Uncommitted (1 file)" in out
    assert "?  dirty.py" in out
    assert "TODO / FIXME (1)" in out
    assert "app.py:1  # TODO: finish the parser" in out


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
    assert render_resume(report).count("Stale branches") == 1


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


def test_decisions_section_renders_one_line_per_event(repo, capsys):
    original = repo.commit("add feature", files={"feature.py": "x = 1\n"})
    repo.git("revert", "--no-edit", original)
    revert_sha = repo.git("rev-parse", "HEAD").strip()[:7]

    assert main([str(repo.path)]) == 0
    out = capsys.readouterr().out

    assert "Decisions" in out
    assert f"| revert: reverted: add feature [e] | {revert_sha}" in out


def test_decisions_show_at_most_fifteen_and_keep_heaviest():
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

    out = render_resume(Report(events=events))
    shown = [line for line in out.splitlines() if " | " in line]

    assert len(shown) == MAX_DECISIONS
    assert "change 19" not in out
    assert shown[-1].endswith("| stop: stopped here [e] | -")


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

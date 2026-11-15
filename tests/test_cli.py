"""Tests for the Resume Here CLI output."""

from __future__ import annotations

from radar.cli import STALE_DAYS, build_report, main, render_resume


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

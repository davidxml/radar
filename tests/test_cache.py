"""Tests for the .git/radar-cache.json report cache."""

from __future__ import annotations

import json
import os

import pytest

from radar import cache, cli


@pytest.fixture
def build_calls(monkeypatch):
    """Count real build_report calls while preserving its behaviour."""
    calls = []
    original = cli.build_report

    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(cli, "build_report", counted)
    return calls


def _run(repo, *args):
    return cli.main([str(repo.path), *args, "--no-copy"])


def test_second_run_hits_the_cache(repo, build_calls, capsys):
    assert _run(repo) == 0
    first = capsys.readouterr().out
    assert len(build_calls) == 1
    assert "(cached)" not in first

    assert _run(repo) == 0
    second = capsys.readouterr().out

    assert len(build_calls) == 1
    assert "(cached)" in second


def test_cache_file_lives_in_the_git_directory(repo):
    assert _run(repo) == 0

    assert (repo.path / ".git" / "radar-cache.json").is_file()


def test_a_new_commit_invalidates_the_cache(repo, build_calls):
    assert _run(repo) == 0

    repo.commit("next change", files={"next.py": "x = 1\n"})
    assert _run(repo) == 0

    assert len(build_calls) == 2


def test_reediting_an_already_modified_file_invalidates(repo, build_calls):
    path = repo.path / "app.py"
    repo.write("app.py", "x = 1\n")
    assert _run(repo) == 0

    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000))
    assert _run(repo) == 0

    assert len(build_calls) == 2


def test_a_new_branch_without_a_commit_invalidates(repo, build_calls):
    assert _run(repo) == 0

    repo.git("branch", "feature/no-commit")
    assert _run(repo) == 0

    assert len(build_calls) == 2


def test_touching_lastfailed_invalidates(repo, build_calls):
    artifact = repo.write(
        ".pytest_cache/v/cache/lastfailed",
        json.dumps({"tests/test_x.py::test_y": True}),
    )
    assert _run(repo) == 0

    stat = os.stat(artifact)
    os.utime(artifact, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000))
    assert _run(repo) == 0

    assert len(build_calls) == 2


def test_a_corrupt_cache_is_ignored_and_rebuilt(repo, build_calls, capsys):
    assert _run(repo) == 0

    cache_path = repo.path / ".git" / "radar-cache.json"
    cache_path.write_text("{not valid json", encoding="utf-8")

    assert _run(repo) == 0
    out = capsys.readouterr().out

    assert len(build_calls) == 2
    assert "RESUME HERE" in out
    assert json.loads(cache_path.read_text(encoding="utf-8"))["key"]


def test_a_read_only_git_directory_does_not_crash(repo, capsys):
    repo.write("app.py", "x = 1\n")
    git_dir = repo.path / ".git"
    original_mode = git_dir.stat().st_mode
    try:
        os.chmod(git_dir, 0o500)
        code = _run(repo)
    finally:
        os.chmod(git_dir, original_mode)

    assert code == 0
    assert "RESUME HERE" in capsys.readouterr().out


def test_no_cache_always_rebuilds(repo, build_calls):
    assert _run(repo, "--no-cache") == 0
    assert _run(repo, "--no-cache") == 0

    assert len(build_calls) == 2
    assert not (repo.path / ".git" / "radar-cache.json").exists()


def test_old_cache_reports_without_new_fields_still_load():
    report = cache._from_dict(
        {
            "uncommitted": [],
            "todos": [],
            "failing_tests": [],
            "stale_branches": [],
            "events": [],
            "last_commit_date": None,
        }
    )

    assert report.hotspots == []
    assert report.env_issues == []


@pytest.mark.parametrize(
    "name,content",
    [
        (".env", "A=1\n"),
        (".env.example", "A=\n"),
        ("docker-compose.yml", "ports: []\n"),
    ],
)
def test_env_file_mtimes_invalidate_the_cache(repo, build_calls, name, content):
    repo.write(".gitignore", ".env\n.env.example\ndocker-compose.yml\n")
    repo.commit("ignore env files")
    path = repo.write(name, content)
    assert _run(repo) == 0

    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000))
    assert _run(repo) == 0

    assert len(build_calls) == 2

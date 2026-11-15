"""Tests for the git layer: status, branches, log, and diff parsing."""

from __future__ import annotations

import pytest

from radar.git import (
    GitError,
    added_lines,
    branches,
    is_ignored,
    is_repo,
    log,
    run,
    status_porcelain,
)


def test_run_and_is_repo(repo, tmp_path):
    assert is_repo(repo.path) is True
    assert is_repo(tmp_path) is False
    assert run(["rev-parse", "--is-inside-work-tree"], repo.path).strip() == "true"


def test_run_raises_on_failure_and_can_opt_out(repo):
    with pytest.raises(GitError):
        run(["rev-parse", "--verify", "does-not-exist"], repo.path)
    assert run(["rev-parse", "--verify", "does-not-exist"], repo.path, check=False) == ""


def test_status_porcelain_reports_modified_added_and_untracked(repo):
    repo.write("app.py", "def main():\n    print('changed')\n")
    repo.write("staged.py", "x = 1\n")
    repo.git("add", "staged.py")
    repo.write("new.txt", "hello\n")

    statuses = {change.path: change.status for change in status_porcelain(repo.path)}

    assert statuses == {"app.py": "M", "staged.py": "A", "new.txt": "?"}


def test_status_porcelain_skips_ignored_paths(repo):
    repo.write("package-lock.json", "{}\n")
    repo.write("node_modules/pkg/index.js", "module.exports = 1\n")

    assert status_porcelain(repo.path) == []


def test_status_porcelain_handles_renames(repo):
    repo.write("old_name.py", "x = 1\n")
    repo.commit("add file")
    repo.git("mv", "old_name.py", "new_name.py")

    changes = status_porcelain(repo.path)

    assert [(c.path, c.status) for c in changes] == [("new_name.py", "R")]


def test_log_returns_short_sha_iso_date_and_subject(repo):
    repo.commit("second commit", files={"b.py": "x = 1\n"})

    rows = log(repo.path, 10)

    assert [subject for _sha, _date, subject in rows] == [
        "second commit",
        "initial commit",
    ]
    sha, date, _subject = rows[0]
    assert len(sha) == 7
    assert date.startswith("20")
    assert log(repo.path, 0) == []


def test_branches_reports_age_in_days(repo):
    repo.git("checkout", "-q", "-b", "old-feature")
    repo.commit(
        "old work",
        files={"old.py": "x = 1\n"},
        date="2020-01-01T00:00:00+0000",
    )
    repo.git("checkout", "-q", "main")

    by_name = {branch.name: branch.days_old for branch in branches(repo.path)}

    assert by_name["main"] == 0
    assert by_name["old-feature"] > 365
    # Oldest first.
    assert branches(repo.path)[0].name == "old-feature"


def test_added_lines_use_new_file_line_numbers(repo):
    repo.commit(
        "base",
        files={"app.py": "".join(f"line {i}\n" for i in range(1, 11))},
    )
    updated = (
        "".join(f"line {i}\n" for i in range(1, 6))
        + "# TODO: added here\n"
        + "".join(f"line {i}\n" for i in range(6, 11))
    )
    sha = repo.commit("insert", files={"app.py": updated})

    rows = list(added_lines(repo.path, 1))

    assert rows == [(sha[:7], "app.py", 6, "# TODO: added here")]


def test_added_lines_never_yield_removed_lines(repo):
    repo.commit("base", files={"app.py": "# TODO: remove me\nx = 1\n"})
    repo.commit("remove", files={"app.py": "x = 1\n"})

    assert list(added_lines(repo.path, 1)) == []


def test_added_lines_handles_multiple_hunks(repo):
    repo.commit(
        "base",
        files={"app.py": "".join(f"line {i}\n" for i in range(1, 21))},
    )
    updated = (
        "line 1\nnew a\nnew b\n"
        + "".join(f"line {i}\n" for i in range(2, 19))
        + "new c\nline 20\n"
    )
    repo.commit("edits", files={"app.py": updated})

    rows = list(added_lines(repo.path, 1))

    assert [(line, text) for _sha, _path, line, text in rows] == [
        (2, "new a"),
        (3, "new b"),
        (21, "new c"),
    ]


def test_added_lines_skips_deleted_files(repo):
    repo.commit("base", files={"gone.py": "# TODO: gone\n"})
    repo.git("rm", "-q", "gone.py")
    repo.git("commit", "-q", "-m", "delete file")

    assert list(added_lines(repo.path, 1)) == []


@pytest.mark.parametrize(
    "path, ignored",
    [
        ("node_modules/pkg/index.js", True),
        ("vendor/lib.py", True),
        ("dist/bundle.js", True),
        ("Cargo.lock", True),
        ("src/vendor.py", False),
        ("src/app.py", False),
    ],
)
def test_is_ignored(path, ignored):
    assert is_ignored(path) is ignored

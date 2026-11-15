"""Tests for the large-deletion heuristic."""

from __future__ import annotations

from radar.signals.deletions import find_large_deletions


def _lines(count: int, prefix: str = "line") -> str:
    return "".join(f"{prefix} {i}\n" for i in range(count))


def test_flags_a_commit_that_deletes_250_lines(repo):
    repo.commit("add big file", files={"big.py": _lines(250)})
    sha = repo.commit("delete big file", files={"big.py": "small\n"})

    events = find_large_deletions(repo.path)

    assert len(events) == 1
    event = events[0]
    assert event.kind == "deletion"
    assert event.conf == "e"
    assert event.text == "-250 lines in 1 files (top: big.py)"
    assert event.ref == sha[:7]


def test_ignores_small_deletions(repo):
    repo.commit("add file", files={"small.py": _lines(10)})
    repo.commit("shrink", files={"small.py": _lines(4)})

    assert find_large_deletions(repo.path) == []


def test_does_not_flag_many_added_lines(repo):
    repo.commit("add file", files={"small.py": _lines(60)})
    repo.commit(
        "grow",
        files={"small.py": _lines(10) + _lines(200, prefix="new")},
    )

    # 50 deleted out of 250 changed lines is below the 30% ratio.
    assert find_large_deletions(repo.path) == []


def test_flags_a_ratio_heavy_deletion_over_fifty_lines(repo):
    repo.commit("add file", files={"a.py": _lines(60)})
    repo.commit(
        "trim and add",
        files={"a.py": _lines(10), "b.py": _lines(20, prefix="new")},
    )

    events = find_large_deletions(repo.path)

    assert len(events) == 1
    assert events[0].text == "-50 lines in 1 files (top: a.py)"


def test_ignores_deletions_in_ignored_paths(repo):
    repo.commit(
        "vendored file", files={"node_modules/big.js": _lines(250)}
    )
    repo.commit("remove vendored", files={"node_modules/big.js": "x\n"})

    assert find_large_deletions(repo.path) == []


def test_top_path_is_the_file_with_most_deletions(repo):
    repo.commit(
        "add files",
        files={"a.py": _lines(120), "b.py": _lines(150)},
    )
    repo.commit(
        "delete both",
        files={"a.py": "x\n", "b.py": "y\n"},
    )

    events = find_large_deletions(repo.path)

    assert len(events) == 1
    assert events[0].text == "-270 lines in 2 files (top: b.py)"

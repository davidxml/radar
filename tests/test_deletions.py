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
    assert event.text == "-249 net lines in 1 file (top: big.py)"
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
    repo.commit("add file", files={"a.py": _lines(100)})
    repo.commit(
        "trim and add",
        files={"a.py": _lines(20), "b.py": _lines(20, prefix="new")},
    )

    events = find_large_deletions(repo.path)

    assert len(events) == 1
    assert events[0].text == "-60 net lines in 1 file (top: a.py)"


def test_ratio_uses_net_deletions_not_total_deleted(repo):
    repo.commit("add file", files={"a.py": _lines(167)})
    repo.commit(
        "trim and add",
        files={"a.py": "", "b.py": _lines(117, prefix="new")},
    )

    # 50 net deletions out of 284 changed lines is below the 30% ratio.
    assert find_large_deletions(repo.path) == []


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
    assert events[0].text == "-268 net lines in 2 files (top: b.py)"


def test_move_with_similar_added_and_deleted_lines_is_not_flagged(repo):
    repo.commit("add old file", files={"old.py": _lines(300)})
    (repo.path / "old.py").unlink()
    repo.commit("move old file", files={"new.py": _lines(300)})

    assert find_large_deletions(repo.path) == []


def test_flags_a_real_300_line_deletion(repo):
    repo.commit("add big file", files={"big.py": _lines(300)})
    (repo.path / "big.py").unlink()
    sha = repo.commit("delete big file")

    events = find_large_deletions(repo.path)

    assert len(events) == 1
    assert events[0].text == "-300 net lines in 1 file (top: big.py)"
    assert events[0].ref == sha[:7]


def test_groups_same_day_deletions_and_keeps_other_days_separate(repo):
    repo.commit(
        "add big files",
        files={
            "a.py": _lines(1250),
            "b.py": _lines(1230),
            "c.py": _lines(1210),
            "d.py": _lines(300),
        },
    )

    (repo.path / "a.py").unlink()
    sha_a = repo.commit("delete a", date="2026-03-01T10:00:00+0000")
    (repo.path / "b.py").unlink()
    repo.commit("delete b", date="2026-03-01T11:00:00+0000")
    (repo.path / "c.py").unlink()
    repo.commit("delete c", date="2026-03-01T12:00:00+0000")
    (repo.path / "d.py").unlink()
    sha_d = repo.commit("delete d", date="2026-03-05T10:00:00+0000")

    events = find_large_deletions(repo.path)

    assert len(events) == 2
    by_date = {event.date: event for event in events}

    grouped = by_date["2026-03-01"]
    assert grouped.text == "-3,690 net lines across 3 commits (top: a.py)"
    assert grouped.ref == sha_a[:7]

    single = by_date["2026-03-05"]
    assert single.text == "-300 net lines in 1 file (top: d.py)"
    assert single.ref == sha_d[:7]

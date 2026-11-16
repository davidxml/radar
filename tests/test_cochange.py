"""Tests for co-change hotspot detection."""

from __future__ import annotations

from radar.signals.cochange import find_hotspots


def _touch(repo, index: int, names):
    files = {name: f"value = {index}\n" for name in names}
    repo.commit(f"change {index}", files=files)


def test_counts_repeated_file_pairs(repo):
    for index in range(4):
        _touch(repo, index, ["a.py", "b.py", "c.py"])

    hotspots = find_hotspots(repo.path, min_count=4)

    counts = {(item.a, item.b): item.count for item in hotspots}
    assert counts[("a.py", "b.py")] == 4
    assert counts[("a.py", "c.py")] == 4
    assert counts[("b.py", "c.py")] == 4
    assert all(item.a < item.b for item in hotspots)


def test_returns_only_the_top_five_pairs(repo):
    for index in range(4):
        _touch(repo, index, ["a.py", "b.py", "c.py", "d.py"])

    hotspots = find_hotspots(repo.path, min_count=4)

    assert len(hotspots) == 5
    assert [(item.a, item.b) for item in hotspots] == sorted(
        (item.a, item.b) for item in hotspots
    )


def test_commits_with_more_than_thirty_files_are_skipped(repo):
    for index in range(4):
        names = [f"src/file{number}.py" for number in range(31)]
        _touch(repo, index, names)

    assert find_hotspots(repo.path, min_count=2) == []

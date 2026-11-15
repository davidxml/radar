"""Tests for revert detection."""

from __future__ import annotations

from radar.signals.reverts import find_reverts


def test_finds_a_real_revert_commit(repo):
    repo.commit("add feature", files={"feature.py": "x = 1\n"})
    repo.git("revert", "--no-edit", "HEAD")

    events = find_reverts(repo.path)

    assert len(events) == 1
    event = events[0]
    assert event.kind == "revert"
    assert event.conf == "e"
    assert event.text == "reverted: add feature"
    assert event.ref == repo.git("rev-parse", "HEAD").strip()[:7]
    assert event.date == repo.git(
        "show", "-s", "--format=%aI", "HEAD"
    ).strip()[:10]


def test_body_only_revert_resolves_the_original_subject(repo):
    original = repo.commit("original change", files={"a.py": "1\n"})
    repo.commit("undo it", files={"a.py": "2\n"})
    repo.git(
        "commit",
        "--amend",
        "-q",
        "-m",
        "undo it",
        "-m",
        f"This reverts commit {original}.",
    )

    events = find_reverts(repo.path)

    assert [e.text for e in events] == ["reverted: original change"]


def test_ignores_normal_commits(repo):
    repo.commit("normal work", files={"a.py": "1\n"})

    assert find_reverts(repo.path) == []


def test_truncates_the_original_subject_to_sixty_chars(repo):
    subject = "very long feature name " + "x" * 100
    repo.commit(subject, files={"a.py": "1\n"})
    repo.git("revert", "--no-edit", "HEAD")

    events = find_reverts(repo.path)

    assert len(events) == 1
    assert events[0].text == "reverted: " + subject[:60]
    assert len(events[0].text) == len("reverted: ") + 60

"""Tests for the added-lines TODO scanner."""

from __future__ import annotations

import pytest

from radar.signals.todos import MAX_TEXT, find_todos


def test_finds_todo_added_in_recent_commit(repo):
    sha = repo.commit(
        "add a todo",
        files={"app.py": "print('hello')\n# TODO: handle empty input\n"},
    )

    todos = find_todos(repo.path)

    assert len(todos) == 1
    todo = todos[0]
    assert todo.path == "app.py"
    assert todo.line == 2
    assert todo.text == "# TODO: handle empty input"
    assert todo.ref == sha[:7]


def test_removed_todo_is_not_reported(repo):
    repo.commit(
        "add a todo",
        files={"app.py": "# TODO: delete me\nprint('hello')\n"},
    )
    repo.commit("remove the todo", files={"app.py": "print('hello')\n"})

    # The removal commit adds no marker, so scanning only it finds nothing.
    assert find_todos(repo.path, n_commits=1) == []

    # The original addition is still visible with a wider history window.
    all_todos = find_todos(repo.path, n_commits=2)
    assert [t.text for t in all_todos] == ["# TODO: delete me"]


def test_line_numbers_follow_the_new_file_version(repo):
    body = "".join(f"line {i}\n" for i in range(1, 11))
    repo.commit("base file", files={"app.py": body})

    updated = (
        "".join(f"line {i}\n" for i in range(1, 6))
        + "# FIXME: inserted here\n"
        + "".join(f"line {i}\n" for i in range(6, 11))
    )
    repo.commit("insert marker", files={"app.py": updated})

    todos = [t for t in find_todos(repo.path, n_commits=1) if t.path == "app.py"]

    assert len(todos) == 1
    assert todos[0].line == 6
    assert todos[0].text == "# FIXME: inserted here"


def test_reports_one_todo_per_hunk_with_new_line_numbers(repo):
    repo.commit(
        "base",
        files={"app.py": "".join(f"line {i}\n" for i in range(1, 21))},
    )

    updated = (
        "line 1\n"
        + "# TODO: first hunk\n"
        + "".join(f"line {i}\n" for i in range(2, 19))
        + "# HACK: second hunk\n"
        + "line 20\n"
    )
    repo.commit("two markers", files={"app.py": updated})

    todos = sorted(
        (t for t in find_todos(repo.path, n_commits=1) if t.path == "app.py"),
        key=lambda t: t.line,
    )

    assert [(t.line, t.text) for t in todos] == [
        (2, "# TODO: first hunk"),
        (20, "# HACK: second hunk"),
    ]


@pytest.mark.parametrize("marker", ["TODO", "FIXME", "HACK", "XXX"])
def test_matches_every_marker_kind(repo, marker):
    repo.commit(
        "add marker",
        files={"notes.txt": f"# {marker}: something to revisit\n"},
    )

    todos = find_todos(repo.path, n_commits=1)

    assert len(todos) == 1
    assert todos[0].text == f"# {marker}: something to revisit"


def test_ignores_markers_that_are_part_of_a_longer_word(repo):
    repo.commit(
        "prose",
        files={"notes.txt": "TODOS are plural\nXXXX marks the spot\n"},
    )

    assert find_todos(repo.path, n_commits=1) == []


def test_truncates_text_to_eighty_characters(repo):
    long_marker = "# TODO: " + "x" * 200
    repo.commit("long marker", files={"app.py": long_marker + "\n"})

    todos = find_todos(repo.path, n_commits=1)

    assert len(todos) == 1
    assert len(todos[0].text) == MAX_TEXT
    assert todos[0].text.startswith("# TODO: xxx")


@pytest.mark.parametrize(
    "path",
    [
        "node_modules/pkg/index.js",
        "vendor/bundle.js",
        "dist/build.js",
        "package-lock.json",
        "yarn.lock",
        "assets/app.min.js",
    ],
)
def test_skips_ignored_paths(repo, path):
    repo.commit(
        "noise",
        files={path: "// TODO: generated, not actionable\n"},
    )

    assert find_todos(repo.path, n_commits=1) == []


def test_tracks_markers_from_multiple_commits_newest_first(repo):
    first = repo.commit("first", files={"a.py": "# TODO: one\n"})
    second = repo.commit("second", files={"b.py": "# TODO: two\n"})

    todos = find_todos(repo.path, n_commits=2)

    assert [(t.path, t.ref) for t in todos] == [
        ("b.py", second[:7]),
        ("a.py", first[:7]),
    ]

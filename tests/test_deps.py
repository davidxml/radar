"""Tests for dependency-change detection and manifest parsing."""

from __future__ import annotations

import json

from radar.signals.deps import find_dep_changes
from radar.signals.manifests import package_json, requirements


def _pkg(dependencies, dev=None, peer=None) -> str:
    data = {"dependencies": dependencies}
    if dev is not None:
        data["devDependencies"] = dev
    if peer is not None:
        data["peerDependencies"] = peer
    return json.dumps(data, indent=2) + "\n"


def test_detects_a_dependency_swap(repo):
    repo.commit(
        "old scheduler",
        files={"package.json": _pkg({"node-cron": "^3.0.0"})},
    )
    sha = repo.commit(
        "new scheduler",
        files={"package.json": _pkg({"bullmq": "^5.0.0"})},
    )

    events = find_dep_changes(repo.path)

    assert len(events) == 1
    event = events[0]
    assert event.kind == "swap"
    assert event.conf == "i"
    assert event.text == "-node-cron +bullmq"
    assert event.ref == sha[:7]


def test_detects_a_requirements_addition(repo):
    repo.commit(
        "base requirements",
        files={"requirements.txt": "requests==2.31.0\n"},
    )
    sha = repo.commit(
        "add flask",
        files={"requirements.txt": "requests==2.31.0\nFlask>=3.0\n"},
    )

    events = find_dep_changes(repo.path)

    assert len(events) == 1
    event = events[0]
    assert event.kind == "other"
    assert event.conf == "e"
    assert event.text == "+flask"
    assert event.ref == sha[:7]


def test_detects_a_requirements_removal(repo):
    repo.commit(
        "base",
        files={"requirements.txt": "requests\nsix\n"},
    )
    repo.commit("drop six", files={"requirements.txt": "requests\n"})

    events = find_dep_changes(repo.path)

    assert [(e.kind, e.text) for e in events] == [("other", "-six")]


def test_unions_dependencies_dev_and_peer(repo):
    repo.commit(
        "base",
        files={"package.json": _pkg({"a": "1"}, dev={"b": "1"})},
    )
    repo.commit(
        "move dev to peer",
        files={"package.json": _pkg({}, dev={"b": "1"}, peer={"a": "1"})},
    )

    # "a" moved sections, so the union of names did not change.
    assert find_dep_changes(repo.path) == []


def test_truncates_many_names_per_side(repo):
    old = {f"old{i}": "1" for i in range(4)}
    new = {f"new{i}": "1" for i in range(4)}
    repo.commit("old deps", files={"package.json": _pkg(old)})
    repo.commit("new deps", files={"package.json": _pkg(new)})

    events = find_dep_changes(repo.path)

    assert [e.text for e in events] == [
        "-old0 -old1 -old2 -1 more +new0 +new1 +new2 +1 more"
    ]


def test_skips_invalid_package_json_without_crashing(repo):
    repo.commit("valid", files={"package.json": _pkg({"a": "1"})})
    repo.commit("broken", files={"package.json": "{not json"})
    repo.commit("valid again", files={"package.json": _pkg({"b": "1"})})
    sha = repo.commit("still valid", files={"package.json": _pkg({"c": "1"})})

    events = find_dep_changes(repo.path)

    # Only the valid-to-valid transition produces an event.
    assert len(events) == 1
    assert events[0].text == "-b +c"
    assert events[0].ref == sha[:7]


def test_merges_same_day_other_events_and_keeps_swaps_separate(repo):
    repo.commit(
        "base manifests",
        files={
            "requirements.txt": "requests\n",
            "package.json": _pkg({}),
        },
    )
    sha_first = repo.commit(
        "add shared requirement",
        files={"requirements.txt": "requests\nshared\n"},
        date="2026-03-01T10:00:00+0000",
    )
    repo.commit(
        "add shared and express",
        files={"package.json": _pkg({"shared": "1", "express": "1"})},
        date="2026-03-01T11:00:00+0000",
    )
    sha_swap = repo.commit(
        "swap express for fastify",
        files={"package.json": _pkg({"shared": "1", "fastify": "1"})},
        date="2026-03-01T12:00:00+0000",
    )

    events = find_dep_changes(repo.path)

    assert len(events) == 2
    by_kind = {event.kind: event for event in events}

    merged = by_kind["other"]
    assert merged.text == "+express +shared"
    assert merged.conf == "e"
    assert merged.ref == sha_first[:7]

    swap = by_kind["swap"]
    assert swap.text == "-express +fastify"
    assert swap.conf == "i"
    assert swap.ref == sha_swap[:7]


def test_reads_nested_package_json(repo):
    repo.commit(
        "web deps",
        files={"apps/web/package.json": _pkg({"react": "^18"})},
    )
    repo.commit(
        "switch framework",
        files={"apps/web/package.json": _pkg({"vue": "^3"})},
    )

    events = find_dep_changes(repo.path)

    assert [(e.kind, e.text) for e in events] == [("swap", "-react +vue")]


def test_ignores_node_modules_manifests(repo):
    repo.commit(
        "vendored",
        files={"node_modules/pkg/package.json": _pkg({"a": "1"})},
    )
    repo.commit(
        "vendored update",
        files={"node_modules/pkg/package.json": _pkg({"b": "1"})},
    )

    assert find_dep_changes(repo.path) == []


def test_root_manifest_has_no_before_side(repo):
    repo.write("package.json", _pkg({"a": "1"}))
    repo.git("add", "-A")
    repo.git("commit", "--amend", "-q", "--no-edit")

    assert find_dep_changes(repo.path) == []


def test_package_json_parser_rejects_invalid_documents():
    assert package_json.parse("{") is None
    assert package_json.parse("[]") is None
    assert package_json.parse("not json") is None
    assert package_json.parse("{}") == set()


def test_requirements_parser_normalizes_names():
    text = """
    # a comment
    Requests==2.31.0
    flask[async]>=3.0 ; python_version >= "3.9"
    python_dateutil
    -r other.txt
    -e .
    --index-url https://example.invalid/simple
    pkg @ https://example.invalid/pkg.whl
    """
    assert requirements.parse(text) == {
        "requests",
        "flask",
        "python-dateutil",
        "pkg",
    }

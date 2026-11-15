"""Tests for reading existing test-failure artifacts."""

from __future__ import annotations

import json
import os
import time

import pytest

from radar.tests_artifacts import find_failing, fingerprint

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="suite">
    <testcase classname="tests.test_alpha" name="test_ok"/>
    <testcase classname="tests.test_alpha" name="test_failure">
      <failure message="boom">traceback</failure>
    </testcase>
    <testcase classname="tests.test_beta" name="test_error">
      <error message="kaboom"/>
    </testcase>
  </testsuite>
</testsuites>
"""

EXPECTED = ["tests.test_alpha::test_failure", "tests.test_beta::test_error"]


def test_lastfailed_parses_node_ids(repo):
    repo.write(
        ".pytest_cache/v/cache/lastfailed",
        json.dumps(
            {
                "tests/test_b.py::test_two": True,
                "tests/test_a.py::test_one": True,
            }
        ),
    )

    assert find_failing(repo.path) == [
        "tests/test_a.py::test_one",
        "tests/test_b.py::test_two",
    ]


@pytest.mark.parametrize(
    "relpath",
    [
        "junit.xml",
        "test-results.xml",
        "reports/junit.xml",
        "test-reports/junit.xml",
    ],
)
def test_junit_failure_and_error_cases(repo, relpath):
    repo.write(relpath, JUNIT)

    assert find_failing(repo.path) == EXPECTED


def test_malformed_xml_is_skipped(repo):
    repo.write("junit.xml", "<testsuite><testcase")
    repo.write("reports/junit.xml", JUNIT)

    assert find_failing(repo.path) == EXPECTED


def test_malformed_lastfailed_is_skipped(repo):
    repo.write(".pytest_cache/v/cache/lastfailed", "{not json")

    assert find_failing(repo.path) == []


def test_artifacts_older_than_thirty_days_are_ignored(repo):
    path = repo.write(
        ".pytest_cache/v/cache/lastfailed",
        json.dumps({"tests/test_old.py::test_old": True}),
    )
    old = time.time() - 31 * 24 * 60 * 60
    os.utime(path, (old, old))

    assert find_failing(repo.path) == []


def test_no_artifacts_returns_empty_list(repo):
    assert find_failing(repo.path) == []


def test_results_are_deduped_sorted_and_capped(repo):
    node_ids = {f"tests/test_{index:03d}.py::test_case": True for index in range(60)}
    repo.write(".pytest_cache/v/cache/lastfailed", json.dumps(node_ids))

    result = find_failing(repo.path)

    assert len(result) == 50
    assert result == sorted(result)
    assert result[0] == "tests/test_000.py::test_case"


def test_fingerprint_is_empty_without_artifacts(repo):
    assert fingerprint(repo.path) == ""


def test_fingerprint_tracks_mtime_and_size(repo):
    path = repo.write("junit.xml", "<testsuites/>")

    first = fingerprint(repo.path)
    assert first.startswith("junit.xml:")

    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    assert fingerprint(repo.path) != first

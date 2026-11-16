"""Tests for the offline environment checks."""

from __future__ import annotations

import socket

import pytest

from radar.signals.env import find_env_issues


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _details(issues):
    return " ".join(issue.detail for issue in issues)


def test_missing_and_empty_keys_are_reported_without_values(tmp_path):
    _write(tmp_path, ".env.example", "SECRET=placeholder\nMISSING=x\nEMPTY=x\n")
    _write(tmp_path, ".env", "SECRET=super-secret-value\nEMPTY=\n")

    issues = find_env_issues(tmp_path)

    details = _details(issues)
    assert all(issue.kind == "missing_key" for issue in issues)
    assert "MISSING" in details
    assert "EMPTY" in details
    assert "super-secret-value" not in details
    assert "SECRET" not in details


def test_missing_env_file_is_one_issue_not_one_per_key(tmp_path):
    _write(tmp_path, ".env.example", "ONE=1\nTWO=2\n")

    issues = find_env_issues(tmp_path)

    assert len(issues) == 1
    assert issues[0].kind == "missing_key"
    assert issues[0].detail == "no .env file"
    assert "ONE" not in issues[0].detail
    assert "TWO" not in issues[0].detail


def test_env_sample_is_used_when_example_is_absent(tmp_path):
    _write(tmp_path, ".env.sample", "SAMPLE_KEY=1\n")
    _write(tmp_path, ".env", "OTHER=1\n")

    issues = find_env_issues(tmp_path)

    assert any("SAMPLE_KEY" in issue.detail for issue in issues)


def test_python_version_pin_mismatch_is_runtime_issue(tmp_path):
    _write(tmp_path, ".python-version", "3.99.0\n")

    issues = find_env_issues(tmp_path)

    runtime = [issue for issue in issues if issue.kind == "runtime"]
    assert runtime
    assert "Python" in runtime[0].detail


def test_pyproject_requires_python_mismatch_is_runtime_issue(tmp_path):
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nrequires-python = "<3.0"\n',
    )

    issues = find_env_issues(tmp_path)

    runtime = [issue for issue in issues if issue.kind == "runtime"]
    assert runtime
    assert "requires-python" in runtime[0].detail


def test_issue_list_is_capped_at_eight(tmp_path):
    keys = "".join(f"KEY_{index}=\n" for index in range(12))
    _write(tmp_path, ".env.example", keys)
    _write(tmp_path, ".env", "")

    issues = find_env_issues(tmp_path)

    assert len(issues) == 8


@pytest.mark.enable_socket
def test_open_compose_port_is_not_reported(tmp_path):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        _write(tmp_path, "docker-compose.yml", f'ports:\n  - "{port}:80"\n')

        issues = find_env_issues(tmp_path)

    assert not [issue for issue in issues if issue.kind == "service_down"]


@pytest.mark.enable_socket
def test_closed_compose_port_is_reported(tmp_path):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
    _write(tmp_path, "docker-compose.yml", f'ports:\n  - "{port}:80"\n')

    issues = find_env_issues(tmp_path)

    down = [issue for issue in issues if issue.kind == "service_down"]
    assert down
    assert str(port) in down[0].detail


@pytest.mark.enable_socket
def test_local_database_url_is_probed_without_leaking_credentials(tmp_path):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
    _write(
        tmp_path,
        ".env",
        f"DATABASE_URL=postgres://user:super-secret@127.0.0.1:{port}/db\n",
    )

    issues = find_env_issues(tmp_path)

    down = [issue for issue in issues if issue.kind == "service_down"]
    assert down
    assert "DATABASE_URL" in down[0].detail
    assert "super-secret" not in _details(issues)
    assert "user:" not in _details(issues)

"""The CLI must work with no network access at all."""

from __future__ import annotations

import socket

import pytest

from radar import cli


@pytest.fixture
def no_sockets(monkeypatch):
    """Fail loudly if the code under test touches a socket."""

    def blocked(*args, **kwargs):
        raise AssertionError("network access is not allowed")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def test_no_copy_runs_offline(repo, no_sockets, capsys):
    repo.commit("add a todo", files={"app.py": "# TODO: offline\n"})

    code = cli.main([str(repo.path), "--no-copy"])
    out = capsys.readouterr().out

    assert code == 0
    assert "RESUME HERE" in out
    assert "Prompt: ~" in out


def test_md_runs_offline(repo, no_sockets, capsys, monkeypatch):
    calls = []
    original = cli.render_md

    def spy(report, limits):
        calls.append(limits)
        return original(report, limits)

    monkeypatch.setattr(cli, "render_md", spy)

    repo.commit("add a todo", files={"app.py": "# FIXME: offline md\n"})
    code = cli.main([str(repo.path), "--md", "--no-copy"])
    out = capsys.readouterr().out

    assert code == 0
    assert calls, "the Markdown renderer was not used"
    assert "RESUME HERE" in out

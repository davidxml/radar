"""Shared fixtures: disposable git repositories for the signals tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import pytest

# Tests run from a source checkout (CI installs with pip, local runs may not).
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class TempRepo:
    """A throwaway repository with a local identity and helper methods."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def git(
        self,
        *args: str,
        date: Optional[str] = None,
        check: bool = True,
    ) -> str:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        if date:
            env["GIT_AUTHOR_DATE"] = date
            env["GIT_COMMITTER_DATE"] = date

        proc = subprocess.run(
            ["git", *args],
            cwd=self.path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if check and proc.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)} failed ({proc.returncode}): "
                f"{proc.stderr.strip()}"
            )
        return proc.stdout

    def write(self, relpath: str, content: str) -> Path:
        target = self.path / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        return target

    def commit(
        self,
        message: str,
        files: Optional[Dict[str, str]] = None,
        date: Optional[str] = None,
    ) -> str:
        for relpath, content in (files or {}).items():
            self.write(relpath, content)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, date=date)
        return self.git("rev-parse", "HEAD").strip()


@pytest.fixture
def repo(tmp_path: Path) -> TempRepo:
    """A temp repo on ``main`` with one initial commit."""
    path = tmp_path / "repo"
    path.mkdir()
    temp = TempRepo(path)

    try:
        temp.git("init", "-q", "-b", "main")
    except AssertionError:
        # Git < 2.28 has no ``init -b``; create main explicitly.
        temp.git("init", "-q")
        temp.git("checkout", "-q", "-b", "main")
    temp.git("config", "user.name", "Radar Test")
    temp.git("config", "user.email", "radar@example.com")
    temp.git("config", "commit.gpgsign", "false")
    temp.git("config", "core.autocrlf", "false")
    temp.git("config", "core.safecrlf", "false")

    temp.commit(
        "initial commit",
        files={
            "README.md": "# demo\n",
            "app.py": "def main():\n    print('hello')\n",
        },
    )
    return temp

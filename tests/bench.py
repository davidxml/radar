"""Manual performance check for radar. Not collected by pytest.

Build a throwaway repository with 1,500 commits, then time a cold run and a
cached run. Nothing is written inside the radar checkout:

    python tests/bench.py

Set ``RADAR_BENCH_COMMITS`` to a smaller number for a quick smoke test.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
COMMITS = int(os.environ.get("RADAR_BENCH_COMMITS", "1500"))


def _env() -> dict:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + existing if existing else "")
    return env


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def write_text(path: Path, text: str) -> None:
    # Path.write_text gained its newline argument in Python 3.10.
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def init_repo(repo: Path) -> None:
    try:
        git(repo, "init", "-q", "-b", "main")
    except RuntimeError:
        git(repo, "init", "-q")
        git(repo, "checkout", "-q", "-b", "main")
    for key, value in (
        ("user.name", "Radar Bench"),
        ("user.email", "bench@example.com"),
        ("commit.gpgsign", "false"),
        ("core.autocrlf", "false"),
        ("core.safecrlf", "false"),
    ):
        git(repo, "config", key, value)


def build_repo(repo: Path) -> None:
    init_repo(repo)
    app = repo / "app.py"
    package = repo / "package.json"
    notes = repo / "notes.md"

    write_text(app, "x = 0\n")
    write_text(
        package,
        json.dumps({"dependencies": {"node-cron": "^3.0.0"}}) + "\n",
    )
    write_text(notes, "")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial commit")

    for number in range(1, COMMITS + 1):
        body = f"x = {number}\n"
        if number % 25 == 0:
            body += "# TODO: follow up on the scheduler\n"
        write_text(app, body)

        if number % 50 == 0:
            deps = (
                {"bullmq": "^5.0.0"}
                if (number // 50) % 2
                else {"node-cron": "^3.0.0"}
            )
            write_text(package, json.dumps({"dependencies": deps}) + "\n")

        if number % 25 == 0:
            with notes.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"- TODO: revisit item {number}\n")

        git(repo, "commit", "-q", "-a", "-m", f"change {number}")

        if number % 100 == 0:
            git(repo, "revert", "--no-edit", "HEAD")


def run_radar(repo: Path, args: Sequence[str]) -> float:
    start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "radar", "--no-copy", *args],
        cwd=repo,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    elapsed = time.perf_counter() - start
    if proc.returncode != 0:
        raise RuntimeError(f"radar {' '.join(args)} failed: {proc.stderr.strip()}")
    return elapsed


def main() -> None:
    workspace = Path(tempfile.mkdtemp(prefix="radar-bench-"))
    repo = workspace / "repo"
    try:
        repo.mkdir()
        print(f"building {COMMITS} commits in {repo} ...")
        build_repo(repo)

        cold = run_radar(repo, ["--no-cache"])
        run_radar(repo, [])  # prime the report cache
        cached = run_radar(repo, [])

        print(f"cold (--no-cache): {cold:.2f}s")
        print(f"cached second run: {cached:.2f}s")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    main()

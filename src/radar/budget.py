from __future__ import annotations
import dataclasses
from dataclasses import dataclass

TARGET = 1400
HARD_MAX = 1450


def est_tokens(text: str) -> int:
    return int(len(text) / 3.2) + 1


@dataclass(frozen=True)
class Limits:
    events: int = 15
    files: int = 10
    todos: int = 8
    tests: int = 5
    branches: int = 3
    todo_chars: int = 80
    path_chars: int = 60
    short_instructions: bool = False
    hotspots: int = 3
    env: int = 5
    diagram: bool = False


# Each rung is strictly smaller than the one before it.
LADDER = (
    Limits(hotspots=3, env=5),
    Limits(events=10, hotspots=3, env=5),
    Limits(events=8, todos=6, hotspots=3, env=5),
    Limits(events=6, todos=5, files=5, hotspots=3, env=5),
    Limits(events=5, todos=4, files=4, tests=3, branches=2, todo_chars=60,
           hotspots=0, env=0),
    Limits(events=4, todos=3, files=3, tests=2, branches=1, todo_chars=50,
           path_chars=40, short_instructions=True, hotspots=0, env=0),
    Limits(events=2, todos=2, files=2, tests=1, branches=0, todo_chars=40,
           path_chars=30, short_instructions=True, hotspots=0, env=0),
    Limits(events=1, todos=0, files=0, tests=0, branches=0, todo_chars=40,
           path_chars=30, short_instructions=True, hotspots=0, env=0),
)

FULL = Limits(events=10**6, files=10**6, todos=10**6, tests=10**6,
              branches=10**6, todo_chars=200, path_chars=200,
              hotspots=10**6, env=10**6)


def shorten(path: str, limit: int) -> str:
    path = path.replace("\\", "/")
    if len(path) <= limit:
        return path
    candidate = ".../" + "/".join(path.split("/")[-2:])
    if len(candidate) <= limit:
        return candidate
    return "..." + path[-(limit - 3):]


def fit(report, render, budget: int = TARGET, diagram: bool = False):
    """Return (text, limits). Walks the ladder until the text fits the cap.

    When a diagram is requested it is tried at the full first rung and then
    dropped before any other section is trimmed, so it never costs events,
    files, hotspots, or env blockers.
    """
    cap = min(budget, HARD_MAX)
    if diagram:
        first = dataclasses.replace(LADDER[0], diagram=True)
        text = render(report, first)
        if est_tokens(text) <= cap:
            return text, first

    text, lim = "", LADDER[-1]
    for lim in LADDER:
        text = render(report, lim)
        if est_tokens(text) <= cap:
            break
    return text, lim


def trimmed(report, lim: Limits) -> list:
    rows = (
        ("events", len(report.events), lim.events),
        ("files", len(report.uncommitted), lim.files),
        ("TODOs", len(report.todos), lim.todos),
        ("tests", len(report.failing_tests), lim.tests),
        ("branches", len(report.stale_branches), lim.branches),
        ("hotspots", len(report.hotspots), lim.hotspots),
        ("env issues", len(report.env_issues), lim.env),
    )
    return [f"{total - kept} {name}" for name, total, kept in rows if total > kept]

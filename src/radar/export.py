from __future__ import annotations
from typing import List
from xml.sax.saxutils import escape, quoteattr

from .budget import Limits, shorten
from .models import Event, Report

INSTR_FULL = (
    "Act as a senior engineer who has worked on this project for months. "
    "[e]=evidence from the repo, [i]=inferred. Treat [i] items as hypotheses "
    "and confirm before relying on them. Resume from <stopped_at>."
)
INSTR_SHORT = (
    "Senior engineer on this project. [e]=evidence, [i]=inferred; "
    "confirm [i] before relying on it."
)
DIAGRAM_WIDTH = 60
DIAGRAM_MAX_LINES = 20


def render_diagram(report: Report, width: int = DIAGRAM_WIDTH,
                   max_lines: int = DIAGRAM_MAX_LINES) -> str:
    """Draw a compact, label-free activity line using only ASCII symbols."""
    events = pick_events(report.events, 15)
    chain = "-".join(">" if event.kind == "stop" else "*" for event in events)
    if not chain:
        chain = ">"

    inner = max(1, width - 4)
    rows = [chain[start:start + inner] for start in range(0, len(chain), inner)]
    rows = rows[: max(1, max_lines - 2)]

    top = "+" + "-" * (width - 2) + "+"
    lines = [top]
    for row in rows:
        lines.append("| " + row[:inner].ljust(inner) + " |")
    lines.append(top)
    return "\n".join(lines[:max_lines])


def pick_events(events: List[Event], n: int) -> List[Event]:
    """Keep the n highest-weight events (newest first on ties), return chronological."""
    by_date = sorted(events, key=lambda e: e.date, reverse=True)
    # On equal weight the synthetic stop event wins ties, so a cap of 1
    # still tells the reader where work stopped.
    top = sorted(by_date, key=lambda e: (-e.weight, e.kind != "stop"))[:n]
    return sorted(top, key=lambda e: e.date)


def event_line(e: Event) -> str:
    line = f"{e.date} | {e.kind}: {e.text} [{e.conf}]"
    return f"{line} | {e.ref}" if e.ref else line


def _select(report: Report, lim: Limits):
    files = sorted(report.uncommitted, key=lambda f: -f.lines_changed)[: lim.files]
    todos = report.todos[: lim.todos]
    tests = report.failing_tests[: lim.tests]
    branches = sorted(report.stale_branches, key=lambda b: b.days_old)[: lim.branches]
    events = pick_events(report.events, lim.events)
    hotspots = report.hotspots[: lim.hotspots]
    env_issues = report.env_issues[: lim.env]
    return files, todos, tests, branches, events, hotspots, env_issues


def _block(tag: str, lines: List[str], total: int) -> List[str]:
    if not lines:
        return []
    more = total - len(lines)
    attr = f' more="{more}"' if more > 0 else ""
    return [f"<{tag}{attr}>", *lines, f"</{tag}>"]


def render_xml(report: Report, lim: Limits, diagram: bool = False) -> str:
    files, todos, tests, branches, events, hotspots, env_issues = _select(report, lim)

    stopped = (
        _block("uncommitted", [
            f'<file path={quoteattr(shorten(f.path, lim.path_chars))} status={quoteattr(f.status)}/>'
            for f in files], len(report.uncommitted))
        + _block("todos", [
            f'<todo path={quoteattr(shorten(t.path, lim.path_chars))} line="{t.line}">'
            f'{escape(t.text[: lim.todo_chars])}</todo>'
            for t in todos], len(report.todos))
        + _block("failing_tests", [
            f"<test>{escape(t[: lim.path_chars + 20])}</test>" for t in tests],
            len(report.failing_tests))
        + _block("stale_branches", [
            f'<branch name={quoteattr(b.name[:40])} age_days="{b.days_old}"/>'
            for b in branches], len(report.stale_branches))
    )

    out = ["<project_handoff>"]
    if stopped:
        out += ["<stopped_at>", *stopped, "</stopped_at>"]
    if events:
        out += ["<timeline>", *[escape(event_line(e)) for e in events], "</timeline>"]
    if hotspots:
        out += [
            "<hotspots>",
            *[
                f'<pair a={quoteattr(h.a)} b={quoteattr(h.b)} n="{h.count}"/>'
                for h in hotspots
            ],
            "</hotspots>",
        ]
    if env_issues:
        out += [
            "<env_blockers>",
            *[
                f'<issue kind={quoteattr(issue.kind)}>{escape(issue.detail)}</issue>'
                for issue in env_issues
            ],
            "</env_blockers>",
        ]
    out.append(
        f"<instructions>{escape(INSTR_SHORT if lim.short_instructions else INSTR_FULL)}</instructions>"
    )
    if lim.diagram or diagram:
        out += ["<diagram>", escape(render_diagram(report)), "</diagram>"]
    out.append("</project_handoff>")
    return "\n".join(out)


def _md(title: str, items: List[str], total: int) -> List[str]:
    if not items:
        return []
    out = [f"## {title}", *[f"- {i}" for i in items]]
    if total > len(items):
        out.append(f"- +{total - len(items)} more")
    return out + [""]


def render_md(report: Report, lim: Limits, diagram: bool = False) -> str:
    files, todos, tests, branches, events, hotspots, env_issues = _select(report, lim)
    out = ["# Project handoff", ""]
    out += _md("Uncommitted", [f"{f.status} {shorten(f.path, lim.path_chars)}" for f in files],
               len(report.uncommitted))
    out += _md("TODOs", [f"{shorten(t.path, lim.path_chars)}:{t.line} {t.text[: lim.todo_chars]}"
                         for t in todos], len(report.todos))
    out += _md("Failing tests", [t[: lim.path_chars + 20] for t in tests],
               len(report.failing_tests))
    out += _md("Stale branches", [f"{b.name[:40]} ({b.days_old}d)" for b in branches],
               len(report.stale_branches))
    out += _md("Timeline", [event_line(e) for e in events], len(events))
    out += _md("Hotspots", [f"{shorten(h.a, lim.path_chars)} + "
                            f"{shorten(h.b, lim.path_chars)} ({h.count}x)"
                            for h in hotspots], len(report.hotspots))
    out += _md("Env blockers", [f"{issue.kind}: {issue.detail}"
                                for issue in env_issues], len(report.env_issues))
    out += ["## Instructions", INSTR_SHORT if lim.short_instructions else INSTR_FULL, ""]
    if lim.diagram or diagram:
        out += ["<diagram>", render_diagram(report), "</diagram>", ""]
    return "\n".join(out)

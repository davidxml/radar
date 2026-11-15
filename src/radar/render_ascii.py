from __future__ import annotations
from datetime import date
from typing import List, Optional

from .budget import shorten
from .export import pick_events
from .models import Report

MARK = {"stop": ">>", "revert": "<-", "swap": "<>", "deletion": "--", "scaffold": "++"}
CAPS = {"files": 10, "todos": 10, "tests": 5, "branches": 5, "events": 15}
GAP_DAYS = 14


def _parse(d: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat((d or "")[:10])
    except ValueError:
        return None


def _age(d: Optional[str], today: date) -> str:
    dt = _parse(d)
    if dt is None:
        return "unknown"
    n = (today - dt).days
    if n <= 0:
        return "today"
    if n == 1:
        return "1 day ago"
    return f"{n} days ago" if n < 60 else f"{n // 30} months ago"


def _list(out: List[str], title: str, rows: List[str], total: int) -> None:
    if total == 0:
        return
    out.append(f"{title} ({total})")
    out.extend(f"  {r}" for r in rows)
    if total > len(rows):
        out.append(f"  +{total - len(rows)} more")
    out.append("")


def render_terminal(report: Report, repo_name: str,
                    today: Optional[date] = None, width: int = 72) -> str:
    """Plain ASCII only: legacy Windows consoles crash on box-drawing characters."""
    today = today or date.today()
    out = ["=" * width,
           f"RADAR  {repo_name}  |  last commit {_age(report.last_commit_date, today)}",
           "=" * width, "", "RESUME HERE", "-" * width]

    files = sorted(report.uncommitted, key=lambda f: -f.lines_changed)[: CAPS["files"]]
    branches = sorted(report.stale_branches, key=lambda b: -b.days_old)[: CAPS["branches"]]
    pending = bool(report.uncommitted or report.todos or report.failing_tests
                   or report.stale_branches)
    if not pending:
        out += ["  Nothing pending: clean tree, no recent TODOs.", ""]
    _list(out, "Uncommitted", [f"{f.status:<2} {shorten(f.path, 56)}" for f in files],
          len(report.uncommitted))
    _list(out, "TODO / FIXME",
          [f"{shorten(t.path, 36)}:{t.line}  {t.text[:50]}" for t in report.todos[: CAPS["todos"]]],
          len(report.todos))
    _list(out, "Failing tests", [t[:70] for t in report.failing_tests[: CAPS["tests"]]],
          len(report.failing_tests))
    _list(out, "Stale branches", [f"{b.name[:40]}  {b.days_old}d" for b in branches],
          len(report.stale_branches))

    events = pick_events(report.events, CAPS["events"])
    if events:
        out += ["TIMELINE", "-" * width]
        prev = None
        for e in events:
            cur = _parse(e.date)
            if prev and cur and (cur - prev).days >= GAP_DAYS:
                out.append(f"      ... {(cur - prev).days} days quiet ...")
            ref = f"  {e.ref}" if e.ref else ""
            out.append(f"  {e.date}  {MARK.get(e.kind, '+ ')}  {e.kind:<8} {e.text} [{e.conf}]{ref}")
            prev = cur or prev
        out += ["", "  >> stop  <- revert  <> swap  -- deletion  [e]=evidence [i]=inferred", ""]
    return "\n".join(out)
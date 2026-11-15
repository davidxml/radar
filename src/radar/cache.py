from __future__ import annotations
import dataclasses
import hashlib
import json
import os
import tempfile
from datetime import date
from typing import Optional

from . import git, tests_artifacts
from .models import Branch, Event, FileChange, Report, Todo

try:
    from . import __version__
except ImportError:  # pragma: no cover
    __version__ = "0"

SCHEMA = 1


def _out(args, cwd) -> str:
    try:
        return str(git.run(args, cwd)).strip()
    except Exception:
        return ""


def _git_dir(cwd: str) -> str:
    out = _out(["rev-parse", "--git-dir"], cwd)
    return out if os.path.isabs(out) else os.path.join(cwd, out)


def _path(cwd: str) -> str:
    return os.path.join(_git_dir(cwd), "radar-cache.json")


def compute_key(cwd: str, n_commits: int = 200, n_todo: int = 30) -> str:
    """Changes whenever anything the report depends on changes."""
    h = hashlib.sha256()
    # Date is in the key because branch ages and the stop event depend on today.
    h.update(f"{SCHEMA}|{__version__}|{date.today().isoformat()}|{n_commits}|{n_todo}".encode())
    h.update(_out(["rev-parse", "HEAD"], cwd).encode())
    h.update(_out(["for-each-ref", "--format=%(objectname) %(refname)", "refs/heads"], cwd).encode())
    # Porcelain status alone misses a dirty file edited again (status stays "M"),
    # so mix in each dirty file's mtime and size.
    for f in sorted(git.status_porcelain(cwd), key=lambda f: f.path):
        try:
            st = os.stat(os.path.join(cwd, f.path))
            sig = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            sig = "gone"
        h.update(f"|{f.status}:{f.path}:{sig}".encode())
    # Test artifacts live outside git (.pytest_cache is usually ignored).
    h.update(tests_artifacts.fingerprint(cwd).encode())
    return h.hexdigest()


def _from_dict(d: dict) -> Report:
    return Report(
        uncommitted=[FileChange(**x) for x in d["uncommitted"]],
        todos=[Todo(**x) for x in d["todos"]],
        failing_tests=list(d["failing_tests"]),
        stale_branches=[Branch(**x) for x in d["stale_branches"]],
        events=[Event(**x) for x in d["events"]],
        last_commit_date=d.get("last_commit_date"),
    )


def load(cwd: str, key: str) -> Optional[Report]:
    try:
        with open(_path(cwd), encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("key") != key:
            return None
        return _from_dict(data["report"])
    except Exception:
        return None  # missing, corrupt, or from an older schema: just rebuild


def save(cwd: str, key: str, report: Report) -> None:
    tmp = None
    try:
        path = _path(cwd)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix="radar-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"key": key, "report": dataclasses.asdict(report)}, fh)
        os.replace(tmp, path)
    except Exception:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass  # a cache that can't be written must never break radar
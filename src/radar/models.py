from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

WEIGHTS = {"stop": 5, "revert": 5, "swap": 4, "deletion": 3, "scaffold": 2}


@dataclass(frozen=True)
class Event:
    date: str                 # ISO "YYYY-MM-DD"
    kind: str                 # stop|revert|swap|deletion|scaffold|other
    text: str
    conf: str = "e"           # "e" evidence, "i" inferred
    ref: Optional[str] = None # 7-char sha

    @property
    def weight(self) -> int:
        return WEIGHTS.get(self.kind, 1)


@dataclass(frozen=True)
class Todo:
    path: str
    line: int
    text: str
    ref: Optional[str] = None


@dataclass(frozen=True)
class FileChange:
    path: str
    status: str               # M, A, D, ?, R
    lines_changed: int = 0


@dataclass(frozen=True)
class Branch:
    name: str
    days_old: int


@dataclass
class Report:
    uncommitted: List[FileChange] = field(default_factory=list)
    todos: List[Todo] = field(default_factory=list)
    failing_tests: List[str] = field(default_factory=list)
    stale_branches: List[Branch] = field(default_factory=list)
    events: List[Event] = field(default_factory=list)
    last_commit_date: Optional[str] = None
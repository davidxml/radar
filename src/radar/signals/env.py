"""Cheap, offline checks for local environment problems."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from ..models import EnvIssue

MAX_ISSUES = 8
PROBE_TIMEOUT = 0.2
NODE_TIMEOUT = 2.0

ENV_EXAMPLE_FILES = (".env.example", ".env.sample")
COMPOSE_FILES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yaml",
    "compose.yml",
)
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"})
DEFAULT_PORTS = {
    "postgres": 5432,
    "postgresql": 5432,
    "mysql": 3306,
    "mariadb": 3306,
    "redis": 6379,
    "rediss": 6379,
    "mongodb": 27017,
    "mongodb+srv": 27017,
    "amqp": 5672,
    "amqps": 5671,
    "http": 80,
    "https": 443,
}

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REQUIRES_RE = re.compile(r"requires-python\s*=\s*[\"']([^\"']+)[\"']", re.S)
_SPEC_RE = re.compile(
    r"^(~=|==|!=|<=|>=|<|>)\s*(\d+(?:\.\d+)*(?:\.\*)?)$"
)
_COMPOSE_PORT_RE = re.compile(
    r'^\s*-\s*["\']?'
    r'(?:(?P<ip>\[[^\]]+\]|[^:\s]+):)?'
    r'(?P<host>\d{1,5}):(?P<container>\d{1,5})'
    r'(?:/(?:tcp|udp))?["\']?\s*(?:#.*)?$'
)
_PUBLISHED_RE = re.compile(r'^\s*published:\s*["\']?(\d{1,5})["\']?\s*(?:#.*)?$')


def _read(cwd, name: str) -> Optional[str]:
    try:
        with open(os.path.join(os.fspath(cwd), name), encoding="utf-8",
                  errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_env(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not _ENV_KEY_RE.match(key):
            continue
        values[key] = _unquote(value)
    return values


def _first_line(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def _version_parts(value: str) -> Optional[Tuple[int, ...]]:
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups() if part is not None)


def _prefix_matches(pin: Tuple[int, ...], running: Tuple[int, ...]) -> bool:
    return len(pin) <= len(running) and running[: len(pin)] == pin


def _cmp(left: Tuple[int, ...], right: Tuple[int, ...]) -> int:
    width = max(len(left), len(right))
    a = left + (0,) * (width - len(left))
    b = right + (0,) * (width - len(right))
    return (a > b) - (a < b)


def _satisfies(running: Tuple[int, ...], spec: str) -> bool:
    """Best-effort PEP 440 subset used by requires-python."""
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        match = _SPEC_RE.match(token)
        if not match:
            return True  # unknown syntax: do not invent a mismatch
        op, raw = match.groups()
        wildcard = raw.endswith(".*")
        parts = _version_parts(raw[:-2] if wildcard else raw)
        if parts is None:
            return True
        comparison = _cmp(running, parts)

        if op == "==":
            if wildcard:
                ok = _prefix_matches(parts, running)
            else:
                ok = comparison == 0
        elif op == "!=":
            if wildcard:
                ok = not _prefix_matches(parts, running)
            else:
                ok = comparison != 0
        elif op == ">=":
            ok = comparison >= 0
        elif op == ">":
            ok = comparison > 0
        elif op == "<=":
            ok = comparison <= 0
        elif op == "<":
            ok = comparison < 0
        else:  # ~=
            if len(parts) < 2:
                return True
            lower_ok = comparison >= 0
            if len(parts) == 2:
                upper = (parts[0] + 1,)
            else:
                upper = parts[:-1]
                upper = upper[:-1] + (upper[-1] + 1,)
            ok = lower_ok and _cmp(running, upper) < 0

        if not ok:
            return False
    return True


def _python_running() -> Tuple[int, ...]:
    return (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)


def _node_running() -> Optional[Tuple[int, ...]]:
    try:
        proc = subprocess.run(
            ["node", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=NODE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return _version_parts(proc.stdout)


def _python_pins(cwd) -> List[Tuple[str, str]]:
    pins: List[Tuple[str, str]] = []
    value = _first_line(_read(cwd, ".python-version"))
    if value:
        pins.append((".python-version", value))

    tool_versions = _read(cwd, ".tool-versions")
    if tool_versions:
        for line in tool_versions.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] in {"python", "python3"}:
                pins.append((".tool-versions", fields[1]))

    pyproject = _read(cwd, "pyproject.toml")
    if pyproject:
        match = _REQUIRES_RE.search(pyproject)
        if match:
            pins.append(("pyproject requires-python", match.group(1).strip()))
    return pins


def _node_pins(cwd) -> List[Tuple[str, str]]:
    pins: List[Tuple[str, str]] = []
    for name in (".nvmrc", ".node-version"):
        value = _first_line(_read(cwd, name))
        if value:
            pins.append((name, value))

    tool_versions = _read(cwd, ".tool-versions")
    if tool_versions:
        for line in tool_versions.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] in {"node", "nodejs"}:
                pins.append((".tool-versions", fields[1]))
    return pins


def _runtime_issues(cwd) -> List[EnvIssue]:
    issues: List[EnvIssue] = []
    running = _python_running()
    running_text = ".".join(str(part) for part in running)

    for source, pin in _python_pins(cwd):
        if source == "pyproject requires-python":
            if not _satisfies(running, pin):
                issues.append(EnvIssue(
                    "runtime",
                    f"{source} is {pin}; running Python {running_text}",
                ))
            continue
        parts = _version_parts(pin)
        if parts is not None and not _prefix_matches(parts, running):
            issues.append(EnvIssue(
                "runtime",
                f"{source} pins Python {pin}; running {running_text}",
            ))

    node_pins = _node_pins(cwd)
    if node_pins:
        node = _node_running()
        if node is not None:
            node_text = ".".join(str(part) for part in node)
            for source, pin in node_pins:
                parts = _version_parts(pin)
                if parts is not None and not _prefix_matches(parts, node):
                    issues.append(EnvIssue(
                        "runtime",
                        f"{source} pins Node {pin}; running {node_text}",
                    ))
    return issues


def _is_local_ip(value: Optional[str]) -> bool:
    if not value:
        return True
    return value.strip("[]").lower() in LOCAL_HOSTS


def _compose_ports(cwd) -> Dict[int, str]:
    found: Dict[int, str] = {}
    for name in COMPOSE_FILES:
        text = _read(cwd, name)
        if text is None:
            continue
        for line in text.splitlines():
            match = _COMPOSE_PORT_RE.match(line)
            if match:
                if not _is_local_ip(match.group("ip")):
                    continue
                port = int(match.group("host"))
                found.setdefault(port, f"port in {name}")
                continue
            published = _PUBLISHED_RE.match(line)
            if published:
                port = int(published.group(1))
                found.setdefault(port, f"port in {name}")
    return found


def _url_ports(env: Dict[str, str]) -> Dict[int, str]:
    found: Dict[int, str] = {}
    for key, value in env.items():
        upper_key = key.upper()
        if not (upper_key.endswith("_URL") or upper_key in {"DATABASE_URL", "REDIS_URL"}):
            continue
        if "://" not in value:
            continue
        try:
            parsed = urlparse(value)
            host = parsed.hostname
            port = parsed.port or DEFAULT_PORTS.get(parsed.scheme.lower())
        except ValueError:
            continue
        if not host or not _is_local_ip(host) or not port:
            continue
        found.setdefault(int(port), f"{key} on 127.0.0.1:{int(port)}")
    return found


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=PROBE_TIMEOUT):
            return True
    except OSError:
        return False


def find_env_issues(cwd) -> List[EnvIssue]:
    """Return up to eight local environment blockers, never secret values."""
    issues: List[EnvIssue] = []

    actual_text = _read(cwd, ".env")
    example_text = None
    for name in ENV_EXAMPLE_FILES:
        example_text = _read(cwd, name)
        if example_text is not None:
            break

    actual: Dict[str, str] = {}
    if example_text is not None:
        if actual_text is None:
            issues.append(EnvIssue("missing_key", "no .env file"))
        else:
            actual = _parse_env(actual_text)
            for key in sorted(_parse_env(example_text)):
                if key not in actual or not actual[key].strip():
                    issues.append(EnvIssue(
                        "missing_key",
                        f"{key} is missing or empty in .env",
                    ))

    if actual_text is not None:
        actual = actual or _parse_env(actual_text)
    issues.extend(_runtime_issues(cwd))

    if len(issues) >= MAX_ISSUES:
        return issues[:MAX_ISSUES]

    ports: Dict[int, str] = {}
    ports.update(_compose_ports(cwd))
    ports.update(_url_ports(actual))
    for port, label in sorted(ports.items()):
        if not _listening(port):
            issues.append(EnvIssue(
                "service_down",
                f"{label} is not reachable on 127.0.0.1:{port}",
            ))
            if len(issues) >= MAX_ISSUES:
                break

    return issues[:MAX_ISSUES]

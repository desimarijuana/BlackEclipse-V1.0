"""Port detection and conflict reporting.

Uses the OS's own listening-socket table — `netstat -ano` / `ss -ltn` — never a
hard-coded list of "development ports". The common dev ports (3000, 5173, 8000,
…) are only used to decorate the report; every listening port the OS reports is
returned.

Conflict handling is honest: we report WHO holds a port. We never kill another
process automatically — `find_conflict` returns the owner and lets policy decide.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Optional

from .types import PortInfo

_PROBE_TIMEOUT_S = 6

#: Development ports worth calling out in a summary. NOT a filter.
COMMON_DEV_PORTS: tuple[int, ...] = (3000, 3001, 3002, 4200, 5000, 5173, 5174, 5432, 6379, 8000, 8080, 8888, 9000)


def _run(argv: list[str]) -> str:
    try:
        completed = subprocess.run(argv, capture_output=True, timeout=_PROBE_TIMEOUT_S, shell=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (completed.stdout or b"").decode("utf-8", "replace")


def _parse_netstat_windows(text: str) -> list[PortInfo]:
    ports: list[PortInfo] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0].upper() not in ("TCP",):
            continue
        if parts[3].upper() != "LISTENING":
            continue
        local = parts[1]
        address, _, port_text = local.rpartition(":")
        try:
            port = int(port_text)
        except ValueError:
            continue
        pid: Optional[int] = None
        for token in parts[4:]:
            if token.isdigit():
                pid = int(token)
        ports.append(PortInfo(port=port, pid=pid, process_id=None, address=address, protocol="tcp", status="listening"))
    return ports


def _parse_ss_posix(text: str) -> list[PortInfo]:
    ports: list[PortInfo] = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        address, _, port_text = local.rpartition(":")
        try:
            port = int(port_text)
        except ValueError:
            continue
        pid: Optional[int] = None
        match = re.search(r"pid=(\d+)", line)
        if match:
            pid = int(match.group(1))
        ports.append(PortInfo(port=port, pid=pid, process_id=None, address=address, protocol="tcp", status="listening"))
    return ports


def list_listening_ports(*, process_index: Optional[dict[int, str]] = None) -> list[PortInfo]:
    """Every listening TCP port the OS reports, with an owner pid when known.

    ``process_index`` maps pid -> processId for the harness's own processes, so a
    port owned by a tracked process names that process.
    """
    if os.name == "nt":
        ports = _parse_netstat_windows(_run(["netstat", "-ano", "-p", "tcp"]))
    else:
        text = _run(["ss", "-ltnp"])
        if not text:
            text = _run(["netstat", "-ltnp"])
        ports = _parse_ss_posix(text)
    if process_index:
        ports = [
            PortInfo(
                port=p.port, pid=p.pid,
                process_id=process_index.get(p.pid) if p.pid is not None else None,
                address=p.address, protocol=p.protocol, status=p.status,
            )
            for p in ports
        ]
    # de-duplicate by (port, pid) preserving order, then sort by port.
    seen: set[tuple[int, Optional[int]]] = set()
    unique: list[PortInfo] = []
    for item in ports:
        key = (item.port, item.pid)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    unique.sort(key=lambda item: (item.port, item.pid or 0))
    return unique


def find_conflict(port: int, *, process_index: Optional[dict[int, str]] = None) -> Optional[PortInfo]:
    """The process holding ``port``, or None when the port is free."""
    for item in list_listening_ports(process_index=process_index):
        if item.port == int(port):
            return item
    return None


def summarize(ports: list[PortInfo]) -> dict[str, Any]:
    """A compact model/UI view: dev ports first, then the rest."""
    dev = [p.to_dict() for p in ports if p.port in COMMON_DEV_PORTS]
    other = [p.to_dict() for p in ports if p.port not in COMMON_DEV_PORTS]
    return {"count": len(ports), "development": dev, "other": other}


__all__ = ["COMMON_DEV_PORTS", "find_conflict", "list_listening_ports", "summarize"]

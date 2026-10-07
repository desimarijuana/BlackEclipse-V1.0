"""The port manager — check, find a free port, list, identify, and release.

It is a thin layer over the terminal subsystem's port table
(`terminal/port_manager.py`), which is the authoritative OS listener reader. This
module adds the application-level concerns: which port a request wants, whether
it belongs to Eclipse, and the safe fallback to another port.

A conflict is never resolved by killing a foreign process. When a requested port
is occupied: it is identified; if it belongs to an Eclipse-managed process it may
be released by that process's owner; otherwise the manager either picks the next
free port (when permitted) or asks for authorization. The selected port is always
recorded.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from typing import Any, Optional

from .models import PortRecord, _COMMON_PORT_SERVICES


@dataclass
class PortConflict:
    """A port that is already in use, with its identified owner when known."""

    port: int
    in_use: bool = True
    pid: Optional[int] = None
    process_id: Optional[str] = None
    managed: bool = False
    owner: str = ""
    likely_service: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port, "inUse": self.in_use, "pid": self.pid,
            "processId": self.process_id, "managed": self.managed,
            "owner": self.owner, "likelyService": self.likely_service,
        }


def _socket_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, int(port)))
            return True
        except OSError:
            return False


class PortManager:
    """Application-level port allocation and conflict identification."""

    def __init__(self, *, terminal: Any = None, range_start: int = 3000, range_end: int = 9999) -> None:
        self._terminal = terminal
        self._range = (range_start, range_end)
        self._reserved: dict[int, str] = {}

    # ── queries ──────────────────────────────────────────────────────────────────
    def check(self, port: int) -> dict[str, Any]:
        """Whether a port is free, and who holds it when it is not."""
        conflict = self.identify(port)
        return {"port": int(port), "inUse": conflict is not None, "conflict": conflict.to_dict() if conflict else None}

    def identify(self, port: int) -> Optional[PortConflict]:
        """Return the owner of an in-use port, or None when it is free.

        Uses the terminal subsystem (OS listener table) first; falls back to a
        direct bind probe. An Eclipse-managed owner is marked `managed`.
        """
        port = int(port)
        if port in self._reserved:
            return PortConflict(port=port, in_use=True, process_id=self._reserved[port],
                                managed=True, owner=self._reserved[port],
                                likely_service=_COMMON_PORT_SERVICES.get(port, ""))
        if self._terminal is not None:
            try:
                found = self._terminal.find_port_conflict(port)
            except Exception:  # noqa: BLE001
                found = None
            if found:
                pid = found.get("pid")
                process_id = found.get("processId")
                managed = bool(process_id)
                owner = process_id or (f"pid {pid}" if pid else "another program")
                return PortConflict(
                    port=port, in_use=True, pid=pid, process_id=process_id,
                    managed=managed, owner=owner,
                    likely_service=_COMMON_PORT_SERVICES.get(port, ""),
                )
        if not _socket_free(port):
            return PortConflict(port=port, in_use=True, owner="another program",
                                likely_service=_COMMON_PORT_SERVICES.get(port, ""))
        return None

    def find_free(self, *, preferred: int = 0, avoid: Optional[list[int]] = None) -> int:
        """A free port: `preferred` when free, else the first free in range."""
        avoid_set = set(int(p) for p in (avoid or []))
        if preferred and preferred not in avoid_set and self.identify(preferred) is None:
            return int(preferred)
        for port in range(self._range[0], self._range[1] + 1):
            if port in avoid_set:
                continue
            if self.identify(port) is None:
                return port
        return 0

    def allocate(self, *, preferred: int = 0, owner: str = "", avoid: Optional[list[int]] = None) -> PortRecord:
        """Reserve the best free port and record it. Returns a `PortRecord` (port=0 if none)."""
        if preferred and self.identify(preferred) is None:
            port = int(preferred)
            source = "declared"
        else:
            port = self.find_free(preferred=0, avoid=avoid)
            source = "allocated"
        if port:
            self._reserved[port] = owner
        return PortRecord(
            port=port, purpose=owner, source=(source if port else "unavailable"),
            service=owner,
        )

    def release(self, port: int) -> None:
        self._reserved.pop(int(port), None)

    def reserved(self) -> list[PortRecord]:
        return [
            PortRecord(port=port, purpose=owner, source="reserved", service=owner)
            for port, owner in sorted(self._reserved.items())
        ]

    def list_listening(self) -> list[dict[str, Any]]:
        if self._terminal is not None:
            try:
                return self._terminal.list_ports()
            except Exception:  # noqa: BLE001
                return []
        return []

    def summary(self) -> dict[str, Any]:
        listening = self.list_listening()
        return {
            "listening": listening,
            "reserved": [r.to_dict() for r in self.reserved()],
            "count": len(listening),
        }


__all__ = ["PortConflict", "PortManager"]

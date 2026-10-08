"""The machine-wide desktop broker.

One machine has one physical pointer/focus; two agents driving it at once corrupt
each other. Each `ComputerSession` already owns a per-session control lease
(`takeover.py`), but that only arbitrates AGENT↔HUMAN within a session. The broker
adds the missing machine-wide serialization: at most ONE session may hold the
"pointer lease" at a time. A session that cannot acquire it waits (the caller
retries) — it never silently interleaves input with another session.

The broker is deliberately tiny, in-memory and synchronous: it is DATA plus a
counter, testable without a desktop, exactly like `TakeoverManager`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class BrokerState:
    session_id: Optional[str] = None
    acquired_at: float = 0.0
    queue: list[str] = field(default_factory=list)


class DesktopBroker:
    """Serializes control of the one physical desktop across sessions."""

    def __init__(self) -> None:
        self._state = BrokerState()

    def owner(self) -> Optional[str]:
        return self._state.session_id

    def acquire(self, session_id: str) -> bool:
        """Take the machine-wide control lease. Returns True when granted.

        Re-entrant for the current owner so a session's successive actions do not
        deadlock on itself.
        """
        if self._state.session_id == session_id:
            return True
        if self._state.session_id is None:
            self._state.session_id = session_id
            self._state.acquired_at = time.time()
            if session_id in self._state.queue:
                self._state.queue.remove(session_id)
            return True
        # Another session holds it: enqueue the waiter (bounded) and refuse.
        if session_id not in self._state.queue:
            self._state.queue.append(session_id)
            del self._state.queue[:-16]
        return False

    def release(self, session_id: str) -> bool:
        """Release the lease if `session_id` holds it. Returns whether it did."""
        if self._state.session_id != session_id:
            return False
        self._state.session_id = None
        self._state.acquired_at = 0.0
        return True

    def waiting(self) -> list[str]:
        return list(self._state.queue)

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self._state.session_id,
            "acquiredAt": self._state.acquired_at,
            "waiting": list(self._state.queue),
        }


# One broker per process (the one physical desktop).
_BROKER: Optional[DesktopBroker] = None


def get_broker() -> DesktopBroker:
    global _BROKER
    if _BROKER is None:
        _BROKER = DesktopBroker()
    return _BROKER


__all__ = ["BrokerState", "DesktopBroker", "get_broker"]

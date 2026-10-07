"""Human takeover — the control lease.

One owner at a time. The agent holds the lease while acting; a person can TAKE
control, PAUSE, RESUME or RELEASE it. When a person holds the lease the agent's
actions stop (the core checks the lease before every mutation) and the agent's
session state is preserved, so it resumes exactly where it stopped.

The lease is DATA with a monotonic owner + generation, so a stale takeover can
never silently re-authorize an old action.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

AGENT = "agent"
HUMAN = "human"


@dataclass
class ControlLease:
    session_id: str
    owner: str = AGENT
    generation: int = 0
    paused: bool = False
    reason: str = ""
    changed_at: float = field(default_factory=time.time)
    history: list[dict[str, Any]] = field(default_factory=list)

    def _record(self, action: str, *, reason: str = "") -> None:
        self.history.append({"action": action, "owner": self.owner, "at": time.time(), "reason": reason})
        if len(self.history) > 64:
            del self.history[0]

    def agent_may_act(self) -> bool:
        return self.owner == AGENT and not self.paused

    def take_control(self, *, reason: str = "a person took control") -> dict[str, Any]:
        self.owner = HUMAN
        self.paused = True
        self.generation += 1
        self.reason = reason
        self.changed_at = time.time()
        self._record("take_control", reason=reason)
        return self.to_dict()

    def pause(self, *, reason: str = "paused") -> dict[str, Any]:
        self.paused = True
        self.reason = reason
        self.changed_at = time.time()
        self._record("pause", reason=reason)
        return self.to_dict()

    def resume(self, *, reason: str = "resumed") -> dict[str, Any]:
        if self.owner == HUMAN:
            # Resuming from a human takeover returns control to the agent.
            self.owner = AGENT
        self.paused = False
        self.reason = reason
        self.generation += 1
        self.changed_at = time.time()
        self._record("resume", reason=reason)
        return self.to_dict()

    def release(self, *, reason: str = "control released") -> dict[str, Any]:
        self.owner = AGENT
        self.paused = False
        self.generation += 1
        self.reason = reason
        self.changed_at = time.time()
        self._record("release", reason=reason)
        return self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id, "owner": self.owner, "generation": self.generation,
            "paused": self.paused, "reason": self.reason, "changedAt": self.changed_at,
            "agentMayAct": self.agent_may_act(),
        }


class TakeoverManager:
    """Owns one `ControlLease` per session."""

    def __init__(self) -> None:
        self._leases: dict[str, ControlLease] = {}

    def lease(self, session_id: str) -> ControlLease:
        lease = self._leases.get(session_id)
        if lease is None:
            lease = ControlLease(session_id=session_id)
            self._leases[session_id] = lease
        return lease

    def agent_may_act(self, session_id: str) -> bool:
        return self.lease(session_id).agent_may_act()

    def take_control(self, session_id: str, *, reason: str = "") -> dict[str, Any]:
        return self.lease(session_id).take_control(reason=reason or "a person took control")

    def pause(self, session_id: str, *, reason: str = "") -> dict[str, Any]:
        return self.lease(session_id).pause(reason=reason or "paused")

    def resume(self, session_id: str, *, reason: str = "") -> dict[str, Any]:
        return self.lease(session_id).resume(reason=reason or "resumed")

    def release(self, session_id: str, *, reason: str = "") -> dict[str, Any]:
        return self.lease(session_id).release(reason=reason or "control released")

    def status(self, session_id: str) -> dict[str, Any]:
        return self.lease(session_id).to_dict()


__all__ = ["AGENT", "ControlLease", "HUMAN", "TakeoverManager"]

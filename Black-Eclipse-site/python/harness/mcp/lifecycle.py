"""MCP lifecycle resilience (Phase 6, Milestone 2).

This module owns the retry/reconnect *policy* so `manager.py` stays a registry
adapter:

  * `RetryBudget` — separate jittered exponential budgets for initial connect and
    reconnect-after-drop, with an explicit max-attempt count and a terminal state
    that is REPORTED, never silent.
  * `classify_session_error` — decide whether a mid-call transport/session error
    is a *session expiry* (safe to replay a READ) or a general error.
  * keepalive cadence and stdio recycle decisions.

No I/O beyond `asyncio.sleep`; the manager drives the connections.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Optional

# Separate budgets: a startup blip and a mid-life drop are different failures.
MAX_INITIAL_ATTEMPTS = 3
MAX_RECONNECT_ATTEMPTS = 4
BASE_BACKOFF_S = 0.5
MAX_BACKOFF_S = 30.0
# A reconnect attempt is only worth marking "proven" after this long alive.
PROVEN_AFTER_S = 5.0


def jittered(backoff: float) -> float:
    """Full-jitter: a uniform value in `[base/2, base]`, floored at 0.05s."""
    if backoff <= 0:
        return 0.05
    return max(0.05, random.uniform(backoff / 2.0, backoff))


@dataclass
class RetryBudget:
    """Counters + backoff for one connect/reconnect lifecycle.

    `initial_attempts` and `reconnect_attempts` are counted separately; a budget
    that exhausts either ladder yields `exhausted = True` with the last error
    recorded, so the terminal state is reported rather than silently set.
    """

    initial_attempts: int = 0
    reconnect_attempts: int = 0
    backoff: float = BASE_BACKOFF_S
    last_error: Optional[str] = None
    last_error_code: Optional[str] = None
    exhausted: bool = False
    ever_connected: bool = False
    reconnects: int = 0

    def note_connected(self) -> None:
        self.ever_connected = True
        self.reconnects += 1
        self.reconnect_attempts = 0
        self.backoff = BASE_BACKOFF_S
        self.exhausted = False
        self.last_error = None
        self.last_error_code = None

    def note_initial_failure(self, message: str, code: Optional[str]) -> bool:
        """Record an initial-connect failure; True if another attempt is allowed."""
        self.initial_attempts += 1
        self.last_error, self.last_error_code = message, code
        if self.initial_attempts >= MAX_INITIAL_ATTEMPTS:
            self.exhausted = True
            return False
        return True

    def note_reconnect_failure(self, message: str, code: Optional[str]) -> bool:
        """Record a reconnect failure; True if another attempt is allowed."""
        self.reconnect_attempts += 1
        self.last_error, self.last_error_code = message, code
        if self.reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
            self.exhausted = True
            return False
        return True

    async def sleep(self) -> None:
        await asyncio.sleep(jittered(self.backoff))
        self.backoff = min(self.backoff * 2, MAX_BACKOFF_S)

    def reset_after_proven(self) -> None:
        self.reconnect_attempts = 0
        self.backoff = BASE_BACKOFF_S

    def public(self) -> dict[str, object]:
        return {
            "initialAttempts": self.initial_attempts,
            "reconnectAttempts": self.reconnect_attempts,
            "reconnects": self.reconnects,
            "everConnected": self.ever_connected,
            "exhausted": self.exhausted,
            "lastError": self.last_error,
            "lastErrorCode": self.last_error_code,
        }


# Tokens that indicate a session/connection expiry rather than a logic error.
_SESSION_TOKENS = (
    "session", "expired", "closed", "eof", "broken pipe", "connection reset",
    "connection aborted", "remotedisconnected", "server disconnected",
    "not connected", "transport", "gone away", "connection closed",
    "stream closed",
)


def is_session_error(message: str) -> bool:
    """True when an error message looks like a transport/session expiry.

    Deliberately conservative: a `read` may be retried once; a non-read call is
    NEVER replayed, so the classification only decides whether a safe read replay
    is attempted — for anything else the answer is the honest `outcome_uncertain`.
    """
    lowered = (message or "").lower()
    return any(token in lowered for token in _SESSION_TOKENS)


def should_recycle(
    *,
    transport: str,
    now: float,
    connected_at: Optional[float],
    last_call_at: Optional[float],
    idle_timeout_s: Optional[int],
    max_lifetime_s: Optional[int],
) -> Optional[str]:
    """Return a recycle reason for a stdio child, or None to keep it.

    Kept pure so the decision is testable without a live process. HTTP/SSE never
    recycle (their transport reconnects per keepalive failure instead).
    """
    if transport != "stdio":
        return None
    if connected_at is not None and max_lifetime_s and now - connected_at >= max_lifetime_s:
        return "max_lifetime"
    if last_call_at is not None and idle_timeout_s and now - last_call_at >= idle_timeout_s:
        return "idle"
    return None


def keepalive_due(
    *, transport: str, now: float, last_activity: Optional[float], interval_s: Optional[int]
) -> bool:
    """Whether a keepalive probe is due. Stdio is never keepalive-pinged unless set."""
    if not interval_s or interval_s <= 0:
        return False
    if transport == "stdio" and interval_s is None:
        return False
    if last_activity is None:
        return False
    return now - last_activity >= interval_s


__all__ = [
    "RetryBudget",
    "jittered",
    "is_session_error",
    "should_recycle",
    "keepalive_due",
    "MAX_INITIAL_ATTEMPTS",
    "MAX_RECONNECT_ATTEMPTS",
    "BASE_BACKOFF_S",
    "MAX_BACKOFF_S",
    "PROVEN_AFTER_S",
]

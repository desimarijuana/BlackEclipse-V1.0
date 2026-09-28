"""External provider reliability (Phase 10).

Deterministic, in-memory reliability controls for external memory providers:

  * **Failure classification** — transient / permanent / unauthorized /
    unsupported / rate_limited / unavailable, from a bounded error string.
  * **Bounded retry** — a transient failure may be retried a small, fixed number
    of times with a short backoff; a permanent/unauthorized failure is not.
  * **Circuit breaking** — a provider that keeps failing is opened (skipped) for a
    cooldown, then half-opened. State is in-memory and per-process; nothing is
    persisted and native memory is never affected.
  * **History** — a bounded rolling latency/failure record per provider, with a
    last-success timestamp.

Native memory is never retried/held back by anything here: the router always
queries native first with no timeout budget.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

# Failure classes.
TRANSIENT = "transient"
PERMANENT = "permanent"
UNAUTHORIZED = "unauthorized"
UNSUPPORTED = "unsupported"
RATE_LIMITED = "rate_limited"
UNAVAILABLE = "unavailable"

CLASSES = (TRANSIENT, PERMANENT, UNAUTHORIZED, UNSUPPORTED, RATE_LIMITED, UNAVAILABLE)

# Retry policy (bounded; never unbounded).
MAX_ATTEMPTS = 2
RETRY_BACKOFF_S = 0.05

# Circuit breaker.
FAILURE_THRESHOLD = 3        # consecutive failures that open the circuit
COOLDOWN_S = 30.0            # how long a circuit stays open

# History bounds.
MAX_HISTORY = 50


def classify_failure(error: Any) -> str:
    """Classify a provider failure from its error text. Deterministic, bounded."""
    text = str(error or "").lower()
    if not text:
        return UNAVAILABLE
    if "403" in text or "401" in text or "unauthor" in text or "forbidden" in text or "auth" in text:
        return UNAUTHORIZED
    if "429" in text or "rate limit" in text or "too many requests" in text:
        return RATE_LIMITED
    if "unsupported" in text or "not supported" in text or "unknown tool" in text:
        return UNSUPPORTED
    if "timeout" in text or "timed out" in text or "transport" in text or "connection" in text or "temporar" in text:
        return TRANSIENT
    if "invalid" in text or "malformed" in text or "parse" in text:
        return PERMANENT
    if "not connected" in text or "closed" in text or "no runtime" in text or "disabled" in text:
        return UNAVAILABLE
    return UNAVAILABLE


def is_retryable(category: str) -> bool:
    """Only transient and rate-limited failures are worth a bounded retry."""
    return category in (TRANSIENT, RATE_LIMITED)


@dataclass
class ProviderRecord:
    """Bounded, in-memory reliability record for one provider."""

    name: str
    consecutive_failures: int = 0
    opened_at: Optional[float] = None
    total_calls: int = 0
    total_failures: int = 0
    last_success_at: Optional[float] = None
    last_failure_at: Optional[float] = None
    last_failure_category: Optional[str] = None
    latencies_ms: list[float] = field(default_factory=list)

    def to_dict(self, *, now: Optional[float] = None) -> dict[str, Any]:
        now = now if now is not None else time.time()
        mean_latency = (
            round(sum(self.latencies_ms) / len(self.latencies_ms), 1)
            if self.latencies_ms else None
        )
        return {
            "name": self.name,
            "state": self.state(now=now),
            "totalCalls": self.total_calls,
            "totalFailures": self.total_failures,
            "failureRate": round(self.total_failures / self.total_calls, 3) if self.total_calls else None,
            "consecutiveFailures": self.consecutive_failures,
            "lastSuccessAt": self.last_success_at,
            "lastFailureAt": self.last_failure_at,
            "lastFailureCategory": self.last_failure_category,
            "meanLatencyMs": mean_latency,
            "circuitOpenUntil": (self.opened_at + COOLDOWN_S) if self.opened_at else None,
        }

    def state(self, *, now: Optional[float] = None) -> str:
        now = now if now is not None else time.time()
        if self.opened_at is None:
            return "closed"
        if now - self.opened_at >= COOLDOWN_S:
            return "half_open"
        return "open"

    def allows_call(self, *, now: Optional[float] = None) -> bool:
        """A closed or half-open circuit allows a call; an open one does not."""
        return self.state(now=now) != "open"

    def record_success(self, latency_ms: float, *, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        self.total_calls += 1
        self.consecutive_failures = 0
        self.opened_at = None
        self.last_success_at = now
        self._push_latency(latency_ms)

    def record_failure(self, category: str, *, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        self.total_calls += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_at = now
        self.last_failure_category = category
        if self.consecutive_failures >= FAILURE_THRESHOLD:
            self.opened_at = now

    def _push_latency(self, latency_ms: float) -> None:
        self.latencies_ms.append(float(latency_ms))
        if len(self.latencies_ms) > MAX_HISTORY:
            del self.latencies_ms[: len(self.latencies_ms) - MAX_HISTORY]


class ProviderReliability:
    """Process-wide, in-memory reliability registry for external providers."""

    def __init__(self) -> None:
        self._records: dict[str, ProviderRecord] = {}

    def record_for(self, name: str) -> ProviderRecord:
        return self._records.setdefault(name, ProviderRecord(name=name))

    def allows_call(self, name: str, *, now: Optional[float] = None) -> bool:
        return self.record_for(name).allows_call(now=now)

    def snapshot(self) -> list[dict[str, Any]]:
        now = time.time()
        return [record.to_dict(now=now) for record in self._records.values()]

    def reset(self) -> None:
        self._records.clear()


# A module-level instance so state survives across calls in one process.
_GLOBAL = ProviderReliability()


def global_reliability() -> ProviderReliability:
    return _GLOBAL


__all__ = [
    "CLASSES",
    "COOLDOWN_S",
    "FAILURE_THRESHOLD",
    "MAX_ATTEMPTS",
    "PERMANENT",
    "ProviderRecord",
    "ProviderReliability",
    "RATE_LIMITED",
    "TRANSIENT",
    "UNAUTHORIZED",
    "UNSUPPORTED",
    "UNAVAILABLE",
    "classify_failure",
    "global_reliability",
    "is_retryable",
]

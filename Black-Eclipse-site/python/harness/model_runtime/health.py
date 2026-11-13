"""Health, rate limits and circuit breaking for providers and models.

All three track bounded rolling windows keyed by a string (`provider` or
`provider/model`). Time is injected (`now`) so tests are deterministic and no
wall-clock is read. Nothing here calls a network; probing is the caller's job.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional

from .errors import ErrorClass, ModelError


def _monotonic() -> float:
    return time.monotonic()


# ── Health ──────────────────────────────────────────────────────────────────


@dataclass
class _Sample:
    at: float
    ok: bool
    latency_ms: float
    error_class: Optional[ErrorClass] = None
    kind: str = "text"


class HealthManager:
    """Rolling-window availability + latency + error-rate tracker (spec §20)."""

    def __init__(
        self,
        *,
        window: int = 100,
        now: Callable[[], float] = _monotonic,
        max_age_s: float = 900.0,
    ) -> None:
        self._window = window
        self._now = now
        self._max_age_s = max_age_s
        self._samples: dict[str, Deque[_Sample]] = {}

    def _deque(self, key: str) -> Deque[_Sample]:
        samples = self._samples.get(key)
        if samples is None:
            samples = deque(maxlen=self._window)
            self._samples[key] = samples
        return samples

    def _prune(self, samples: Deque[_Sample]) -> None:
        cutoff = self._now() - self._max_age_s
        while samples and samples[0].at < cutoff:
            samples.popleft()

    def record_success(self, key: str, *, latency_ms: float, kind: str = "text") -> None:
        self._deque(key).append(_Sample(self._now(), True, latency_ms, None, kind))

    def record_failure(
        self, key: str, *, error_class: ErrorClass, latency_ms: float = 0.0, kind: str = "text"
    ) -> None:
        self._deque(key).append(_Sample(self._now(), False, latency_ms, error_class, kind))

    def record(self, key: str, *, ok: bool, latency_ms: float, error_class: Optional[ErrorClass] = None) -> None:
        if ok:
            self.record_success(key, latency_ms=latency_ms)
        else:
            self.record_failure(key, error_class=error_class or ErrorClass.UNKNOWN_ERROR, latency_ms=latency_ms)

    def _live(self, key: str) -> list[_Sample]:
        samples = self._samples.get(key)
        if not samples:
            return []
        self._prune(samples)
        return list(samples)

    def health(self, key: str) -> Optional[float]:
        """Success ratio 0..1, or None when there is no evidence yet."""
        samples = self._live(key)
        if not samples:
            return None
        return sum(1 for s in samples if s.ok) / len(samples)

    def error_rate(self, key: str) -> Optional[float]:
        health = self.health(key)
        return None if health is None else round(1.0 - health, 4)

    def latency_percentiles(self, key: str) -> dict[str, Optional[float]]:
        samples = [s.latency_ms for s in self._live(key) if s.latency_ms > 0]
        if not samples:
            return {"p50": None, "p90": None, "p95": None, "p99": None}
        return {
            "p50": _percentile(samples, 50),
            "p90": _percentile(samples, 90),
            "p95": _percentile(samples, 95),
            "p99": _percentile(samples, 99),
        }

    def rate_capability(self, key: str, capability: str) -> Optional[float]:
        """Success ratio for a specific interaction kind: tool / structured."""
        samples = [s for s in self._live(key) if s.kind == capability]
        if not samples:
            return None
        return sum(1 for s in samples if s.ok) / len(samples)

    def snapshot(self, key: str) -> dict[str, object]:
        samples = self._live(key)
        return {
            "key": key,
            "count": len(samples),
            "health": self.health(key),
            "errorRate": self.error_rate(key),
            "latency": self.latency_percentiles(key),
            "toolSuccessRate": self.rate_capability(key, "tool"),
            "structuredOutputSuccessRate": self.rate_capability(key, "structured"),
        }


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    value = ordered[low] * (1 - frac) + ordered[high] * frac
    return round(value, 2)


# ── Circuit breaker ─────────────────────────────────────────────────────────


class CircuitState(str):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OPEN = "open"
    COOLDOWN = "cooldown"
    RECOVERED = "recovered"


@dataclass
class _Circuit:
    state: str = CircuitState.HEALTHY
    failures: int = 0
    successes: int = 0
    opened_at: float = 0.0
    half_open_successes: int = 0


class CircuitBreaker:
    """A per-key breaker: STOP routing to a repeatedly failing target (spec §21).

    States: HEALTHY → DEGRADED (failures accrue) → OPEN (threshold crossed, all
    calls refused) → COOLDOWN (elapsed) → HALF_OPEN (one probe allowed) →
    RECOVERED (closed) or back to OPEN.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 4,
        degraded_threshold: int = 1,
        cooldown_s: float = 30.0,
        half_open_max_successes: int = 2,
        now: Callable[[], float] = _monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._degraded_threshold = degraded_threshold
        self._cooldown_s = cooldown_s
        self._half_open_max_successes = half_open_max_successes
        self._now = now
        self._circuits: dict[str, _Circuit] = {}
        self.on_open: Optional[Callable[[str], None]] = None
        self.on_close: Optional[Callable[[str], None]] = None

    def _circuit(self, key: str) -> _Circuit:
        return self._circuits.setdefault(key, _Circuit())

    def state(self, key: str) -> str:
        circuit = self._circuit(key)
        self._advance(key, circuit)
        return circuit.state

    def _advance(self, key: str, circuit: _Circuit) -> None:
        if circuit.state in (CircuitState.OPEN, CircuitState.COOLDOWN):
            if self._now() - circuit.opened_at >= self._cooldown_s:
                circuit.state = CircuitState.DEGRADED  # half-open probe window
                circuit.successes = 0

    def allow(self, key: str) -> bool:
        """True when a call to `key` may proceed right now."""
        circuit = self._circuit(key)
        self._advance(key, circuit)
        if circuit.state == CircuitState.OPEN:
            return False
        if circuit.state == CircuitState.COOLDOWN:
            return False
        return True

    def record_success(self, key: str) -> None:
        circuit = self._circuit(key)
        was = circuit.state
        circuit.failures = 0
        circuit.successes += 1
        if was == CircuitState.DEGRADED and circuit.successes >= self._half_open_max_successes:
            circuit.state = CircuitState.RECOVERED
            circuit.state = CircuitState.HEALTHY
            if self.on_close:
                self.on_close(key)
        elif was == CircuitState.RECOVERED:
            circuit.state = CircuitState.HEALTHY
            if self.on_close:
                self.on_close(key)

    def record_failure(self, key: str, *, provider_fault: bool = True) -> None:
        """Count a failure. A caller-caused error (bad request) is not a fault."""
        if not provider_fault:
            return
        circuit = self._circuit(key)
        circuit.failures += 1
        if circuit.failures >= self._failure_threshold:
            if circuit.state != CircuitState.OPEN:
                circuit.state = CircuitState.OPEN
                circuit.opened_at = self._now()
                if self.on_open:
                    self.on_open(key)
        elif circuit.failures >= self._degraded_threshold:
            circuit.state = CircuitState.DEGRADED

    def record(self, key: str, error: Optional[ModelError]) -> None:
        if error is None:
            self.record_success(key)
            return
        self.record_failure(key, provider_fault=error.is_provider_fault)

    def reset(self, key: str) -> None:
        self._circuits.pop(key, None)


# ── Rate limits ─────────────────────────────────────────────────────────────


@dataclass
class RateLimitState:
    requests_in_window: int = 0
    tokens_in_window: int = 0
    concurrent: int = 0
    last_429_at: Optional[float] = None
    reset_at: Optional[float] = None


class RateLimitManager:
    """Track provider/model limits independently (spec §19).

    Limits are DECLARED by configuration (the runtime cannot know a provider's
    real quota). With no declared limit the manager still tracks observed 429s
    and concurrent calls, and deprioritizes a target that recently 429'd.
    """

    def __init__(
        self,
        *,
        now: Callable[[], float] = _monotonic,
        window_s: float = 60.0,
        backoff_s: float = 20.0,
        default_concurrency: Optional[int] = None,
    ) -> None:
        self._now = now
        self._window_s = window_s
        self._backoff_s = backoff_s
        self._limits: dict[str, dict[str, Optional[int]]] = {}
        self._state: dict[str, RateLimitState] = {}
        self._events: dict[str, Deque[tuple[float, int]]] = {}
        # Admission is per key. Without a declared `concurrent` limit the
        # default applies to every provider/model key, so parallel sessions
        # cannot stampede one provider. 0/None keeps the old unbounded mode.
        self._default_concurrency = default_concurrency
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    def set_limits(
        self,
        key: str,
        *,
        requests_per_minute: Optional[int] = None,
        tokens_per_minute: Optional[int] = None,
        concurrent: Optional[int] = None,
    ) -> None:
        self._limits[key] = {
            "rpm": requests_per_minute,
            "tpm": tokens_per_minute,
            "concurrent": concurrent,
        }

    def _requests(self, key: str) -> list[float]:
        events = self._events.setdefault(key, deque())
        cutoff = self._now() - self._window_s
        while events and events[0][0] < cutoff:
            events.popleft()
        return [at for at, _ in events]

    def _tokens(self, key: str) -> int:
        events = self._events.setdefault(key, deque())
        cutoff = self._now() - self._window_s
        total = 0
        for at, tokens in events:
            if at >= cutoff:
                total += tokens
        return total

    def record_request(self, key: str, *, tokens: int = 0) -> None:
        self._events.setdefault(key, deque()).append((self._now(), tokens))
        state = self._state.setdefault(key, RateLimitState())
        state.requests_in_window = len(self._requests(key))
        state.tokens_in_window = self._tokens(key)

    def acquire(self, key: str) -> None:
        self._state.setdefault(key, RateLimitState()).concurrent += 1

    def release(self, key: str) -> None:
        state = self._state.setdefault(key, RateLimitState())
        state.concurrent = max(0, state.concurrent - 1)

    def record_429(self, key: str, *, retry_after_s: Optional[float] = None) -> None:
        state = self._state.setdefault(key, RateLimitState())
        state.last_429_at = self._now()
        # Honor the provider's own hint (already bounded by retry_policy).
        state.reset_at = self._now() + max(1.0, float(retry_after_s or self._backoff_s))

    def _concurrency_limit(self, key: str) -> Optional[int]:
        declared = (self._limits.get(key) or {}).get("concurrent")
        if declared is not None:
            return int(declared)
        return self._default_concurrency if self._default_concurrency else None

    def _semaphore(self, key: str) -> Optional[asyncio.Semaphore]:
        limit = self._concurrency_limit(key)
        if limit is None:
            return None
        sem = self._semaphores.get(key)
        if sem is None:
            sem = asyncio.Semaphore(max(1, int(limit)))
            self._semaphores[key] = sem
        return sem

    def _cooldown_or_window_wait(self, key: str) -> float:
        """Seconds until the key's cooldown/RPM/TPM window admits a call."""
        state = self._state.get(key)
        wait = 0.0
        reset_at = state.reset_at if state else None
        if reset_at is not None:
            wait = max(wait, reset_at - self._now())
        limits = self._limits.get(key) or {}
        rpm = limits.get("rpm")
        if rpm is not None:
            events = self._events.setdefault(key, deque())
            cutoff = self._now() - self._window_s
            while events and events[0][0] < cutoff:
                events.popleft()
            if len(events) >= rpm and events:
                wait = max(wait, events[0][0] + self._window_s - self._now())
        tpm = limits.get("tpm")
        if tpm is not None:
            events = self._events.setdefault(key, deque())
            cutoff = self._now() - self._window_s
            total = sum(tokens for at, tokens in events if at >= cutoff)
            if total >= tpm:
                for at, tokens in events:
                    if at >= cutoff:
                        total -= tokens
                        wait = max(wait, at + self._window_s - self._now())
                        if total < tpm:
                            break
        return max(0.0, wait)

    def seconds_until_available(self, key: str) -> float:
        """How long a caller should wait before this key can accept a call.

        Concurrency is handled by the async semaphore, so this returns 0 for a
        key that is merely at its in-flight ceiling (the caller will queue on
        `acquire_slot`).
        """
        return self._cooldown_or_window_wait(key)

    async def acquire_slot(self, key: str, *, timeout_s: Optional[float] = None) -> None:
        """Wait for one admission slot, honoring cooldown/RPM/TPM and limits.

        The semaphore is FIFO, so a burst of sessions queues fairly instead of
        all retrying at once. `timeout_s` bounds the wait; the caller maps
        `asyncio.TimeoutError` to an honest RATE_LIMITED failure.
        """
        loop = asyncio.get_running_loop()
        deadline = (loop.time() + max(0.0, timeout_s)) if timeout_s is not None else None
        sem = self._semaphore(key)
        if sem is not None:
            remaining = None if deadline is None else max(0.0, deadline - loop.time())
            await asyncio.wait_for(sem.acquire(), timeout=remaining)
        try:
            while True:
                wait = self._cooldown_or_window_wait(key)
                if wait <= 0:
                    break
                if deadline is not None and loop.time() + wait > deadline:
                    raise asyncio.TimeoutError
                # Short sleeps keep a second writer's 429 visible promptly.
                await asyncio.sleep(min(max(0.05, wait), 0.5))
            self.acquire(key)
        except BaseException:
            if sem is not None:
                sem.release()
            raise

    def release_slot(self, key: str) -> None:
        self.release(key)
        sem = self._semaphores.get(key)
        if sem is not None:
            sem.release()

    def is_limited(self, key: str) -> bool:
        """True when a declared limit is reached, or a recent 429 is cooling."""
        state = self._state.get(key)
        reset_at = state.reset_at if state else None
        if reset_at is not None and self._now() < reset_at:
            return True
        limits = self._limits.get(key) or {}
        rpm = limits.get("rpm")
        tpm = limits.get("tpm")
        concurrent = limits.get("concurrent")
        if rpm is not None and len(self._requests(key)) >= rpm:
            return True
        if tpm is not None and self._tokens(key) >= tpm:
            return True
        if concurrent is not None and state is not None and state.concurrent >= concurrent:
            return True
        return False

    def snapshot(self, key: str) -> dict[str, object]:
        state = self._state.get(key, RateLimitState())
        return {
            "key": key,
            "requestsInWindow": len(self._requests(key)),
            "tokensInWindow": self._tokens(key),
            "concurrent": state.concurrent,
            "limited": self.is_limited(key),
            "limits": {
                **self._limits.get(key, {}),
                "concurrentDefault": self._default_concurrency,
            },
        }


__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "HealthManager",
    "RateLimitManager",
    "RateLimitState",
]

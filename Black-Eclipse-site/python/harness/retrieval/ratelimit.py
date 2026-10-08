"""Centralized rate-limit / quota management (Financial Data Gateway).

Before this module each provider's pacing was implicit: the retry helper handled a
transient 429 with backoff, but nothing stopped the layer from issuing a burst of
requests to the same provider within one retrieval (or across the parallel
arbitration path). This module centralizes provider pacing so:

  * a provider's declared requests/minute is enforced with a sliding window,
  * per-provider concurrency is bounded,
  * a 429 (or an explicit `Retry-After`) opens a cooldown for that provider,
  * quota/health state is observable.

It is deliberately in-process (asyncio) and additive: a layer constructed without
a manager behaves exactly as before. No new infrastructure dependency.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from .registry import RateLimitSpec


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: Optional[str] = None
    retry_after_s: Optional[float] = None


@dataclass
class _ProviderState:
    spec: RateLimitSpec
    # Sliding-window timestamps of accepted requests (monotonic seconds).
    window: list[float] = field(default_factory=list)
    # Number of calls currently in flight.
    inflight: int = 0
    # Earliest monotonic time a new call is allowed after a 429 cooldown.
    cooldown_until: float = 0.0
    # Observability counters.
    granted: int = 0
    denied: int = 0
    throttled_429: int = 0


class RateLimitManager:
    """Per-provider sliding-window + concurrency limiter. In-process, best-effort.

    Correctness note: pacing is an optimization, never a gate on data honesty.
    When a provider has no declared limit the manager only bounds concurrency; it
    never invents a requests/minute number.
    """

    def __init__(self, *, now: Optional[object] = None) -> None:
        self._states: dict[str, _ProviderState] = {}
        self._lock = asyncio.Lock()
        self._now = now or time.monotonic

    def _state(self, provider: str, spec: Optional[RateLimitSpec]) -> _ProviderState:
        st = self._states.get(provider)
        if st is None:
            st = _ProviderState(spec=spec or RateLimitSpec())
            self._states[provider] = st
        elif spec is not None:
            st.spec = spec
        return st

    async def acquire(
        self, provider: str, spec: Optional[RateLimitSpec] = None
    ) -> RateLimitDecision:
        async with self._lock:
            st = self._state(provider, spec)
            now = float(self._now())  # type: ignore[operator]

            if now < st.cooldown_until:
                st.denied += 1
                return RateLimitDecision(
                    False,
                    f"{provider} is in a rate-limit cooldown",
                    round(st.cooldown_until - now, 2),
                )

            if st.inflight >= max(1, st.spec.concurrency):
                st.denied += 1
                return RateLimitDecision(
                    False,
                    f"{provider} concurrency limit ({st.spec.concurrency}) is reached",
                    None,
                )

            rpm = st.spec.requests_per_minute
            if rpm:
                cutoff = now - 60.0
                st.window = [t for t in st.window if t > cutoff]
                if len(st.window) >= rpm:
                    oldest = st.window[0]
                    retry = max(0.0, 60.0 - (now - oldest))
                    st.denied += 1
                    return RateLimitDecision(
                        False,
                        f"{provider} would exceed {rpm} requests/minute",
                        round(retry, 2),
                    )
                st.window.append(now)

            st.inflight += 1
            st.granted += 1
            return RateLimitDecision(True)

    async def release(self, provider: str) -> None:
        async with self._lock:
            st = self._states.get(provider)
            if st is not None and st.inflight > 0:
                st.inflight -= 1

    async def record_429(self, provider: str, retry_after_s: Optional[float] = None) -> None:
        """Open a cooldown for a provider that returned 429 / an explicit hint."""
        async with self._lock:
            st = self._state(provider, None)
            now = float(self._now())  # type: ignore[operator]
            window = float(retry_after_s) if retry_after_s and retry_after_s > 0 else 30.0
            st.cooldown_until = max(st.cooldown_until, now + window)
            st.throttled_429 += 1

    def snapshot(self) -> dict[str, dict[str, object]]:
        out: dict[str, dict[str, object]] = {}
        for name, st in self._states.items():
            out[name] = {
                "requestsPerMinute": st.spec.requests_per_minute,
                "concurrency": st.spec.concurrency,
                "inflight": st.inflight,
                "granted": st.granted,
                "denied": st.denied,
                "throttled429": st.throttled_429,
                "cooldownRemainingS": max(0.0, round(st.cooldown_until - float(self._now()), 2)),  # type: ignore[operator]
            }
        return out


__all__ = ["RateLimitDecision", "RateLimitManager"]

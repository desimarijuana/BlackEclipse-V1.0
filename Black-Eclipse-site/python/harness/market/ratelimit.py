"""Provider-aware rate limiting with LIVE-quota observation.

The router already declares each provider's limit; this module makes pacing
*measured*, not merely assumed:

  * a declared `requests_per_minute` / concurrency is enforced with a sliding
    window and an in-flight cap,
  * a provider's REAL quota reported in a response (e.g. Binance's
    `X-MBX-USED-WEIGHT-1M`, or a `Retry-After` on a 429) is OBSERVED and used —
    the effective limit is the stricter of declared and observed, and a 429 opens
    a cooldown for that provider,
  * every decision and observation is exposed for the operator surface, so
    "declared" and "observed" never get conflated.

In-process, asyncio, additive. Correctness note (unchanged): pacing is an
optimization, never a gate on data honesty.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from .providers import RateLimit


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: Optional[str] = None
    retry_after_s: Optional[float] = None


@dataclass
class _State:
    declared: RateLimit
    window: list[float] = field(default_factory=list)
    inflight: int = 0
    cooldown_until: float = 0.0
    granted: int = 0
    denied: int = 0
    throttled_429: int = 0
    # ── observed (provider-reported) live quota ──
    observed_limit: Optional[int] = None
    observed_used: Optional[int] = None
    observed_remaining: Optional[int] = None
    observed_window_s: Optional[int] = None
    observed_at: Optional[str] = None
    last_retry_after_s: Optional[float] = None


class MarketRateLimiter:
    """Per-provider pacing with declared + observed quota."""

    def __init__(self, *, now: Optional[object] = None) -> None:
        self._states: dict[str, _State] = {}
        self._lock = asyncio.Lock()
        self._now = now or time.monotonic

    def _state(self, provider: str, declared: Optional[RateLimit] = None) -> _State:
        st = self._states.get(provider)
        if st is None:
            st = _State(declared=declared or RateLimit())
            self._states[provider] = st
        elif declared is not None:
            st.declared = declared
        return st

    def _effective_rpm(self, st: _State) -> Optional[int]:
        """The stricter of declared and live-observed requests/minute."""
        declared = st.declared.requests_per_minute
        observed = None
        if st.observed_limit and st.observed_window_s:
            # Normalise an observed window to a per-minute figure.
            observed = int(st.observed_limit * (60.0 / st.observed_window_s))
        candidates = [v for v in (declared, observed) if v]
        return min(candidates) if candidates else None

    async def acquire(self, provider: str, declared: Optional[RateLimit] = None) -> Decision:
        async with self._lock:
            st = self._state(provider, declared)
            now = float(self._now())  # type: ignore[operator]
            if now < st.cooldown_until:
                st.denied += 1
                return Decision(False, f"{provider} is in a rate-limit cooldown",
                                round(st.cooldown_until - now, 2))
            if st.inflight >= max(1, st.declared.concurrency):
                st.denied += 1
                return Decision(False, f"{provider} concurrency limit ({st.declared.concurrency}) reached")
            rpm = self._effective_rpm(st)
            if rpm:
                cutoff = now - 60.0
                st.window = [t for t in st.window if t > cutoff]
                if len(st.window) >= rpm:
                    oldest = st.window[0]
                    st.denied += 1
                    return Decision(False, f"{provider} would exceed {rpm} requests/minute",
                                    round(max(0.0, 60.0 - (now - oldest)), 2))
                st.window.append(now)
            st.inflight += 1
            st.granted += 1
            return Decision(True)

    async def release(self, provider: str) -> None:
        async with self._lock:
            st = self._states.get(provider)
            if st is not None and st.inflight > 0:
                st.inflight -= 1

    async def observe(
        self,
        provider: str,
        *,
        limit: Optional[int] = None,
        used: Optional[int] = None,
        remaining: Optional[int] = None,
        window_seconds: Optional[int] = None,
        retry_after_s: Optional[float] = None,
    ) -> None:
        """Record a provider's REAL quota reported in a response."""
        async with self._lock:
            st = self._state(provider)
            if limit is not None:
                st.observed_limit = int(limit)
            if used is not None:
                st.observed_used = int(used)
            if remaining is not None:
                st.observed_remaining = int(remaining)
            if window_seconds is not None:
                st.observed_window_s = int(window_seconds)
            if retry_after_s is not None:
                st.last_retry_after_s = float(retry_after_s)
            st.observed_at = _iso_now()

    async def record_429(self, provider: str, retry_after_s: Optional[float] = None) -> None:
        async with self._lock:
            st = self._state(provider)
            now = float(self._now())  # type: ignore[operator]
            window = float(retry_after_s) if retry_after_s and retry_after_s > 0 else 30.0
            st.cooldown_until = max(st.cooldown_until, now + window)
            st.throttled_429 += 1
            st.last_retry_after_s = window

    def snapshot(self) -> dict[str, dict[str, object]]:
        out: dict[str, dict[str, object]] = {}
        for name, st in self._states.items():
            out[name] = {
                "declared": {
                    "requestsPerMinute": st.declared.requests_per_minute,
                    "requestsPerDay": st.declared.requests_per_day,
                    "concurrency": st.declared.concurrency,
                    "costTier": st.declared.cost_tier,
                },
                "observed": {
                    "limit": st.observed_limit,
                    "used": st.observed_used,
                    "remaining": st.observed_remaining,
                    "windowSeconds": st.observed_window_s,
                    "at": st.observed_at,
                },
                "effectiveRequestsPerMinute": self._effective_rpm(st),
                "inflight": st.inflight,
                "granted": st.granted,
                "denied": st.denied,
                "throttled429": st.throttled_429,
                "cooldownRemainingS": max(0.0, round(st.cooldown_until - float(self._now()), 2)),  # type: ignore[operator]
            }
        return out


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


__all__ = ["Decision", "MarketRateLimiter"]

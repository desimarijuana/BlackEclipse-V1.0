"""Resource-aware concurrency: limits, admission, and rate limiting.

Parallelism is never unlimited. Every running node consumes a `global` slot plus
any named class slots it declares (llm, browser, code, database, network, or a
provider-specific key). `ResourceManager.try_acquire` is all-or-nothing, so a node
either gets its full set of slots or none — it can never deadlock half-acquired.

Limits are configuration, not constants: they come from `HARNESS_ORCH_*`
environment variables with safe desktop defaults. `RateLimiter` is a token bucket
per key for provider/tool request limits.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

# Class defaults. A desktop app, not a datacenter.
DEFAULT_LIMITS: dict[str, int] = {
    "global": 8,
    "agent": 8,
    "llm": 8,
    "browser": 3,
    "code": 4,
    "database": 10,
    "network": 20,
}

_ENV_KEYS = {
    "global": "HARNESS_ORCH_MAX_CONCURRENCY",
    "agent": "HARNESS_ORCH_AGENT_CONCURRENCY",
    "llm": "HARNESS_ORCH_LLM_CONCURRENCY",
    "browser": "HARNESS_ORCH_BROWSER_CONCURRENCY",
    "code": "HARNESS_ORCH_CODE_CONCURRENCY",
    "database": "HARNESS_ORCH_DATABASE_CONCURRENCY",
    "network": "HARNESS_ORCH_NETWORK_CONCURRENCY",
}

DEFAULT_LEASE_TTL_MS = 120_000


def limits_from_env(overrides: Optional[dict[str, int]] = None) -> dict[str, int]:
    """Resolve resource limits from the environment, then explicit overrides."""
    limits = dict(DEFAULT_LIMITS)
    for key, env_name in _ENV_KEYS.items():
        raw = os.environ.get(env_name)
        if raw:
            try:
                limits[key] = max(1, int(raw))
            except (TypeError, ValueError):
                pass
    for key, value in (overrides or {}).items():
        try:
            limits[str(key)] = max(0, int(value))
        except (TypeError, ValueError):
            pass
    return limits


@dataclass
class ResourceManager:
    """A bounded, all-or-nothing admission controller for node execution.

    Admission is SYNCHRONOUS because the scheduler runs in one event-loop thread;
    there is no lock to await, so a node either gets its full set of slots or
    none, and a release can never be lost to task cancellation. `wait_release`
    gives the scheduler an event to await when no node fits.
    """

    limits: dict[str, int] = field(default_factory=limits_from_env)
    _used: dict[str, int] = field(default_factory=dict)
    _released: asyncio.Event = field(default_factory=asyncio.Event)

    def limit_for(self, key: str) -> int:
        if key in self.limits:
            return self.limits[key]
        # An unknown named class falls back to the global ceiling rather than a
        # fabricated per-name limit.
        return self.limits.get("global", DEFAULT_LIMITS["global"])

    def _fits(self, reqs: dict[str, int]) -> bool:
        for key, weight in reqs.items():
            if self._used.get(key, 0) + weight > self.limit_for(key):
                return False
        return True

    def try_acquire(self, reqs: dict[str, int]) -> bool:
        if not reqs:
            return True
        if not self._fits(reqs):
            return False
        for key, weight in reqs.items():
            self._used[key] = self._used.get(key, 0) + weight
        return True

    def release(self, reqs: dict[str, int]) -> None:
        if not reqs:
            return
        for key, weight in reqs.items():
            remaining = self._used.get(key, 0) - weight
            if remaining <= 0:
                self._used.pop(key, None)
            else:
                self._used[key] = remaining
        self._released.set()

    async def wait_release(self) -> None:
        """Block until some slot is released (or return immediately if idle)."""
        if not self._used:
            return
        self._released.clear()
        await self._released.wait()

    def snapshot(self) -> dict[str, Any]:
        return {
            "limits": dict(self.limits),
            "used": dict(self._used),
            "available": {k: max(0, self.limit_for(k) - self._used.get(k, 0)) for k in self.limits},
        }


class RateLimitExceeded(RuntimeError):
    """A token bucket has no tokens. Callers feed this into retry/backoff."""


@dataclass
class _Bucket:
    capacity: float
    rate_per_s: float
    tokens: float
    updated: float


class RateLimiter:
    """Token-bucket rate limiting keyed by provider/tool name.

    A bucket is configured with a sustained rate (requests/second) and a burst
    capacity. `acquire` waits for a token; `try_acquire` raises immediately, which
    is what the engine maps to a retryable RATE_LIMITED error.
    """

    def __init__(self, default_rate: float = 0.0, default_burst: float = 0.0) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._default_rate = max(0.0, default_rate)
        self._default_burst = max(0.0, default_burst)
        self._lock = asyncio.Lock()

    def configure(self, key: str, *, requests_per_second: float, burst: Optional[float] = None) -> None:
        rate = max(0.0, float(requests_per_second))
        cap = float(burst if burst is not None else max(1.0, rate))
        self._buckets[key] = _Bucket(capacity=cap, rate_per_s=rate, tokens=cap, updated=time.monotonic())

    def _bucket(self, key: str) -> Optional[_Bucket]:
        if key in self._buckets:
            return self._buckets[key]
        if self._default_rate <= 0:
            return None
        self._buckets[key] = _Bucket(
            capacity=max(1.0, self._default_burst or self._default_rate),
            rate_per_s=self._default_rate,
            tokens=max(1.0, self._default_burst or self._default_rate),
            updated=time.monotonic(),
        )
        return self._buckets[key]

    def _refill(self, bucket: _Bucket) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - bucket.updated)
        bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.rate_per_s)
        bucket.updated = now

    async def try_acquire(self, key: str, tokens: float = 1.0) -> bool:
        async with self._lock:
            bucket = self._bucket(key)
            if bucket is None:
                return True
            self._refill(bucket)
            if bucket.tokens >= tokens:
                bucket.tokens -= tokens
                return True
            return False

    async def acquire(self, key: str, tokens: float = 1.0) -> None:
        while True:
            async with self._lock:
                bucket = self._bucket(key)
                if bucket is None:
                    return
                self._refill(bucket)
                if bucket.tokens >= tokens:
                    bucket.tokens -= tokens
                    return
                needed = (tokens - bucket.tokens) / max(bucket.rate_per_s, 0.001)
            await asyncio.sleep(min(needed, 5.0))


__all__ = [
    "DEFAULT_LEASE_TTL_MS",
    "DEFAULT_LIMITS",
    "RateLimitExceeded",
    "RateLimiter",
    "ResourceManager",
    "limits_from_env",
]

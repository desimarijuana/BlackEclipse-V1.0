"""Per-identity rate limiting — abuse control for an internet-facing runtime.

A thread-safe token bucket keyed by tenant/user (falling back to client host).
This is a safety net, not the primary edge limiter (a reverse proxy should also
rate-limit); it protects the expensive decision/network endpoints from being
hammered by one tenant. Bounded memory: the oldest idle keys are evicted.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Optional


class RateLimiter:
    def __init__(self, *, rate_per_minute: float = 120.0, burst: Optional[float] = None,
                 max_keys: int = 10_000) -> None:
        self._rate = max(1.0, float(rate_per_minute)) / 60.0  # tokens per second
        self._burst = float(burst if burst is not None else rate_per_minute)
        self._max_keys = max(16, int(max_keys))
        self._lock = threading.RLock()
        self._buckets: "OrderedDict[str, list[float]]" = OrderedDict()

    def _bucket(self, key: str) -> list[float]:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = [self._burst, time.monotonic()]
            self._buckets[key] = bucket
            if len(self._buckets) > self._max_keys:
                self._buckets.popitem(last=False)
        else:
            self._buckets.move_to_end(key)
        return bucket

    def allow(self, key: str, cost: float = 1.0) -> bool:
        """Consume `cost` tokens for `key`; True when allowed."""
        with self._lock:
            bucket = self._bucket(key or "-")
            now = time.monotonic()
            elapsed = now - bucket[1]
            bucket[0] = min(self._burst, bucket[0] + elapsed * self._rate)
            bucket[1] = now
            if bucket[0] >= cost:
                bucket[0] -= cost
                return True
            return False

    def retry_after(self, key: str, cost: float = 1.0) -> float:
        """Seconds until `cost` tokens are available for `key`."""
        with self._lock:
            bucket = self._bucket(key or "-")
            if bucket[0] >= cost:
                return 0.0
            return max(0.0, (cost - bucket[0]) / self._rate)


_DEFAULT: Optional[RateLimiter] = None
_LOCK = threading.Lock()


def default_limiter() -> RateLimiter:
    global _DEFAULT
    with _LOCK:
        if _DEFAULT is None:
            import os

            rate = float(os.environ.get("BLACK_ECLIPSE_RATE_LIMIT_PER_MIN") or 240)
            _DEFAULT = RateLimiter(rate_per_minute=rate)
        return _DEFAULT


__all__ = ["RateLimiter", "default_limiter"]

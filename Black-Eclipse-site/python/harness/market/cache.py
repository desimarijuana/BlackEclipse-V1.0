"""Market Data cache — freshness-aware, in-process.

There is no Redis in Eclipse (single-node, zero-config); this reuses the
existing in-process cache idiom from `retrieval/cache.py`. It is deliberately
SEPARATED from the retrieval cache because market data has its own short TTLs
and an explicit-freshness contract the retrieval cache does not model.

Correctness rule (directive §26): caching must NEVER violate an explicit
freshness requirement. A cache entry records the DATA timestamp (when the value
is about) as well as the write time; `get` re-checks both the per-capability TTL
and the caller's freshness ceiling, and a stale entry is treated as a miss.

An in-flight map deduplicates concurrent identical requests so a burst does not
stampede a provider.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, TypeVar

from .config import get_config

T = TypeVar("T")

# Freshness class → the maximum age (seconds) a cached value may have before a
# request with that requirement refuses to use it.
_FRESHNESS_CEILING: dict[str, float] = {
    "realtime": 60.0,
    "intraday": 15 * 60.0,
    "daily": 24 * 3600.0,
    "slow": 7 * 24 * 3600.0,
    "any": float("inf"),
}


@dataclass
class _Entry:
    key: str
    value: Any
    cached_at: float
    data_timestamp: Optional[str]
    provider: str
    freshness: str

    def age(self, now: Optional[float] = None) -> float:
        return (now if now is not None else time.time()) - self.cached_at


def _parse_age_seconds(ts: Optional[str], now: Optional[float] = None) -> Optional[float]:
    if not ts:
        return None
    import datetime as _dt

    text = str(ts).strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    ref = _dt.datetime.now(_dt.timezone.utc) if now is None else _dt.datetime.fromtimestamp(
        now, _dt.timezone.utc
    )
    return (ref - parsed).total_seconds()


class MarketCache:
    """Per-capability TTL cache with an explicit-freshness guard."""

    def __init__(self, max_entries: int = 1024) -> None:
        self._entries: dict[str, _Entry] = {}
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self._max_entries = max_entries
        self.hits = 0
        self.misses = 0
        self.stale_skips = 0

    @staticmethod
    def key_for(capability: str, params: dict[str, Any]) -> str:
        parts = [capability]
        for name in sorted(params):
            if params[name] in (None, ""):
                continue
            parts.append(f"{name}={params[name]}")
        return "|".join(parts)

    def get(
        self,
        capability: str,
        params: dict[str, Any],
        *,
        freshness: str = "any",
    ) -> Optional[Any]:
        if not get_config().cache_enabled:
            return None
        key = self.key_for(capability, params)
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        now = time.time()
        ttl = get_config().ttl(capability)
        if entry.age(now) >= ttl:
            self.misses += 1
            return None
        # Explicit freshness: if the DATA timestamp is older than the ceiling, a
        # stale entry is a miss even when the write TTL has not elapsed.
        ceiling = _FRESHNESS_CEILING.get(freshness, float("inf"))
        data_age = _parse_age_seconds(entry.data_timestamp, now)
        if data_age is not None and data_age > ceiling:
            self.stale_skips += 1
            self.misses += 1
            return None
        # A realtime ask must never take a cached value older than the realtime
        # ceiling by WRITE time either.
        if freshness == "realtime" and entry.age(now) > ceiling:
            self.stale_skips += 1
            self.misses += 1
            return None
        self.hits += 1
        return entry.value

    def put(
        self,
        capability: str,
        params: dict[str, Any],
        value: Any,
        *,
        data_timestamp: Optional[str] = None,
        provider: str = "unknown",
        freshness: str = "any",
    ) -> None:
        if not get_config().cache_enabled:
            return
        if value is None:
            return
        # Never cache an empty/invalid result as if it were data.
        status = getattr(value, "meta", None)
        if status is not None and getattr(status, "data_status", "OK") in ("UNAVAILABLE", "CONFLICTING"):
            return
        key = self.key_for(capability, params)
        self._entries[key] = _Entry(
            key=key,
            value=value,
            cached_at=time.time(),
            data_timestamp=data_timestamp,
            provider=provider,
            freshness=freshness,
        )
        if len(self._entries) > self._max_entries:
            oldest = min(self._entries.values(), key=lambda e: e.cached_at)
            self._entries.pop(oldest.key, None)

    async def get_or_fetch(
        self,
        capability: str,
        params: dict[str, Any],
        fetch: Callable[[], Awaitable[Any]],
        *,
        freshness: str = "any",
    ) -> tuple[Any, bool]:
        """Return (value, cache_hit). Deduplicates identical in-flight fetches."""
        cached = self.get(capability, params, freshness=freshness)
        if cached is not None:
            return cached, True
        key = self.key_for(capability, params)
        existing = self._inflight.get(key)
        if existing is not None:
            return await asyncio.shield(existing), False
        loop = asyncio.get_event_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._inflight[key] = future
        try:
            value = await fetch()
            if not future.done():
                future.set_result(value)
            return value, False
        except Exception as exc:  # noqa: BLE001
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)

    def stats(self) -> dict[str, Any]:
        return {
            "entries": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
            "staleSkips": self.stale_skips,
            "inflight": len(self._inflight),
        }

    def clear(self) -> None:
        self._entries.clear()


__all__ = ["MarketCache"]

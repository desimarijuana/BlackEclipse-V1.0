"""Cache layer (Milestone 2G).

A small in-process cache with per-data-type freshness policy. It is deliberately
NOT a new database: caching is operational, short-lived state, and `agent-memory.db`
stays the only harness-owned store.

Every cached result retains `cachedAt`, `originalRetrievedAt`, `source`,
`dataTimestamp` and `freshness`, so a stale entry can always be labeled stale
instead of being presented as current.

Concurrency safety: an in-flight map lets N concurrent callers for the same key
share ONE retrieval (deduplication) rather than stampeding the provider.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .contract import FinancialRetrievalRequest, FinancialRetrievalResult
from .policies import ttl_seconds


@dataclass
class CacheEntry:
    key: str
    result: FinancialRetrievalResult
    cachedAt: float
    originalRetrievedAt: str
    source: str
    dataTimestamp: Optional[str]
    freshness: str

    def age_seconds(self, now: Optional[float] = None) -> float:
        return (now if now is not None else time.time()) - self.cachedAt

    def is_fresh(self, ttl: int, now: Optional[float] = None) -> bool:
        return self.age_seconds(now) < ttl


class RetrievalCache:
    """In-process, TTL'd, with in-flight deduplication."""

    def __init__(self, max_entries: int = 512) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._inflight: dict[str, asyncio.Future[FinancialRetrievalResult]] = {}
        self._max_entries = max_entries
        # Basic hit/miss instrumentation (exposed for the performance report).
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key_for(request: FinancialRetrievalRequest) -> str:
        return "|".join(
            [
                request.dataType,
                (request.instrument or "").upper(),
                (request.market or "").upper(),
                request.quantity or "",
                (request.query or request.objective or "").strip().lower()[:120],
            ]
        )

    def get(self, request: FinancialRetrievalRequest) -> Optional[CacheEntry]:
        key = self.key_for(request)
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        return entry

    def get_fresh(self, request: FinancialRetrievalRequest) -> Optional[CacheEntry]:
        entry = self.get(request)
        if entry is None:
            return None
        if entry.is_fresh(ttl_seconds(request.dataType)):
            self.hits += 1
            return entry
        return None

    def put(
        self,
        request: FinancialRetrievalRequest,
        result: FinancialRetrievalResult,
        *,
        source: str,
        data_timestamp: Optional[str] = None,
    ) -> None:
        if not result.data and not result.evidence:
            return  # never cache an empty answer as if it were data
        key = self.key_for(request)
        self._entries[key] = CacheEntry(
            key=key,
            result=result.model_copy(deep=True),
            cachedAt=time.time(),
            originalRetrievedAt=result.retrievedAt,
            source=source,
            dataTimestamp=data_timestamp,
            freshness=result.freshness,
        )
        if len(self._entries) > self._max_entries:
            oldest = min(self._entries.values(), key=lambda e: e.cachedAt)
            self._entries.pop(oldest.key, None)

    async def get_or_retrieve(
        self,
        request: FinancialRetrievalRequest,
        retrieve: Callable[[], Awaitable[FinancialRetrievalResult]],
    ) -> tuple[FinancialRetrievalResult, bool, bool]:
        """Return (result, cache_hit, deduplicated).

        - fresh cache → return immediately (hit=True)
        - an identical retrieval already in flight → await it (deduplicated=True)
        - otherwise run `retrieve`, cache and return it
        """
        fresh = self.get_fresh(request)
        if fresh is not None:
            return fresh.result.model_copy(deep=True), True, False

        key = self.key_for(request)
        existing = self._inflight.get(key)
        if existing is not None:
            self.hits += 1
            return await asyncio.shield(existing), False, True

        loop = asyncio.get_event_loop()
        future: asyncio.Future[FinancialRetrievalResult] = loop.create_future()
        self._inflight[key] = future
        try:
            result = await retrieve()
            if not future.done():
                future.set_result(result)
            return result, False, False
        except Exception as exc:  # noqa: BLE001
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)

    def stats(self) -> dict[str, Any]:
        return {"entries": len(self._entries), "hits": self.hits, "misses": self.misses, "inflight": len(self._inflight)}

    def clear(self) -> None:
        self._entries.clear()


__all__ = ["RetrievalCache", "CacheEntry"]

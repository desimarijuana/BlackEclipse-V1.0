"""Computation-identity cache for the statistical engine.

A cached value is only reused when the *complete* computation identity matches:
tool + tool version + validated parameters + a content hash of the input data.
Any change to inputs or parameters produces a different key, so a stale value can
never be served as a current result. Also caches `evaluate` results of a formula
under the same identity scheme.

The cache is process-local and bounded (LRU); it adds no new infrastructure.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any, Callable, Optional

import numpy as np


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def hash_inputs(value: Any) -> str:
    """A stable content hash of a JSON-ish value (arrays included)."""
    try:
        if isinstance(value, np.ndarray):
            payload = np.ascontiguousarray(value, dtype=float).tobytes()
            return _hash_bytes(payload)
        encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
        return _hash_bytes(encoded)
    except (TypeError, ValueError):
        return _hash_bytes(str(value).encode())


def computation_key(tool: str, tool_version: str, parameters: dict[str, Any], inputs: Any) -> str:
    ident = {
        "tool": tool,
        "version": tool_version,
        "parameters": parameters,
        "inputs": hash_inputs(inputs),
    }
    return _hash_bytes(json.dumps(ident, sort_keys=True, default=str).encode())


class StatsCache:
    def __init__(self, *, max_entries: int = 256) -> None:
        self._store: "OrderedDict[str, Any]" = OrderedDict()
        self._max = max(1, max_entries)
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        if key in self._store:
            self._store.move_to_end(key)
            self.hits += 1
            return self._store[key]
        self.misses += 1
        return None

    def put(self, key: str, value: Any) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()
        self.hits = self.misses = 0

    def stats(self) -> dict[str, int]:
        total = self.hits + self.misses
        return {
            "entries": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hitRate": round(self.hits / total, 4) if total else 0.0,
        }

    def get_or_compute(
        self, key: str, factory: Callable[[], Any], *, enabled: bool = True
    ) -> tuple[Any, bool]:
        """Return (value, cache_hit). Never caches exceptions."""
        if not enabled:
            return factory(), False
        cached = self.get(key)
        if cached is not None:
            return cached, True
        value = factory()
        self.put(key, value)
        return value, False


_cache: Optional[StatsCache] = None


def get_cache() -> StatsCache:
    global _cache
    if _cache is None:
        _cache = StatsCache()
    return _cache


def reset_cache() -> None:
    """Tests only."""
    global _cache
    _cache = None


__all__ = ["StatsCache", "computation_key", "hash_inputs", "get_cache", "reset_cache"]

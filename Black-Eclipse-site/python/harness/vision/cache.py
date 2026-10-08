"""Vision result cache.

There is no Redis in Eclipse (single-node, zero-config — see the existing
`retrieval/cache.py` and the TS investor-eye cache), so the vision cache is a
bounded, in-process, TTL store, consistent with the rest of the runtime. It is
keyed so a result is reused ONLY when the image, the model, the routing target,
the question, the mode, the preprocessing parameters and the result schema
version are all identical — so a model/contract change can never serve a stale
answer.

Cache hits and misses are counted and emitted as telemetry by the orchestrator;
this module only owns the store + the key.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Optional

from .config import VisionConfig, vision_config
from .contracts import VisionInput

#: Bump when the shape/meaning of a `VisionResult` changes. A different version
#: yields a different key, so old entries can never be mistaken for new results.
SCHEMA_VERSION = "vision-result-v1"


def cache_key(
    *,
    asset_id: str,
    settings: Any,
    input: VisionInput,
    backend: str = "",
) -> str:
    """A deterministic key over everything that changes the RESULT identity."""
    provider = getattr(settings, "provider", None) if settings is not None else None
    model = getattr(settings, "model", None) if settings is not None else None
    payload = {
        "asset": asset_id,
        "provider": provider,
        "model": model,
        "backend": backend,
        "mode": input.mode,
        "question": input.question,
        "options": input.cache_options(),
        "schema": SCHEMA_VERSION,
    }
    import json  # noqa: PLC0415

    blob = json.dumps(payload, sort_keys=True, default=str)
    return "vcache_" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


@dataclass
class _Entry:
    value: dict[str, Any]
    expires_at: float


class VisionCache:
    """A bounded in-process TTL cache for normalized vision results."""

    def __init__(self, *, cfg: Optional[VisionConfig] = None) -> None:
        self._cfg = cfg or vision_config()
        self._entries: dict[str, _Entry] = {}
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key: str) -> Optional[dict[str, Any]]:
        if not self._cfg.cache_enabled:
            return None
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        if entry.expires_at and entry.expires_at < time.monotonic():
            self._entries.pop(key, None)
            self.misses += 1
            return None
        # Refresh recency for the LRU eviction below.
        self._entries[key] = entry
        self.hits += 1
        return entry.value

    def put(self, key: str, value: dict[str, Any]) -> None:
        if not self._cfg.cache_enabled:
            return
        ttl = self._cfg.cache_ttl_seconds
        expires = (time.monotonic() + ttl) if ttl > 0 else 0.0
        self._entries[key] = _Entry(value=value, expires_at=expires)
        self._evict()

    def _evict(self) -> None:
        limit = self._cfg.cache_max_entries
        if len(self._entries) <= limit:
            return
        # Insertion-ordered dict = oldest-first eviction (bounded memory).
        overflow = len(self._entries) - limit
        for key in list(self._entries.keys())[:overflow]:
            self._entries.pop(key, None)
            self.evictions += 1

    def invalidate(self, key: str) -> bool:
        return self._entries.pop(key, None) is not None

    def clear(self) -> None:
        self._entries.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self._cfg.cache_enabled,
            "entries": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "schemaVersion": SCHEMA_VERSION,
        }


_CACHE: Optional[VisionCache] = None


def get_cache() -> VisionCache:
    global _CACHE
    if _CACHE is None:
        _CACHE = VisionCache()
    return _CACHE


def reset_cache() -> None:
    global _CACHE
    _CACHE = None


__all__ = ["VisionCache", "cache_key", "get_cache", "reset_cache", "SCHEMA_VERSION"]

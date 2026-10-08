"""Cross-execution result cache and in-flight deduplication.

Both are keyed by `fingerprint :: scope`, where the scope is derived from the
invoking runtime (authorized tool set, user/tenant, and — for an agent node — the
resolved provider/model). That is what makes sharing SAFE: two nodes only share
when they would run under equivalent authorization and configuration, so a cached
or shared result can never cross a privilege or tenancy boundary.

Freshness is explicit: a cache entry only exists when a node declares itself
`cacheable` with a positive TTL, so financial data is never silently served stale.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

from .models import ExecutionNode, NodeKind


def compute_dedup_key(node: ExecutionNode) -> str:
    """A stable fingerprint of a node's work, for dedup and caching."""
    spec = node.input or {}
    payload = {
        "kind": node.kind.value,
        "tool": spec.get("tool") or spec.get("name"),
        "function": spec.get("function"),
        "query": spec.get("query") or spec.get("instruction"),
        "args": spec.get("args"),
        "context": spec.get("context"),
    }
    try:
        encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        encoded = str(payload)
    return "dd_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def scope_key(runtime: Any, node: ExecutionNode) -> str:
    """A stable authorization/configuration scope for a node's work."""
    allowed = getattr(runtime, "allowed", None)
    parts = [str(getattr(runtime, "user_id", None) or "")]
    parts.append(",".join(sorted(allowed)) if allowed is not None else "*")
    if node.kind is NodeKind.AGENT:
        settings = getattr(runtime, "model_settings", None)
        provider = getattr(settings, "provider", None)
        model = getattr(settings, "model", None)
        parts.append(f"{provider or '?'}:{model or '?'}")
    return "|".join(parts)


def fingerprint(node: ExecutionNode, runtime: Any) -> Optional[str]:
    if not node.dedup_key:
        return None
    return f"{node.dedup_key}::{scope_key(runtime, node)}"


class SharedResultCache:
    """A process-wide TTL cache. Only fresh entries are ever returned."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[Optional[float], Any]] = {}

    def get(self, key: Optional[str]) -> Any:
        if not key:
            return MISS
        entry = self._entries.get(key)
        if entry is None:
            return MISS
        expires_at, value = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            self._entries.pop(key, None)
            return MISS
        return value

    def put(self, key: Optional[str], value: Any, ttl_ms: int) -> None:
        if not key or ttl_ms <= 0:
            return
        self._entries[key] = (time.monotonic() + ttl_ms / 1000, value)

    def invalidate(self, key: Optional[str]) -> None:
        if key:
            self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()


class _Missing:
    pass


MISS = _Missing()


def is_miss(value: Any) -> bool:
    return value is MISS


__all__ = [
    "MISS",
    "SharedResultCache",
    "compute_dedup_key",
    "fingerprint",
    "is_miss",
    "scope_key",
]

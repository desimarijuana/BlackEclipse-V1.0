"""Bounded, content-free memory-provider diagnostics.

Never returns raw provider content or secrets — only provider names, declared
capabilities, health state, latency, freshness and counts. This is the data
behind the Provider UI's health panel and the `/memory-providers/*` API.

Phase 7 additions: a capability summary, a privacy/data-location warning, a
freshness stamp per provider, and a bounded, non-destructive `provider_test`.
"""

from __future__ import annotations

import time
from typing import Any

from .registry import MemoryProviderRegistry

# A provider's declared data location is NOT inferrable from the process; these
# are conservative defaults chosen by provider kind so the UI can always show an
# honest warning rather than implying data stays local.
_DATA_LOCATION = {
    "native": "local (eclipse-memory.db on this machine)",
    "mcp": "external (via the connected MCP server; may leave this machine)",
}

_PRIVACY_NOTE = (
    "Native memory stays in eclipse-memory.db on this machine. External "
    "providers may store or transmit data according to their own policy; "
    "their results are UNVERIFIED CONTEXT, are never promoted to native "
    "memory, and never answer a current financial question."
)


def _capability_summary(capabilities: dict[str, Any], is_native: bool) -> str:
    label = "native" if is_native else "external"
    parts = [name for name in ("search", "write", "delete", "export") if capabilities.get(name)]
    if not parts:
        parts = ["none"]
    if capabilities.get("readOnly"):
        parts.append("read-only")
    return f"{label}: {', '.join(parts)}"


async def provider_diagnostics(registry: MemoryProviderRegistry) -> dict[str, Any]:
    """Collect bounded diagnostics for every registered provider."""
    providers = await registry.health()
    now = time.time()
    for provider in providers:
        is_native = bool(provider.get("isNative"))
        provider["capabilitySummary"] = _capability_summary(provider.get("capabilities", {}), is_native)
        provider["dataLocation"] = (
            _DATA_LOCATION["native"] if is_native else _DATA_LOCATION["mcp"]
        )
        provider["verifiedByEclipse"] = is_native
        # Freshness: health was just probed, so the check time is now. A provider
        # that failed reports state honestly; no stale cached "ok".
        provider["checkedAt"] = now
    native_count = sum(1 for p in providers if p.get("isNative"))
    external = [p for p in providers if not p.get("isNative")]
    available = [p["name"] for p in providers if p.get("health", {}).get("ok")]
    failed = [p["name"] for p in providers if not p.get("health", {}).get("ok")]
    return {
        "externalEnabled": registry.external_enabled,
        "providerCount": len(providers),
        "nativeCount": native_count,
        "externalCount": len(external),
        "available": available,
        "failed": failed,
        "providers": providers,
        "privacyNote": _PRIVACY_NOTE,
        "note": (
            "Discovery does not activate a provider. External results are "
            "unverified context and are never promoted to native memory."
        ),
    }


async def provider_test(registry: MemoryProviderRegistry, name: str) -> dict[str, Any]:
    """A bounded, non-destructive test of ONE provider.

    Probes health and a capped search. Never writes, deletes or exports. The
    result carries no raw provider content beyond a bounded count.
    """
    provider = registry.get(name)
    if provider is None:
        return {"ok": False, "state": "unknown", "detail": f"provider {name!r} is not registered"}
    try:
        health = await provider.health()
    except Exception as exc:  # noqa: BLE001 - a failing probe is a structured result
        return {"ok": False, "state": "unavailable", "detail": str(exc)}
    started = time.monotonic()
    count = 0
    search_error = None
    caps = provider.capabilities()
    if caps.search:
        from .protocol import MemorySearchRequest  # noqa: PLC0415

        try:
            response = await provider.search(MemorySearchRequest(query="test", limit=1))
            count = len(response.results)
            if response.detail:
                search_error = response.detail
        except Exception as exc:  # noqa: BLE001
            search_error = str(exc)
    return {
        "ok": bool(health.ok),
        "state": health.state,
        "detail": health.detail or search_error,
        "latencyMs": health.latency_ms if health.latency_ms is not None else int((time.monotonic() - started) * 1000),
        "searchProbed": bool(caps.search),
        "probeResultCount": count,
        "externalVerified": False,
    }


__all__ = ["provider_diagnostics", "provider_test"]

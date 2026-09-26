"""Bounded, content-free memory-provider diagnostics.

Never returns raw provider content or secrets — only provider names, declared
capabilities, health state, latency and counts. This is the data behind the
Provider UI's health panel and the `/memory-providers/*` API.
"""

from __future__ import annotations

from typing import Any

from .registry import MemoryProviderRegistry


async def provider_diagnostics(registry: MemoryProviderRegistry) -> dict[str, Any]:
    """Collect bounded diagnostics for every registered provider."""
    providers = await registry.health()
    native_count = sum(1 for p in providers if p.get("isNative"))
    external = [p for p in providers if not p.get("isNative")]
    available = [p["name"] for p in providers if p.get("health", {}).get("ok")]
    return {
        "externalEnabled": registry.external_enabled,
        "providerCount": len(providers),
        "nativeCount": native_count,
        "externalCount": len(external),
        "available": available,
        "providers": providers,
        "note": (
            "Discovery does not activate a provider. External results are "
            "unverified context and are never promoted to native memory."
        ),
    }


__all__ = ["provider_diagnostics"]

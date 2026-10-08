"""Market Data Layer HTTP routes (operator-gated introspection + stream control).

Thin adapters over the SAME market subsystem the agent tools use. The routes
reach shared runtime state only through `harness.deps.service`, so the UI and the
agent can never disagree, and a second gateway/stream manager is never built.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["market"])


def _gateway() -> Any:
    return getattr(service, "market_gateway", None)


@router.get("/market/providers")
async def market_providers(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Every market provider: capabilities, credential presence (never the
    secret), implemented/degraded state, rate shape — plus live health."""
    gateway = _gateway()
    if gateway is None:
        return {"available": False, "reason": "the market data layer is unavailable"}
    router_obj = gateway._router_ref()  # noqa: SLF001 - introspection seam
    described = router_obj.describe() if router_obj else {"providers": [], "health": []}
    return {"available": True, **described}


@router.get("/market/health")
async def market_health(_: bool = Depends(require_operator)) -> dict[str, Any]:
    gateway = _gateway()
    if gateway is None:
        return {"available": False}
    store = getattr(service, "market_store", None)
    return {
        "available": True,
        "cache": gateway.cache.stats(),
        "metrics": dict(gateway.metrics),
        "config": {
            "maxProviders": gateway.config.max_providers,
            "requestTimeoutMs": gateway.config.request_timeout_ms,
            "maxRetries": gateway.config.max_retries,
            "cacheEnabled": gateway.config.cache_enabled,
            "streamingEnabled": gateway.config.stream_enabled,
        },
        "persistedHealth": store.provider_health() if store is not None else [],
    }


@router.get("/market/quality")
async def market_quality(limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = getattr(service, "market_store", None)
    if store is None:
        return {"available": False}
    return {"available": True, "events": store.recent_quality(limit)}


@router.get("/market/stream")
async def market_stream_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = getattr(service, "market_stream", None)
    if manager is None:
        return {"available": False, "reason": "streaming is not available"}
    return {"available": True, **manager.snapshot()}


class StreamSubscribeBody(BaseModel):
    symbols: list[str] = Field(min_length=1)
    eventTypes: list[str] = Field(default_factory=lambda: ["trade"])


@router.post("/market/stream/subscribe")
async def market_stream_subscribe(
    body: StreamSubscribeBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    manager = getattr(service, "market_stream", None)
    if manager is None:
        return {"available": False, "reason": "streaming is not available"}
    subscription_id = await manager.subscribe(body.symbols, tuple(body.eventTypes))
    return {"available": True, "subscriptionId": subscription_id, "symbols": body.symbols}


@router.post("/market/stream/unsubscribe")
async def market_stream_unsubscribe(
    subscription_id: str, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    manager = getattr(service, "market_stream", None)
    if manager is None:
        return {"available": False, "reason": "streaming is not available"}
    return {"removed": await manager.unsubscribe(subscription_id)}


__all__ = ["router"]

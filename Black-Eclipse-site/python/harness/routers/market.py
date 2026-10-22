"""Market Data Layer HTTP routes (operator-gated introspection + stream control).

Thin adapters over the SAME market subsystem the agent tools use. The routes
reach shared runtime state only through `harness.deps.service`, so the UI and the
agent can never disagree, and a second gateway/stream manager is never built.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["market"])


def _gateway() -> Any:
    return getattr(service, "market_gateway", None)


class BackfillBody(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    interval: str = "1d"
    start: Optional[str] = None
    end: Optional[str] = None
    provider: Optional[str] = None
    adjusted: bool = True
    maxSymbols: int = 25


@router.post("/market/history/backfill")
async def market_history_backfill(body: BackfillBody,
                                  _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Bundle history into the local vault: fetch the window once and keep it."""
    from ..market.tools import backfill_history

    class _Ctx:
        """The slice of a run context the backfill needs."""

        def __init__(self) -> None:
            self.market_gateway = getattr(service, "market_gateway", None)
            self.market_series_store = getattr(service, "market_series_store", None)

    if not body.symbols:
        raise HTTPException(status_code=422, detail="provide the symbols to bundle")
    text, payload = await backfill_history({
        "symbols": body.symbols, "interval": body.interval, "start": body.start,
        "end": body.end, "provider": body.provider, "adjusted": body.adjusted,
        "maxSymbols": body.maxSymbols,
    }, _Ctx())
    return {"status": payload.get("status", "ok"), "summary": text, **payload}


@router.get("/market/history")
async def market_history(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """The history this machine holds.

    The durable cache is the local copy of the market Eclipse has already paid
    for: what it covers, how fresh it is, and where it came from. It is the
    honest answer to "what data do I actually have?".
    """
    store = getattr(service, "market_series_store", None)
    if store is None:
        return {"available": False,
                "reason": "the durable history cache is unavailable in this runtime"}
    try:
        series = store.list_series(limit=200)
    except Exception as exc:  # noqa: BLE001 - a read failure is reported
        return {"available": False, "reason": str(exc)[:200]}
    return {"available": True, "series": series, "count": len(series)}


@router.get("/market/history/{symbol}")
async def market_history_coverage(symbol: str, interval: str = "1d",
                                  _: bool = Depends(require_operator)) -> dict[str, Any]:
    """What the durable cache holds for one instrument."""
    store = getattr(service, "market_series_store", None)
    if store is None:
        return {"available": False,
                "reason": "the durable history cache is unavailable in this runtime"}
    try:
        coverage = store.coverage(symbol, interval)
    except Exception as exc:  # noqa: BLE001 - a read failure is reported
        return {"available": False, "reason": str(exc)[:200]}
    return {"available": True, "coverage": coverage}


@router.get("/market/history/{symbol}/bars")
async def market_history_bars(symbol: str, interval: str = "1d", limit: int = 5_000,
                              start: Optional[str] = None, end: Optional[str] = None,
                              _: bool = Depends(require_operator)) -> dict[str, Any]:
    """The cached bars for one instrument.

    Served from the local copy - no provider is called, so this works offline.
    """
    store = getattr(service, "market_series_store", None)
    if store is None:
        return {"available": False,
                "reason": "the durable history cache is unavailable in this runtime"}
    try:
        bars = store.get_bars(symbol, interval, start=start, end=end,
                              limit=max(1, min(int(limit), 100_000)))
    except Exception as exc:  # noqa: BLE001 - a read failure is reported
        return {"available": False, "reason": str(exc)[:200]}
    return {"available": True, "symbol": symbol.upper(), "interval": interval,
            "bars": bars, "count": len(bars),
            "source": "durable-cache"}


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
        "providerMetrics": gateway.provider_metrics(),
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
    from ..market.streaming import all_stream_managers, default_stream_manager

    managers = all_stream_managers() or {"binance": default_stream_manager()}
    snapshot = {name: mgr.snapshot() for name, mgr in managers.items()}
    if not snapshot:
        return {"available": False, "reason": "streaming is not available"}
    # The first manager's fields remain top-level for backward compatibility.
    primary = next(iter(snapshot.values()))
    return {"available": True, **primary, "managers": snapshot}


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

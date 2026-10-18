"""The video layer's market-data adapter (the EXISTING Market Data Gateway).

Phase 5's rule: bound figures resolve through the same gateway the agent tools
use — never a second provider, HTTP client or cache. The service supplies a
bridge (the read-only JDdS front door); the gateway is built lazily on first
use and shares the process-wide market cache and provider router.

The provider returns raw normalized numbers plus provenance only; display
formatting lives in `video/data.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from .models import VideoError

_INTERVAL_SECONDS = {"1h": 3600, "4h": 4 * 3600, "1d": 24 * 3600}


class MarketGatewayProvider:
    """A `video.data` provider over `MarketDataGateway` records."""

    def __init__(self, gateway_factory: Callable[[], Any]) -> None:
        self._gateway_factory = gateway_factory
        self._gateway: Optional[Any] = None

    def _gateway_instance(self) -> Any:
        if self._gateway is None:
            self._gateway = self._gateway_factory()
        return self._gateway

    @staticmethod
    def _meta(record: Any) -> dict[str, Any]:
        meta = getattr(record, "meta", None)
        data_status = str(getattr(meta, "data_status", "OK") or "OK")
        data_timestamp = (
            getattr(meta, "event_time", None)
            or getattr(record, "timestamp", None)
        )
        conflict = getattr(record, "conflict", None)
        warnings = list(getattr(meta, "warnings", []) or [])
        if conflict:
            warnings.append(str(conflict))
        return {
            "provider": getattr(meta, "provider", None),
            "source": getattr(meta, "source", None),
            "retrievedAt": getattr(meta, "retrieved_at", None),
            "dataTimestamp": data_timestamp,
            "freshness": str(getattr(meta, "freshness", "any")),
            "dataStatus": data_status,
            "stale": data_status == "STALE",
            "quality": str(getattr(meta, "quality", "unknown")),
            "warnings": warnings,
            "currency": getattr(meta, "currency", None),
        }

    @staticmethod
    def _raise_market_error(symbol: str, error: Any) -> None:
        message = str(getattr(error, "message", error))
        code = str(getattr(error, "code", "MARKET_ERROR"))
        raise VideoError("DATA_UNAVAILABLE", f"{symbol}: market data unavailable [{code}] {message}")

    async def quote(self, symbol: str, market: Optional[str] = None) -> dict[str, Any]:
        from ..market.errors import MarketError  # noqa: PLC0415

        result = await self._gateway_instance().get_quote(symbol, market)
        if isinstance(result, MarketError):
            self._raise_market_error(symbol, result)
        return {
            "price": getattr(result, "price", None),
            "changePct": getattr(result, "change_pct", None),
            "volume": getattr(result, "volume", None),
            "currency": getattr(getattr(result, "meta", None), "currency", None),
            "meta": self._meta(result),
        }

    async def candles(
        self, symbol: str, market: Optional[str], interval: str, count: int
    ) -> dict[str, Any]:
        from ..market.errors import MarketError  # noqa: PLC0415

        seconds = _INTERVAL_SECONDS.get(interval, 24 * 3600)
        lookback = timedelta(seconds=seconds * (count * 1.75 + 5))
        start = (datetime.now(timezone.utc) - lookback).isoformat()
        result = await self._gateway_instance().get_ohlcv(
            symbol, market, start=start, interval=interval, freshness="slow"
        )
        if isinstance(result, MarketError):
            self._raise_market_error(symbol, result)
        bars: list[dict[str, Any]] = []
        for bar in getattr(result, "bars", []) or []:
            close = getattr(bar, "close", None)
            if close is None:
                continue
            bars.append({
                "t": getattr(bar, "timestamp", None),
                "o": getattr(bar, "open", None),
                "h": getattr(bar, "high", None),
                "l": getattr(bar, "low", None),
                "c": close,
            })
        meta = self._meta(result)
        if bars:
            meta["dataTimestamp"] = bars[-1].get("t")
        return {"bars": bars, "meta": meta}


__all__ = ["MarketGatewayProvider"]

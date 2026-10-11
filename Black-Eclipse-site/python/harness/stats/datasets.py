"""Market-data adapter for the statistical engine.

The statistical engine is pure computation: it never calls a provider itself.
This adapter asks the ONE Market Data Gateway (which routes, paces, normalizes
and quality-checks) for a normalized historical series per symbol/timeframe and
returns plain timestamp-aligned arrays plus provenance. An unavailable symbol or
timeframe is an honest, typed error — never a fabricated series.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import INSUFFICIENT_DATA, INVALID_INPUT, StatsError

_FIELDS = ("close", "open", "high", "low", "volume", "vwap")


def _extract(payload: Any, field: str) -> tuple[list[str], list[Optional[float]]]:
    bars = getattr(payload, "bars", None)
    if bars is None and isinstance(payload, dict):
        bars = payload.get("bars")
    if not bars:
        return [], []
    timestamps: list[str] = []
    values: list[Optional[float]] = []
    for bar in bars:
        ts = getattr(bar, "timestamp", None) if not isinstance(bar, dict) else bar.get("timestamp")
        val = getattr(bar, field, None) if not isinstance(bar, dict) else bar.get(field)
        timestamps.append(str(ts) if ts is not None else "")
        values.append(float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None)
    return timestamps, values


def _provenance(payload: Any) -> dict[str, Any]:
    def g(key: str) -> Any:
        return getattr(payload, key, None) if not isinstance(payload, dict) else payload.get(key)

    return {
        "provider": g("provider"),
        "source": g("source"),
        "providerSymbol": g("provider_symbol") or g("providerSymbol"),
        "interval": g("interval"),
        "adjusted": g("adjusted"),
        "asOf": g("timestamp") or g("as_of") or g("asOf"),
        "quality": g("quality") if not hasattr(g("quality"), "to_dict") else g("quality").to_dict(),
        "aggregation": g("aggregation"),
        "duplicateTimestamps": g("duplicate_timestamps") or g("duplicateTimestamps"),
    }


async def resolve_series(
    gateway: Any,
    symbol: str,
    *,
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    field: str = "close",
    adjusted: bool = True,
) -> dict[str, Any]:
    """Fetch one normalized series. Raises `StatsError` if it cannot be obtained."""
    if field not in _FIELDS:
        raise StatsError(INVALID_INPUT, f"unknown field {field!r}; choose one of {_FIELDS}")
    if gateway is None:
        raise StatsError("DEPENDENCY_MISSING", "the market data gateway is unavailable in this runtime", 503)
    from ..market.errors import MarketError  # noqa: PLC0415

    try:
        result = await gateway.get_historical_prices(
            symbol, None, start=start, end=end, interval=interval, adjusted=adjusted
        )
    except MarketError as exc:
        raise StatsError(INVALID_INPUT, f"could not load {symbol}@{interval}: {exc.message}", 422) from exc
    if isinstance(result, MarketError):
        raise StatsError(INVALID_INPUT, f"could not load {symbol}@{interval}: {result.message}", 422)
    timestamps, values = _extract(result, field)
    if not values:
        raise StatsError(INSUFFICIENT_DATA, f"{symbol}@{interval} returned no {field} values", 422)
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "field": field,
        "timestamps": timestamps,
        "values": values,
        "provenance": _provenance(result),
    }


async def resolve_frame(
    gateway: Any,
    symbols: list[str],
    *,
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    field: str = "close",
    adjusted: bool = True,
) -> dict[str, Any]:
    """Fetch several series and align them to the intersection of timestamps.

    Returns a rectangular frame: `timestamps` (shared) and `values` (one row per
    symbol). Symbols whose series do not overlap are reported, not dropped
    silently.
    """
    if not symbols:
        raise StatsError(INVALID_INPUT, "symbols must be a non-empty list")
    series = []
    for symbol in symbols:
        series.append(await resolve_series(
            gateway, symbol, interval=interval, start=start, end=end, field=field, adjusted=adjusted
        ))
    common: Optional[set[str]] = None
    for s in series:
        stamps = {t for t, v in zip(s["timestamps"], s["values"]) if v is not None}
        common = stamps if common is None else (common & stamps)
    common = common or set()
    ordered = [t for t in series[0]["timestamps"] if t in common]
    if not ordered:
        raise StatsError(INSUFFICIENT_DATA, "the requested symbols share no aligned observations", 422)
    index = {s["symbol"]: {t: v for t, v in zip(s["timestamps"], s["values"])} for s in series}
    rows = [[index[s["symbol"]].get(t) for t in ordered] for s in series]
    return {
        "symbols": [s["symbol"] for s in series],
        "interval": interval,
        "field": field,
        "timestamps": ordered,
        "values": rows,
        "provenance": [s["provenance"] for s in series],
    }


__all__ = ["resolve_series", "resolve_frame"]

"""Resolve a backtest dataset from the Market Data Gateway or a declared source.

The engine never calls a provider: this adapter asks the gateway (which routes,
paces, normalizes and quality-checks) for a normalized `HistoricalPriceSeries`
per symbol/timeframe and packs the results into the engine's `MarketDataset`.

A caller may instead NAME an operator-declared dataset (Settings -> Data
Sources, `custom_dataset_records`). That path is exclusive: it never mixes with
the market providers and there is no fallback, so a result is always built on
the data the caller actually asked for. See `custom_source.py`.

An unavailable symbol/timeframe is an honest, typed error — never a fabricated
series. Confirmation timeframes that the providers cannot supply are simply
absent (the engine then warns and disables the indicators that needed them).
"""

from __future__ import annotations

from typing import Any, Optional

from ..market.errors import MarketError
from .custom_source import fetch_custom_series, normalize_data_source
from .data import BarSeries, MarketDataset, series_from_historical, series_from_rows
from .errors import InvalidSymbol, MissingData, UnsupportedTimeframe
from .strategy import StrategySpec


async def fetch_series(
    gateway,
    symbol: str,
    *,
    interval: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    adjusted: bool = True,
    data_source: Optional[dict[str, Any]] = None,
    bridge: Any = None,
) -> BarSeries:
    # A named operator dataset is the ONLY source for this series. No gateway
    # call, no cache lookup, no fallback: the caller asked for their own data.
    if data_source:
        source = normalize_data_source(data_source)
        return await fetch_custom_series(
            bridge, source, symbol, interval, start=start, end=end
        )

    # The DURABLE cache comes first: history the runtime has already paid for
    # is kept on this machine, so a repeat run is served from it and the whole
    # stack (the backtest, the regimes, the Monte-Carlo, Pine, the trade-log
    # analysis) reads the SAME local bars.
    cache = getattr(gateway, "history_cache", None)
    if cache is not None and getattr(cache, "available", False):
        cached = cache.lookup(symbol, interval, adjusted=adjusted,
                              start=start, end=end)
        if cached:
            series = series_from_rows(symbol, interval, cached, source="cache")
            if series.length:
                return series

    result = await gateway.get_historical_prices(
        symbol, None, start=start, end=end, interval=interval, adjusted=adjusted
    )
    if isinstance(result, MarketError):
        if result.code in ("DATA_NOT_AVAILABLE", "INVALID_REQUEST"):
            raise InvalidSymbol(
                f"no {interval} data for {symbol}: {result.message}",
                detail={"symbol": symbol, "interval": interval, "provider": result.provider},
            )
        raise MissingData(
            f"could not load {interval} data for {symbol}: {result.message}",
            detail={"symbol": symbol, "interval": interval, "code": result.code},
        )
    series = series_from_historical(result)
    if series.length == 0:
        raise MissingData(f"{symbol} returned no bars at {interval}",
                          detail={"symbol": symbol, "interval": interval})
    # Keep what we just fetched, so the next request for this window is a hit.
    if cache is not None and getattr(cache, "available", False):
        bars = getattr(result, "bars", None) or []
        if bars:
            provider = str(getattr(result, "provider", "") or "unknown")
            cache.store(symbol, interval, provider, adjusted,
                        [_bar_row(bar) for bar in bars])
    return series


def _bar_row(bar: Any) -> dict[str, Any]:
    """A bar as the durable store wants it, whether it is a model or a dict."""
    if isinstance(bar, dict):
        return {k: bar.get(k) for k in
                ("timestamp", "open", "high", "low", "close", "volume", "vwap")}
    return {k: getattr(bar, k, None) for k in
            ("timestamp", "open", "high", "low", "close", "volume", "vwap")}


async def resolve_dataset(
    gateway,
    symbols: list[str],
    *,
    primary: str = "1d",
    confirmation: Optional[list[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    adjusted: bool = True,
    data_source: Optional[dict[str, Any]] = None,
    bridge: Any = None,
) -> MarketDataset:
    confirmation = confirmation or []
    for tf in confirmation:
        from .data import INTERVAL_SECONDS

        if tf not in INTERVAL_SECONDS:
            raise UnsupportedTimeframe(f"unsupported confirmation timeframe {tf!r}")
    series: dict[str, BarSeries] = {}
    higher: dict[tuple[str, str], BarSeries] = {}
    for symbol in symbols:
        series[symbol] = await fetch_series(
            gateway, symbol, interval=primary, start=start, end=end, adjusted=adjusted,
            data_source=data_source, bridge=bridge,
        )
        for tf in confirmation:
            try:
                higher[(symbol, tf)] = await fetch_series(
                    gateway, symbol, interval=tf, start=start, end=end, adjusted=adjusted,
                    data_source=data_source, bridge=bridge,
                )
            except (MissingData, InvalidSymbol):
                # Confirmation data is optional; the engine warns when it is absent.
                continue
    return MarketDataset(series=series, higher=higher)


async def dataset_from_strategy(
    gateway,
    strategy: StrategySpec,
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    symbols: Optional[list[str]] = None,
    adjusted: bool = True,
    data_source: Optional[dict[str, Any]] = None,
    bridge: Any = None,
) -> MarketDataset:
    selected = [s.upper() for s in (symbols or strategy.universe.symbols)]
    # An explicit call argument wins; otherwise a strategy may PIN its source in
    # `metadata.dataSource` so a saved strategy reproduces on its own data.
    source = data_source if data_source is not None else strategy.metadata.get("dataSource")
    return await resolve_dataset(
        gateway, selected, primary=strategy.timeframes.primary,
        confirmation=strategy.timeframes.confirmation, start=start, end=end,
        adjusted=adjusted, data_source=source, bridge=bridge,
    )


__all__ = ["dataset_from_strategy", "fetch_series", "resolve_dataset"]

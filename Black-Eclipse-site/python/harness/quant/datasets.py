"""Resolve a backtest dataset from the Market Data Gateway.

The engine never calls a provider: this adapter asks the gateway (which routes,
paces, normalizes and quality-checks) for a normalized `HistoricalPriceSeries`
per symbol/timeframe and packs the results into the engine's `MarketDataset`.

An unavailable symbol/timeframe is an honest, typed error — never a fabricated
series. Confirmation timeframes that the providers cannot supply are simply
absent (the engine then warns and disables the indicators that needed them).
"""

from __future__ import annotations

from typing import Optional

from ..market.errors import MarketError
from .data import BarSeries, MarketDataset, series_from_historical
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
) -> BarSeries:
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
    return series


async def resolve_dataset(
    gateway,
    symbols: list[str],
    *,
    primary: str = "1d",
    confirmation: Optional[list[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    adjusted: bool = True,
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
            gateway, symbol, interval=primary, start=start, end=end, adjusted=adjusted
        )
        for tf in confirmation:
            try:
                higher[(symbol, tf)] = await fetch_series(
                    gateway, symbol, interval=tf, start=start, end=end, adjusted=adjusted
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
) -> MarketDataset:
    selected = [s.upper() for s in (symbols or strategy.universe.symbols)]
    return await resolve_dataset(
        gateway, selected, primary=strategy.timeframes.primary,
        confirmation=strategy.timeframes.confirmation, start=start, end=end, adjusted=adjusted,
    )


__all__ = ["dataset_from_strategy", "fetch_series", "resolve_dataset"]

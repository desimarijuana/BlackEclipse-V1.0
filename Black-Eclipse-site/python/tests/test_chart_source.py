"""A chart that NAMES its series (the engine fetches it) — the fix for a lost chart.

A 250-point chart block is ~4KB of JSON. The model wrote it, ran out of output,
and the truncated fence was lost: the reader saw raw JSON and no chart. A named
source keeps the numbers out of the message entirely.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.charts.scene import ChartDataSource, ChartMark
from harness.charts.source import ChartSourceError, resolve_data_sources
from harness.charts.spec import ChartSpec


class _Bar:
    def __init__(self, close: float) -> None:
        self.close = close
        self.open = close
        self.high = close
        self.low = close
        self.volume = 100.0


class _Series:
    def __init__(self, bars: list[_Bar]) -> None:
        self.bars = bars


class _Gateway:
    """A gateway that answers one symbol and refuses another."""

    def __init__(self, bars: list[float] | None) -> None:
        self._bars = bars
        self.calls: list[dict[str, Any]] = []

    async def get_historical_prices(self, symbol, market=None, **kwargs):
        self.calls.append({"symbol": symbol, "market": market, **kwargs})
        if self._bars is None:
            return RuntimeError(f"no series for {symbol}")
        return _Series([_Bar(v) for v in self._bars])


class _Ctx:
    def __init__(self, gateway) -> None:
        self.market_gateway = gateway


def _spec(source: dict[str, Any]) -> ChartSpec:
    return ChartSpec(
        kind="scene",
        panels=[{"marks": [ChartMark(type="regression", data_source=source)]}],
    )


def test_a_named_source_becomes_the_series_it_names():
    gateway = _Gateway([10.0, 11.0, 12.0, 13.0])
    spec = _spec({"symbol": "AAPL", "interval": "1d"})
    asyncio.run(resolve_data_sources(spec, _Ctx(gateway)))
    mark = spec.panels[0].marks[0]
    assert mark.y == [10.0, 11.0, 12.0, 13.0]
    # The x axis is the session index: a regression against the trading-day
    # index is what "the trend over the period" means.
    assert mark.x == [1, 2, 3, 4]
    assert gateway.calls and gateway.calls[0]["symbol"] == "AAPL"


def test_a_named_source_passes_the_window_through():
    gateway = _Gateway([1.0, 2.0])
    spec = _spec({"symbol": "AAPL", "start": "2025-10-21", "end": "2026-10-21"})
    asyncio.run(resolve_data_sources(spec, _Ctx(gateway)))
    call = gateway.calls[0]
    assert call["start"] == "2025-10-21"
    assert call["end"] == "2026-10-21"


def test_a_source_that_cannot_be_fetched_is_refused_not_guessed():
    gateway = _Gateway(None)
    spec = _spec({"symbol": "NOPE"})
    with pytest.raises(ChartSourceError) as excinfo:
        asyncio.run(resolve_data_sources(spec, _Ctx(gateway)))
    assert "NOPE" in str(excinfo.value)


def test_a_mark_that_carries_its_values_is_left_alone():
    gateway = _Gateway([1.0, 2.0])
    spec = ChartSpec(
        kind="scene",
        panels=[{"marks": [ChartMark(type="regression", x=[1, 2], y=[5.0, 6.0])]}],
    )
    asyncio.run(resolve_data_sources(spec, _Ctx(gateway)))
    mark = spec.panels[0].marks[0]
    assert mark.y == [5.0, 6.0]
    assert gateway.calls == []


def test_the_source_model_is_wired_to_the_mark():
    source = ChartDataSource(symbol="AAPL", interval="1d", field="close")
    mark = ChartMark(type="regression", data_source=source)
    assert mark.data_source is not None
    assert mark.data_source.symbol == "AAPL"

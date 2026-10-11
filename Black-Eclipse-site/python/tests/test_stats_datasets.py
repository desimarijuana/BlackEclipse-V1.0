"""Market-data adapter — series/frame resolution against a fake gateway."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.stats.base import StatsError
from harness.stats.datasets import resolve_frame, resolve_series


def _bars(prices, start="2026-01-01"):
    out = []
    for i, p in enumerate(prices):
        out.append(SimpleNamespace(timestamp=f"{start}T{i:02d}", open=p, high=p, low=p, close=p,
                                   volume=100 + i))
    return out


class FakeGateway:
    def __init__(self, series: dict[str, list[float]]):
        self.series = series

    async def get_historical_prices(self, symbol, _unused, *, start=None, end=None, interval="1d",
                                    adjusted=True):
        if symbol not in self.series:
            from harness.market.errors import MarketError

            return MarketError(code="DATA_NOT_AVAILABLE", message="no data", provider="fake")
        return SimpleNamespace(bars=_bars(self.series[symbol]), provider="fake",
                               interval=interval, adjusted=adjusted, source="test")


async def test_resolve_series_returns_arrays_and_provenance():
    gw = FakeGateway({"AAPL": [100.0, 101.0, 102.0]})
    out = await resolve_series(gw, "AAPL", interval="1d", field="close")
    assert out["symbol"] == "AAPL"
    assert out["values"] == [100.0, 101.0, 102.0]
    assert out["provenance"]["provider"] == "fake"


async def test_resolve_series_unknown_symbol_is_honest_error():
    gw = FakeGateway({"AAPL": [1.0]})
    with pytest.raises(StatsError) as exc:
        await resolve_series(gw, "MSFT")
    assert exc.value.code == "INVALID_INPUT"


async def test_resolve_frame_aligns_to_intersection():
    gw = FakeGateway({"A": [1.0, 2.0, 3.0, 4.0], "B": [10.0, 20.0, 30.0, 40.0]})
    out = await resolve_frame(gw, ["A", "B"])
    assert out["symbols"] == ["A", "B"]
    assert len(out["values"]) == 2
    assert len(out["values"][0]) == len(out["timestamps"])


async def test_resolve_frame_missing_symbol_errors():
    gw = FakeGateway({"A": [1.0, 2.0]})
    with pytest.raises(StatsError):
        await resolve_frame(gw, ["A", "MISSING"])

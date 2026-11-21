"""Market mandates are enforced by the event engine, not just declared."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import market_rules as MR
from harness.quant import strategy as S

UTC = timezone.utc


def _rows(points, *, interval_min: int = 1440, start: datetime | None = None):
    """points: list of (open, close) or a single price per bar."""
    t0 = start or datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    for i, point in enumerate(points):
        o, c = point if isinstance(point, tuple) else (point, point)
        rows.append({
            "timestamp": (t0 + timedelta(minutes=interval_min * i)).strftime("%Y-%m-%dT%H:%M:%S"),
            "open": o,
            "high": max(o, c) * 1.001,
            "low": min(o, c) * 0.999,
            "close": c,
            "volume": 10_000.0,
        })
    return rows


def _dataset(symbol: str, rows, interval: str = "1d"):
    return D.build_dataset({symbol: D.series_from_rows(symbol, interval, rows, source="synthetic")})


def _spec(symbol: str, market: str, *, sizing: dict | None = None) -> S.StrategySpec:
    always = {"conditions": [{"left": {"ref": "close"}, "op": ">", "right": {"value": 0.01}}]}
    return S.parse_strategy({
        "strategy": {"id": "always", "name": "Always", "version": "1.0.0"},
        "market": market,
        "universe": {"symbols": [symbol]},
        "rules": {"entry": {"long": always}, "exit": {"long": always}},
        "position_sizing": sizing or {"type": "fixed_dollar", "value": 1234},
    })


# -- lot rounding ------------------------------------------------------------


def test_a_share_orders_are_floored_to_whole_lots():
    symbol = "600519.SH"
    rows = _rows([10.0] * 6)
    res = E.run_backtest(_spec(symbol, "a_share"), _dataset(symbol, rows))
    assert res.fills, res.warnings
    # 1234 / 10 = 123.4 shares -> 100-share lot.
    assert res.fills[0]["quantity"] == 100


def test_a_sub_lot_entry_becomes_no_trade():
    symbol = "600519.SH"
    rows = _rows([100.0] * 6)
    res = E.run_backtest(
        _spec(symbol, "a_share", sizing={"type": "fixed_dollar", "value": 50}),
        _dataset(symbol, rows),
    )
    assert res.fills == []
    assert any(w["code"] == "MARKET_LOT_BELOW_ONE" for w in res.warnings)


def test_us_keeps_fractional_size():
    symbol = "AAPL.US"
    rows = _rows([10.0] * 6)
    res = E.run_backtest(_spec(symbol, "us_equity"), _dataset(symbol, rows))
    assert res.fills and res.fills[0]["quantity"] == pytest.approx(123.4)


# -- price limits ------------------------------------------------------------


def test_a_share_fill_outside_the_limit_band_is_refused():
    symbol = "600519.SH"
    # Bars 0-2 hold at 10; bar 3 gaps to 12 (+20%) against a +10% main-board
    # limit computed from the previous close. The first fillable bar is 3.
    rows = _rows([(10.0, 10.0)] * 3 + [(12.0, 12.0)] * 3)
    res = E.run_backtest(_spec(symbol, "a_share"), _dataset(symbol, rows))
    assert any(w["code"] == "MARKET_LIMIT_BAND" for w in res.warnings)
    # The out-of-band print itself never fills; later bars re-base on 12.
    assert all(fill["index"] != 3 for fill in res.fills)


def test_us_has_no_band_so_the_same_gap_fills():
    symbol = "AAPL.US"
    rows = _rows([(10.0, 10.0)] * 3 + [(12.0, 12.0)] * 3)
    res = E.run_backtest(_spec(symbol, "us_equity"), _dataset(symbol, rows))
    assert res.fills, res.warnings
    assert res.fills[0]["index"] == 3
    assert res.fills[0]["price"] == pytest.approx(12.0)


def test_chinext_uses_the_20_percent_band():
    symbol = "300750.SZ"
    # +15% is inside ChiNext's +20% band, outside the main board's +10%.
    rows = _rows([(10.0, 10.0)] * 3 + [(11.5, 11.5)] * 3)
    res = E.run_backtest(_spec(symbol, "a_share"), _dataset(symbol, rows))
    assert res.fills, res.warnings
    assert res.fills[0]["index"] == 3


# -- settlement --------------------------------------------------------------


def test_a_share_blocks_same_day_exit():
    symbol = "600519.SH"
    rows = _rows([10.0] * 8, interval_min=1)
    res = E.run_backtest(_spec(symbol, "a_share"), _dataset(symbol, rows, interval="1m"))
    assert any(w["code"] == "MARKET_T1_UNSETTLED" for w in res.warnings)


def test_us_allows_same_day_exit():
    symbol = "AAPL.US"
    rows = _rows([10.0] * 8, interval_min=1)
    res = E.run_backtest(_spec(symbol, "us_equity"), _dataset(symbol, rows, interval="1m"))
    assert not any(w["code"] == "MARKET_T1_UNSETTLED" for w in res.warnings)


# -- board mapping -----------------------------------------------------------


def test_board_for_code_maps_the_published_prefixes():
    assert MR.board_for_code("688981.SH") == "star"
    assert MR.board_for_code("300750.SZ") == "chinext"
    assert MR.board_for_code("830799.BJ") == "beijing"
    assert MR.board_for_code("600519.SH") == "main"
    assert MR.board_for_code("AAPL.US") == "unknown"


def test_config_market_overrides_the_strategy():
    symbol = "600519.SH"
    rows = _rows([(10.0, 10.0)] * 3 + [(12.0, 12.0)] * 3)
    spec = _spec(symbol, "a_share")
    # Overriding to us_equity disables the band and the lot mandate.
    res = E.run_backtest(spec, _dataset(symbol, rows), E.BacktestConfig(market="us_equity"))
    assert res.fills
    assert res.fills[0]["index"] == 3

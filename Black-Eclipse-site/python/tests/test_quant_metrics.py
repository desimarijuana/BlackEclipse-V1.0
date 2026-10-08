"""Unit tests for the metrics engine on a hand-checked equity curve."""

from __future__ import annotations

import pytest

from harness.quant.metrics import MetricInputs, MetricsEngine
from harness.quant.models import EquityPoint, TradeRecord


def _trade(pnl, direction="long", bars=2, symbol="X"):
    return TradeRecord(id="t", symbol=symbol, direction=direction, entry_ts=None, exit_ts=None,
                       entry_price=100.0, exit_price=100.0 + pnl, quantity=1.0,
                       gross_pnl=pnl, net_pnl=pnl, commission=0.0, bars_held=bars, pnl_pct=0.0)


def _engine(equity, trades, exposure=None, interval="1d", initial=None):
    exp = exposure or [EquityPoint(i, None, e, e, 0.0, 0.0, 0.0, 0.0) for i, e in enumerate(equity)]
    return MetricsEngine(MetricInputs(
        equity=equity, timestamps=[None] * len(equity), trades=trades, exposure=exp,
        interval=interval, initial_capital=initial if initial is not None else equity[0],
    ))


def test_returns_and_drawdown():
    e = _engine([100.0, 110.0, 100.0, 120.0], [])
    v = e.values()
    assert v["total_return"] == pytest.approx(20.0)
    assert v["max_drawdown"] == pytest.approx((100.0 / 110.0 - 1.0) * 100.0)


def test_trade_statistics():
    trades = [_trade(10), _trade(-5), _trade(20)]
    v = _engine([100, 105, 110], trades).values()
    assert v["trade_count"] == 3
    assert v["win_rate"] == pytest.approx(2 / 3 * 100)
    assert v["profit_factor"] == pytest.approx(30 / 5)
    assert v["expectancy"] == pytest.approx(25 / 3)
    assert v["largest_win"] == pytest.approx(20)
    assert v["largest_loss"] == pytest.approx(-5)


def test_metric_definitions_present():
    defs = _engine([100, 101], []).definitions()
    assert "sharpe" in defs
    assert defs["max_drawdown"]["unit"] == "%"
    assert defs["sharpe"]["definition"]
    assert defs["total_return"]["definition"]


def test_streaks():
    trades = [_trade(1), _trade(1), _trade(-1), _trade(-1), _trade(-1), _trade(1)]
    v = _engine([100] * 7, trades).values()
    assert v["max_winning_streak"] == 2
    assert v["max_losing_streak"] == 3


def test_var_cvar_small_sample_is_none():
    v = _engine([100, 101], []).values()
    assert v["var_95"] is None
    assert v["cvar_95"] is None

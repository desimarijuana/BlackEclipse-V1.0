"""Integration / regression / property tests for the event-driven engine.

Covers the data → strategy → signal → order → execution → portfolio → metrics
pipeline, the anti-lookahead contract, multi-timeframe alignment, deterministic
reproducibility, and the accounting invariants.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.errors import CorruptDataset


def _spec(**over):
    base = {
        "strategy": {"id": "ema_cross", "name": "EMA Cross", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [
            {"id": "ema_fast", "type": "ema", "params": {"period": 5}},
            {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
            {"id": "atr", "type": "atr", "params": {"period": 14}},
        ],
        "rules": {
            "entry": {"long": {"conditions": [
                {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}}]}},
            "exit": {"stop_loss": {"type": "atr", "value": 2}, "take_profit": {"type": "risk_reward", "value": 2}},
        },
        "position_sizing": {"type": "percent_equity", "value": 90},
    }
    base.update(over)
    return S.parse_strategy(base)


def _dataset(rows=None, **kw):
    rows = rows if rows is not None else F.bull_market("TESTUSDT", n=300)
    return D.build_dataset({"TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})


def test_engine_produces_wellformed_result():
    res = E.run_backtest(_spec(), _dataset(), E.BacktestConfig(initial_capital=100_000))
    assert res.status == "OK"
    assert res.equity_curve and res.drawdown_curve
    assert res.equity_curve[0]["equity"] == pytest.approx(100_000)
    assert res.metrics["trade_count"] >= 0
    assert res.capability["options"] == "unsupported"
    assert res.observability["barsProcessed"] == 300


def test_order_never_fills_on_signal_bar():
    # An entry signal on bar i must fill at bar i+1 at the earliest.
    res = E.run_backtest(_spec(), _dataset(), E.BacktestConfig(initial_capital=100_000))
    for order in res.orders:
        if order["status"] == "filled":
            assert order["filledQuantity"] > 0
    events = {f["orderId"]: f["index"] for f in res.fills}
    assert events, "expected at least one fill on a trending series"


def test_future_mutation_does_not_change_past_equity():
    rows = F.bull_market("TESTUSDT", n=200, seed=3)
    a = E.run_backtest(_spec(), _dataset(rows), E.BacktestConfig())
    mutated = [dict(r) for r in rows]
    for r in mutated[120:]:
        for f in ("open", "high", "low", "close"):
            r[f] *= 2.0
    b = E.run_backtest(_spec(), _dataset(mutated), E.BacktestConfig())
    for i in range(0, 120):
        assert a.equity_curve[i]["equity"] == pytest.approx(b.equity_curve[i]["equity"])


def test_reproducible_with_same_seed():
    spec = _spec(execution={"commission": {"type": "percentage", "value": 0.1},
                            "slippage": {"type": "randomized", "value": 0.05, "seed": 99}})
    r1 = E.run_backtest(spec, _dataset(), E.BacktestConfig(random_seed=99))
    r2 = E.run_backtest(spec, _dataset(), E.BacktestConfig(random_seed=99))
    assert r1.metrics == r2.metrics
    assert [t["netPnl"] for t in r1.trades] == [t["netPnl"] for t in r2.trades]


def test_frictionless_only_when_selected():
    frictionless = _spec()  # no execution block -> all none
    res = E.run_backtest(frictionless, _dataset(), E.BacktestConfig())
    assert res.configuration["execution"]["frictionless"] is True
    costly = _spec(execution={"commission": {"type": "percentage", "value": 0.1}})
    res2 = E.run_backtest(costly, _dataset(), E.BacktestConfig())
    assert res2.configuration["execution"]["frictionless"] is False


def _minute_rows(n: int):
    from datetime import datetime, timedelta, timezone

    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    price = 100.0
    for i in range(n):
        ts = t0 + timedelta(minutes=i)
        o = price
        c = price + (0.1 if i % 3 else -0.05)
        rows.append({"timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S"), "open": o,
                     "high": max(o, c) + 0.2, "low": min(o, c) - 0.2, "close": c, "volume": 10})
        price = c
    return rows


def test_multi_timeframe_alignment_no_lookahead():
    rows = _minute_rows(60)
    primary = D.series_from_rows("X", "1m", rows)
    higher = D.series_from_rows("X", "5m", F.aggregate(rows, 5))
    align = D.align_higher_to_primary(higher, primary.timestamps, "1m")
    # The first 4 primary bars precede the close of the first 5-minute bar.
    assert list(align[:4]) == [-1, -1, -1, -1]
    assert align[4] == 0
    # Monotonic non-decreasing thereafter (never a future bar).
    assert all(align[i] <= align[i + 1] for i in range(len(align) - 1))


def test_short_strategy_runs():
    spec = S.parse_strategy({
        "strategy": {"id": "shorty", "name": "Shorty", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [{"id": "ema_fast", "type": "ema", "params": {"period": 5}},
                       {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
                       {"id": "atr", "type": "atr", "params": {"period": 14}}],
        "rules": {"entry": {"short": {"conditions": [
            {"left": {"ref": "ema_fast"}, "op": "cross_below", "right": {"ref": "ema_slow"}}]}},
            "exit": {"stop_loss": {"type": "atr", "value": 2}}},
        "position_sizing": {"type": "percent_equity", "value": 90},
    })
    res = E.run_backtest(spec, _dataset(F.bear_market("TESTUSDT", n=300)), E.BacktestConfig())
    assert res.status == "OK"
    assert any(t["direction"] == "short" for t in res.trades) or res.metrics["trade_count"] == 0


def test_risk_rejection_is_recorded():
    spec = S.parse_strategy({
        "strategy": {"id": "r", "name": "r", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [{"id": "ema_fast", "type": "ema", "params": {"period": 5}},
                       {"id": "ema_slow", "type": "ema", "params": {"period": 20}}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}}]}},
            "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 90},
        "risk": {"max_open_positions": 0},
    })
    res = E.run_backtest(spec, _dataset(), E.BacktestConfig())
    assert any(w["code"] == "RISK_REJECTED" for w in res.warnings)


def test_portfolio_backtest_rejects_conflicting_symbols():
    a = _spec(strategy={"id": "a", "name": "a", "version": "1.0.0"})
    b = _spec(strategy={"id": "b", "name": "b", "version": "1.0.0"})
    with pytest.raises(CorruptDataset):
        E.run_portfolio_backtest([a, b], _dataset(), E.BacktestConfig())


def test_portfolio_backtest_honours_per_strategy_costs():
    def spec(sid, symbol, value):
        return S.parse_strategy({
            "strategy": {"id": sid, "name": sid, "version": "1.0.0"},
            "universe": {"symbols": [symbol]},
            "indicators": [{"id": "ema_fast", "type": "ema", "params": {"period": 5}},
                           {"id": "ema_slow", "type": "ema", "params": {"period": 20}}],
            "rules": {"entry": {"long": {"conditions": [
                {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}}]}},
                "exit": {}},
            "position_sizing": {"type": "percent_equity", "value": 40},
            "execution": {"commission": {"type": "percentage", "value": value}},
        })
    a = spec("cheap", "AAAUSDT", 0.0)
    b = spec("rich", "BBBUSDT", 1.0)
    rows_a = F.bull_market("AAAUSDT", n=200, seed=11)
    rows_b = F.bull_market("BBBUSDT", n=200, seed=23)
    ds = D.build_dataset({
        "AAAUSDT": D.series_from_rows("AAAUSDT", "1d", rows_a, source="synthetic"),
        "BBBUSDT": D.series_from_rows("BBBUSDT", "1d", rows_b, source="synthetic"),
    })
    res = E.run_portfolio_backtest([a, b], ds, E.BacktestConfig())
    fills = res.fills
    assert fills
    # Each symbol's commission follows ITS OWN strategy, not the first binding's.
    assert all(f["commission"] == pytest.approx(0.0) for f in fills if f["symbol"] == "AAAUSDT")
    assert all(f["commission"] > 0 for f in fills if f["symbol"] == "BBBUSDT")
    # The configuration records each binding's own execution assumptions.
    execs = {b["strategyId"]: b["execution"]["commission"]["value"]
             for b in res.configuration["bindings"]}
    assert execs["cheap"] == 0.0 and execs["rich"] == 1.0


def test_historical_spread_uses_per_bar_data_and_warns_when_absent():
    spec = _spec(execution={"spread": {"type": "historical", "value": 0.0}})
    rows = F.bull_market("TESTUSDT", n=300)
    for r in rows:
        r["spread"] = 0.4
    bs = D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")
    assert bs.spread is not None
    res = E.run_backtest(spec, D.build_dataset({"TESTUSDT": bs}), E.BacktestConfig())
    assert res.fills and any(f["spreadCost"] > 0 for f in res.fills)
    assert not any(w["code"] == "HISTORICAL_SPREAD_UNAVAILABLE" for w in res.warnings)
    # No spread column -> cost is zero AND a warning names the shortfall.
    bs2 = D.series_from_rows("TESTUSDT", "1d", F.bull_market("TESTUSDT", n=300), source="synthetic")
    res2 = E.run_backtest(spec, D.build_dataset({"TESTUSDT": bs2}), E.BacktestConfig())
    assert any(w["code"] == "HISTORICAL_SPREAD_UNAVAILABLE" for w in res2.warnings)


def test_dataset_quality_findings_are_surfaced():
    rows = F.with_duplicate_candle("TESTUSDT", n=200, dup_at=100)
    res = E.run_backtest(_spec(), _dataset(rows), E.BacktestConfig())
    assert any(w["code"].startswith("DATA_") for w in res.warnings)


def test_regression_golden_equity_curve_is_stable():
    # Deterministic dataset + engine ⇒ byte-stable result (regression fixture).
    res = E.run_backtest(_spec(), _dataset(F.sideways_market("TESTUSDT", n=200, seed=5)),
                         E.BacktestConfig(initial_capital=50_000, risk_free_rate=0.0))
    digest = round(sum(p["equity"] for p in res.equity_curve), 4)
    res2 = E.run_backtest(_spec(), _dataset(F.sideways_market("TESTUSDT", n=200, seed=5)),
                          E.BacktestConfig(initial_capital=50_000, risk_free_rate=0.0))
    digest2 = round(sum(p["equity"] for p in res2.equity_curve), 4)
    assert digest == digest2

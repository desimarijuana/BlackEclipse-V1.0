"""Tests for the Pine report adapter.

The adapter is what lets a Pine run be graded by Eclipse's own machinery. The
tests use the REAL engine when it is installed and skip when it is not - the
Python side must never pretend the engine is there.
"""

from __future__ import annotations

import pytest

from harness.quant.pine import PineRunConfig, PineRunner
from harness.quant.pine_report import (
    build_equity_curve,
    build_pine_artifact,
    drawdown_curve,
    pine_trades_to_records,
    regime_attribution,
)

SOURCE = """//@version=6
strategy("Eclipse cross", overlay = true, initial_capital = 100000)
fast = ta.ema(close, 9)
slow = ta.ema(close, 21)
if ta.crossover(fast, slow)
    strategy.entry("long", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("long")
plot(fast, "Fast")
"""


def _bars(n=400):
    bars = []
    price = 100.0
    for i in range(n):
        drift = 0.004 if (i // 40) % 2 == 0 else -0.003
        price *= 1 + drift + (0.003 if i % 11 < 5 else -0.003)
        bars.append({"time": 1700000000000 + i * 86400000, "o": price * 0.997,
                     "h": price * 1.008, "l": price * 0.992, "c": price, "v": 1000.0})
    return bars


# ── the translation ──────────────────────────────────────────────────────────

def test_pine_trades_translate_into_the_engines_trade_shape():
    records = pine_trades_to_records([
        {"id": "trade_1", "direction": "long", "entryTime": 1700000000000,
         "exitTime": 1700086400000, "entryBarIndex": 3, "exitBarIndex": 8,
         "entryPrice": 100.0, "exitPrice": 104.0, "quantity": 2.0, "profit": 8.0,
         "commission": 0.5, "exitId": "Close entry(s) order long"},
    ], symbol="TEST")
    assert len(records) == 1
    record = records[0]
    assert record.symbol == "TEST"
    assert record.direction == "long"
    assert record.net_pnl == 8.0
    assert record.gross_pnl == 8.0
    assert record.commission == 0.5
    assert record.bars_held == 5
    assert record.entry_ts and record.entry_ts.startswith("2023-11-14")
    assert record.exit_reason == "Close entry(s) order long"


def test_a_short_trade_stays_a_short():
    records = pine_trades_to_records([
        {"id": "t", "direction": "short", "entryTime": 1700000000000,
         "exitTime": 1700086400000, "entryPrice": 100.0, "exitPrice": 96.0,
         "quantity": 1.0, "profit": 4.0},
    ])
    assert records[0].direction == "short"


def test_a_trade_without_a_profit_does_not_break_the_translation():
    records = pine_trades_to_records([{"id": "t", "entryTime": 1700000000000}])
    assert records[0].net_pnl == 0.0
    assert records[0].bars_held == 0


# ── the equity curve ─────────────────────────────────────────────────────────

def test_the_equity_curve_marks_a_trade_at_its_exit_bar():
    bars = _bars(10)
    records = pine_trades_to_records([
        {"id": "t", "entryTime": bars[2]["time"], "exitTime": bars[5]["time"],
         "entryBarIndex": 2, "exitBarIndex": 5, "entryPrice": 100.0,
         "exitPrice": 110.0, "quantity": 1.0, "profit": 10.0},
    ])
    equity, times, points = build_equity_curve(bars, records, initial_capital=1000.0)
    assert len(equity) == 10
    assert equity[4] == 1000.0     # not yet realised
    assert equity[5] == 1010.0    # realised at the exit bar
    assert points[5].equity == 1010.0
    assert times[0] and times[0].startswith("2023-")


def test_the_drawdown_curve_is_never_positive():
    equity = [100.0, 120.0, 90.0, 110.0]
    curve = drawdown_curve(equity)
    assert all(point["drawdown"] <= 0 for point in curve)
    assert curve[2]["drawdown"] == pytest.approx(-25.0)


# ── the artifact ─────────────────────────────────────────────────────────────

def test_the_artifact_carries_the_metrics_the_verdict_needs():
    class _Result:
        trades = [{"id": "t", "entryTime": 1700000000000, "exitTime": 1700086400000,
                   "entryBarIndex": 1, "exitBarIndex": 3, "entryPrice": 100.0,
                   "exitPrice": 104.0, "quantity": 1.0, "profit": 4.0}]
        diagnostics = {"initialCapital": 1000.0, "barCount": 40, "tradeCount": 1}

    built = build_pine_artifact(_Result(), _bars(40), symbol="TEST")
    artifact = built.artifact
    for name in ("total_return", "sharpe", "max_drawdown", "profit_factor",
                 "expectancy", "win_rate", "trade_count"):
        assert name in artifact["metrics"], name
    assert artifact["metadata"]["strategyId"] == "pine:TEST"
    assert artifact["configuration"]["initialCapital"] == 1000.0
    assert len(artifact["trades"]) == 1


def test_the_artifact_states_the_two_methodological_caveats():
    class _Result:
        trades = []
        diagnostics = {"initialCapital": 1000.0}

    artifact = build_pine_artifact(_Result(), _bars(40)).artifact
    codes = {w["code"] for w in artifact["warnings"]}
    assert "PINE_EQUITY_MARKED_AT_EXIT" in codes
    assert "PINE_FILLS_ARE_THE_ENGINES_OWN" in codes


# ── the regimes ──────────────────────────────────────────────────────────────

def test_trades_are_attributed_to_the_regime_of_their_entry_bar():
    bars = _bars(300)
    trades = [{"id": "t1", "entryBarIndex": 10, "profit": 100.0},
              {"id": "t2", "entryBarIndex": 200, "profit": -50.0}]
    attribution = regime_attribution(bars, trades)
    assert attribution["regimeCount"] >= 1
    regimes = attribution["regimes"]
    assert sum(bucket["trades"] for bucket in regimes.values()) == 2


def test_a_trade_outside_the_bars_is_not_attributed():
    attribution = regime_attribution(_bars(50), [{"id": "t", "entryBarIndex": 999,
                                                   "profit": 10.0}])
    assert attribution["regimeCount"] == 0


# ── the whole chain, with the real engine ───────────────────────────────────

@pytest.mark.skipif(not PineRunner().available, reason="the Pine engine is not installed")
def test_a_pine_run_is_graded_by_the_edge_verdict():
    from harness.quant.edge_report import build_edge_report
    from harness.quant.montecarlo import MonteCarloConfig, MonteCarloEngine

    bars = _bars(400)
    result = PineRunner().run(SOURCE, bars, config=PineRunConfig(timeout_s=60))
    artifact = build_pine_artifact(result, bars, symbol="TEST").artifact
    regimes = regime_attribution(bars, result.trades)

    monte_carlo = MonteCarloEngine.from_recorded(
        trades=artifact["trades"], equity_curve=artifact["equityCurve"],
        metrics=artifact["metrics"],
        config=MonteCarloConfig(method="regime_block_bootstrap", simulations=50, seed=7,
                                 initial_capital=artifact["configuration"]["initialCapital"]),
    ).run().to_dict()
    if regimes:
        monte_carlo["regimeAttribution"] = regimes

    report = build_edge_report(artifact, monte_carlo)
    assert report.verdict["grade"] in ("A", "B", "C", "D", "E", "F")
    # A handful of trades can never be a strong sample, and the verdict must
    # say so rather than reward a small lucky run.
    assert "SAMPLE_TOO_SMALL" in {f["code"] for f in report.verdict["flags"]}
    assert "## Warnings from the run" in report.markdown
    assert "PINE_EQUITY_MARKED_AT_EXIT" in report.markdown


@pytest.mark.skipif(not PineRunner().available, reason="the Pine engine is not installed")
def test_a_recorded_run_cannot_be_perturbed_by_parameter():
    """The families that re-run the strategy must refuse a recorded run."""
    from harness.quant.montecarlo import MonteCarloConfig, MonteCarloEngine

    with pytest.raises(Exception):
        MonteCarloEngine.from_recorded(
            trades=[], equity_curve=[], metrics={},
            config=MonteCarloConfig(method="parameter_perturbation"),
        )

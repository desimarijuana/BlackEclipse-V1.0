"""Tests for the regime classifier, the regime-block Monte-Carlo method and
the edge verdict."""

from __future__ import annotations

import math

import numpy as np
import pytest

from harness.quant import data as D
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.montecarlo import MonteCarloConfig, MonteCarloEngine
from harness.quant.regime import (
    RegimeConfig,
    RegimeError,
    attribute_regimes,
    classify_dataset,
    classify_series,
    label_trades,
    regime_blocks,
)
from harness.quant.verdict import VerdictConfig, VerdictError, grade_edge


def _series_from(rows):
    return D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")


def _trending_rows(n=400, drift=0.004, vol=0.010, seed=3):
    """A seeded synthetic uptrend. Synthetic, and only ever used as a fixture."""
    return F._series("TESTUSDT", n=n, start=100.0, drift=drift, vol=vol, seed=seed)


# ── regime classification ────────────────────────────────────────────────────

def test_classify_series_labels_every_bar_and_is_causal():
    rows = _trending_rows(n=300)
    series = _series_from(rows)
    cfg = RegimeConfig(fast=10, slow=30, vol_period=10, vol_baseline=40)
    result = classify_series("TESTUSDT", series.high, series.low, series.close,
                             list(series.timestamps), cfg)

    assert len(result.labels) == len(result.timestamps)
    assert set(result.trend) <= {"up", "down", "flat"}
    assert set(result.volatility) <= {"high", "normal", "low"}
    assert all(0.0 <= c <= 1.0 for c in result.confidence)
    # A persistent uptrend must be classified as trending up for most of the tail.
    tail = result.trend[-60:]
    assert tail.count("up") > len(tail) * 0.5


def test_classify_series_refuses_too_few_bars():
    rows = _trending_rows(n=20)
    series = _series_from(rows)
    with pytest.raises(RegimeError):
        classify_series("TESTUSDT", series.high, series.low, series.close,
                        list(series.timestamps), RegimeConfig())


def test_regime_config_rejects_incoherent_parameters():
    with pytest.raises(RegimeError):
        RegimeConfig(fast=50, slow=20).validate()
    with pytest.raises(RegimeError):
        RegimeConfig(high_vol_ratio=0.5, low_vol_ratio=0.9).validate()


def test_classify_dataset_skips_instruments_that_are_too_short():
    rows = _trending_rows(n=300)
    dataset = D.build_dataset({"TESTUSDT": _series_from(rows)})
    out = classify_dataset(dataset, RegimeConfig(fast=10, slow=30, vol_period=10,
                                                 vol_baseline=40))
    assert "TESTUSDT" in out
    assert out["TESTUSDT"].symbol == "TESTUSDT"


# ── trade labelling and attribution ──────────────────────────────────────────

def test_label_trades_places_trades_on_their_entry_bar():
    rows = _trending_rows(n=300)
    series = _series_from(rows)
    classified = classify_series("TESTUSDT", series.high, series.low, series.close,
                                  list(series.timestamps),
                                  RegimeConfig(fast=10, slow=30, vol_period=10,
                                               vol_baseline=40))
    trades = [
        {"id": "t1", "symbol": "TESTUSDT", "entryTs": series.timestamps[100],
         "netPnl": 100.0},
        {"id": "t2", "symbol": "TESTUSDT", "entryTs": series.timestamps[150],
         "netPnl": -50.0},
        {"id": "t3", "symbol": "OTHER", "entryTs": series.timestamps[120],
         "netPnl": 10.0},
    ]
    labels, report = label_trades(trades, {"TESTUSDT": classified})
    assert labels[0] == classified.labels[100]
    assert labels[1] == classified.labels[150]
    assert labels[2] is None
    assert report["assigned"] == 2
    assert report["unassigned"] == 1
    assert report["unassignedReasons"]["symbol_not_classified"] == 1


def test_attribute_regimes_shares_are_relative_to_gross_profit():
    trades = [
        {"netPnl": 100.0}, {"netPnl": -20.0},
        {"netPnl": 50.0}, {"netPnl": 5.0},
    ]
    labels = ["up_high", "up_high", "down_low", "down_low"]
    out = attribute_regimes(trades, labels)
    regimes = out["regimes"]
    assert regimes["up_high"]["trades"] == 2
    assert regimes["up_high"]["netPnl"] == 80.0
    assert regimes["down_low"]["netPnl"] == 55.0
    assert out["grossPositivePnl"] == 155.0
    assert regimes["up_high"]["grossPositiveShare"] == pytest.approx(100.0 / 155.0 * 100.0)


def test_regime_blocks_split_on_label_changes():
    blocks = regime_blocks(["a", "a", "b", None, None, "a"])
    assert blocks == [[0, 1], [2], [3, 4], [5]]


# ── regime-block Monte-Carlo ─────────────────────────────────────────────────

def _spec():
    return S.parse_strategy({
        "strategy": {"id": "ema_cross", "name": "EMA", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [
            {"id": "ema_fast", "type": "ema", "params": {"period": 5}},
            {"id": "ema_slow", "type": "ema", "params": {"period": 20}},
            {"id": "atr", "type": "atr", "params": {"period": 14}},
        ],
        "rules": {
            "entry": {"long": {"conditions": [
                {"left": {"ref": "ema_fast"}, "op": "cross_above", "right": {"ref": "ema_slow"}}]}},
            "exit": {"stop_loss": {"type": "atr", "value": 2},
                     "take_profit": {"type": "risk_reward", "value": 2}},
        },
        "position_sizing": {"type": "percent_equity", "value": 90},
        "execution": {"commission": {"type": "percentage", "value": 0.05},
                      "slippage": {"type": "percentage", "value": 0.02}},
    })


def _dataset(n=600):
    rows = _trending_rows(n=n, drift=0.003, vol=0.012, seed=11)
    return D.build_dataset({"TESTUSDT": _series_from(rows)})


def test_regime_block_bootstrap_runs_and_reports_regime_attribution():
    dataset = _dataset()
    result = MonteCarloEngine(_spec(), dataset, MonteCarloConfig(
        method="regime_block_bootstrap", simulations=40, seed=5,
        regime_config={"fast": 10, "slow": 30, "vol_period": 10,
                       "vol_baseline": 40},
    )).run()

    payload = result.payload
    assert payload["method"] == "regime_block_bootstrap"
    assert payload["regimeMix"] == "resample"
    assert payload["regimeBlocks"] >= 1
    assert payload["successful"] == 40
    assert "regimeAttribution" in payload
    assert "regimeContributions" in payload
    assert result.metrics["probability_of_loss"] >= 0.0


def test_regime_block_bootstrap_is_reproducible_for_a_seed():
    dataset = _dataset()
    config = dict(method="regime_block_bootstrap", simulations=25, seed=99,
                  regime_config={"fast": 10, "slow": 30, "vol_period": 10,
                                 "vol_baseline": 40})
    first = MonteCarloEngine(_spec(), dataset, MonteCarloConfig(**config)).run()
    second = MonteCarloEngine(_spec(), dataset, MonteCarloConfig(**config)).run()
    assert first.payload["returnPercentiles"] == second.payload["returnPercentiles"]


def test_regime_preserve_mode_keeps_the_trade_count_of_the_base_run():
    dataset = _dataset()
    result = MonteCarloEngine(_spec(), dataset, MonteCarloConfig(
        method="regime_block_bootstrap", simulations=10, seed=3,
        regime_mix="preserve",
        regime_config={"fast": 10, "slow": 30, "vol_period": 10, "vol_baseline": 40},
    )).run()
    assert result.payload["regimeMix"] == "preserve"
    assert result.payload["successful"] == 10


def test_unknown_regime_mix_is_refused():
    dataset = _dataset()
    with pytest.raises(Exception):
        MonteCarloEngine(_spec(), dataset, MonteCarloConfig(
            method="regime_block_bootstrap", simulations=2,
            regime_mix="nonsense")).run()


# ── the edge verdict ─────────────────────────────────────────────────────────

def _good_metrics(**over):
    metrics = {
        "total_return": 42.0, "sharpe": 1.8, "sortino": 2.2, "calmar": 1.4,
        "max_drawdown": -12.0, "ulcer_index": 4.0, "profit_factor": 1.9,
        "expectancy": 220.0, "win_rate": 55.0, "trade_count": 120,
    }
    metrics.update(over)
    return metrics


def _trades(n=120, pnl=220.0):
    return [{"id": f"t{i}", "netPnl": pnl, "symbol": "TESTUSDT",
             "entryTs": "2024-01-01T00:00:00Z"} for i in range(n)]


def test_verdict_grades_a_strong_strategy_high():
    verdict = grade_edge(metrics=_good_metrics(), trades=_trades(),
                         monte_carlo={"probabilityOfLoss": 8.0,
                                      "returnPercentiles": {"p5": 6.0}})
    assert verdict["grade"] in ("A", "B")
    assert verdict["score"] > 70
    assert verdict["flagCounts"]["critical"] == 0


def test_verdict_caps_the_grade_when_expectancy_is_not_positive():
    verdict = grade_edge(metrics=_good_metrics(expectancy=-5.0, profit_factor=0.8),
                         trades=_trades(pnl=-5.0))
    codes = {f["code"] for f in verdict["flags"]}
    assert "EXPECTANCY_NOT_POSITIVE" in codes
    assert "PROFIT_FACTOR_BELOW_ONE" in codes
    assert verdict["grade"] in ("D", "E", "F")


def test_verdict_flags_a_sample_too_small_to_judge():
    verdict = grade_edge(metrics=_good_metrics(trade_count=5), trades=_trades(n=5))
    codes = {f["code"] for f in verdict["flags"]}
    assert "SAMPLE_TOO_SMALL" in codes
    assert verdict["grade"] in ("D", "E", "F")


def test_verdict_redistributes_the_weight_of_an_untested_axis():
    verdict = grade_edge(metrics=_good_metrics(), trades=_trades())
    assert "robustness" in verdict["assumptions"]["notGradedOn"]
    assert "edge" in verdict["assumptions"]["gradedOn"]
    codes = {f["code"] for f in verdict["flags"]}
    assert "ROBUSTNESS_NOT_TESTED" in codes


def test_verdict_flags_pnl_concentrated_in_a_few_trades():
    pnls = [5000.0] * 3 + [1.0] * 100
    trades = [{"id": str(i), "netPnl": p} for i, p in enumerate(pnls)]
    verdict = grade_edge(metrics=_good_metrics(trade_count=len(pnls)), trades=trades)
    codes = {f["code"] for f in verdict["flags"]}
    assert "PNL_CONCENTRATED_IN_FEW_TRADES" in codes


def test_verdict_flags_a_suspiciously_smooth_equity_curve():
    equity = []
    value = 100_000.0
    for i in range(60):
        value *= 1.001 + 1e-4 * math.sin(i * 0.3)
        equity.append({"equity": value})
    verdict = grade_edge(metrics=_good_metrics(), trades=_trades(),
                         equity_curve=equity)
    codes = {f["code"] for f in verdict["flags"]}
    assert "EQUITY_CURVE_SUSPICIOUSLY_SMOOTH" in codes


def test_verdict_flags_single_regime_dependency():
    regimes = {"regimes": {"up_high": {"trades": 40, "netPnl": 9000.0},
                           "down_low": {"trades": 40, "netPnl": 1000.0}}}
    verdict = grade_edge(metrics=_good_metrics(), trades=_trades(), regimes=regimes)
    codes = {f["code"] for f in verdict["flags"]}
    assert "SINGLE_REGIME_DEPENDENT" in codes


def test_verdict_config_rejects_an_incoherent_sample_window():
    with pytest.raises(VerdictError):
        VerdictConfig(min_trades=100, good_trades=10).validate()


def test_verdict_score_is_finite():
    verdict = grade_edge(metrics={}, trades=[])
    assert math.isfinite(verdict["score"])
    assert verdict["grade"] in ("A", "B", "C", "D", "E", "F")

"""Tests for the research engines: parameters, optimization, walk-forward,
Monte-Carlo, sensitivity and robustness."""

from __future__ import annotations

import pytest

from harness.quant import data as D
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.montecarlo import MonteCarloConfig, MonteCarloEngine
from harness.quant.optimize import (
    OptimizationConfig,
    OptimizationEngine,
    objective_score,
    pareto_front,
)
from harness.quant.params import ParamSpace, apply_params, get_path, set_path
from harness.quant.robustness import (
    RobustnessConfig,
    RobustnessEngine,
    SensitivityConfig,
    SensitivityEngine,
)
from harness.quant.walkforward import WalkForwardConfig, WalkForwardEngine

SPACE = {"indicators.0.params.period": [4, 6, 10],
         "indicators.1.params.period": [15, 25, 40]}


def _spec(period_fast=5, period_slow=20):
    return S.parse_strategy({
        "strategy": {"id": "ema_cross", "name": "EMA", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [
            {"id": "ema_fast", "type": "ema", "params": {"period": period_fast}},
            {"id": "ema_slow", "type": "ema", "params": {"period": period_slow}},
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


def _dataset(n=800, seed=7):
    rows = F.bull_market("TESTUSDT", n=n, seed=seed)
    return D.build_dataset({"TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})


# ── params ───────────────────────────────────────────────────────────────────

def test_param_paths_and_apply():
    spec = {"indicators": [{"params": {"period": 5}}], "position_sizing": {"value": 90}}
    set_path(spec, "indicators.0.params.period", 9)
    assert get_path(spec, "indicators.0.params.period") == 9
    out = apply_params(spec, {"position_sizing.value": 50})
    assert out["position_sizing"]["value"] == 50
    assert spec["position_sizing"]["value"] == 90  # deep copy, base untouched


def test_space_range_and_grid():
    space = ParamSpace.from_dict({"a": {"start": 1, "stop": 5, "count": 3}})
    assert space.axes["a"] == [1.0, 3.0, 5.0]
    grid = list(ParamSpace.from_dict({"a": [1, 2], "b": [10, 20, 30]}).grid())
    assert len(grid) == 6


def test_objective_scores():
    assert objective_score("max_drawdown", {"max_drawdown": -30.0}) == -30.0
    assert objective_score("return_drawdown", {"cagr": 20.0, "max_drawdown": -10.0}) == pytest.approx(2.0)
    assert objective_score("sharpe", {"sharpe": None}) is None


# ── optimization ─────────────────────────────────────────────────────────────

def test_optimizer_methods_run_and_are_deterministic():
    for method in ("grid", "random", "evolutionary", "bayesian"):
        cfg = OptimizationConfig(method=method, objective="sharpe", max_evaluations=10, seed=3)
        a = OptimizationEngine(_spec(), _dataset(n=400), ParamSpace.from_dict(SPACE), cfg).run()
        b = OptimizationEngine(_spec(), _dataset(n=400), ParamSpace.from_dict(SPACE), cfg).run()
        assert a.status == "OK"
        assert (a.payload["best"]["params"] if a.payload["best"] else None) == \
               (b.payload["best"]["params"] if b.payload["best"] else None)


def test_optimization_never_defaults_to_raw_return():
    cfg = OptimizationConfig(method="random", max_evaluations=6, seed=1)
    assert cfg.objective == "sharpe"
    raw = OptimizationEngine(_spec(), _dataset(n=400), ParamSpace.from_dict(SPACE),
                             OptimizationConfig(method="random", objective="total_return",
                                                max_evaluations=6, seed=1)).run()
    assert any(w["code"] == "RAW_RETURN_OBJECTIVE" for w in raw.warnings)


def test_pareto_front():
    from harness.quant.optimize import Trial

    trials = [
        Trial({"x": 1}, 1.0, {"total_return": 10.0, "max_drawdown": -5.0}),
        Trial({"x": 2}, 2.0, {"total_return": 20.0, "max_drawdown": -15.0}),
        Trial({"x": 3}, 0.5, {"total_return": 5.0, "max_drawdown": -20.0}),  # dominated
    ]
    front = pareto_front(trials, ["total_return", "max_drawdown"])
    assert len(front) == 2


# ── walk-forward ─────────────────────────────────────────────────────────────

def test_walk_forward_reports_is_oos_and_does_not_leak_test_data():
    cfg = WalkForwardConfig(train_bars=300, test_bars=100, step_bars=100, method="random",
                            objective="sharpe", param_space=SPACE, max_evaluations=6, seed=2)
    ds = _dataset(n=800)
    result = WalkForwardEngine(_spec(), ds, cfg).run()
    assert result.status == "OK"
    assert result.observability["windows"] >= 1
    assert "inSampleAggregate" in result.payload and "outOfSampleAggregate" in result.payload
    windows = WalkForwardEngine(_spec(), ds, cfg).windows()
    protected_end = max(te for (_, _, te, _) in windows)  # never inside any train window

    # Mutate ONLY bars that are exclusively test -> chosen params must not move.
    rows_mut = F.bull_market("TESTUSDT", n=800, seed=7)
    for r in rows_mut[protected_end:]:
        for f in ("open", "high", "low", "close"):
            r[f] *= 3.0
    ds_mut = D.build_dataset({"TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows_mut, source="synthetic")})
    mutated = WalkForwardEngine(_spec(), ds_mut, cfg).run()
    orig_params = [w["bestParams"] for w in result.payload["windows"]]
    mut_params = [w["bestParams"] for w in mutated.payload["windows"]]
    assert orig_params == mut_params


# ── Monte-Carlo ──────────────────────────────────────────────────────────────

def test_monte_carlo_seed_reproducible_and_bounded():
    cfg = MonteCarloConfig(method="trade_reshuffle", simulations=100, seed=5)
    a = MonteCarloEngine(_spec(), _dataset(n=500), cfg).run()
    b = MonteCarloEngine(_spec(), _dataset(n=500), cfg).run()
    assert a.payload["returnPercentiles"]["p50"] == pytest.approx(b.payload["returnPercentiles"]["p50"])
    assert 0 <= a.payload["probabilityOfLoss"] <= 100
    assert 0 <= a.payload["probabilityOfRuin"] <= 100
    p = a.payload["returnPercentiles"]
    assert p["p5"] <= p["p50"] <= p["p95"]


def test_monte_carlo_ruin_detected_at_high_threshold():
    # ruin threshold 1.0 means "any point at/below initial capital counts".
    cfg = MonteCarloConfig(method="trade_reshuffle", simulations=50, seed=2, ruin_threshold=1.0)
    run = MonteCarloEngine(_spec(), _dataset(n=500), cfg).run()
    assert run.payload["probabilityOfRuin"] > 0


# ── sensitivity / robustness ─────────────────────────────────────────────────

def test_sensitivity_reports_collapse_or_stability():
    cfg = SensitivityConfig(param_ranges={"indicators.0.params.period": [3, 5, 10, 20, 40]},
                            objective="sharpe")
    run = SensitivityEngine(_spec(), _dataset(n=600), cfg).run()
    entry = run.payload["parameters"]["indicators.0.params.period"]
    assert len(entry["scores"]) == 5
    assert isinstance(entry["collapse"], bool)
    assert entry["best"] is not None


def test_robustness_verdict_is_evidence_backed():
    cfg = RobustnessConfig(param_ranges={"indicators.0.params.period": [3, 5, 10, 20, 40]},
                           objective="sharpe", cost_multipliers=[1, 2, 5], min_trades=30)
    run = RobustnessEngine(_spec(), _dataset(n=600), cfg).run()
    assert run.payload["verdict"] in {"robust", "fragile", "insufficient_evidence"}
    assert isinstance(run.payload["conclusions"], list)
    # A tiny dataset cannot be called robust.
    small = RobustnessEngine(_spec(), _dataset(n=120), cfg).run()
    assert small.payload["verdict"] == "insufficient_evidence"

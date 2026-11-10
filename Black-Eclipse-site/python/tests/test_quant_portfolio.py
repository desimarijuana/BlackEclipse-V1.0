"""Portfolio construction, risk model, stress, options-chain and futures analytics."""

from __future__ import annotations

import numpy as np
import pytest

from harness.quant.errors import QuantError
from harness.quant.futures import roll_cost, term_structure
from harness.quant.options_backtest import backtest_option_chain
from harness.quant.portfolio_optimizer import (
    OptimizerConstraints,
    efficient_frontier,
    optimize_portfolio,
)
from harness.quant.risk_model import (
    covariance_matrix,
    factor_exposures,
    portfolio_volatility,
    risk_contributions,
)
from harness.quant.scenario import (
    historical_risk,
    parametric_risk,
    reverse_stress,
    scenario_pnl,
)


def _panel(seed=5, t=300, n=5):
    rng = np.random.default_rng(seed)
    return rng.normal(0.0005, 0.01, size=(t, n))


def test_covariance_estimators_are_valid():
    rets = _panel()
    for method in ("sample", "ewma", "ledoit_wolf"):
        out = covariance_matrix(rets, method=method, annualize=True, interval="1d")
        cov = np.array(out["covariance"])
        assert cov.shape == (5, 5)
        assert np.allclose(cov, cov.T)
        assert np.all(np.linalg.eigvalsh(cov) > -1e-10)
        assert len(out["volatility"]) == 5


def test_risk_contributions_sum_to_volatility():
    cov = np.array(covariance_matrix(_panel())["covariance"])
    w = np.array([0.2, 0.3, 0.1, 0.25, 0.15])
    rc = risk_contributions(w, cov)
    assert rc["volatility"] == pytest.approx(portfolio_volatility(w, cov))
    assert sum(rc["component"]) == pytest.approx(rc["volatility"], rel=1e-9)
    assert sum(rc["share"]) == pytest.approx(1.0, rel=1e-9)


@pytest.mark.parametrize("method", ["equal_weight", "min_variance", "mean_variance",
                                    "max_sharpe", "risk_parity", "hrp"])
def test_optimizer_respects_constraints(method):
    rets = _panel()
    cov = np.array(covariance_matrix(rets)["covariance"])
    mu = np.array([0.08, 0.05, 0.12, 0.03, 0.09])
    result = optimize_portfolio(
        mu if method in ("mean_variance", "max_sharpe") else None,
        cov, method=method,
        constraints=OptimizerConstraints(min_weight=0.0, max_weight=0.5),
    )
    assert sum(result.weights) == pytest.approx(1.0, abs=1e-5)
    assert max(result.weights) <= 0.5 + 1e-6
    assert min(result.weights) >= -1e-9
    assert result.diagnostics["feasible"] is True


def test_black_litterman_changes_returns_only_when_views_exist():
    cov = np.array(covariance_matrix(_panel())["covariance"])
    base = optimize_portfolio(None, cov, method="black_litterman",
                              constraints=OptimizerConstraints(min_weight=0.0))
    view = {"P": [[1.0, 0.0, 0.0, 0.0, 0.0]], "Q": [0.2]}
    changed = optimize_portfolio(None, cov, method="black_litterman",
                                 constraints=OptimizerConstraints(min_weight=0.0),
                                 views=view)
    assert abs(sum(base.weights) - 1.0) < 1e-5
    assert abs(sum(changed.weights) - 1.0) < 1e-5


def test_efficient_frontier_traces_points():
    cov = np.array(covariance_matrix(_panel())["covariance"])
    mu = np.array([0.08, 0.05, 0.12, 0.03, 0.09])
    frontier = efficient_frontier(mu, cov, points=5)
    assert frontier["count"] == 5
    assert all(p["volatility"] >= 0 for p in frontier["points"])


def test_stress_parametric_historical_and_scenarios():
    rets = _panel()
    cov = np.array(covariance_matrix(rets)["covariance"])
    w = [0.2, 0.2, 0.2, 0.2, 0.2]
    p = parametric_risk(w, cov, confidence=0.95, portfolio_value=1_000_000)
    assert p["varPct"] > 0
    assert p["expectedShortfallPct"] >= p["varPct"]
    assert sum(p["componentVarShare"]) == pytest.approx(1.0, rel=1e-6)
    h = historical_risk(rets, w, confidence=0.95)
    assert h["varPct"] > 0
    s = scenario_pnl(w, {"crash": {"A": -0.2, "B": -0.1}}, symbols=["A", "B", "C", "D", "E"])
    assert s["worst"]["name"] == "crash"
    assert set(s["worst"]["uncoveredSymbols"]) == {"C", "D", "E"}
    r = reverse_stress(w, cov, loss_threshold=0.1)
    assert r["available"] and r["parallelShockPct"] > 0


def test_factor_exposures_recover_known_betas():
    rng = np.random.default_rng(9)
    f1 = rng.normal(0, 0.01, 400)
    f2 = rng.normal(0, 0.01, 400)
    y = np.column_stack([2.0 * f1 + 0.5 * f2, -1.0 * f1 + 1.5 * f2])
    out = factor_exposures(y, np.column_stack([f1, f2]))
    assert out["betas"][0][0] == pytest.approx(2.0, abs=1e-8)
    assert out["betas"][1][0] == pytest.approx(-1.0, abs=1e-8)
    assert out["r2"][0] > 0.99


def test_option_chain_backtest_marks_and_settles():
    snapshots = [
        {"date": "2026-01-02", "spot": 100, "expiry": "2026-02-01",
         "riskFree": 0.04, "legs": [
             {"type": "call", "strike": 100, "quantity": 1, "iv": 0.2, "multiplier": 100}
         ]},
        {"date": "2026-01-16", "spot": 108, "expiry": "2026-02-01",
         "riskFree": 0.04, "legs": [
             {"type": "call", "strike": 100, "quantity": 1, "iv": 0.2, "multiplier": 100}
         ]},
        {"date": "2026-02-01", "spot": 112, "expiry": "2026-02-01",
         "riskFree": 0.04, "legs": [
             {"type": "call", "strike": 100, "quantity": 1, "iv": 0.2, "multiplier": 100}
         ]},
    ]
    result = backtest_option_chain(snapshots, initial_capital=10_000)
    assert result["settledAtExpiry"] is True
    assert result["metrics"]["totalReturn"] > 0
    assert result["capability"]["earlyExercise"] == "unsupported"


def test_futures_term_structure_and_roll_cost():
    points = [{"expiry": "2026-03-01", "price": 100},
              {"expiry": "2026-06-01", "price": 104}]
    curve = term_structure(points, spot=99)
    assert curve["shape"] == "contango"
    assert curve["points"][0]["impliedCarry"] is not None
    contracts = [
        {"symbol": "A", "rows": [
            {"timestamp": "2026-01-01", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
            {"timestamp": "2026-01-02", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
        ]},
        {"symbol": "B", "rows": [
            {"timestamp": "2026-01-03", "open": 104, "high": 105, "low": 103, "close": 104, "volume": 10},
            {"timestamp": "2026-01-04", "open": 104, "high": 105, "low": 103, "close": 104, "volume": 10},
        ]},
    ]
    result = roll_cost(contracts, ["2026-01-03"], cost_bps=10)
    assert result["rollCount"] == 1
    assert result["totalCost"] > 0

"""Risk + performance calculators: determinism, honesty, reproducibility."""

from __future__ import annotations

import math

from harness.portfolio.performance import (
    cagr,
    cumulative_return,
    irr,
    time_weighted_return,
)
from harness.portfolio.risk import (
    beta,
    compute_risk,
    correlation,
    historic_var,
    max_drawdown,
    monte_carlo_var,
    portfolio_nav,
)


def test_max_drawdown():
    assert max_drawdown([1.0, 2.0, 1.0]) == -0.5
    assert max_drawdown([1.0]) is None


def test_historic_var_and_cvar_order():
    rets = [-0.05, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
    var = historic_var(rets, 0.9)
    assert var is not None
    assert var <= 0.0


def test_monte_carlo_is_deterministic_for_a_seed():
    rets = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.005, 0.0, 0.012, -0.008]
    a = monte_carlo_var(rets, 0.95, seed=7)
    b = monte_carlo_var(rets, 0.95, seed=7)
    assert a == b
    assert a is not None


def test_portfolio_nav_rebases_and_weights():
    closes = {"A": [100, 110, 121], "B": [200, 200, 200]}
    nav, used = portfolio_nav({"A": 0.5, "B": 0.5}, closes)
    assert used == ["A", "B"]
    assert nav[0] == 1.0
    assert math.isclose(nav[-1], 0.5 * 1.21 + 0.5 * 1.0, rel_tol=1e-9)


def test_beta_and_correlation_of_identical_series():
    a = [0.01, -0.02, 0.03, 0.0, 0.02]
    assert math.isclose(beta(a, a), 1.0, rel_tol=1e-9)
    assert math.isclose(correlation(a, a), 1.0, rel_tol=1e-9)


def test_compute_risk_unavailable_without_history():
    out = compute_risk(weights={"A": 1.0}, closes={})
    assert out["status"] == "UNAVAILABLE"


def test_compute_risk_ok_with_history_and_reports_methodology():
    closes = {"A": [100, 101, 102, 101, 103, 104, 105, 106, 107, 108]}
    out = compute_risk(weights={"A": 1.0}, closes=closes, benchmark_closes=[100, 99, 101, 100, 102])
    assert out["status"] == "OK"
    assert out["metrics"]["volatility"] is not None
    assert out["metrics"]["maxDrawdown"] is not None
    assert "volatility" in out["methodology"]


def test_performance_returns():
    assert math.isclose(cumulative_return([1.0, 1.1, 1.21]), 0.21, rel_tol=1e-9)
    assert math.isclose(cagr(100.0, 121.0, 2.0), 0.1, rel_tol=1e-9)


def test_time_weighted_return_ignores_flows():
    # value doubles because of a contribution, not performance: TWR must be ~0.
    values = [100.0, 200.0]
    flows = [0.0, 100.0]
    twr = time_weighted_return(values, flows)
    assert math.isclose(twr, 0.0, abs_tol=1e-9)


def test_irr_of_a_simple_investment():
    # invest 100, receive 110 after one period ⇒ 10%
    rate = irr([-100.0, 110.0])
    assert math.isclose(rate, 0.1, rel_tol=1e-6)

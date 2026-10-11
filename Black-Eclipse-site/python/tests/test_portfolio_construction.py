"""Deterministic numerical tests for the Portfolio Construction & Risk Engine.

Every expected value here is computed by hand from an analytically known small
problem — not copied from the implementation.
"""

from __future__ import annotations

import math

import pytest

from harness.portfolio import construction as C
from harness.portfolio.costs import transaction_costs, turnover
from harness.portfolio.estimation import (align_returns, estimate_covariance,
                                           estimate_expected_returns)
from harness.portfolio.risk_engine import (hypothetical_impact, monte_carlo,
                                            risk_contributions, stress_test)


def construct(symbols, method, **kw):
    return C.construct(symbols=symbols, method=method,
                       covariance=kw.pop("covariance"), constraints_payload=kw.pop("constraints", {}),
                       **kw)


# ── Equal weight ──────────────────────────────────────────────────────────────

def test_equal_weight_is_uniform():
    r = construct(["A", "B", "C", "D"], "equal_weight", covariance=[[1.0 if i == j else 0 for j in range(4)]
                                                                     for i in range(4)])
    assert r["status"] == "OPTIMAL"
    assert r["allocation"] == "equal"
    assert all(abs(v - 0.25) < 1e-9 for v in r["weights"].values())


def test_equal_weight_respects_a_cap():
    cov = [[0.04, 0, 0], [0, 0.04, 0], [0, 0, 0.04]]
    r = construct(["A", "B", "C"], "equal_weight", covariance=cov,
                  constraints={"max_weights": {"A": 0.2}})
    assert r["allocation"] == "constrained_equal_weight"
    assert r["weights"]["A"] <= 0.2 + 1e-7
    assert r["validation"]["satisfied"]


# ── Minimum variance (analytic) ───────────────────────────────────────────────

def test_min_variance_two_asset_analytic():
    cov = [[0.04, 0.01], [0.01, 0.09]]
    r = construct(["A", "B"], "min_variance", covariance=cov)
    # w1 = (c - b) / (a + c - 2b) = 0.08 / 0.11
    assert abs(r["weights"]["A"] - 0.08 / 0.11) < 1e-6
    assert abs(r["weights"]["B"] - 0.03 / 0.11) < 1e-6


def test_min_variance_identity_is_equal():
    cov = [[0.05, 0, 0], [0, 0.05, 0], [0, 0, 0.05]]
    r = construct(["A", "B", "C"], "min_variance", covariance=cov)
    assert all(abs(v - 1 / 3) < 1e-6 for v in r["weights"].values())


# ── Mean variance (analytic) ──────────────────────────────────────────────────

def test_mean_variance_analytic_scales_with_risk_aversion():
    cov = [[1.0, 0.0], [0.0, 1.0]]
    r = construct(["A", "B"], "mean_variance", covariance=cov,
                  expected_returns=[0.10, 0.05], risk_aversion=1.0)
    # w_i = mu_i/λ + c, Σw = 1 -> c = (1 - 0.15)/2 = 0.425
    assert abs(r["weights"]["A"] - 0.525) < 1e-5
    assert abs(r["weights"]["B"] - 0.475) < 1e-5


# ── Risk parity (ERC) ─────────────────────────────────────────────────────────

def test_risk_parity_equal_risk_contributions():
    cov = [[0.04, 0.0], [0.0, 0.01]]
    r = construct(["A", "B"], "risk_parity", covariance=cov)
    # w ∝ 1/σ -> [1/0.2, 1/0.1] normalized = [1/3, 2/3]
    assert abs(r["weights"]["A"] - 1 / 3) < 1e-6
    assert abs(r["weights"]["B"] - 2 / 3) < 1e-6
    comps = [v["component"] for v in r["riskContributions"]["riskContributions"].values()]
    assert abs(comps[0] - comps[1]) < 1e-8
    assert r["riskContributions"]["reconciliation"]["reconciles"]


def test_risk_parity_custom_budgets():
    cov = [[0.04, 0.0], [0.0, 0.04]]
    r = construct(["A", "B"], "risk_parity", covariance=cov, risk_budgets=[0.75, 0.25])
    shares = [v["shareOfVariance"] for v in r["riskContributions"]["riskContributions"].values()]
    assert abs(shares[0] - 0.75) < 1e-6 and abs(shares[1] - 0.25) < 1e-6


# ── Volatility target ─────────────────────────────────────────────────────────

def test_volatility_target_achieves_target_or_reports():
    cov = [[0.0004, 0.0], [0.0, 0.0004]]  # 2% daily vol, uncorrelated
    r = construct(["A", "B"], "volatility_target", covariance=cov, target_volatility=0.15)
    assert r["status"] in ("OPTIMAL", "OPTIMAL_INACCURATE")
    assert abs(r["metrics"]["achievedVolatility"] - 0.15) < 1e-6
    assert "cashWeight" in r


# ── Benchmark weight ──────────────────────────────────────────────────────────

def test_benchmark_weight_replicates():
    cov = [[0.04, 0, 0], [0, 0.04, 0], [0, 0, 0.04]]
    r = construct(["A", "B", "C"], "benchmark_weight", covariance=cov,
                  benchmark_weights={"A": 0.5, "B": 0.3, "C": 0.2})
    assert abs(r["weights"]["A"] - 0.5) < 1e-9

    missing = construct(["A", "B", "C"], "benchmark_weight", covariance=cov,
                        benchmark_weights={"A": 0.5})
    assert missing["available"] is False and missing["status"] == "INFEASIBLE"


# ── Black–Litterman ───────────────────────────────────────────────────────────

def test_black_litterman_equilibrium_returns():
    cov = [[0.04, 0.0], [0.0, 0.09]]
    r = construct(["A", "B"], "black_litterman", covariance=cov,
                  market_weights=[0.6, 0.4], risk_aversion=2.5)
    # Π = δΣw_mkt = [2.5*0.04*0.6, 2.5*0.09*0.4] = [0.06, 0.09]
    assert abs(r["equilibriumReturns"]["A"] - 0.06) < 1e-9
    assert abs(r["equilibriumReturns"]["B"] - 0.09) < 1e-9


def test_black_litterman_view_tilts_posterior_by_scopes():
    cov = [[0.04, 0.0], [0.0, 0.04]]
    r = construct(["A", "B"], "black_litterman", covariance=cov,
                  market_weights=[0.5, 0.5],
                  views=[{"scope": {"A": 1.0, "B": -1.0}, "return": 0.10, "confidence": 0.7}])
    # A relative view (A outperforms B) must push Π_A above Π_B.
    assert r["posteriorReturns"]["A"] > r["posteriorReturns"]["B"]


# ── Factor constrained ────────────────────────────────────────────────────────

def test_factor_constrained_cap_is_enforced():
    cov = [[0.04, 0, 0], [0, 0.04, 0], [0, 0, 0.04]]
    r = construct(["A", "B", "C"], "factor_constrained", covariance=cov,
                  expected_returns=[0.12, 0.08, 0.04],
                  factor_loadings={"A": {"mkt": 1.5}, "B": {"mkt": 1.0}, "C": {"mkt": 0.2}},
                  factor_constraints=[{"factor": "mkt", "max": 0.8}])
    exposure = r["factorExposures"]["mkt"]
    assert exposure <= 0.8 + 1e-6
    assert r["validation"]["satisfied"]


# ── Constraint failures ───────────────────────────────────────────────────────

def test_infeasible_max_weights_is_diagnosed():
    cov = [[0.04, 0, 0], [0, 0.04, 0], [0, 0, 0.04]]
    r = construct(["A", "B", "C"], "min_variance", covariance=cov,
                  constraints={"max_weights": {"A": 0.1, "B": 0.1, "C": 0.1}})
    assert r["status"] == "INFEASIBLE"
    assert r["weights"] == {}


def test_unknown_method_is_solver_error():
    r = C.construct(symbols=["A"], method="does_not_exist", covariance=[[0.04]])
    assert r["available"] is False and r["status"] == "SOLVER_ERROR"


def test_covariance_dimension_mismatch():
    r = C.construct(symbols=["A", "B"], method="min_variance", covariance=[[0.04]])
    assert r["available"] is False and r["status"] == "SOLVER_ERROR"


# ── Estimation ────────────────────────────────────────────────────────────────

def test_estimate_covariance_sample_known_value():
    a = [0.01, -0.01, 0.02, -0.02, 0.0]
    b = [0.02, 0.00, -0.01, 0.01, -0.02]
    res = estimate_covariance({"A": a, "B": b}, method="sample", ddof=1)
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    expected = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)
    # matrix is aligned to sorted symbols A, B
    assert abs(res["covariance"][0][1] - expected) < 1e-12
    assert res["diagnostics"]["symmetric"] and res["diagnostics"]["positiveSemidefinite"]


def test_estimate_expected_returns_geometric_le_arithmetic():
    rets = {"A": [0.10, -0.05, 0.03, 0.02]}
    arith = estimate_expected_returns(rets, method="arithmetic")
    geo = estimate_expected_returns(rets, method="geometric")
    assert geo["expectedReturns"]["A"] < arith["expectedReturns"]["A"]


def test_estimate_covariance_flags_rank_deficiency():
    # 3 assets, 2 observations -> rank-deficient sample covariance (singular).
    rets = {"A": [0.01, 0.02], "B": [0.02, 0.04], "C": [0.03, 0.06]}
    res = estimate_covariance(rets, method="sample", regularize=True)
    assert res["diagnostics"]["positiveSemidefinite"]
    assert res["diagnostics"]["conditionNumber"] is None  # singular


def test_nearest_psd_regularizer_repairs_indefinite_matrix():
    from harness.portfolio.estimation import _nearest_psd
    indefinite = [[0.04, 0.10], [0.10, 0.01]]  # not PSD (det < 0)
    repaired, shift = _nearest_psd(indefinite)
    assert shift > 0
    import numpy as np
    assert np.linalg.eigvalsh(np.array(repaired)).min() >= -1e-12


def test_align_returns_drops_missing_and_reports():
    series = {
        "A": [{"date": "2024-01-01", "close": 10}, {"date": "2024-01-02", "close": 11},
              {"date": "2024-01-03", "close": 12}, {"date": "2024-01-04", "close": 13}],
        "B": [{"date": "2024-01-01", "close": 5}, {"date": "2024-01-02", "close": 5.5},
              {"date": "2024-01-03", "close": 5.4}, {"date": "2024-01-04", "close": 5.6}],
        "C": [{"date": "2024-01-01", "close": 1}],
    }
    aligned = align_returns(series)
    # common dates for A and B = 4 -> 3 returns; C dropped (<2 observations).
    assert "C" in aligned["excluded"]
    assert aligned["observations"] == 3


# ── Risk contributions ────────────────────────────────────────────────────────

def test_risk_contributions_reconcile_and_preserve_short_sign():
    # A short leg that hedges can carry a NEGATIVE risk contribution; it must be
    # reported, not clamped to zero.
    cov = [[0.09, 0.03], [0.03, 0.04]]
    r = risk_contributions({"A": 1.0, "B": -0.5}, cov, names=["A", "B"])
    assert r["reconciliation"]["reconciles"]
    assert r["riskContributions"]["B"]["component"] < 0


def test_group_risk_contributions_sum():
    cov = [[0.04, 0, 0], [0, 0.04, 0], [0, 0, 0.04]]
    r = risk_contributions({"A": 0.5, "B": 0.3, "C": 0.2}, cov, names=["A", "B", "C"],
                           groups={"A": "tech", "B": "tech", "C": "fin"})
    groups = r["groupContributions"]
    assert abs(sum(groups.values()) - r["portfolioVolatility"]) < 1e-8


# ── Stress testing ────────────────────────────────────────────────────────────

def test_hypothetical_shock_linear():
    r = hypothetical_impact({"A": 0.6, "B": 0.4}, {"A": -0.25})
    assert abs(r["portfolioReturn"] - (-0.15)) < 1e-12


def test_monte_carlo_is_seeded_and_reproducible():
    cov = [[0.0004, 0.0001], [0.0001, 0.0009]]
    a = monte_carlo({"A": 0.5, "B": 0.5}, cov, seed=7, simulations=2000)
    b = monte_carlo({"A": 0.5, "B": 0.5}, cov, seed=7, simulations=2000)
    assert a["var"] == b["var"]
    assert a["cvar"] <= a["var"]


def test_stress_test_runs_multiple_scenarios():
    out = stress_test({"A": 0.6, "B": 0.4}, scenarios=[
        {"name": "drawdown", "type": "hypothetical", "shocks": {"A": -0.3, "B": -0.1}},
        {"name": "historic", "type": "historical", "returns": {"A": [-0.1, 0.2], "B": [-0.05, 0.1]}},
    ])
    assert out["available"] and len(out["scenarios"]) == 2


# ── Turnover and costs ────────────────────────────────────────────────────────

def test_turnover_convention():
    to = turnover({"A": 0.5, "B": 0.5}, {"A": 0.6, "B": 0.4})
    assert abs(to["oneWayTurnover"] - 0.1) < 1e-12
    assert abs(to["grossTradedNotional"] - 0.2) < 1e-12


def test_transaction_costs_commission_and_notes():
    costs = transaction_costs({"A": 0.1, "B": -0.1}, commission_rate=0.001)
    assert abs(costs["components"]["commission"] - 0.0002) < 1e-12
    assert costs["notes"]  # no half-spread supplied -> explicit note


# ── Tool registry integration ─────────────────────────────────────────────────

async def test_construct_tool_proposal_via_registry(tmp_path):
    from harness.portfolio.tools import register_portfolio_tools
    from harness.tools import ToolContext, ToolRegistry
    from portfolio_helpers import make_portfolio, make_service

    reg = ToolRegistry()
    register_portfolio_tools(reg)
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)

    async def authorize(tool, args, ctx=None):
        return tool.name == "portfolio_construct"

    ctx = ToolContext(run_id="r", log=lambda *_: None, portfolio_service=svc,
                      authorize_effect=authorize)
    result = await reg.execute(
        "portfolio_construct", "c1",
        {"portfolio_id": pid, "symbols": ["A", "B"], "method": "min_variance",
         "covariance": [[0.04, 0.0], [0.0, 0.09]]}, ctx)
    assert result.ok
    assert result.data["available"] and result.data["weights"]
    assert "proposal-only" in result.data["execution"]
    assert result.data.get("planId")  # a proposal plan was persisted

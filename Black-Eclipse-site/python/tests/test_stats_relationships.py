"""Numerical correctness — correlation, beta, regression, lead-lag, IC."""

from __future__ import annotations

import numpy as np
import pytest

from harness.stats import run_tool, run_tool_safe


# ── calculate_correlation ────────────────────────────────────────────────────

def test_correlation_perfect_positive():
    out = run_tool("calculate_correlation", {"x": [1, 2, 3, 4, 5], "y": [2, 4, 6, 8, 10]})
    assert out["results"]["coefficient"] == pytest.approx(1.0, abs=1e-12)


def test_correlation_perfect_negative():
    out = run_tool("calculate_correlation", {"x": [1, 2, 3, 4, 5], "y": [10, 8, 6, 4, 2]})
    assert out["results"]["coefficient"] == pytest.approx(-1.0, abs=1e-12)


def test_spearman_monotonic_nonlinear():
    # strictly increasing but nonlinear -> Spearman = 1, Pearson < 1
    x = [1, 2, 3, 4, 5]
    y = [1, 4, 9, 16, 25]
    pear = run_tool("calculate_correlation", {"x": x, "y": y, "method": "pearson"})
    spear = run_tool("calculate_correlation", {"x": x, "y": y, "method": "spearman"})
    assert spear["results"]["coefficient"] == pytest.approx(1.0, abs=1e-12)
    assert pear["results"]["coefficient"] < 1.0


def test_correlation_matrix_symmetric_and_bounded():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, 100)
    b = a + rng.normal(0, 0.5, 100)
    c = rng.normal(0, 1, 100)
    out = run_tool("calculate_correlation", {"series": [a.tolist(), b.tolist(), c.tolist()]})
    m = out["results"]["correlationMatrix"]
    for i in range(3):
        assert m[i][i] == pytest.approx(1.0, abs=1e-9)
        for j in range(3):
            assert m[i][j] == pytest.approx(m[j][i], abs=1e-12)
            assert -1.000001 <= m[i][j] <= 1.000001


def test_correlation_zero_variance_series_is_nan():
    out = run_tool_safe("calculate_correlation", {"x": [1, 1, 1, 1], "y": [1, 2, 3, 4]})
    assert out["status"] == "ok"
    # NaN coefficient surfaces as null
    assert out["results"]["coefficient"] is None


# ── calculate_beta ───────────────────────────────────────────────────────────

def test_beta_exact_two():
    rng = np.random.default_rng(1)
    bench = rng.normal(0, 0.01, 200)
    asset = 2.0 * bench + 0.0 * rng.normal(0, 0.001, 200)  # near-exact
    out = run_tool("calculate_beta", {"asset": asset.tolist(), "benchmark": bench.tolist(),
                                      "inputType": "returns"})
    assert out["summary"]["beta"] == pytest.approx(2.0, abs=1e-6)
    assert out["summary"]["rSquared"] == pytest.approx(1.0, abs=1e-6)


def test_beta_alpha_annualization():
    rng = np.random.default_rng(2)
    bench = rng.normal(0, 0.01, 250)
    asset = 0.0005 + 1.0 * bench
    out = run_tool("calculate_beta", {"asset": asset.tolist(), "benchmark": bench.tolist(),
                                      "periodsPerYear": 252})
    assert out["summary"]["alphaAnnualized"] == pytest.approx(
        out["summary"]["alphaPerPeriod"] * 252, rel=1e-9)


def test_beta_robust_covariance_runs():
    rng = np.random.default_rng(3)
    bench = rng.normal(0, 0.01, 200)
    asset = 1.3 * bench + rng.normal(0, 0.005, 200)
    out = run_tool("calculate_beta", {"asset": asset.tolist(), "benchmark": bench.tolist(),
                                      "covType": "HC3"})
    assert out["results"]["coefficients"]["covType"] == "HC3"
    assert out["summary"]["beta"] == pytest.approx(1.3, abs=0.1)


# ── calculate_regression ─────────────────────────────────────────────────────

def test_regression_exact_linear():
    x = [1, 2, 3, 4, 5, 6, 7, 8]
    y = [3 + 2 * xi for xi in x]
    out = run_tool("calculate_regression", {"y": y, "x": [[v] for v in x]})
    coefs = out["results"]["coefficients"]["coefficients"]
    assert coefs[0] == pytest.approx(3.0, abs=1e-9)
    assert coefs[1] == pytest.approx(2.0, abs=1e-9)
    assert out["results"]["coefficients"]["rSquared"] == pytest.approx(1.0, abs=1e-9)


def test_regression_ridge_shrinks():
    rng = np.random.default_rng(5)
    X = rng.normal(0, 1, (200, 3))
    y = X @ np.array([1.0, -2.0, 0.5]) + rng.normal(0, 0.1, 200)
    ols = run_tool("calculate_regression", {"y": y.tolist(), "x": X.tolist(), "method": "ols"})
    ridge = run_tool("calculate_regression", {"y": y.tolist(), "x": X.tolist(),
                                              "method": "ridge", "alpha": 50.0})
    ols_norm = sum(c * c for c in ols["results"]["coefficients"]["coefficients"][1:])
    ridge_norm = sum(c * c for c in ridge["results"]["coefficients"]["coefficients"][1:])
    assert ridge_norm < ols_norm


def test_regression_lasso_sparsifies():
    rng = np.random.default_rng(6)
    X = rng.normal(0, 1, (300, 5))
    y = 3.0 * X[:, 0] + rng.normal(0, 0.1, 300)  # only one true signal
    out = run_tool("calculate_regression", {"y": y.tolist(), "x": X.tolist(),
                                            "method": "lasso", "alpha": 1.0})
    coefs = out["results"]["coefficients"]["coefficients"][1:]
    nonzero = sum(1 for c in coefs if abs(c) > 0.05)
    assert nonzero <= 2


def test_regression_out_of_sample_is_chronological():
    x = np.arange(100, dtype=float)
    y = 0.5 * x + np.random.default_rng(7).normal(0, 2, 100)
    out = run_tool("calculate_regression", {"y": y.tolist(), "x": x.reshape(-1, 1).tolist(),
                                            "trainFraction": 0.7})
    oos = out["results"]["outOfSample"]
    assert oos["trainSize"] == 70
    assert oos["testSize"] == 30


# ── analyze_lead_lag ─────────────────────────────────────────────────────────

def test_lead_lag_peak_at_known_lag():
    rng = np.random.default_rng(8)
    x = rng.normal(0, 1, 300)
    y = np.zeros(300)
    y[1:] = 0.9 * x[:-1] + rng.normal(0, 0.1, 299)  # x leads y by 1
    out = run_tool("analyze_lead_lag", {"predictor": x.tolist(), "target": y.tolist(),
                                        "maxLag": 5, "method": "cross_correlation"})
    assert out["summary"]["peakLag"] == 1


def test_granger_detects_predictive_direction():
    rng = np.random.default_rng(9)
    x = rng.normal(0, 1, 250)
    y = np.zeros(250)
    y[1:] = 0.7 * x[:-1] + rng.normal(0, 0.1, 249)
    out = run_tool("analyze_lead_lag", {"predictor": x.tolist(), "target": y.tolist(),
                                        "maxLag": 3, "method": "granger"})
    assert out["summary"]["grangerRejectsXtoY"] is True


# ── calculate_information_coefficient ────────────────────────────────────────

def test_ic_perfect_time_series():
    rng = np.random.default_rng(10)
    prices = 100 * np.cumprod(1 + rng.normal(0, 0.01, 120))
    fwd = np.full(120, np.nan)
    fwd[:-1] = prices[1:] / prices[:-1] - 1.0
    factor = fwd.copy()  # factor known at t equals next return (perfect oracle)
    out = run_tool("calculate_information_coefficient", {
        "factor": factor.tolist(), "forwardReturns": fwd.tolist(), "method": "pearson"})
    assert out["summary"]["ic"] == pytest.approx(1.0, abs=1e-9)


def test_ic_cross_sectional_averages_dates():
    rng = np.random.default_rng(11)
    factor = rng.normal(0, 1, (20, 30))
    fwd = factor * 0.01 + rng.normal(0, 0.001, (20, 30))
    out = run_tool("calculate_information_coefficient", {
        "factor": factor.tolist(), "forwardReturns": fwd.tolist(), "method": "pearson"})
    assert out["summary"]["meanIC"] > 0.9

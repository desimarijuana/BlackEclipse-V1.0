"""Correctness — regime, build_features, detect_outliers."""

from __future__ import annotations

import numpy as np
import pytest

from harness.stats import run_tool, run_tool_safe


# ── calculate_regime ─────────────────────────────────────────────────────────

def test_volatility_regimes_separate_low_and_high():
    rng = np.random.default_rng(0)
    r = np.concatenate([rng.normal(0, 0.005, 200), rng.normal(0, 0.03, 200)])
    prices = 100 * np.cumprod(1 + r)
    out = run_tool("calculate_regime", {"values": prices.tolist(), "method": "volatility",
                                        "window": 20, "nRegimes": 2})
    labels = out["results"]["regimeLabels"]
    late = int(out["diagnostics"]["counts"]["vol_q2"])
    assert late > 0
    # the high-volatility regime must dominate the second half
    tail = [lab for lab in labels[-50:] if lab >= 0]
    assert tail.count(max(set(tail), key=tail.count)) == tail.count(1) or tail.count(1) > 20


def test_changepoint_detects_mean_shift():
    rng = np.random.default_rng(1)
    r = np.concatenate([rng.normal(0, 0.01, 100), rng.normal(0, 0.01, 100) + 0.05])
    out = run_tool("calculate_regime", {"values": r.tolist(), "inputType": "returns",
                                        "method": "changepoint"})
    cps = out["diagnostics"]["changePoints"]
    assert any(90 <= cp <= 110 for cp in cps)


def test_hmm_two_states():
    rng = np.random.default_rng(2)
    r = np.concatenate([rng.normal(0, 0.005, 200), rng.normal(0, 0.02, 200)])
    out = run_tool("calculate_regime", {"values": r.tolist(), "inputType": "returns",
                                        "method": "hmm", "nRegimes": 2})
    tm = out["diagnostics"]["transitionMatrix"]
    variances = out["diagnostics"]["variances"]
    assert len(tm) == 2
    assert max(variances) / min(variances) > 4.0


def test_trend_range_labels_uptrend():
    r = np.linspace(0.001, 0.02, 60)
    out = run_tool("calculate_regime", {"values": r.tolist(), "inputType": "returns",
                                        "method": "trend_range", "window": 10})
    assert 1 in out["results"]["regimeLabels"]


# ── build_features ───────────────────────────────────────────────────────────

def test_feature_momentum_known_value():
    prices = [100.0, 110.0, 121.0]
    out = run_tool("build_features", {"values": prices, "features": [
        {"name": "mom", "type": "momentum", "params": {"n": 1}}]})
    mom = out["results"]["features"]["mom"]
    assert mom[1] == pytest.approx(0.10, abs=1e-12)
    assert mom[2] == pytest.approx(0.10, abs=1e-12)


def test_feature_formula_zscore():
    prices = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = run_tool("build_features", {"values": prices, "features": [
        {"name": "z", "expression": "zscore(close)"}]})
    z = np.array([v for v in out["results"]["features"]["z"] if v is not None])
    # z-score has zero mean and unit population stdev
    assert z.mean() == pytest.approx(0.0, abs=1e-9)
    assert z.std() == pytest.approx(1.0, abs=1e-9)


def test_feature_lookback_and_missingness_metadata():
    prices = list(np.linspace(100, 120, 50))
    out = run_tool("build_features", {"values": prices, "features": [
        {"name": "sma20", "type": "sma", "params": {"window": 20}}]})
    meta = out["results"]["featureMetadata"]["sma20"]
    assert meta["lookback"] == 20
    assert meta["warmUp"] == 20
    assert meta["pointInTimeSafe"] is True
    assert out["diagnostics"]["missingness"]["sma20"]["missingCount"] == 19


def test_feature_unknown_type_errors():
    out = run_tool_safe("build_features", {"values": [1.0] * 10, "features": [
        {"name": "x", "type": "not_a_feature"}]})
    assert out["status"] == "error"
    assert out["errors"][0]["code"] == "INVALID_INPUT"


# ── detect_outliers ──────────────────────────────────────────────────────────

def test_zscore_flags_injected_outlier():
    rng = np.random.default_rng(3)
    x = rng.normal(0, 1, 200)
    x[100] = 12.0
    out = run_tool("detect_outliers", {"values": x.tolist(), "method": "zscore", "threshold": 3.0})
    assert 100 in out["results"]["flaggedIndices"]


def test_mad_robust_to_mask_outlier():
    rng = np.random.default_rng(4)
    x = rng.normal(0, 1, 300)
    x[50] = 8.0
    out = run_tool("detect_outliers", {"values": x.tolist(), "method": "mad", "threshold": 3.5})
    assert 50 in out["results"]["flaggedIndices"]
    assert len(out["results"]["flaggedIndices"]) < 10


def test_iqr_fences():
    x = list(np.random.default_rng(5).normal(0, 1, 100)) + [50.0]
    out = run_tool("detect_outliers", {"values": x, "method": "iqr"})
    assert 100 in out["results"]["flaggedIndices"]


def test_isolation_forest_flags_outliers():
    rng = np.random.default_rng(6)
    x = rng.normal(0, 1, 300)
    x[10] = 20.0
    x[200] = -18.0
    out = run_tool("detect_outliers", {"values": x.tolist(), "method": "isolation_forest",
                                       "contamination": 0.02, "seed": 1})
    flagged = set(out["results"]["flaggedIndices"])
    assert 10 in flagged or 200 in flagged

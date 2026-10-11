"""Numerical correctness — stationarity (ADF/KPSS) and cointegration."""

from __future__ import annotations

import numpy as np
import pytest

from harness.stats import run_tool, run_tool_safe


def _random_walk(n=400, seed=0):
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.normal(0, 1, n))


# ── calculate_stationarity ───────────────────────────────────────────────────

def test_adf_does_not_reject_random_walk():
    x = _random_walk(seed=1)
    out = run_tool("calculate_stationarity", {"values": x.tolist(), "test": "adf"})
    assert out["results"]["adf"]["pValueApprox"] > 0.05


def test_adf_rejects_white_noise():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 1, 400)
    out = run_tool("calculate_stationarity", {"values": x.tolist(), "test": "adf"})
    assert out["results"]["adf"]["pValueApprox"] < 0.05


def test_kpss_opposite_direction():
    rw = run_tool("calculate_stationarity", {"values": _random_walk(seed=3).tolist(), "test": "kpss"})
    wn = np.random.default_rng(4).normal(0, 1, 400)
    stat = run_tool("calculate_stationarity", {"values": wn.tolist(), "test": "kpss"})
    assert rw["results"]["kpss"]["pValueApprox"] < stat["results"]["kpss"]["pValueApprox"]


def test_stationarity_both_reports_disagreement_field():
    out = run_tool("calculate_stationarity", {"values": _random_walk(seed=5).tolist(), "test": "both"})
    assert "interpretation" in out["results"]


def test_adf_reports_null_hypothesis_and_critical_values():
    out = run_tool("calculate_stationarity", {"values": _random_walk(seed=6).tolist(), "test": "adf"})
    adf = out["results"]["adf"]
    assert set(adf["criticalValues"].keys()) == {1, 5, 10}
    assert "unit root" in adf["null"]


# ── calculate_cointegration ──────────────────────────────────────────────────

def test_engle_granger_detects_cointegrated_pair():
    rng = np.random.default_rng(7)
    x = np.cumsum(rng.normal(0, 1, 400))
    noise = np.zeros(400)
    for i in range(1, 400):
        noise[i] = 0.5 * noise[i - 1] + rng.normal(0, 0.5)  # stationary AR(1)
    y = 2.0 * x + noise + 5.0
    out = run_tool("calculate_cointegration", {"series": [y.tolist(), x.tolist()],
                                               "method": "engle_granger"})
    eg = out["results"]["engleGranger"]
    assert eg["cointegrated"] is True
    # cointegrating vector second element recovers the 2.0 slope (1, b)
    assert eg["cointegratingVector"][1] == pytest.approx(2.0, abs=0.3)


def test_engle_granger_independent_walks_not_cointegrated():
    rng = np.random.default_rng(8)
    x = np.cumsum(rng.normal(0, 1, 400))
    y = np.cumsum(rng.normal(0, 1, 400))
    out = run_tool("calculate_cointegration", {"series": [y.tolist(), x.tolist()],
                                               "method": "engle_granger"})
    assert out["results"]["engleGranger"]["cointegrated"] is False


def test_johansen_rank_cointegrated_system():
    rng = np.random.default_rng(9)
    x = np.cumsum(rng.normal(0, 1, 500))
    noise = 0.4 * np.random.default_rng(11).normal(0, 1, 500)
    y = 1.5 * x + noise
    out = run_tool("calculate_cointegration", {"series": [y.tolist(), x.tolist()],
                                               "method": "johansen"})
    assert out["results"]["johansen"]["rank"] >= 1


def test_cointegration_requires_equal_lengths():
    out = run_tool_safe("calculate_cointegration", {"series": [[1.0] * 30, [1.0] * 20]})
    assert out["status"] == "error"
    assert out["errors"][0]["code"] == "INVALID_INPUT"

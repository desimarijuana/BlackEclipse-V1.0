"""Numerical correctness — returns, volatility, drawdown, autocorrelation."""

from __future__ import annotations

import math

import numpy as np
import pytest

from harness.stats import run_tool, run_tool_safe
from harness.stats.base import StatsError


# ── calculate_returns ────────────────────────────────────────────────────────

def test_returns_simple_known_values():
    out = run_tool("calculate_returns", {"values": [100.0, 110.0, 121.0]})
    r = out["results"]["returns"]
    assert r[0] is None
    assert r[1] == pytest.approx(0.10, abs=1e-12)
    assert r[2] == pytest.approx(0.10, abs=1e-12)
    assert out["summary"]["cumulativeReturn"] == pytest.approx(0.21, abs=1e-12)


def test_returns_log_known_values():
    out = run_tool("calculate_returns", {"values": [100.0, 110.0], "method": "log"})
    assert out["results"]["returns"][1] == pytest.approx(math.log(1.1), abs=1e-12)


def test_returns_rejects_nonpositive_for_log():
    with pytest.raises(StatsError) as exc:
        run_tool("calculate_returns", {"values": [100.0, 0.0, 50.0], "method": "log"})
    assert exc.value.code == "INVALID_INPUT"


def test_returns_lagged_and_rolling():
    out = run_tool("calculate_returns", {"values": [1.0, 2.0, 4.0, 8.0], "lag": 1, "rollingWindow": 2})
    lagged = out["results"]["laggedReturns"]
    assert lagged[2] == pytest.approx(1.0, abs=1e-12)  # return at t=1 (0.5) shifted to t=2
    rolling = out["results"]["rollingReturns"]
    assert rolling[2] == pytest.approx(3.0, abs=1e-12)  # 4/1 - 1


def test_returns_missing_prices_are_nan():
    out = run_tool_safe("calculate_returns", {"values": [100.0, None, 120.0]})
    assert out["status"] == "ok"  # default policy allows nan
    assert out["results"]["returns"][2] is None


# ── calculate_volatility ─────────────────────────────────────────────────────

def test_volatility_rolling_std_known_value():
    # returns 0.01 and -0.01 alternating; sample stdev over window=4 = 0.0115470
    prices = [100.0]
    for i in range(1, 40):
        prices.append(prices[-1] * (1.01 if i % 2 else 0.99))
    out = run_tool("calculate_volatility", {
        "values": prices, "method": "rolling_std", "window": 4, "annualize": False})
    series = [v for v in out["results"]["rollingSeries"] if v is not None]
    assert series[-1] == pytest.approx(0.0115470, abs=1e-6)


def test_volatility_annualization_scales_by_sqrt_periods():
    prices = [100.0]
    rng = np.random.default_rng(0)
    for _ in range(60):
        prices.append(prices[-1] * (1 + rng.normal(0, 0.01)))
    raw = run_tool("calculate_volatility", {"values": prices, "method": "rolling_std",
                                            "window": 20, "annualize": False})
    ann = run_tool("calculate_volatility", {"values": prices, "method": "rolling_std",
                                            "window": 20, "annualize": True, "periodsPerYear": 252})
    a = [v for v in raw["results"]["rollingSeries"] if v is not None][-1]
    b = [v for v in ann["results"]["rollingSeries"] if v is not None][-1]
    assert b == pytest.approx(a * math.sqrt(252), rel=1e-9)


def test_volatility_ewma_constant_returns_zero():
    out = run_tool("calculate_volatility", {"values": [0.0] * 30, "inputType": "returns",
                                            "method": "ewma"})
    assert out["summary"]["latest"] == pytest.approx(0.0, abs=1e-12)


def test_volatility_garch_runs_and_is_stationary():
    rng = np.random.default_rng(1)
    r = np.zeros(500)
    v = 1e-4
    for i in range(1, 500):
        v = 1e-6 + 0.1 * r[i - 1] ** 2 + 0.8 * v
        r[i] = rng.normal(0, math.sqrt(v))
    out = run_tool("calculate_volatility", {"values": r.tolist(), "inputType": "returns",
                                            "method": "garch11"})
    g = out["results"]["garch"]
    assert 0.0 <= g["alpha"] < 1.0
    assert 0.0 <= g["beta"] < 1.0
    assert g["persistence"] < 1.0


def test_volatility_insufficient_window_raises():
    with pytest.raises(StatsError) as exc:
        run_tool("calculate_volatility", {"values": [1.0, 2.0, 3.0], "window": 10})
    assert exc.value.code == "INSUFFICIENT_DATA"


# ── calculate_drawdown ───────────────────────────────────────────────────────

def test_drawdown_known_series():
    out = run_tool("calculate_drawdown", {"values": [100.0, 120.0, 90.0, 100.0, 130.0]})
    dd = out["results"]["drawdownSeries"]
    assert dd == pytest.approx([0.0, 0.0, -0.25, -1 / 6, 0.0], abs=1e-12)
    assert out["summary"]["maxDrawdown"] == pytest.approx(-0.25, abs=1e-12)
    assert out["summary"]["maxDrawdownRecoveryIndex"] == 4
    assert out["summary"]["recovered"] is True


def test_drawdown_repeated_peaks_and_unrecovered():
    out = run_tool("calculate_drawdown", {"values": [100.0, 100.0, 100.0, 80.0]})
    assert out["summary"]["maxDrawdown"] == pytest.approx(-0.2, abs=1e-12)
    assert out["summary"]["recovered"] is False
    assert any("unrecovered" in w for w in out["warnings"])


def test_drawdown_monotonic_up_has_no_drawdown():
    out = run_tool("calculate_drawdown", {"values": [100.0, 110.0, 120.0, 130.0]})
    assert out["summary"]["maxDrawdown"] == pytest.approx(0.0, abs=1e-12)
    assert out["summary"]["episodeCount"] == 0


# ── calculate_autocorrelation ────────────────────────────────────────────────

def test_acf_first_lag_matches_manual():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    xc = x - x.mean()
    r1 = float(xc[1:] @ xc[:-1]) / float(xc @ xc)
    out = run_tool("calculate_autocorrelation", {"values": x.tolist(), "maxLags": 2})
    assert out["results"]["acf"][0] == pytest.approx(1.0, abs=1e-12)
    assert out["results"]["acf"][1] == pytest.approx(r1, abs=1e-12)


def test_ljung_box_white_noise_not_significant():
    rng = np.random.default_rng(3)
    x = rng.normal(0, 1, 400)
    out = run_tool("calculate_autocorrelation", {"values": x.tolist(), "maxLags": 10})
    assert out["summary"]["ljungBoxPValue"] > 0.01


def test_ljung_box_strong_autocorrelation_significant():
    rng = np.random.default_rng(4)
    x = np.zeros(300)
    for i in range(1, 300):
        x[i] = 0.9 * x[i - 1] + rng.normal(0, 0.1)
    out = run_tool("calculate_autocorrelation", {"values": x.tolist(), "maxLags": 10})
    assert out["summary"]["ljungBoxPValue"] < 1e-6

"""Tests for multiple-testing diagnostics (Deflated Sharpe + PBO/CSCV)."""

from __future__ import annotations

import math
import random

import pytest

from harness.quant.multiple_testing import (
    MultipleTestingError,
    deflated_sharpe,
    norm_cdf,
    norm_ppf,
    pbo_cscv,
)


def test_norm_helpers_round_trip():
    assert norm_ppf(0.5) == pytest.approx(0.0, abs=1e-6)
    assert norm_ppf(0.975) == pytest.approx(1.959964, abs=1e-4)
    assert norm_cdf(0.0) == pytest.approx(0.5)
    for x in (-2.5, -0.7, 0.3, 1.8):
        assert norm_cdf(norm_ppf(norm_cdf(x))) == pytest.approx(norm_cdf(x), abs=1e-6)
    with pytest.raises(MultipleTestingError):
        norm_ppf(0.0)


def _strong_returns(n=400, seed=1):
    rng = random.Random(seed)
    return [0.002 + rng.gauss(0.0, 0.01) for _ in range(n)]


def test_deflated_sharpe_available_and_bounded():
    r = _strong_returns()
    out = deflated_sharpe(r, trial_sharpes=[0.05, 0.08, 0.12, 0.20, 0.30, 0.15])
    assert out["available"] is True
    assert 0.0 <= out["deflatedSharpeRatio"] <= 1.0
    assert out["trialCount"] == 6
    assert out["expectedMaxSharpe"] >= 0


def test_deflated_sharpe_more_trials_lowers_confidence():
    r = _strong_returns()
    few = deflated_sharpe(r, sr_variance=0.02 ** 2, trial_count=2)
    many = deflated_sharpe(r, sr_variance=0.02 ** 2, trial_count=1000)
    assert few["deflatedSharpeRatio"] >= many["deflatedSharpeRatio"]


def test_deflated_sharpe_unavailable_without_variance():
    out = deflated_sharpe(_strong_returns())
    assert out["available"] is False and "variance" in out["reason"]


def test_pbo_dominant_config_wins():
    # config 0 has a far higher mean with low variance -> always IS-best and OOS-best.
    t = 64
    base = [[0.001 + (0.01 if i % 2 else -0.01) for i in range(t)] for _ in range(3)]
    base.insert(0, [0.05 + (0.001 if i % 2 else -0.001) for i in range(t)])
    out = pbo_cscv(base, n_splits=8)
    assert out["available"] is True
    assert out["probabilityOfBacktestOverfitting"] == pytest.approx(0.0)
    assert out["combinations"] == math.comb(8, 4)


def test_pbo_noise_is_not_zero_or_one():
    rng = random.Random(7)
    matrix = [[rng.gauss(0.0, 0.01) for _ in range(128)] for _ in range(12)]
    out = pbo_cscv(matrix, n_splits=10)
    assert out["available"] is True
    assert 0.0 < out["probabilityOfBacktestOverfitting"] < 1.0


def test_pbo_rejects_bad_inputs():
    assert pbo_cscv([[0.01, 0.02]])["available"] is False
    uneven = [[0.01, 0.02, 0.03], [0.01, 0.02]]
    assert pbo_cscv(uneven)["available"] is False

"""Unit tests for the quant indicators — correctness and causality.

No network, no database. Every expectation is computed by hand or from an
independent identity so a regression is unambiguous.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.quant import indicators as ind


def _ohlcv(n=60, base=100.0):
    close = np.linspace(base, base + 20, n)
    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.5
    volume = np.full(n, 1000.0)
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def test_sma_known_values():
    values = np.array([1.0, 2, 3, 4, 5])
    out = ind.sma(values, 3)
    assert np.isnan(out[0]) and np.isnan(out[1])
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)
    assert out[4] == pytest.approx(4.0)


def test_ema_matches_recursion():
    values = np.arange(1.0, 11.0)
    period = 3
    out = ind.ema(values, period)
    alpha = 2.0 / (period + 1)
    seed = values[:period].mean()
    assert out[period - 1] == pytest.approx(seed)
    prev = seed
    for i in range(period, len(values)):
        prev = alpha * values[i] + (1 - alpha) * prev
        assert out[i] == pytest.approx(prev)


def test_rsi_bounds_and_warmup():
    o = _ohlcv()
    out = ind.rsi(o["close"], 14)
    assert np.isnan(out[:14]).all()
    valid = out[~np.isnan(out)]
    assert ((valid >= 0) & (valid <= 100)).all()


def test_atr_positive():
    o = _ohlcv()
    out = ind.atr(o["high"], o["low"], o["close"], 14)
    valid = out[~np.isnan(out)]
    assert (valid > 0).all()


def test_causality_future_does_not_change_past():
    o = _ohlcv(n=80)
    a = ind.ema(o["close"], 10)
    b = ind.rsi(o["close"], 14)
    # Mutate the future only.
    o2 = {k: v.copy() for k, v in o.items()}
    o2["close"][-10:] += 1000.0
    o2["high"][-10:] += 1000.0
    a2 = ind.ema(o2["close"], 10)
    b2 = ind.rsi(o2["close"], 14)
    cut = len(o["close"]) - 10
    assert np.allclose(a[:cut], a2[:cut], equal_nan=True)
    assert np.allclose(b[:cut], b2[:cut], equal_nan=True)


def test_bollinger_and_macd_outputs():
    o = _ohlcv()
    b = ind.compute_one(ind.IndicatorSpec("bollinger", {"period": 20, "num_std": 2}, id="bb"), o)
    assert set(b) == {"bb_upper", "bb_middle", "bb_lower"}
    assert b["bb_upper"][-1] > b["bb_middle"][-1] > b["bb_lower"][-1]
    m = ind.compute_one(ind.IndicatorSpec("macd", {}, id="macd"), o)
    assert set(m) == {"macd", "macd_signal", "macd_hist"}


def test_compute_indicators_duplicate_rejected():
    o = _ohlcv()
    specs = [ind.IndicatorSpec("ema", {"period": 5}), ind.IndicatorSpec("ema", {"period": 5})]
    with pytest.raises(ind.IndicatorError):
        ind.compute_indicators(specs, o)


def test_unknown_indicator_rejected():
    with pytest.raises(ind.IndicatorError):
        ind.resolve_spec(ind.IndicatorSpec("no_such", {"period": 5}))

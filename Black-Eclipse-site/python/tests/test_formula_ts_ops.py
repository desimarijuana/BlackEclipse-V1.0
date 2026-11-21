"""Time-series operators: ts_rank, ts_argmax, decay_linear, scale_series."""

from __future__ import annotations

import numpy as np
import pytest

from harness.stats import formula


def _eval(expr, **context):
    value, _ = formula.evaluate(expr, {k: np.asarray(v, dtype=float) for k, v in context.items()})
    return value


def test_ts_rank_of_an_increasing_window_is_one():
    close = np.arange(1, 11, dtype=float)
    value = _eval("ts_rank(close, 5)", close=close)
    assert np.isnan(value[3])           # window not warm
    assert value[4] == pytest.approx(1.0)


def test_ts_rank_of_a_constant_window_is_one_half():
    close = np.ones(6)
    value = _eval("ts_rank(close, 3)", close=close)
    assert value[-1] == pytest.approx(0.5)


def test_ts_rank_ties_share_credit():
    # window [1, 1, 3]: 3 is the max -> rank 1.0
    close = np.array([1.0, 1.0, 3.0])
    assert _eval("ts_rank(close, 3)", close=close)[-1] == pytest.approx(1.0)
    # window [3, 1, 1]: the last value ties the minimum, so the tie takes half
    # credit -> 0.5 * 1 / 2 = 0.25 (a constant window ranks 0.5)
    mixed = np.array([3.0, 1.0, 1.0])
    assert _eval("ts_rank(close, 3)", close=mixed)[-1] == pytest.approx(0.25)


def test_ts_argmax_returns_the_window_position():
    up = np.arange(1, 8, dtype=float)
    down = up[::-1].copy()
    assert _eval("ts_argmax(close, 4)", close=up)[-1] == pytest.approx(3.0)
    assert _eval("ts_argmax(close, 4)", close=down)[-1] == pytest.approx(0.0)


def test_ts_argmax_ties_take_the_earliest():
    close = np.array([1.0, 5.0, 5.0, 2.0])
    assert _eval("ts_argmax(close, 4)", close=close)[-1] == pytest.approx(1.0)


def test_decay_linear_weights_the_latest_observation_most():
    close = np.array([0.0, 0.0, 10.0])
    # weights 1,2,3 over [0,0,10], normalized by 6 -> 30/6 = 5
    assert _eval("decay_linear(close, 3)", close=close)[-1] == pytest.approx(5.0)
    flat = _eval("decay_linear(close, 3)", close=np.full(3, 7.0))
    assert flat[-1] == pytest.approx(7.0)


def test_decay_linear_is_between_the_mean_and_the_last_value():
    close = np.array([1.0, 2.0, 3.0, 4.0])
    value = _eval("decay_linear(close, 4)", close=close)[-1]
    assert close.mean() < value < close[-1]


def test_scale_series_normalizes_by_the_absolute_sum():
    close = np.array([1.0, -2.0, 2.0])
    value = _eval("scale_series(close, 2)", close=close)
    assert np.nansum(np.abs(value)) == pytest.approx(2.0)


def test_scale_series_of_all_zeros_is_nan_not_infinity():
    value = _eval("scale_series(close)", close=np.zeros(3))
    assert np.isnan(value).all()


def test_the_new_operators_are_parsed_as_functions():
    _, parsed = formula.evaluate("ts_rank(close, 20) + decay_linear(close, 5)", {"close": np.arange(30.0)})
    assert {"ts_rank", "decay_linear"} <= set(parsed.functions)

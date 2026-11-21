"""Rolling regression operators: slope, r2, resi."""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import panel as P
from harness.stats import formula


def _eval(expr, **context):
    value, _ = formula.evaluate(expr, {k: np.asarray(v, dtype=float) for k, v in context.items()})
    return value


def test_slope_of_a_perfect_line_is_its_gradient():
    close = np.arange(10, dtype=float) * 2.0
    value = _eval("slope(close, 5)", close=close)
    assert np.isnan(value[3])
    assert value[-1] == pytest.approx(2.0)


def test_r2_of_a_perfect_line_is_one():
    close = np.arange(10, dtype=float)
    assert _eval("r2(close, 5)", close=close)[-1] == pytest.approx(1.0)


def test_r2_of_a_flat_line_is_one_and_slope_zero():
    close = np.full(6, 7.0)
    assert _eval("slope(close, 5)", close=close)[-1] == pytest.approx(0.0)
    assert _eval("r2(close, 5)", close=close)[-1] == pytest.approx(1.0)


def test_residual_of_a_perfect_line_is_zero():
    close = np.arange(8, dtype=float) * 3.0 + 1.0
    assert _eval("resi(close, 5)", close=close)[-1] == pytest.approx(0.0, abs=1e-9)


def test_residual_is_the_last_point_off_the_trend():
    # a perfect line except a spike at the end
    close = np.array([0.0, 1.0, 2.0, 3.0, 10.0])
    value = _eval("resi(close, 5)", close=close)[-1]
    assert value > 0


def test_a_noisy_series_has_r2_below_one():
    rng = np.random.default_rng(4)
    close = rng.normal(size=60)
    value = _eval("r2(close, 20)", close=close)[-1]
    assert 0.0 <= value < 1.0


def test_the_operators_are_registered_for_parsing():
    _, parsed = formula.evaluate("slope(close, 5) + r2(close, 5) + resi(close, 5)",
                                 {"close": np.arange(10.0)})
    assert {"slope", "r2", "resi"} <= set(parsed.functions)


# -- the panel evaluator has the same operators ------------------------------


def _panel():
    rows = {
        "AAA": [{"timestamp": f"d{i}", "close": 10.0 + 2.0 * i} for i in range(10)],
        "BBB": [{"timestamp": f"d{i}", "close": 10.0 - 1.0 * i} for i in range(10)],
    }
    return P.build_panel(rows, ["close"])


def test_panel_slope_matches_the_series_slope():
    result = P.evaluate("slope(close, 5)", _panel())
    assert result[-1][0] == pytest.approx(2.0)
    assert result[-1][1] == pytest.approx(-1.0)


def test_panel_r2_is_one_for_a_perfect_trend():
    result = P.evaluate("r2(close, 5)", _panel())
    assert result[-1][0] == pytest.approx(1.0)


def test_panel_resi_is_zero_on_a_perfect_trend():
    result = P.evaluate("resi(close, 5)", _panel())
    assert abs(result[-1][0]) < 1e-9

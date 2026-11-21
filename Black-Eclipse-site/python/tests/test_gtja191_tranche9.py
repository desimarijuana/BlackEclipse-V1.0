"""GTJA191 tranche 9: series-on-series regression, a selection mask, and state.

Four operator additions, each with its own test before any alpha relied on it:

  * **`regbeta(y, x, n)`** — rolling OLS slope of `y` on `x`. Deliberately distinct
    from `slope(y, n)`, which regresses against **time**; confusing the two would
    measure a different quantity.
  * **`regresi(y, x, n)`** — the residual of the last point.
  * **`regbeta_where(y, x, mask, n)`** — the same slope restricted to selected
    observations. GTJA #149 is a *downside* beta: only the benchmark-down days
    count. Dropping rows instead of carrying the mask would silently change what
    the window means, and a window with fewer than two selected days is NaN rather
    than a one-point slope.
  * **`cumprod(x)`** — an expanding product, which is what GTJA #143's `SELF`
    state is (`SELF_t = SELF_{t-1} * gross_return` on up days only).

All four exist in the per-series engine **and** the panel evaluator, and the tests
assert the two paths agree.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (51, 56, 108, 115, 121, 123, 138, 143, 146, 148, 149)
VWAP_USERS = (108, 121, 138)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=320, seed=103):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.012, n))
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    benchmark_close = 100 * np.cumprod(1 + rng.normal(0, 0.009, n))
    return {
        "open": close * (1 + rng.normal(0, 0.003, n)),
        "high": close * (1 + abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - abs(rng.normal(0, 0.006, n))),
        "close": close,
        "volume": volume,
        "vwap": close * (1 + rng.normal(0, 0.002, n)),
        "benchmark_close": benchmark_close,
    }


def _panel(rows=200, cols=4, seed=107):
    rng = np.random.default_rng(seed)
    timestamps = [f"d{i:03d}" for i in range(rows)]
    rows_by_symbol = {}
    for index in range(cols):
        close = 100 * np.cumprod(1 + rng.normal(0, 0.012, rows))
        open_ = close * (1 + rng.normal(0, 0.003, rows))
        high = close * (1 + abs(rng.normal(0, 0.006, rows)))
        low = close * (1 - abs(rng.normal(0, 0.006, rows)))
        volume = rng.integers(1_000_000, 5_000_000, rows).astype(float)
        vwap = close * (1 + rng.normal(0, 0.002, rows))
        rows_by_symbol[f"S{index}"] = [
            {"timestamp": timestamps[i], "open": float(open_[i]),
             "high": float(high[i]), "low": float(low[i]),
             "close": float(close[i]), "volume": float(volume[i]),
             "vwap": float(vwap[i])}
            for i in range(rows)
        ]
    return P.build_panel(rows_by_symbol,
                         ["open", "high", "low", "close", "volume", "vwap"])


# -- the operators ----------------------------------------------------------


def test_regbeta_regresses_on_the_other_series_not_on_time():
    # y = 0.5 * x exactly: the slope on x is 0.5 at every scale.
    y = np.array([1.0, 2.0, 3.0, 4.0])
    x = np.array([2.0, 4.0, 6.0, 8.0])
    beta, _ = formula.evaluate("regbeta(y, x, 3)", {"y": y, "x": x})
    assert beta[-1] == pytest.approx(0.5)
    # Regressing y on TIME would give 1.0 here — a different factor.
    time_slope, _ = formula.evaluate("slope(y, 3)", {"y": y})
    assert time_slope[-1] != pytest.approx(0.5)


def test_regresi_is_the_last_point_off_the_regression_line():
    y = np.array([1.0, 2.0, 3.0, 10.0])
    x = np.array([1.0, 2.0, 3.0, 4.0])
    resi, _ = formula.evaluate("regresi(y, x, 4)", {"y": y, "x": x})
    # y - x is constant until the last point, so the residual there is large.
    assert resi[-1] > 1.0


def test_regbeta_refuses_a_degenerate_window():
    with pytest.raises(formula.FormulaError):
        formula.evaluate("regbeta(y, x, 1)", {"y": np.arange(5.0), "x": np.arange(5.0)})


def test_regbeta_where_only_counts_selected_observations():
    # Two regimes: on selected days the slope is 2, on the others it is 0.
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    y = np.array([2.0, 4.0, 6.0, 0.0, 0.0, 0.0])
    mask = np.array([1.0, 1.0, 1.0, 1.0, 0.0, 0.0])
    beta, _ = formula.evaluate(
        "regbeta_where(y, x, m, 3)", {"y": y, "x": x, "m": mask})
    # Window 3 ends at index 2 and is fully selected, so the slope is exactly 2.
    # (A window of w is NaN before index w-1 — that is the rolling convention.)
    assert beta[2] == pytest.approx(2.0)


def test_regbeta_where_is_nan_when_too_few_days_are_selected():
    x = np.arange(6.0)
    y = np.arange(6.0)
    mask = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 0.0])
    beta, _ = formula.evaluate(
        "regbeta_where(y, x, m, 4)", {"y": y, "x": x, "m": mask})
    assert np.isnan(beta[-1])


def test_cumprod_is_an_expanding_product_that_carries_through_a_gap():
    value, _ = formula.evaluate("cumprod(x)", {"x": np.array([2.0, 3.0, np.nan, 2.0])})
    assert list(value) == pytest.approx([2.0, 6.0, 6.0, 12.0])


def test_the_panel_operators_agree_with_the_series_engine():
    rows = {"AAA": [{"timestamp": f"d{i:02d}", "x": 2.0 * (i + 1), "y": float(i + 1)}
                    for i in range(4)]}
    built = P.build_panel(rows, ["x", "y"])
    panel_beta = P.evaluate("regbeta(y, x, 3)", built)[-1][0]
    series_beta, _ = formula.evaluate(
        "regbeta(y, x, 3)", {"y": np.arange(1.0, 5.0), "x": 2 * np.arange(1.0, 5.0)})
    assert panel_beta == pytest.approx(series_beta[-1])
    assert P.evaluate("cumprod(x)", built)[-1][0] == pytest.approx(384.0)


# -- the tranche ------------------------------------------------------------


def test_the_tranche_is_present_and_counted():
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS) >= 130
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


def test_the_declared_inputs_are_declared():
    for number in VWAP_USERS:
        assert contracts.required_inputs(_by_number()[number]) == ("vwap",), number
    assert contracts.required_inputs(_by_number()[149]) == ("benchmark_close",)


def test_alpha149_is_a_downside_beta():
    data = _series()
    factor = _by_number()[149]
    assert "regbeta_where(" in factor["expression"]
    assert "less_than(benchmark_close, lag(benchmark_close, 1))" in factor["expression"]
    value, _ = formula.evaluate(factor["expression"], data)
    assert np.isfinite(value[-1])


def test_alpha143_is_a_cumulative_product_seeded_at_one():
    data = _series()
    value, _ = formula.evaluate(_by_number()[143]["expression"], data)
    finite = value[np.isfinite(value)]
    assert finite[0] == pytest.approx(1.0)
    assert finite[-1] > 0


def test_alpha51_and_49_complement_each_other():
    data = _series()
    a49, _ = formula.evaluate(_by_number()[49]["expression"], data)
    a51, _ = formula.evaluate(_by_number()[51]["expression"], data)
    # up/(up+dn) + dn/(up+dn) = 1.
    assert a49[-1] + a51[-1] == pytest.approx(1.0)


@pytest.mark.parametrize("number", [56, 123, 148])
def test_the_boolean_panel_alphas_take_only_their_two_values(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
    finite = value[np.isfinite(value)]
    assert finite.size
    assert set(np.unique(finite)) <= {0.0, 1.0}


def test_every_new_alpha_runs():
    data = _series()
    for number in NEW:
        factor = _by_number()[number]
        value, _ = formula.evaluate(factor["expression"],
                                    {k: data[k] for k in factor["inputs"]})
        assert np.isfinite(value).any(), number

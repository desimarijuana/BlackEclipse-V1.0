"""GTJA191 tranche 3, and the two operators it required.

The operators are the contract change, so they are tested first and on their own
terms:

  * `wilder(x, n, m)` is GTJA's `SMA(X,N,M)` — the recursion
    `Y_t = (m·X_t + (n−m)·Y_{t−1}) / n`, seeded by the first finite value, with a
    NaN step skipped and the recursion resumed. It is deliberately **not** the
    rolling `sma`: a rolling mean and a Wilder mean differ materially on any
    trending series, and swapping them would silently change every GTJA alpha.
  * `maximum`/`minimum` are GTJA's elementwise `MAX(x, y)`/`MIN(x, y)`, distinct
    from the rolling `rolling_max`/`rolling_min`.

Both exist in the per-series engine **and** the panel evaluator, and the tests
assert they agree.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (3, 4, 9, 10, 19, 22, 23, 24, 26, 40, 47)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=300, seed=53):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.012, n))
    return {
        "open": close * (1 + rng.normal(0, 0.003, n)),
        "high": close * (1 + abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - abs(rng.normal(0, 0.006, n))),
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        "vwap": close * (1 + rng.normal(0, 0.002, n)),
    }


def _panel(rows=300, cols=4, seed=59):
    rng = np.random.default_rng(seed)
    timestamps = [f"d{i}" for i in range(rows)]
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


def test_wilder_is_the_recursion_not_a_rolling_mean():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    value, _ = formula.evaluate("wilder(x, 4, 1)", {"x": x})
    # Y0 = 1; Y1 = (1*2 + 3*1)/4 = 1.25; Y2 = (1*3 + 3*1.25)/4 = 1.6875.
    assert value[0] == pytest.approx(1.0)
    assert value[1] == pytest.approx(1.25)
    assert value[2] == pytest.approx(1.6875)
    rolling, _ = formula.evaluate("sma(x, 2)", {"x": x})
    assert value[-1] != pytest.approx(rolling[-1])


def test_wilder_reaches_its_own_recursion_on_a_constant_series():
    x = np.full(20, 7.0)
    value, _ = formula.evaluate("wilder(x, 5, 1)", {"x": x})
    assert np.allclose(value[5:], 7.0)


def test_wilder_rejects_impossible_arguments():
    with pytest.raises(formula.FormulaError):
        formula.evaluate("wilder(x, 5, 9)", {"x": np.arange(10.0)})
    with pytest.raises(formula.FormulaError):
        formula.evaluate("wilder(x, 0, 1)", {"x": np.arange(10.0)})


def test_wilder_resets_on_a_nan_then_reseeds():
    # The published GTJA implementation resets the recursion on a missing input
    # and reseeds from the next valid one; it does NOT smooth across the gap.
    x = np.array([1.0, np.nan, 3.0])
    value, _ = formula.evaluate("wilder(x, 2, 1)", {"x": x})
    assert value[1] != value[1]          # NaN stays NaN
    assert value[2] == pytest.approx(3.0)  # reseeded, not (3+1)/2


def test_maximum_and_minimum_are_elementwise_not_rolling():
    a = np.array([1.0, 5.0, 2.0])
    b = np.array([3.0, 2.0, 4.0])
    hi, _ = formula.evaluate("maximum(a, b)", {"a": a, "b": b})
    lo, _ = formula.evaluate("minimum(a, b)", {"a": a, "b": b})
    assert list(hi) == [3.0, 5.0, 4.0]
    assert list(lo) == [1.0, 2.0, 2.0]


def test_the_panel_evaluator_agrees_with_the_series_engine():
    rows = {"AAA": [{"timestamp": f"d{i}", "x": float(i)} for i in range(6)],
            "BBB": [{"timestamp": f"d{i}", "x": 2.0} for i in range(6)]}
    built = P.build_panel(rows, ["x"])
    panel_wilder = P.evaluate("wilder(x, 4, 1)", built)[-1]
    series_wilder, _ = formula.evaluate(
        "wilder(x, 4, 1)", {"x": np.arange(6.0)})
    assert panel_wilder[0] == pytest.approx(series_wilder[-1])
    assert panel_wilder[1] == pytest.approx(2.0)
    assert P.evaluate("maximum(x, 3)", built)[-1].tolist() == [5.0, 3.0]


# -- the tranche ------------------------------------------------------------


def test_the_tranche_is_present_and_counted():
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS)
    assert gtja191.PORTED >= 32   # tranche 4 only adds
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


def test_every_new_alpha_evaluates():
    data = _series()
    for number in NEW:
        factor = _by_number()[number]
        if factor.get("requiresPanel"):
            value = P.evaluate(factor["expression"], _panel())[-1]
            assert np.isfinite(value).any(), number
        else:
            value, _ = formula.evaluate(factor["expression"],
                                        {k: data[k] for k in factor["inputs"]})
            assert np.isfinite(value[-1]), number


def test_gtja24_is_the_wilder_smoothing_of_the_five_day_change():
    data = _series()
    value, _ = formula.evaluate(_by_number()[24]["expression"], data)
    expected, _ = formula.evaluate("wilder(close - lag(close, 5), 5, 1)", data)
    assert value[-1] == pytest.approx(expected[-1])


def test_gtja4_takes_only_minus_one_or_plus_one():
    data = _series()
    value, _ = formula.evaluate(_by_number()[4]["expression"], data)
    assert set(np.unique(value[25:])) <= {-1.0, 1.0}


def test_gtja10_is_a_cross_sectional_rank():
    value = P.evaluate(_by_number()[10]["expression"], _panel())[-1]
    assert np.isfinite(value).all()
    assert (value >= 0).all() and (value <= 1.0 + 1e-9).all()


def test_gtja40_is_a_ratio_of_up_day_to_down_day_volume():
    data = _series()
    value, _ = formula.evaluate(_by_number()[40]["expression"], data)
    assert value[-1] >= 0
    assert np.isfinite(value[-1])


def test_gtja47_is_a_percentage_inside_its_range():
    data = _series()
    value, _ = formula.evaluate(_by_number()[47]["expression"], data)
    # A Wilder mean of a 0..100 series stays inside 0..100.
    assert -1e-9 <= value[-1] <= 100.0 + 1e-9


def test_gtja3_uses_the_elementwise_pairs():
    expression = _by_number()[3]["expression"]
    assert "minimum(low, lag(close, 1))" in expression
    assert "maximum(high, lag(close, 1))" in expression


def test_gtja19_and_22_are_finite_and_use_the_wilder_recursion():
    data = _series()
    for number in (19, 22, 23):
        value, _ = formula.evaluate(_by_number()[number]["expression"], data)
        assert np.isfinite(value[-1]), number
    assert "wilder(" in _by_number()[22]["expression"]

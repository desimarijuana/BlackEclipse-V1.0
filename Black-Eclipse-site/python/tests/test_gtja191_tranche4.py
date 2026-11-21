"""GTJA191 tranche 4: `wma`, the reset fix, and ten more verified formulas.

Two contract-level facts are pinned here:

  * **`wma(x, n)` is oldest-heaviest** (weights `n, n-1, …, 1`), the mirror of
    `decay_linear`. On `[1, 2, 3]` with n=3 the weights are `(3,2,1)/6`, so the
    answer is `(3·1 + 2·2 + 1·3)/6 = 1.667` — while `decay_linear` gives `2.333`.
    Implementing one as the other silently inverts the smoothing.
  * **`wilder` resets on a gap.** The published GTJA implementation documents
    "missing input resets this stock; the next valid input reseeds it", so a NaN
    clears the recursion instead of carrying a stale value across the hole.

Then the tranche: #21 (a rolling OLS slope, no new operator), #25, #27 (WMA),
#35 (elementwise MIN of two ranks), #37, #39, #41, #44, #45, #49.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (21, 25, 27, 35, 37, 39, 41, 44, 45, 49)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=300, seed=61):
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


def _panel(rows=320, cols=4, seed=67):
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


def test_wma_is_oldest_heaviest_and_is_not_decay_linear():
    x = np.array([1.0, 2.0, 3.0])
    wma, _ = formula.evaluate("wma(x, 3)", {"x": x})
    decay, _ = formula.evaluate("decay_linear(x, 3)", {"x": x})
    assert wma[-1] == pytest.approx((3 * 1 + 2 * 2 + 1 * 3) / 6)
    assert decay[-1] == pytest.approx((1 * 1 + 2 * 2 + 3 * 3) / 6)
    assert wma[-1] != pytest.approx(decay[-1])


def test_wma_is_constant_preserving_and_bounded():
    x = np.full(10, 5.0)
    value, _ = formula.evaluate("wma(x, 4)", {"x": x})
    assert np.allclose(value[3:], 5.0)
    rng = np.random.default_rng(2)
    data = rng.normal(0, 1, 50)
    out, _ = formula.evaluate("wma(x, 5)", {"x": data})
    finite = out[np.isfinite(out)]
    assert finite.min() >= data.min() - 1e-9
    assert finite.max() <= data.max() + 1e-9


def test_wilder_resets_on_a_gap():
    # [1, NaN, 3, 5] with n=2, m=1: 1, gap, reseed 3, then (3+5)/2 = 4.
    value, _ = formula.evaluate("wilder(x, 2, 1)", {"x": np.array([1.0, np.nan, 3.0, 5.0])})
    assert value[0] == pytest.approx(1.0)
    assert value[1] != value[1]
    assert value[2] == pytest.approx(3.0)      # reseeded, not (3+1)/2
    assert value[3] == pytest.approx(4.0)


def test_the_panel_wma_agrees_with_the_series_engine():
    rows = {"AAA": [{"timestamp": f"d{i}", "x": float(i + 1)} for i in range(3)]}
    built = P.build_panel(rows, ["x"])
    panel_value = P.evaluate("wma(x, 3)", built)[-1][0]
    series_value, _ = formula.evaluate("wma(x, 3)", {"x": np.array([1.0, 2.0, 3.0])})
    assert panel_value == pytest.approx(series_value[-1])


def test_the_panel_wilder_resets_like_the_series_engine():
    rows = {"AAA": [{"timestamp": f"d{i}", "x": v}
                    for i, v in enumerate([1.0, float("nan"), 3.0, 5.0])]}
    built = P.build_panel(rows, ["x"])
    # P.evaluate returns T x N: column 0 is the single symbol's series.
    series = P.evaluate("wilder(x, 2, 1)", built)[:, 0]
    assert series[0] == pytest.approx(1.0)
    assert series[2] == pytest.approx(3.0)
    assert series[3] == pytest.approx(4.0)


# -- the tranche ------------------------------------------------------------


def test_the_tranche_is_present_and_counted():
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS)
    assert gtja191.PORTED >= 42   # tranche 5 only adds
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


def test_gtja21_is_a_rolling_regression_slope_without_a_new_operator():
    data = _series()
    value, _ = formula.evaluate(_by_number()[21]["expression"], data)
    expected, _ = formula.evaluate("slope(sma(close, 6), 6)", data)
    assert value[-1] == pytest.approx(expected[-1])
    assert np.isfinite(value[-1])


def test_gtja27_uses_the_oldest_heaviest_wma():
    data = _series()
    value, _ = formula.evaluate(_by_number()[27]["expression"], data)
    inner = ((data["close"] - np.roll(data["close"], 3)) / np.roll(data["close"], 3) * 100
             + (data["close"] - np.roll(data["close"], 6)) / np.roll(data["close"], 6) * 100)
    window = inner[-12:]
    weights = np.arange(12, 0, -1, dtype=float)
    weights /= weights.sum()
    assert value[-1] == pytest.approx(float(np.dot(window, weights)))


def test_gtja35_is_a_minimum_of_two_ranks_so_it_is_bounded():
    value = P.evaluate(_by_number()[35]["expression"], _panel())[-1]
    assert np.isfinite(value).all()
    # -min(rank, rank): the negation of a percentile, so in [-1, 0].
    assert (value <= 0).all() and (value >= -1.0 - 1e-9).all()


def test_gtja49_is_a_share_between_zero_and_one():
    data = _series()
    value, _ = formula.evaluate(_by_number()[49]["expression"], data)
    assert 0.0 <= value[-1] <= 1.0 + 1e-9


@pytest.mark.parametrize("number", [25, 35, 37, 39, 41, 45])
def test_the_panel_alphas_evaluate(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
    assert np.isfinite(value).any()


def test_every_new_series_alpha_evaluates():
    data = _series()
    for number in (21, 27, 44, 49):
        factor = _by_number()[number]
        value, _ = formula.evaluate(factor["expression"],
                                    {k: data[k] for k in factor["inputs"]})
        assert np.isfinite(value[-1]), number

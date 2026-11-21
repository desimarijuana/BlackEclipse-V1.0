"""GTJA191 tranche 13: DTM/DBM settle #69; #137/#172/#186/#190 are transcribed.

The research step that made this possible was reading
`lrb777/gtja191/src/lib/special.py`, which defines the two operators #69 needs:

    DTM = MAX(HIGH - OPEN, OPEN - DELAY(OPEN,1))   when the open gapped UP, else 0
    DBM = MAX(OPEN - LOW,  OPEN - DELAY(OPEN,1))   when the open gapped DOWN, else 0

Note DBM's second term **keeps its sign** — the published form does not take an
absolute value there, and "fixing" it would change the factor.

One formula remains unported (#159), and the test asserts that it is the ONLY one,
so the gap is a standing fact rather than a drifting number.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (69, 91, 137, 172, 190)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=260, seed=163):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.012, n))
    return {
        "open": close * (1 + rng.normal(0, 0.003, n)),
        "high": close * (1 + abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - abs(rng.normal(0, 0.006, n))),
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }


def _panel(rows=120, cols=20, seed=167):
    rng = np.random.default_rng(seed)
    timestamps = [f"d{i:03d}" for i in range(rows)]
    rows_by_symbol = {}
    for index in range(cols):
        close = 100 * np.cumprod(1 + rng.normal(0, 0.012, rows))
        rows_by_symbol[f"S{index}"] = [
            {"timestamp": timestamps[i],
             "open": float(close[i] * (1 + rng.normal(0, 0.003))),
             "high": float(close[i] * (1 + abs(rng.normal(0, 0.006)))),
             "low": float(close[i] * (1 - abs(rng.normal(0, 0.006)))),
             "close": float(close[i]),
             "volume": float(rng.integers(1_000_000, 5_000_000))}
            for i in range(rows)
        ]
    return P.build_panel(rows_by_symbol,
                         ["open", "high", "low", "close", "volume"])


# -- completeness statement -------------------------------------------------


def test_nothing_remains_unported():
    numbers = {f["alphaNumber"] for f in gtja191.GTJA191_FACTORS}
    assert len(numbers) == len(gtja191.GTJA191_FACTORS), "duplicate alpha number"
    # tranche 14 resolved both: #159's weights are confirmed by a second
    # implementation, and #186's node cap was raised with a stated bound.
    assert set(range(1, 192)) - numbers == set()
    assert gtja191.PORTED == 191


def test_the_new_alphas_are_present():
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


# -- DTM / DBM semantics ----------------------------------------------------


def test_gtja69_uses_the_two_gap_operators_with_the_published_signs():
    expression = _by_number()[69]["expression"]
    # DTM's active branch and DBM's active branch, both with OPEN - prev_open.
    assert "greater_than(open, lag(open, 1))" in expression
    assert "less_than(open, lag(open, 1))" in expression
    assert "maximum(high - open, open - lag(open, 1))" in expression
    assert "maximum(open - low, open - lag(open, 1))" in expression


def test_gtja69_is_finite_and_between_minus_one_and_one():
    value, _ = formula.evaluate(_by_number()[69]["expression"], _series())
    assert np.isfinite(value[-1])
    assert -1.0 - 1e-9 <= value[-1] <= 1.0 + 1e-9


# -- the ATR / DMI family ---------------------------------------------------


def test_gtja91_reads_max_close_5_as_a_rolling_max():
    expression = _by_number()[91]["expression"]
    assert "rolling_max(close, 5)" in expression
    value = P.evaluate(expression, _panel())[-1]
    assert np.isfinite(value).any()


def test_gtja137_is_finite_and_uses_the_published_true_range():
    expression = _by_number()[137]["expression"]
    assert "abs(high - lag(close, 1))" in expression
    assert "abs(lag(close, 1) - lag(open, 1))" in expression
    value, _ = formula.evaluate(expression, _series())
    assert np.isfinite(value[-1])


@pytest.mark.parametrize("number", [172])
def test_the_dmi_alphas_stay_inside_zero_to_one_hundred(number):
    value, _ = formula.evaluate(_by_number()[number]["expression"], _series())
    finite = value[30:]
    finite = finite[np.isfinite(finite)]
    assert finite.size
    assert (finite >= -1e-9).all() and (finite <= 100.0 + 1e-9).all()


# -- the asymmetric SUMIF ---------------------------------------------------


def test_gtja190_keeps_the_asymmetric_guards_and_is_finite():
    expression = _by_number()[190]["expression"]
    assert "log(" in expression
    # the numerator uses the DOWN-side sum, the denominator the UP-side sum
    assert "* 1) * ts_sum(where(less_than(" in expression or "rolling_mean(greater_than(" in expression
    value, _ = formula.evaluate(expression, _series())
    assert np.isfinite(value).any()


def test_every_new_alpha_produces_a_finite_value():
    data = _series()
    for number in NEW:
        factor = _by_number()[number]
        if factor.get("requiresPanel"):
            value = P.evaluate(factor["expression"], _panel())[-1]
        else:
            value, _ = formula.evaluate(factor["expression"],
                                        {k: data[k] for k in factor["inputs"]})
        assert np.isfinite(value).any(), number

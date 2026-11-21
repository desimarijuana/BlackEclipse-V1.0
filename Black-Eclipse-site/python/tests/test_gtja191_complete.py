"""GTJA191 is COMPLETE: 191 of 191, with both late additions verified twice.

The two formulas this suite covers were the ones I had previously called blocked:

  * **#159** — the "corrected-weight erratum" I inferred did not exist. A second
    published implementation (`NeoSPQR404/gtja191-research`) uses the **same**
    weights as lrb777's port (`12*24`, `6*24`, `6*24`, denominator
    `6*12+6*24+12*24`). Two independent transcriptions agreeing *is* the
    verification, so it is ported.
  * **#186** — blocked only by this repo's own parser guard: the published form
    duplicates the #172 DMI block and needs 421 AST nodes. `MAX_NODES` was raised
    256 → 512 with a stated bound, and `test_formula_guards.py` still proves a
    runaway expression is refused.

#172/#186 were also realigned to the reference's **standard Wilder true range**
(`max(max(high-low, |high-prev_close|), |low-prev_close|)`); lrb777's port uses a
different TR, and this suite pins which one we ship so the pair stays consistent.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors.zoo import gtja191
from harness.stats import formula


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=260, seed=173):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.012, n))
    return {
        "open": close * (1 + rng.normal(0, 0.003, n)),
        "high": close * (1 + abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - abs(rng.normal(0, 0.006, n))),
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }


# -- the completeness statement -------------------------------------------


def test_the_whole_series_is_ported():
    numbers = [f["alphaNumber"] for f in gtja191.GTJA191_FACTORS]
    assert len(numbers) == len(set(numbers)), "duplicate alpha number"
    assert set(numbers) == set(range(1, 192)), (
        f"missing {sorted(set(range(1, 192)) - set(numbers))}")
    assert gtja191.PORTED == len(numbers) == 191
    assert gtja191.TOTAL == 191


def test_every_expression_parses():
    for factor in gtja191.GTJA191_FACTORS:
        formula.parse(factor["expression"])


# -- #159 ------------------------------------------------------------------


def test_alpha159_is_the_three_horizon_share():
    factor = _by_number()[159]
    expression = factor["expression"]
    # three horizons, the published weights, and the published normaliser
    for window in (6, 12, 24):
        assert f"ts_sum(minimum(low, lag(close, 1)), {window})" in expression
    assert "* 12 * 24" in expression and "* 6 * 24" in expression
    assert "(6 * 12 + 6 * 24 + 12 * 24)" in expression


def test_alpha159_matches_a_hand_computed_value():
    data = _series()
    value, _ = formula.evaluate(_by_number()[159]["expression"], data)
    close, high, low = data["close"], data["high"], data["low"]
    prev = np.roll(close, 1)
    min_low = np.minimum(low, prev)
    diff = np.maximum(high, prev) - min_low
    # the last complete windows
    term = 0.0
    for window, weight in ((6, 12 * 24), (12, 6 * 24), (24, 6 * 24)):
        if len(close) < window:
            continue
        num = close[-1] - float(np.sum(min_low[-window:]))
        den = float(np.sum(diff[-window:]))
        term += num / den * weight
    expected = term * 100 / (6 * 12 + 6 * 24 + 12 * 24)
    assert value[-1] == pytest.approx(expected)


# -- #172 / #186 -----------------------------------------------------------


def test_the_pair_uses_the_standard_wilder_true_range():
    tr = ("maximum(maximum(high - low, abs(high - lag(close, 1))), "
          "abs(low - lag(close, 1)))")
    assert tr in _by_number()[172]["expression"]
    assert tr in _by_number()[186]["expression"]


def test_alpha186_is_alpha172_averaged_with_its_six_day_lag():
    data = _series()
    a172, _ = formula.evaluate(_by_number()[172]["expression"], data)
    a186, _ = formula.evaluate(_by_number()[186]["expression"], data)
    assert a186[-1] == pytest.approx((a172[-1] + a172[-7]) / 2, rel=1e-9)


@pytest.mark.parametrize("number", [172, 186])
def test_the_dmi_pair_stays_inside_zero_to_one_hundred(number):
    value, _ = formula.evaluate(_by_number()[number]["expression"], _series())
    finite = value[30:]
    finite = finite[np.isfinite(finite)]
    assert finite.size
    assert (finite >= -1e-9).all() and (finite <= 100.0 + 1e-9).all()

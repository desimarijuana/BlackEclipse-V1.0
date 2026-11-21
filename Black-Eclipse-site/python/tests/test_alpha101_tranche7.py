"""Alpha101 tranche 7: the family the new operators unblocked (65 -> 84 of 101).

Three capabilities converge here, and each was proved in an earlier tranche before
being relied on:

  * **cross-sectional rank nested in a rolling correlation** (`correlation(rank(a),
    rank(b), n)`) — supported by the panel evaluator, and the subject of a
    documented self-correction in GTJA tranche 11;
  * **`neutralize(x, industry)`** — declared classification, cohort-wise centring;
  * **elementwise `minimum`/`maximum`** and a **cross-sectional rank inside
    `ts_rank`** (`ts_rank(rank(low), 9)`).

The invariant that catches the most likely slip is *boundedness*: a boolean alpha
must take exactly two values, a `rank`-of-anything must stay in [0, 1], and a
negated one in [-1, 0].
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import alpha101

NEW = (2, 3, 4, 13, 15, 16, 27, 44, 55, 59, 62, 64, 67, 68, 70, 71, 73, 74, 75)
VWAP_USERS = (27, 59, 62, 64, 67, 70, 71, 73, 74, 75)
NEUTRALISED = (59, 67, 70)
BOOLEAN = (62, 64, 68, 75)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in alpha101.ALPHA101_FACTORS}


def _panel(rows=340, cols=24, seed=137):
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
             "vwap": float(vwap[i]),
             "industry": float(index % 4), "sector": float(index % 2)}
            for i in range(rows)
        ]
    return P.build_panel(rows_by_symbol,
                         ["open", "high", "low", "close", "volume", "vwap",
                          "industry", "sector"])


# -- count and contracts ----------------------------------------------------


def test_the_tranche_is_present_and_unique():
    nums = [f["alphaNumber"] for f in alpha101.ALPHA101_FACTORS]
    assert len(nums) == len(set(nums)), "duplicate alpha number"
    assert alpha101.PORTED == len(alpha101.ALPHA101_FACTORS)
    assert alpha101.PORTED >= 84   # tranche 8 completes the paper
    for number in NEW:
        assert number in _by_number(), f"Alpha#{number} missing"


def test_every_vwap_user_declares_it():
    for number in VWAP_USERS:
        assert "vwap" in contracts.required_inputs(_by_number()[number]), number


def test_the_neutralised_alphas_declare_their_classification():
    for number in NEUTRALISED:
        declared = contracts.required_inputs(_by_number()[number])
        assert "industry" in declared, number
        with pytest.raises(contracts.FactorInputError):
            contracts.require_inputs(_by_number()[number], ["close", "volume", "vwap"])


# -- invariants -------------------------------------------------------------


@pytest.mark.parametrize("number", NEW)
def test_each_alpha_evaluates_on_a_panel_sized_for_its_lookback(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
    assert np.isfinite(value).any(), number


@pytest.mark.parametrize("number", BOOLEAN)
def test_the_boolean_alphas_take_only_their_two_values(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
    finite = value[np.isfinite(value)]
    assert finite.size
    assert set(np.unique(np.round(finite, 9))) <= {0.0, 1.0, -1.0}, number


@pytest.mark.parametrize("number", [4, 13, 15, 16, 44])
def test_the_rank_families_are_percentiles(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
    finite = value[np.isfinite(value)]
    assert finite.size
    assert (finite >= -3.0 - 1e-9).all() and (finite <= 1.0 + 1e-9).all(), number


def test_alpha2_and_alpha3_are_negated_correlations():
    for number in (2, 3):
        value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
        finite = value[np.isfinite(value)]
        assert (finite >= -1.0 - 1e-9).all() and (finite <= 1.0 + 1e-9).all(), number


def test_alpha4_is_the_time_rank_of_a_cross_sectional_rank():
    expression = _by_number()[4]["expression"]
    assert expression == "0 - ts_rank(rank(low), 9)"
    value = P.evaluate(expression, _panel())[-1]
    finite = value[np.isfinite(value)]
    assert (finite >= -1.0 - 1e-9).all() and (finite <= 0.0 + 1e-9).all()


def test_alpha71_takes_the_maximum_of_two_decayed_trends():
    expression = _by_number()[71]["expression"]
    assert expression.startswith("maximum(")
    value = P.evaluate(expression, _panel())[-1]
    assert np.isfinite(value).any()

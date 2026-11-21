"""Alpha101 tranche 4: six more formulas, pinned by their own structure.

These are the alphas that need nothing beyond operators already verified in earlier
tranches — `ts_sum`, `decay_linear`, `scale`, cross-sectional `rank`, `^`, and the
declared adv20 (`sma(volume * close, 20)`).

Each case asserts a property the formula must have if it was transcribed
correctly, not merely that it returns a number: a rank-centred alpha must live in
[-0.5, 0.5], a product of three ranks in [-1, 1], a `scale`d value in [-1, 1].
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import panel as P
from harness.factors.zoo import alpha101
from harness.stats import formula

NEW = (1, 14, 17, 28, 31, 39)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in alpha101.ALPHA101_FACTORS}


def _panel(rows=300, cols=5, seed=29):
    rng = np.random.default_rng(seed)
    timestamps = [f"d{i}" for i in range(rows)]
    rows_by_symbol = {}
    for index in range(cols):
        close = 100 * np.cumprod(1 + rng.normal(0, 0.012, rows))
        open_ = close * (1 + rng.normal(0, 0.003, rows))
        high = close * (1 + abs(rng.normal(0, 0.006, rows)))
        low = close * (1 - abs(rng.normal(0, 0.006, rows)))
        volume = rng.integers(1_000_000, 5_000_000, rows).astype(float)
        rows_by_symbol[f"S{index}"] = [
            {"timestamp": timestamps[i], "open": float(open_[i]),
             "high": float(high[i]), "low": float(low[i]),
             "close": float(close[i]), "volume": float(volume[i])}
            for i in range(rows)
        ]
    return P.build_panel(rows_by_symbol, ["open", "high", "low", "close", "volume"])


def _value(number: int, rows: int = 300):
    return P.evaluate(_by_number()[number]["expression"], _panel(rows=rows))


# -- the count --------------------------------------------------------------


def test_the_count_is_derived_and_grew_by_six():
    assert alpha101.PORTED == len(alpha101.ALPHA101_FACTORS)
    assert alpha101.PORTED >= 39
    for number in NEW:
        assert number in _by_number(), f"Alpha#{number} missing"


def test_every_new_alpha_is_cross_sectional():
    for number in NEW:
        assert _by_number()[number]["requiresPanel"] is True


def test_every_new_expression_parses_with_the_panel_allowance():
    for number in NEW:
        formula.parse(_by_number()[number]["expression"], allow=P.PANEL_FUNCTIONS)


# -- structural invariants --------------------------------------------------


def test_alpha1_is_a_rank_minus_half():
    # rank(...) is in (0, 1], so the published "- 0.5" must land in (-0.5, 0.5].
    value = _value(1)
    assert np.isfinite(value[-1]).all()
    assert (value[-1] > -0.5 - 1e-9).all() and (value[-1] <= 0.5 + 1e-9).all()


def test_alpha14_is_a_rank_times_a_correlation():
    value = _value(14)
    assert np.isfinite(value[-1]).all()
    # |rank| <= 1 and |correlation| <= 1, so the product cannot exceed 1.
    assert (np.abs(value[-1]) <= 1.0 + 1e-9).all()


def test_alpha17_is_a_product_of_three_bounded_terms():
    value = _value(17)
    assert np.isfinite(value[-1]).all()
    assert (np.abs(value[-1]) <= 1.0 + 1e-9).all()


def test_alpha28_is_scaled_across_names():
    # `scale(x)` is x / sum(|x|), so the column sums to 1 in absolute value.
    value = P.evaluate(_by_number()[28]["expression"], _panel())
    row = value[-1]
    assert np.isfinite(row).all()
    assert abs(float(np.abs(row).sum()) - 1.0) < 1e-9


def test_alpha31_adds_a_sign_so_it_exceeds_a_pure_rank():
    value = _value(31)
    assert np.isfinite(value[-1]).all()
    # rank chain + rank + sign: the possible range is wider than a single rank.
    assert np.abs(value[-1]).max() > 1.0


def test_alpha39_brackets_are_right_so_it_is_not_floored_at_minus_one():
    # The published formula multiplies the whole rank by (1 + rank(...)); a
    # misplaced bracket would instead subtract the second term and floor the value
    # near -2. The correct form keeps |value| <= 2 with most of it above -1.
    value = _value(39)
    assert np.isfinite(value[-1]).all()
    assert (np.abs(value[-1]) <= 2.0 + 1e-9).all()
    assert np.median(value[-1]) > -1.0


def test_alpha39_uses_the_annual_flow_term():
    expression = _by_number()[39]["expression"]
    assert "ts_sum(pct_change(close, 1), 250)" in expression
    assert "(1 + rank(" in expression


def test_the_adv20_users_share_one_definition():
    for number in (17, 28, 31, 39):
        assert "sma(volume * close, 20)" in _by_number()[number]["expression"]

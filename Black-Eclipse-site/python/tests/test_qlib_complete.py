"""Qlib Alpha158 is complete: 158 of 158, and the arithmetic proves it.

The three features the module had counted as "unnamed" were not missing from qlib —
they were missing from *this* port. Fetching qlib's own
`Alpha158DL.get_feature_config` settled it: its kbar block has **nine** fields
(KMID, KLEN, KMID2, KUP, **KUP2**, KLOW, **KLOW2**, KSFT, **KSFT2**), and the base
price block is `OPEN0/HIGH0/LOW0/VWAP0`. That makes 13 base features plus 29 per
horizon across five horizons = **158 exactly**, which is the check this suite
asserts rather than trusting a counter.

KUP2 / KLOW2 / KSFT2 are the range-normalised twins of KUP / KLOW / KSFT, each with
qlib's `1e-12` denominator guard.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors.zoo import qlib158
from harness.stats import formula

HORIZONS = qlib158.HORIZONS


def _by_name() -> dict[str, dict]:
    return {factor["name"]: factor for factor in qlib158.QLIB158_FACTORS}


def _bar(open_=10.0, high=12.0, low=8.0, close=11.0):
    return {"open": np.array([open_]), "high": np.array([high]),
            "low": np.array([low]), "close": np.array([close])}


# -- completeness -----------------------------------------------------------


def test_the_count_is_qlibs_published_158_and_the_arithmetic_says_so():
    assert qlib158.PORTED == len(qlib158.QLIB158_FACTORS) == 158
    assert qlib158.TOTAL == 158
    # 9 kbar + 4 price-level + 29 per horizon * 5 horizons
    assert qlib158.PORTED == 13 + 29 * len(HORIZONS)


def test_every_feature_has_a_name_family_and_expression():
    names = [f["name"] for f in qlib158.QLIB158_FACTORS]
    assert len(names) == len(set(names)), "duplicate feature name"
    for factor in qlib158.QLIB158_FACTORS:
        assert factor["zoo"] == "qlib158"
        assert factor["expression"] and factor["inputs"]
        assert factor["reference"]


def test_the_nine_kbar_features_are_present():
    names = set(_by_name())
    for kbar in ("kmid", "klen", "kmid2", "kup", "kup2", "klow", "klow2",
                 "ksft", "ksft2"):
        assert f"qlib_{kbar}" in names, kbar
    # and the four price-level normalisations
    for level in ("open0", "high0", "low0", "vwap0"):
        assert f"qlib_{level}" in names, level


# -- the three that were missing -------------------------------------------


def test_kup2_is_the_upper_shadow_over_the_range():
    factor = _by_name()["qlib_kup2"]
    value, _ = formula.evaluate(factor["expression"], _bar())
    # high 12, max(open 10, close 11) = 11 -> shadow 1; range 4 -> 0.25
    assert value[-1] == pytest.approx(0.25)


def test_klow2_is_the_lower_shadow_over_the_range():
    factor = _by_name()["qlib_klow2"]
    value, _ = formula.evaluate(factor["expression"], _bar())
    # min(open 10, close 11) = 10, low 8 -> shadow 2; range 4 -> 0.5
    assert value[-1] == pytest.approx(0.5)


def test_ksft2_is_the_close_position_over_the_range():
    factor = _by_name()["qlib_ksft2"]
    value, _ = formula.evaluate(factor["expression"], _bar())
    # 2*11 - 12 - 8 = 2; range 4 -> 0.5
    assert value[-1] == pytest.approx(0.5)


def test_the_range_normalised_twins_sum_to_at_most_one():
    data = _bar()
    kup2, _ = formula.evaluate(_by_name()["qlib_kup2"]["expression"], data)
    klow2, _ = formula.evaluate(_by_name()["qlib_klow2"]["expression"], data)
    # upper + lower shadow = range - |body|, so their shares cannot exceed 1.
    assert kup2[-1] + klow2[-1] <= 1.0 + 1e-9


def test_the_range_guard_keeps_a_zero_range_finite():
    flat = _bar(open_=10.0, high=10.0, low=10.0, close=10.0)
    for name in ("qlib_kup2", "qlib_klow2", "qlib_ksft2"):
        value, _ = formula.evaluate(_by_name()[name]["expression"], flat)
        assert np.isfinite(value[-1]), name


# -- every feature still evaluates ----------------------------------------


def test_every_expression_parses():
    for factor in qlib158.QLIB158_FACTORS:
        formula.parse(factor["expression"])

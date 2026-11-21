"""Qlib158 flow families: OPEN0/HIGH0/LOW0, CORD, CNTD, SUMP/N/D, WVMA.

Each definition is transcribed from qlib's `Alpha158DL` with a one-to-one operator
map (`Ref`→`lag`, `Sum`→`ts_sum`, `Mean`→`rolling_mean`, `Greater`→`greater_than`,
`Std`→`rolling_std`), and the algebra is pinned rather than smoke-tested:

  * SUMP and SUMN are **shares** — in (0, 1) and summing near 1;
  * SUMD is SUMP − SUMN, so it can be negative and never exceeds either share's
    range;
  * CNTD is the down-share minus the up-share, the mirror of CNTP/CNTN;
  * CORD is a correlation, so it is bounded by ±1;
  * OPEN0/HIGH0/LOW0 are relative to **close**, not to open.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors.zoo import qlib158
from harness.stats import formula

HORIZONS = qlib158.HORIZONS


def _by_name() -> dict[str, dict]:
    return {factor["name"]: factor for factor in qlib158.QLIB158_FACTORS}


def _series(n=200, seed=17):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.012, n))
    return {
        "open": close * (1 + rng.normal(0, 0.002, n)),
        "high": close * (1 + abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - abs(rng.normal(0, 0.006, n))),
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }


def _eval(name: str):
    factor = _by_name()[name]
    data = _series()
    value, _ = formula.evaluate(factor["expression"],
                               {k: data[k] for k in factor["inputs"]})
    return value[-1]


# -- the count --------------------------------------------------------------


def test_the_ported_count_is_derived_and_matches_the_list():
    assert qlib158.PORTED == len(qlib158.QLIB158_FACTORS)
    # Tranche 2 shipped 9 base + 26 per horizon; tranche 3 only ADDS (VWAP0 and
    # the VSUM* families), so this is a floor rather than an equality.
    assert qlib158.PORTED >= 9 + 26 * len(HORIZONS)


def test_the_new_families_exist_for_every_horizon():
    names = set(_by_name())
    for d in HORIZONS:
        for family in ("CORD", "CNTD", "SUMP", "SUMN", "SUMD", "WVMA"):
            assert f"qlib_{family.lower()}_{d}" in names


# -- the base normalisations ------------------------------------------------


def test_open0_high0_low0_are_relative_to_close():
    assert _by_name()["qlib_open0"]["expression"] == "open / close - 1"
    assert _by_name()["qlib_high0"]["expression"] == "high / close - 1"
    assert _by_name()["qlib_low0"]["expression"] == "low / close - 1"
    # A bar where high > close > low must satisfy high0 > 0 > low0.
    assert _eval("qlib_high0") > 0 > _eval("qlib_low0")


def test_vwap0_was_absent_from_tranche_two():
    # It landed in tranche 3 behind the declared `vwap` input contract; the
    # contract itself is asserted in `test_qlib_tranche3`.
    factor = _by_name().get("qlib_vwap0")
    assert factor is None or factor.get("requiresInputs") == ["vwap"]


# -- the flow families ------------------------------------------------------


def test_sump_and_sumn_are_shares_that_sum_near_one():
    for d in HORIZONS:
        up = _eval(f"qlib_sump_{d}")
        down = _eval(f"qlib_sumn_{d}")
        assert 0.0 <= up <= 1.0
        assert 0.0 <= down <= 1.0
        # The +1 denominators make the pair sum to just under 1.
        assert up + down <= 1.0 + 1e-9
        assert up + down > 0.5


def test_sumd_is_sump_minus_sumn():
    d = 10
    expected = _eval(f"qlib_sump_{d}") - _eval(f"qlib_sumn_{d}")
    assert _eval(f"qlib_sumd_{d}") == pytest.approx(expected, abs=1e-12)


def test_cntd_is_the_mirror_of_cntp_and_cntn():
    d = 20
    up = _eval(f"qlib_cntp_{d}")
    down = _eval(f"qlib_cntn_{d}")
    assert _eval(f"qlib_cntd_{d}") == pytest.approx(down - up, abs=1e-12)


def test_cord_is_a_correlation_and_therefore_bounded():
    for d in HORIZONS:
        value = _eval(f"qlib_cord_{d}")
        assert -1.0000001 <= value <= 1.0000001


def test_wvma_is_a_positive_volatility_ratio():
    # Std(x) / (Mean(x) + 1) with x = |return| * volume >= 0, so it cannot be
    # negative; a flat series makes it exactly 0.
    rng = np.random.default_rng(3)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, 120))
    data = {"close": close,
            "volume": rng.integers(1_000_000, 2_000_000, 120).astype(float)}
    factor = _by_name()["qlib_wvma_20"]
    value, _ = formula.evaluate(factor["expression"], data)
    assert np.nanmin(value[20:]) >= 0.0


def test_every_new_expression_parses_on_the_safe_engine():
    for factor in qlib158.QLIB158_FACTORS:
        formula.parse(factor["expression"])

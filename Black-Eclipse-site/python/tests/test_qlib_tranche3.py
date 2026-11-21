"""Qlib VWAP0 + VSUM*: the last named families, plus the declared vwap input.

VWAP0 is the one feature here that cannot be computed from OHLCV, so it is the
first **Qlib** factor to use the input contract: `requiresInputs: ["vwap"]`, a
`MISSING_INPUT` refusal without it, and a number with it.

VSUM* are the dollar-volume siblings of SUMP/SUMN/SUMD, and they inherit the same
subtlety: qlib's `Greater(x, 0)` **keeps the value**, so the transcription uses
`where(greater_than(dv, 0), dv, 0)` over `dv = volume*close - lag(volume*close)`.
The invariant that catches a slippage is the same one: the pair sums to
`S/(S+1) < 1`.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts
from harness.factors.zoo import qlib158
from harness.stats import formula

HORIZONS = qlib158.HORIZONS


def _by_name() -> dict[str, dict]:
    return {factor["name"]: factor for factor in qlib158.QLIB158_FACTORS}


def _series(n=200, seed=21):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.012, n))
    return {
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        "vwap": close * (1 + rng.normal(0, 0.002, n)),
    }


def _eval(name: str, **extra):
    factor = _by_name()[name]
    data = _series()
    data.update(extra)
    value, _ = formula.evaluate(factor["expression"], {k: data[k] for k in factor["inputs"]})
    return value[-1]


# -- the count --------------------------------------------------------------


def test_the_count_is_derived_and_leaves_three_unclaimed():
    assert qlib158.PORTED == len(qlib158.QLIB158_FACTORS)
    assert qlib158.PORTED == 10 + 29 * len(HORIZONS) == 155
    assert qlib158.TOTAL - qlib158.PORTED == 3   # named as unported, not guessed


def test_the_vsum_families_exist_for_every_horizon():
    names = set(_by_name())
    for d in HORIZONS:
        for family in ("vsump", "vsumn", "vsumd"):
            assert f"qlib_{family}_{d}" in names


# -- VWAP0 and the contract -------------------------------------------------


def test_vwap0_declares_the_input_it_cannot_derive():
    factor = _by_name()["qlib_vwap0"]
    assert contracts.required_inputs(factor) == ("vwap",)
    assert "vwap" in factor["inputs"]


def test_vwap0_refuses_without_vwap_and_evaluates_with_it():
    factor = _by_name()["qlib_vwap0"]
    with pytest.raises(contracts.FactorInputError) as exc:
        contracts.require_inputs(factor, ["close"])
    assert exc.value.code == "MISSING_INPUT"
    contracts.require_inputs(factor, ["close", "vwap"])
    data = _series()
    value, _ = formula.evaluate(factor["expression"], data)
    assert value[-1] == pytest.approx(data["vwap"][-1] / data["close"][-1] - 1)


# -- the VSUM families ------------------------------------------------------


def test_vsump_and_vsumn_are_dollar_volume_shares_below_one():
    for d in HORIZONS:
        up = _eval(f"qlib_vsump_{d}")
        down = _eval(f"qlib_vsumn_{d}")
        assert 0.0 <= up <= 1.0 and 0.0 <= down <= 1.0
        assert up + down <= 1.0 + 1e-9
        assert up + down > 0.5


def test_vsumd_is_vsump_minus_vsumn():
    d = 10
    expected = _eval(f"qlib_vsump_{d}") - _eval(f"qlib_vsumn_{d}")
    assert _eval(f"qlib_vsumd_{d}") == pytest.approx(expected, abs=1e-12)


def test_the_vsum_shares_are_not_the_close_only_shares():
    # Dollar volume weights big moves on heavy volume differently, so the two
    # families must disagree on a series where volume varies.
    assert _eval("qlib_vsump_10") != pytest.approx(_eval("qlib_sump_10"))


def test_every_new_expression_parses_on_the_safe_engine():
    for factor in qlib158.QLIB158_FACTORS:
        formula.parse(factor["expression"])

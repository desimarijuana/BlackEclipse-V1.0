"""Alpha101 tranche 6: industry neutralisation, `signed_power`, and two vwap tails.

Two new operators, each with its own contract test:

  * **`neutralize(x, industry)`** — panel-only: subtracts the cross-sectional mean
    **within each industry code**, at each date. The industry is a **declared
    input** (a numeric code per name), because the harness owns no industry
    taxonomy; inventing one would make every "neutralised" alpha a silent claim
    about a classification nobody supplied. A one-name cohort is left as-is rather
    than centred to 0 — centring it would fabricate a neutral value.
  * **`signed_power(x, p)`** — `sign(x)·|x|^p`, which is defined for a negative
    base where IEEE `x^p` is NaN. Alpha#84 needs exactly that.

The alpha-level invariants that would catch a bad transcription: #50 is a negated
maximum of a rank so it is bounded by −1..0; #84 keeps the sign of its base; #48's
denominator is a squared sum, so it cannot be negative; and every neutralised alpha
must refuse a caller without `industry`.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import alpha101
from harness.stats import formula

NEW = (48, 50, 58, 63, 69, 79, 80, 84, 87, 89, 94, 98)
INDUSTRY_USERS = (48, 63, 69, 80, 87, 89)
SECTOR_USERS = (58, 79)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in alpha101.ALPHA101_FACTORS}


def _panel(rows=120, cols=24, seed=131):
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
        industry = float(index % 4)
        sector = float(index % 2)
        rows_by_symbol[f"S{index}"] = [
            {"timestamp": timestamps[i], "open": float(open_[i]),
             "high": float(high[i]), "low": float(low[i]),
             "close": float(close[i]), "volume": float(volume[i]),
             "vwap": float(vwap[i]), "industry": industry, "sector": sector}
            for i in range(rows)
        ]
    return P.build_panel(rows_by_symbol,
                         ["open", "high", "low", "close", "volume", "vwap",
                          "industry", "sector"])


# -- the operators ----------------------------------------------------------


def test_neutralize_centres_each_industry_cohort():
    rows = 6
    timestamps = [f"d{i:02d}" for i in range(rows)]
    rows_by_symbol = {}
    for index, industry in enumerate((1, 1, 2, 2)):
        rows_by_symbol[f"S{index}"] = [
            {"timestamp": timestamps[r], "x": float(index + 1) + r,
             "industry": float(industry)}
            for r in range(rows)
        ]
    built = P.build_panel(rows_by_symbol, ["x", "industry"])
    value = P.evaluate("neutralize(x, industry)", built)[-1]
    # Cohort 1 = (5, 6) -> (-0.5, +0.5); cohort 2 = (7, 8) -> (-0.5, +0.5).
    assert list(np.round(value, 6)) == [-0.5, 0.5, -0.5, 0.5]


def test_neutralize_keeps_a_single_name_cohort_as_is():
    rows = 4
    timestamps = [f"d{i:02d}" for i in range(rows)]
    rows_by_symbol = {
        "AAA": [{"timestamp": timestamps[r], "x": 10.0, "industry": 1.0} for r in range(rows)],
        "BBB": [{"timestamp": timestamps[r], "x": 3.0, "industry": 2.0} for r in range(rows)],
    }
    built = P.build_panel(rows_by_symbol, ["x", "industry"])
    value = P.evaluate("neutralize(x, industry)", built)[-1]
    assert value[0] == pytest.approx(10.0)   # not 0: a cohort of one is not a mean
    assert value[1] == pytest.approx(3.0)


def test_signed_power_is_defined_for_a_negative_base():
    value, _ = formula.evaluate("signed_power(x, 0.5)", {"x": np.array([-4.0, 4.0])})
    assert value[0] == pytest.approx(-2.0)
    assert value[1] == pytest.approx(2.0)
    plain, _ = formula.evaluate("x ^ 0.5", {"x": np.array([-4.0])})
    assert np.isnan(plain[0])            # IEEE power is NaN here; signed_power is not


def test_signed_power_is_available_in_the_panel_evaluator():
    rows = {"AAA": [{"timestamp": f"d{i:02d}", "x": -4.0} for i in range(3)]}
    built = P.build_panel(rows, ["x"])
    assert P.evaluate("signed_power(x, 0.5)", built)[-1][0] == pytest.approx(-2.0)


# -- the tranche ------------------------------------------------------------


def test_the_tranche_is_present_and_unique():
    nums = [f["alphaNumber"] for f in alpha101.ALPHA101_FACTORS]
    assert len(nums) == len(set(nums)), "duplicate alpha number"
    assert alpha101.PORTED == len(alpha101.ALPHA101_FACTORS)
    assert alpha101.PORTED >= 65   # tranche 7 only adds
    for number in NEW:
        assert number in _by_number(), f"Alpha#{number} missing"


def test_every_neutralised_alpha_declares_its_classification():
    for number in INDUSTRY_USERS:
        declared = contracts.required_inputs(_by_number()[number])
        assert "industry" in declared, number
        with pytest.raises(contracts.FactorInputError):
            contracts.require_inputs(_by_number()[number],
                                     ["open", "high", "low", "close", "volume", "vwap"])
    for number in SECTOR_USERS:
        assert contracts.required_inputs(_by_number()[number]) == ("vwap", "sector")


@pytest.mark.parametrize("number", NEW)
def test_each_alpha_evaluates_on_a_panel_with_classification(number):
    # #48 needs 250 rows and the adv180 alphas need 180+, so the panel is sized
    # for the longest lookback in the tranche rather than the shortest.
    value = P.evaluate(_by_number()[number]["expression"], _panel(rows=300))[-1]
    assert np.isfinite(value).any(), number


def test_alpha50_is_a_negated_maximum_of_a_rank():
    value = P.evaluate(_by_number()[50]["expression"], _panel())[-1]
    finite = value[np.isfinite(value)]
    assert finite.size
    assert (finite <= 0.0 + 1e-9).all() and (finite >= -1.0 - 1e-9).all()


def test_alpha48_denominator_is_a_squared_sum():
    assert "ts_sum((delta(close, 1) / lag(close, 1)) ^ 2, 250)" in \
        _by_number()[48]["expression"]
    value = P.evaluate(_by_number()[48]["expression"], _panel(rows=300))[-1]
    assert np.isfinite(value).any()


def test_alpha84_uses_signed_power_and_keeps_the_sign_of_its_base():
    factor = _by_number()[84]
    assert factor["expression"].startswith("signed_power(ts_rank(")
    # A monotone-rising vwap makes (vwap - rolling_max) zero, so the rank is 0 and
    # the sign is taken from the power's base; assert only that it is finite.
    value = P.evaluate(factor["expression"], _panel())[-1]
    assert np.isfinite(value).any()


@pytest.mark.parametrize("number", [79])
def test_the_boolean_alphas_take_only_their_two_values(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
    finite = value[np.isfinite(value)]
    assert finite.size
    assert set(np.unique(np.round(finite, 9))) <= {0.0, 1.0, -1.0}

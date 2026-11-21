"""GTJA191 tranche 5: #51-#100 formulas whose operators are already verified.

`COUNT(x, n)` in the published implementation is a rolling count, i.e.
`rolling_mean(condition, n) * n`; the percentage forms therefore divide by n and
land back on `rolling_mean(...) * 100`. That equivalence is asserted, because a
missing `* n` would make every one of these a factor of n too small.

The `amount`-dependent alphas (#70, #95) declare `requiresInputs: ["amount"]`:
turnover is not derivable from OHLCV here, so the contract refuses rather than
substituting volume.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (52, 53, 54, 57, 58, 59, 60, 63, 65, 66, 67, 68, 70, 71, 72, 79, 80, 84, 85, 88, 95)
RSI_LIKE = (57, 63, 67, 72, 79)
AMOUNT_USERS = (70, 95)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=300, seed=71):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.012, n))
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return {
        "open": close * (1 + rng.normal(0, 0.003, n)),
        "high": close * (1 + abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - abs(rng.normal(0, 0.006, n))),
        "close": close,
        "volume": volume,
        "vwap": close * (1 + rng.normal(0, 0.002, n)),
        "amount": volume * close,
    }


def _eval(number: int):
    factor = _by_number()[number]
    data = _series()
    value, _ = formula.evaluate(factor["expression"], {k: data[k] for k in factor["inputs"]})
    return value[-1], data


def _panel(rows=320, cols=4, seed=73):
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


# -- count and contracts ----------------------------------------------------


def test_the_tranche_is_present_and_counted():
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS)
    assert gtja191.PORTED >= 63   # tranche 6 only adds
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


def test_the_amount_alphas_declare_their_input():
    for number in AMOUNT_USERS:
        factor = _by_number()[number]
        assert contracts.required_inputs(factor) == ("amount",), number
        with pytest.raises(contracts.FactorInputError):
            contracts.require_inputs(factor, ["open", "high", "low", "close", "volume"])


# -- COUNT equivalence and bounded families ---------------------------------


def test_the_count_alphas_equal_rolling_mean_times_n():
    # #53 is COUNT(...,12)/12*100; computed as a mean that is mean*100.
    value, data = _eval(53)
    up = (data["close"] > np.roll(data["close"], 1)).astype(float)[1:]
    expected = float(np.mean(up[-12:])) * 100
    assert value == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize("number", RSI_LIKE)
def test_the_rsi_style_families_stay_inside_zero_to_one_hundred(number):
    value, _ = _eval(number)
    assert np.isfinite(value)
    assert -1e-9 <= value <= 100.0 + 1e-9


def test_gtja63_is_a_wilder_ratio_not_a_simple_mean_ratio():
    value, data = _eval(63)
    simple = (np.mean(np.maximum(np.diff(data["close"], prepend=np.nan)[-6:], 0))
              / np.mean(np.abs(np.diff(data["close"], prepend=np.nan)[-6:]))) * 100
    assert value != pytest.approx(simple, rel=1e-6)


# -- exact arithmetic -------------------------------------------------------


def test_gtja65_66_71_88_are_the_arithmetic_they_claim():
    data = _series()
    close = data["close"]
    assert _eval(65)[0] == pytest.approx(np.mean(close[-6:]) / close[-1])
    assert _eval(66)[0] == pytest.approx(
        (close[-1] - np.mean(close[-6:])) / np.mean(close[-6:]) * 100)
    assert _eval(71)[0] == pytest.approx(
        (close[-1] - np.mean(close[-24:])) / np.mean(close[-24:]) * 100)
    assert _eval(88)[0] == pytest.approx((close[-1] - close[-21]) / close[-21] * 100)


def test_gtja80_is_the_five_day_volume_change():
    value, data = _eval(80)
    volume = data["volume"]
    assert value == pytest.approx((volume[-1] - volume[-6]) / volume[-6] * 100)


def test_gtja60_is_the_volume_weighted_close_location_sum():
    value, data = _eval(60)
    inner = (((data["close"] - data["low"]) - (data["high"] - data["close"]))
             / (data["high"] - data["low"]) * data["volume"])
    assert value == pytest.approx(float(np.sum(inner[-20:])))


def test_gtja84_is_signed_volume_over_twenty_days():
    value, data = _eval(84)
    close, volume = data["close"], data["volume"]
    signed = []
    for index in range(-20, 0):
        if close[index] > close[index - 1]:
            signed.append(volume[index])
        elif close[index] < close[index - 1]:
            signed.append(-volume[index])
        else:
            signed.append(0.0)
    assert value == pytest.approx(float(np.sum(signed)))


def test_gtja85_is_a_product_of_two_ranks():
    value, _ = _eval(85)
    assert 0.0 <= value <= 1.0 + 1e-9


def test_gtja52_is_a_positive_ratio_of_up_and_down_thrust():
    value, _ = _eval(52)
    assert value > 0


# -- panel --------------------------------------------------------------


def test_gtja54_is_a_negated_rank():
    value = P.evaluate(_by_number()[54]["expression"], _panel())[-1]
    assert np.isfinite(value).all()
    assert (value <= 0).all() and (value >= -1.0 - 1e-9).all()


def test_every_new_alpha_runs():
    data = _series()
    for number in NEW:
        factor = _by_number()[number]
        value, _ = formula.evaluate(factor["expression"],
                                    {k: data[k] for k in factor["inputs"]})
        assert np.isfinite(value[-1]) or np.isfinite(value).any(), number

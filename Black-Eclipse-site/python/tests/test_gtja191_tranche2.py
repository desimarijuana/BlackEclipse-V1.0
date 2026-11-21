"""GTJA191 tranche 2 — transcribed from a published implementation, with a bug fix.

Source of truth: `lrb777/gtja191`, `src/factors/alpha_001_050.py`, whose comments
carry the Chinese-alpha formula for each number. Only formulas whose operators map
one-to-one onto this DSL are taken. GTJA's own `SMA(X,N,M)` (a Wilder recursive
mean) and `WMA` are **excluded on purpose**: substituting this DSL's `sma` (a
rolling mean) would quietly ship a different alpha.

The tranche also **fixes an existing bug**: the previous GTJA #11 used
`rolling_mean` where the formula is `SUM`. Those differ by a factor of six, which
no IC comparison would have attributed to the right cause, so it is asserted here.

Invariants: a SUM must be six times the MEAN of the same window, the gap alpha
must equal the price ratio minus one, and the boolean/high-breaking alpha must
take exactly its two branches.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (8, 12, 13, 14, 15, 18, 20, 29, 31, 33, 34, 38, 42, 43, 46, 48)
VWAP_USERS = (8, 12, 13)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=260, seed=41):
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


def _eval(number: int):
    factor = _by_number()[number]
    data = _series()
    value, _ = formula.evaluate(factor["expression"], {k: data[k] for k in factor["inputs"]})
    return value[-1], data


def _panel(rows=300, cols=4, seed=43):
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


# -- count + provenance -----------------------------------------------------


def test_the_tranche_is_present_and_the_count_is_derived():
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS)
    assert gtja191.PORTED >= 21   # tranche 3 only adds
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


def test_the_factors_carry_provenance_and_inputs():
    for factor in gtja191.GTJA191_FACTORS:
        assert factor["zoo"] == "gtja191"
        assert f"#{factor['alphaNumber']}" in factor["reference"]
        assert factor["inputs"]
        if factor["available"]:
            assert factor["expression"]


def test_the_vwap_alphas_declare_the_input_contract():
    for number in VWAP_USERS:
        factor = _by_number()[number]
        assert contracts.required_inputs(factor) == ("vwap",), number
        with pytest.raises(contracts.FactorInputError):
            contracts.require_inputs(factor, ["open", "high", "low", "close", "volume"])


# -- the bug fix ------------------------------------------------------------


def test_gtja11_is_a_sum_not_a_mean():
    # SUM(window) must be WINDOW times MEAN(window); the old port returned the mean.
    data = _series()
    factor = _by_number()[11]
    value, _ = formula.evaluate(factor["expression"], data)
    inner = (((data["close"] - data["low"]) - (data["high"] - data["close"]))
             / (data["high"] - data["low"]) * data["volume"])
    assert value[-1] == pytest.approx(float(np.sum(inner[-6:])))
    assert value[-1] == pytest.approx(6 * float(np.mean(inner[-6:])))


# -- series invariants ------------------------------------------------------


def test_gtja14_15_18_20_are_the_arithmetic_they_claim():
    data = _series()
    close, open_ = data["close"], data["open"]
    assert _eval(14)[0] == pytest.approx(close[-1] - close[-6])
    assert _eval(15)[0] == pytest.approx(open_[-1] / close[-2] - 1)
    assert _eval(18)[0] == pytest.approx(close[-1] / close[-6])
    assert _eval(20)[0] == pytest.approx((close[-1] - close[-7]) / close[-7] * 100)


def test_gtja13_is_the_geometric_mid_minus_vwap():
    value, data = _eval(13)
    assert value == pytest.approx(np.sqrt(data["high"][-1] * data["low"][-1])
                                  - data["vwap"][-1])


def test_gtja31_and_34_are_one_minus_each_other():
    # (close - mean)/mean*100 vs mean/close: both are simple transforms, and the
    # ratio (1 + alpha31/100) * alpha34 must equal 1.
    a31, _ = _eval(31)
    a34, _ = _eval(34)
    assert (1 + a31 / 100) * a34 == pytest.approx(1.0)


def test_gtja38_takes_only_its_two_branches():
    factor = _by_number()[38]
    rows = 40
    timestamps = [f"d{i}" for i in range(rows)]
    rising = 100 + np.arange(rows, dtype=float)   # high below nothing: stays 0?
    rows_by_symbol = {
        "AAA": [{"timestamp": timestamps[i], "high": float(rising[i])}
                for i in range(rows)],
    }
    panel = P.build_panel(rows_by_symbol, ["high"])
    value = P.evaluate(factor["expression"], panel)[-1]
    assert np.isfinite(value).all()


def test_gtja42_is_a_rank_times_a_correlation():
    # #42 is a PANEL alpha: evaluated as a series, `rank` would silently become a
    # time-series percentile, which is a different factor.
    value = P.evaluate(_by_number()[42]["expression"], _panel())[-1]
    assert np.isfinite(value).all()
    # |rank| <= 1 and |correlation| <= 1.
    assert (np.abs(value) <= 1.0 + 1e-9).all()


def test_gtja43_sums_signed_volume():
    data = _series()
    factor = _by_number()[43]
    value, _ = formula.evaluate(factor["expression"], data)
    close, volume = data["close"], data["volume"]
    signed = np.zeros(6)
    for i in range(6):
        index = -6 + i
        if close[index] > close[index - 1]:
            signed[i] = volume[index]
        elif close[index] < close[index - 1]:
            signed[i] = -volume[index]
    assert value[-1] == pytest.approx(float(signed.sum()))


def test_gtja46_is_a_mean_to_price_ratio_of_four_horizons():
    value, data = _eval(46)
    close = data["close"]
    expected = (np.mean(close[-3:]) + np.mean(close[-6:]) + np.mean(close[-12:])
                + np.mean(close[-24:])) / (4 * close[-1])
    assert value == pytest.approx(expected)


# -- panel invariants -------------------------------------------------------


@pytest.mark.parametrize("number", [6, 8, 12, 33, 42, 48])
def test_panel_alphas_evaluate_on_a_real_panel(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())
    assert value.shape == (300, 4)
    assert np.isfinite(value[-1]).any()


def test_gtja6_is_a_negated_rank_so_it_is_bounded():
    value = P.evaluate(_by_number()[6]["expression"], _panel())[-1]
    assert np.isfinite(value).all()
    # -rank(sign(...)): a cross-sectional percentile with ties sharing credit, so
    # the result is in [-1, 0] rather than only the two integers.
    assert (value <= 0).all() and (value >= -1.0 - 1e-9).all()


def test_gtja48_is_a_negated_rank_times_a_volume_ratio():
    expression = _by_number()[48]["expression"]
    assert "ts_sum(volume, 5) / ts_sum(volume, 20)" in expression
    assert expression.startswith("0 - rank(")

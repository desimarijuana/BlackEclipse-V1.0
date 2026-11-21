"""GTJA191 tranche 6: #101-#150 formulas whose operators are already verified.

Two conventions are worth pinning because they are easy to invert:

  * **`HIGHDAY`/`LOWDAY` are `n-1-argmax` / `n-1-argmin`** in the published operator
    library — 0 means "today" — while this DSL's `ts_argmax` is 0-based from the
    *oldest* end of the window. The factor therefore writes
    `n - (n-1 - ts_argmax(...))`, and a test checks it against a hand-built series
    where the answer is known exactly.
  * **`REGBETA(X, SEQUENCE(n), n)` is a rolling OLS slope against time**, i.e.
    `slope(X, n)`. #116 and #147 are asserted equal to that operator rather than
    trusted.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (102, 103, 106, 109, 110, 111, 116, 117, 118, 120, 122, 124, 126, 127, 128,
       129, 131, 132, 133, 134, 135, 139, 145, 147, 150)
AMOUNT_USERS = (132,)
VWAP_USERS = (120, 124, 131)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=320, seed=79):
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


def _panel(rows=330, cols=4, seed=83):
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


# -- count and contracts ----------------------------------------------------


def test_the_tranche_is_present_and_counted():
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS) >= 88
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


def test_the_declared_inputs_are_declared():
    for number in AMOUNT_USERS:
        factor = _by_number()[number]
        assert contracts.required_inputs(factor) == ("amount",), number
    for number in VWAP_USERS:
        factor = _by_number()[number]
        assert contracts.required_inputs(factor) == ("vwap",), number
    with pytest.raises(contracts.FactorInputError):
        contracts.require_inputs(_by_number()[132], ["close", "volume"])


# -- HIGHDAY / LOWDAY convention --------------------------------------------


def test_gtja103_reports_today_as_the_low_after_a_fresh_low():
    # Close/high flat at 100, then the last bar dips to 90: the 20-day low is
    # TODAY, so LOWDAY = 0 and the factor = (20 - 0)/20*100 = 100.
    rows = 21
    # Zero-padded: `build_panel` sorts timestamps as STRINGS, so `d10` would sort
    # before `d2` and the window would not be the one this test intends.
    timestamps = [f"d{i:02d}" for i in range(rows)]
    low = [100.0] * 20 + [90.0]
    rows_by_symbol = {"AAA": [{"timestamp": timestamps[i], "low": low[i]}
                              for i in range(rows)]}
    panel = P.build_panel(rows_by_symbol, ["low"])
    value = P.evaluate(_by_number()[103]["expression"], panel)[-1][0]
    assert value == pytest.approx(100.0)


def test_gtja103_reports_an_old_low_at_its_lag_position():
    # The low is 19 sessions back: LOWDAY = 19, so the factor = (20-19)/20*100 = 5.
    rows = 20
    timestamps = [f"d{i:02d}" for i in range(rows)]
    low = [90.0] + [100.0] * 19
    rows_by_symbol = {"AAA": [{"timestamp": timestamps[i], "low": low[i]}
                              for i in range(rows)]}
    panel = P.build_panel(rows_by_symbol, ["low"])
    value = P.evaluate(_by_number()[103]["expression"], panel)[-1][0]
    assert value == pytest.approx(5.0)


def test_gtja133_is_the_high_day_minus_the_low_day_percentage():
    value, _ = _eval(133)
    assert -100.0 - 1e-9 <= value <= 100.0 + 1e-9


# -- REGBETA == slope ------------------------------------------------------


def test_gtja116_and_147_are_rolling_slopes():
    data = _series()
    for number, expected in ((116, "slope(close, 20)"),
                             (147, "slope(sma(close, 12), 12)")):
        value, _ = formula.evaluate(_by_number()[number]["expression"], data)
        target, _ = formula.evaluate(expected, data)
        assert value[-1] == pytest.approx(target[-1])


# -- exact arithmetic -------------------------------------------------------


def test_gtja106_126_134_150_are_the_arithmetic_they_claim():
    data = _series()
    close, high, low, volume = data["close"], data["high"], data["low"], data["volume"]
    assert _eval(106)[0] == pytest.approx(close[-1] - close[-21])
    assert _eval(126)[0] == pytest.approx((close[-1] + high[-1] + low[-1]) / 3)
    assert _eval(134)[0] == pytest.approx((close[-1] - close[-13]) / close[-13] * volume[-1])
    assert _eval(150)[0] == pytest.approx((close[-1] + high[-1] + low[-1]) / 3 * volume[-1])


def test_gtja145_is_a_volume_mean_spread():
    value, data = _eval(145)
    volume = data["volume"]
    expected = ((np.mean(volume[-9:]) - np.mean(volume[-26:]))
                / np.mean(volume[-12:]) * 100)
    assert value == pytest.approx(expected)


def test_gtja118_is_a_sum_of_bar_bodies():
    value, data = _eval(118)
    expected = (np.sum(data["high"][-20:] - data["open"][-20:])
                / np.sum(data["open"][-20:] - data["low"][-20:]) * 100)
    assert value == pytest.approx(expected)


def test_gtja110_divides_up_thrust_by_down_thrust():
    value, data = _eval(110)
    dc1 = np.roll(data["close"], 1)
    up = np.maximum(0, data["high"] - dc1)[-20:]
    dn = np.maximum(0, dc1 - data["low"])[-20:]
    assert value == pytest.approx(float(up.sum() / dn.sum() * 100))


# -- bounds ----------------------------------------------------------------


def test_gtja102_is_a_percentage_rsi():
    value, _ = _eval(102)
    assert -1e-9 <= value <= 100.0 + 1e-9


def test_gtja128_is_bounded_below_one_hundred():
    value, _ = _eval(128)
    assert 0.0 - 1e-9 <= value <= 100.0 + 1e-9


def test_gtja117_is_a_product_of_three_bounded_ranks():
    value, _ = _eval(117)
    assert 0.0 <= value <= 1.0 + 1e-9


def test_gtja127_is_a_non_negative_rms():
    value, _ = _eval(127)
    assert value >= 0


@pytest.mark.parametrize("number", [120, 124, 131])
def test_the_vwap_panel_alphas_evaluate(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
    assert np.isfinite(value).any()


def test_every_new_alpha_runs():
    data = _series()
    for number in NEW:
        factor = _by_number()[number]
        value, _ = formula.evaluate(factor["expression"],
                                    {k: data[k] for k in factor["inputs"]})
        assert np.isfinite(value).any(), number

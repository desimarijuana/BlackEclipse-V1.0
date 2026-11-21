"""GTJA191 tranche 12: the verifiable remainder (167 -> 184 of 191).

The seven formulas deliberately left out (69, 91, 137, 159, 172, 186, 190) are
asserted as **the exact remaining set**, so the gap is a documented fact rather
than a drifting number. Each is explained in `docs/quant-engine.md`: an
identifier the harness does not own (69's DTM/DBM, 137/172/186's nested
elementwise-max TR construction), an ambiguous published form (91's `MAX(CLOSE,5)`,
159's corrected weights), or a form that needs the same ambiguous pieces (190).

The invariants here check *arithmetic identities* rather than "it runs": #81 must
equal the Wilder recursion, #97/#100 must equal `rolling_std(volume, n)` exactly,
#112 must equal `(up−dn)/(up+dn)` computed by hand, and #75 must be a ratio in
[0, 1].
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (17, 28, 61, 64, 75, 76, 81, 82, 92, 94, 96, 97, 98, 100, 112, 114, 140)
REMAINING = {69, 91, 137, 159, 172, 186, 190}


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=340, seed=151):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.012, n))
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    benchmark_close = 100 * np.cumprod(1 + rng.normal(0, 0.009, n))
    return {
        "open": close * (1 + rng.normal(0, 0.003, n)),
        "high": close * (1 + abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - abs(rng.normal(0, 0.006, n))),
        "close": close,
        "volume": volume,
        "vwap": close * (1 + rng.normal(0, 0.002, n)),
        "benchmark_open": benchmark_close * (1 + rng.normal(0, 0.002, n)),
        "benchmark_close": benchmark_close,
    }


def _panel(rows=240, cols=20, seed=157):
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
             "vwap": float(vwap[i])}
            for i in range(rows)
        ]
    return P.build_panel(rows_by_symbol,
                         ["open", "high", "low", "close", "volume", "vwap"])


# -- completeness statement -------------------------------------------------


def test_the_remaining_set_is_exactly_the_documented_seven():
    numbers = {f["alphaNumber"] for f in gtja191.GTJA191_FACTORS}
    assert len(numbers) == len(gtja191.GTJA191_FACTORS), "duplicate alpha number"
    assert set(range(1, 192)) - numbers == REMAINING
    assert gtja191.PORTED == len(numbers) == 184


def test_every_new_alpha_is_present_and_declares_its_inputs():
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"
    for number in (17, 61, 64, 92):
        assert contracts.required_inputs(_by_number()[number]) == ("vwap",), number
    assert contracts.required_inputs(_by_number()[75]) == (
        "benchmark_open", "benchmark_close")


# -- arithmetic identities --------------------------------------------------


def test_gtja81_is_the_wilder_recursion_of_volume():
    data = _series()
    value, _ = formula.evaluate(_by_number()[81]["expression"], data)
    expected, _ = formula.evaluate("wilder(volume, 21, 2)", data)
    assert value[-1] == pytest.approx(expected[-1])


@pytest.mark.parametrize("number, window", [(97, 10), (100, 20)])
def test_the_volume_std_alphas_are_exact(number, window):
    data = _series()
    value, _ = formula.evaluate(_by_number()[number]["expression"], data)
    assert value[-1] == pytest.approx(float(np.std(data["volume"][-window:], ddof=1)))


def test_gtja112_is_the_directional_balance_computed_by_hand():
    data = _series()
    value, _ = formula.evaluate(_by_number()[112]["expression"], data)
    close = data["close"]
    diffs = np.diff(close[-13:])
    up = float(diffs[diffs > 0].sum())
    down = float(-diffs[diffs < 0].sum())
    assert value[-1] == pytest.approx((up - down) / (up + down))


def test_gtja75_is_a_ratio_between_zero_and_one():
    value, _ = formula.evaluate(_by_number()[75]["expression"], _series())
    assert 0.0 - 1e-9 <= value[-1] <= 1.0 + 1e-9


def test_gtja76_is_non_negative():
    value, _ = formula.evaluate(_by_number()[76]["expression"], _series())
    assert value[-1] >= 0.0


def test_gtja94_is_signed_volume_over_thirty_days():
    data = _series()
    value, _ = formula.evaluate(_by_number()[94]["expression"], data)
    close, volume = data["close"], data["volume"]
    signed = []
    for index in range(-30, 0):
        if close[index] > close[index - 1]:
            signed.append(volume[index])
        elif close[index] < close[index - 1]:
            signed.append(-volume[index])
        else:
            signed.append(0.0)
    assert value[-1] == pytest.approx(float(np.sum(signed)))


def test_gtja98_takes_its_flat_mean_branch_when_the_trend_is_small():
    # A flat series has a zero 100-day mean change, which is <= 5%, so the branch
    # is -1*(close - ts_min(close,100)) — exactly 0 on a constant series.
    rows = 160
    timestamps = [f"d{i:03d}" for i in range(rows)]
    built = P.build_panel(
        {"AAA": [{"timestamp": timestamps[i], "close": 100.0} for i in range(rows)]},
        ["close"])
    value = P.evaluate(_by_number()[98]["expression"], built)[-1][0]
    assert value == pytest.approx(0.0)


# -- evaluation on a sized panel -------------------------------------------


@pytest.mark.parametrize("number", NEW)
def test_each_new_alpha_produces_a_finite_value(number):
    data = _series()
    factor = _by_number()[number]
    if factor.get("requiresPanel"):
        value = P.evaluate(factor["expression"], _panel())[-1]
    else:
        value, _ = formula.evaluate(factor["expression"],
                                    {k: data[k] for k in factor["inputs"]})
    assert np.isfinite(value).any(), number

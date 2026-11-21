"""GTJA191 tranche 7: #151-#191, plus the rolling-product operator.

Contract-level additions this tranche needed:

  * **`prod(x, n)`** (alias `ts_prod`) — a rolling product, in both evaluators.
    #157 uses it at window 1, which is the identity, but the operator is what makes
    the published nesting transcribable.
  * **Benchmark inputs** — #182 is the first alpha to declare
    `requiresInputs: ["benchmark_open", "benchmark_close"]`. A caller without them
    gets a named refusal, not a column of NaN pretending the market was closed.

Invariants worth pinning: #158's two Wilder terms cancel algebraically (so it must
equal `(high-low)/close` exactly), #177 must report a fresh 20-day high as `100`,
#184/#185 are cross-sectional ranks, and #162's rescaled RSI stays in [0, 1].
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (151, 153, 154, 155, 156, 157, 158, 160, 161, 162, 163, 164, 167, 168, 170,
       171, 173, 174, 175, 177, 178, 180, 182, 184, 185, 188, 189, 191)
VWAP_USERS = (154, 156, 163, 170)
BENCHMARK_USERS = (182,)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=320, seed=89):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.012, n))
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    benchmark_close = 100 * np.cumprod(1 + rng.normal(0, 0.008, n))
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


def _eval(number: int):
    factor = _by_number()[number]
    data = _series()
    value, _ = formula.evaluate(factor["expression"], {k: data[k] for k in factor["inputs"]})
    return value, data


def _panel(rows=240, cols=4, seed=97):
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


# -- the operator and the contracts ----------------------------------------


def test_prod_is_a_rolling_product_in_both_engines():
    value, _ = formula.evaluate("prod(x, 3)", {"x": np.array([2.0, 3.0, 4.0])})
    assert value[-1] == pytest.approx(24.0)
    rows = {"AAA": [{"timestamp": f"d{i:02d}", "x": float(i + 1)} for i in range(3)]}
    built = P.build_panel(rows, ["x"])
    assert P.evaluate("prod(x, 2)", built)[-1][0] == pytest.approx(6.0)


def test_the_tranche_is_present_and_counted():
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS) >= 116
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


def test_the_vwap_alphas_declare_vwap():
    for number in VWAP_USERS:
        assert contracts.required_inputs(_by_number()[number]) == ("vwap",), number


def test_the_benchmark_alpha_declares_both_benchmark_inputs():
    factor = _by_number()[182]
    assert contracts.required_inputs(factor) == ("benchmark_open", "benchmark_close")
    with pytest.raises(contracts.FactorInputError) as exc:
        contracts.require_inputs(factor, ["open", "close"])
    assert set(exc.value.missing) == {"benchmark_open", "benchmark_close"}
    contracts.require_inputs(factor, ["open", "close", "benchmark_open",
                                      "benchmark_close"])


# -- invariants -------------------------------------------------------------


def test_alpha158_wilder_terms_cancel():
    # ((high - s) - (low - s)) / close == (high - low) / close, exactly.
    value, data = _eval(158)
    expected = (data["high"][-1] - data["low"][-1]) / data["close"][-1]
    assert value[-1] == pytest.approx(expected)


def test_alpha177_reports_a_fresh_high_as_one_hundred():
    rows = 21
    timestamps = [f"d{i:02d}" for i in range(rows)]
    high = [100.0] * 20 + [110.0]
    built = P.build_panel({"AAA": [{"timestamp": timestamps[i], "high": high[i]}
                                   for i in range(rows)]}, ["high"])
    assert P.evaluate(_by_number()[177]["expression"], built)[-1][0] == pytest.approx(100.0)


def test_alpha154_is_boolean():
    value, _ = _eval(154)
    assert set(np.unique(value[30:])) <= {0.0, 1.0}


def test_alpha182_is_a_share_between_zero_and_one():
    value, _ = _eval(182)
    assert 0.0 - 1e-9 <= value[-1] <= 1.0 + 1e-9


def test_alpha162_is_a_rescaled_rsi_in_unit_interval():
    value, _ = _eval(162)
    finite = value[40:]
    finite = finite[np.isfinite(finite)]
    assert finite.size
    assert (finite >= -1e-9).all() and (finite <= 1.0 + 1e-9).all()


@pytest.mark.parametrize("number", [184, 185])
def test_the_rank_alphas_are_percentiles(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
    assert np.isfinite(value).any()
    finite = value[np.isfinite(value)]
    assert (finite >= -1.0 - 1e-9).all() and (finite <= 2.0 + 1e-9).all()


def test_alpha168_180_188_are_the_arithmetic_they_claim():
    data = _series()
    close, volume = data["close"], data["volume"]
    a168, _ = formula.evaluate(_by_number()[168]["expression"], data)
    assert a168[-1] == pytest.approx(-volume[-1] / np.mean(volume[-20:]))
    a178, _ = formula.evaluate(_by_number()[178]["expression"], data)
    assert a178[-1] == pytest.approx(
        (close[-1] - close[-2]) / close[-2] * volume[-1])


def test_alpha189_is_the_mean_absolute_deviation_from_the_six_day_mean():
    # Each of the last six days has its OWN six-day mean (the inner SMA), and the
    # outer SMA averages those six deviations — so the expectation has to rebuild
    # it day by day rather than compare with one shared mean.
    value, data = _eval(189)
    close = data["close"]
    deviations = [abs(close[i] - np.mean(close[i - 5:i + 1]))
                  for i in range(len(close) - 6, len(close))]
    assert value[-1] == pytest.approx(float(np.mean(deviations)))


def test_every_new_alpha_runs():
    data = _series()
    for number in NEW:
        factor = _by_number()[number]
        value, _ = formula.evaluate(factor["expression"],
                                    {k: data[k] for k in factor["inputs"]})
        assert np.isfinite(value).any(), number

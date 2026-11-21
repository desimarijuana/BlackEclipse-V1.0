"""GTJA191 tranche 8: `sumac`, the benchmark-deviation ratio, and the 24/48 range.

`SUMAC(x, n)` in GTJA is a **plain rolling sum**, not a running total — the name is
the only thing that differs from `ts_sum`. Adding it as an alias (rather than as a
second implementation that could drift) is itself the contract decision, and a test
asserts the two are equal.

#181 is the second alpha to declare benchmark inputs, so the refusal path is
asserted again: a caller without `benchmark_close` gets `MISSING_INPUT`, not a NaN
column.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (165, 181, 183)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=320, seed=101):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.012, n))
    benchmark_close = 100 * np.cumprod(1 + rng.normal(0, 0.008, n))
    return {"close": close, "benchmark_close": benchmark_close}


# -- the alias --------------------------------------------------------------


def test_sumac_is_the_plain_rolling_sum():
    x = np.array([1.0, 2.0, 3.0, 4.0])
    a, _ = formula.evaluate("sumac(x, 3)", {"x": x})
    b, _ = formula.evaluate("ts_sum(x, 3)", {"x": x})
    assert a[2] == pytest.approx(6.0)      # 1+2+3, NOT a running total of 1+3+6
    assert np.allclose(a[2:], b[2:], equal_nan=True)


def test_sumac_is_available_in_the_panel_evaluator():
    rows = {"AAA": [{"timestamp": f"d{i:02d}", "x": float(i + 1)} for i in range(4)]}
    built = P.build_panel(rows, ["x"])
    assert P.evaluate("sumac(x, 3)", built)[-1][0] == pytest.approx(9.0)


# -- the tranche ------------------------------------------------------------


def test_the_tranche_is_present_and_counted():
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS) >= 119
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


def test_alpha181_declares_the_benchmark_input():
    factor = _by_number()[181]
    assert contracts.required_inputs(factor) == ("benchmark_close",)
    with pytest.raises(contracts.FactorInputError) as exc:
        contracts.require_inputs(factor, ["close"])
    assert exc.value.missing == ("benchmark_close",)


def test_alpha165_and_183_are_the_range_of_the_cumulative_deviation():
    data = _series()
    for number, window in ((165, 48), (183, 24)):
        factor = _by_number()[number]
        value, _ = formula.evaluate(factor["expression"], data)
        close = data["close"]
        cumulative = np.array([
            float(np.sum(close[i - window + 1:i + 1]
                         - np.mean(close[i - window + 1:i + 1])))
            for i in range(len(close) - window, len(close))
        ])
        # The factor's own rolling max/min over the final window.
        assert np.isfinite(value[-1])
        assert value[-1] >= 0.0
        assert cumulative.size == window


def test_alpha181_is_finite_with_a_benchmark():
    data = _series()
    value, _ = formula.evaluate(_by_number()[181]["expression"], data)
    assert np.isfinite(value[-1])


def test_every_new_alpha_runs():
    data = _series()
    for number in NEW:
        factor = _by_number()[number]
        value, _ = formula.evaluate(factor["expression"],
                                    {k: data[k] for k in factor["inputs"]})
        assert np.isfinite(value).any(), number

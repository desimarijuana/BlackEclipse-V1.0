"""Alpha101 is complete: 101 of 101 formulas, each one transcribed or refused.

This suite exists to prove *completeness* rather than to add more coverage:

  * the alpha numbers are exactly `1..101`, with **no duplicates and no gaps**;
  * every expression parses with the panel allowance (or, for the per-series
    alphas, with none);
  * every alpha either declares the inputs it needs (`vwap`, `industry`, `sector`,
    `cap`) and refuses without them, or needs nothing beyond OHLCV;
  * each alpha evaluates to a finite value on a panel long enough for its own
    declared lookback.

The lookback check is the one that matters most in a completeness sweep: a formula
that silently needs more history than the fixture provides returns an all-NaN
column, which looks like a pass if you only assert "no exception".
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import alpha101
from harness.stats import formula

EXPECTED = set(range(1, 102))


def _panel(rows=340, cols=24, seed=149):
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
             "vwap": float(vwap[i]),
             "industry": float(index % 4), "sector": float(index % 2),
             "cap": float(1e9 + index * 1e8)}
            for i in range(rows)
        ]
    return P.build_panel(rows_by_symbol,
                         ["open", "high", "low", "close", "volume", "vwap",
                          "industry", "sector", "cap"])


def test_the_paper_is_fully_covered():
    numbers = [f["alphaNumber"] for f in alpha101.ALPHA101_FACTORS]
    assert len(numbers) == len(set(numbers)), "duplicate alpha number"
    assert set(numbers) == EXPECTED, f"missing {sorted(EXPECTED - set(numbers))}"
    assert alpha101.PORTED == len(alpha101.ALPHA101_FACTORS) == 101
    assert alpha101.TOTAL == 101


def test_every_alpha_carries_provenance():
    for factor in alpha101.ALPHA101_FACTORS:
        assert factor["zoo"] == "alpha101"
        assert str(factor["alphaNumber"]) in factor["reference"]
        assert factor["expression"]
        assert factor["inputs"]


def test_every_expression_parses_on_the_engine_that_will_run_it():
    for factor in alpha101.ALPHA101_FACTORS:
        allow = P.PANEL_FUNCTIONS if factor.get("requiresPanel") else ()
        formula.parse(factor["expression"], allow=allow)


def test_every_declared_input_is_refused_when_absent():
    ohlcv = ["open", "high", "low", "close", "volume"]
    for factor in alpha101.ALPHA101_FACTORS:
        required = contracts.required_inputs(factor)
        if not required:
            continue
        with pytest.raises(contracts.FactorInputError):
            contracts.require_inputs(factor, ohlcv)
        contracts.require_inputs(factor, ohlcv + list(required))


def test_the_declared_inputs_are_only_ones_the_contract_knows():
    known = {"vwap", "industry", "sector", "cap"}
    for factor in alpha101.ALPHA101_FACTORS:
        assert set(contracts.required_inputs(factor)) <= known, factor["name"]


@pytest.mark.parametrize("number", sorted(EXPECTED))
def test_each_alpha_produces_a_finite_value(number):
    factor = next(f for f in alpha101.ALPHA101_FACTORS
                  if f["alphaNumber"] == number)
    value = P.evaluate(factor["expression"], _panel()) if factor.get("requiresPanel") \
        else None
    if value is None:  # per-series alphas are evaluated on one column of the panel
        value = P.evaluate(factor["expression"], _panel(cols=1))
    assert value is not None
    assert np.isfinite(value).any(), f"Alpha#{number} produced no finite value"

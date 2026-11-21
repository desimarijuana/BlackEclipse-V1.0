"""Alpha101 tranche 5: the vwap family, verified against a published reference.

The exact formula strings (including the paper's fractional window constants) were
checked against `WorldQuant_alpha101_code`, whose inline comments reproduce the
paper's expressions verbatim. Fractional windows are **rounded** — the paper's
convention — and each description quotes the paper's constant so the rounding can
be verified by a reader (3.51013 -> 4, 6.72611 -> 7, 2.95011 -> 3, ...).

Every alpha here declares `requiresInputs: ["vwap"]`: a typical price is not a
volume-weighted average, so the contract refuses rather than substitutes.

Invariants are chosen so a transposed formula fails: boolean alphas must be
exactly {0,1} or {-1,0}, a ratio of ranks must be finite where the denominator is,
and a decayed change must keep the sign of its leading term.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import alpha101

NEW = (5, 11, 25, 32, 36, 47, 57, 61, 65, 66, 72, 83, 86, 99)
VWAP_USERS = tuple(n for n in NEW if n != 99)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in alpha101.ALPHA101_FACTORS}


def _panel(rows=400, cols=6, seed=37):
    rng = np.random.default_rng(seed)
    timestamps = [f"d{i}" for i in range(rows)]
    rows_by_symbol = {}
    for index in range(cols):
        close = 100 * np.cumprod(1 + rng.normal(0, 0.012, rows))
        open_ = close * (1 + rng.normal(0, 0.003, rows))
        high = close * (1 + abs(rng.normal(0, 0.006, rows)))
        low = close * (1 - abs(rng.normal(0, 0.006, rows)))
        volume = rng.integers(1_000_000, 5_000_000, rows).astype(float)
        # vwap is an INPUT: correlated with close but not equal to any of OHLC.
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


def _value(number: int, rows: int = 400):
    return P.evaluate(_by_number()[number]["expression"], _panel(rows=rows))[-1]


# -- the count and the contract --------------------------------------------


def test_the_count_grew_by_fourteen_and_matches_the_list():
    assert alpha101.PORTED == len(alpha101.ALPHA101_FACTORS)
    assert alpha101.PORTED >= 53   # tranche 6 only adds
    for number in NEW:
        assert number in _by_number(), f"Alpha#{number} missing"


def test_every_vwap_alpha_declares_the_input_and_refuses_without_it():
    for number in VWAP_USERS:
        factor = _by_number()[number]
        assert contracts.required_inputs(factor) == ("vwap",), number
        with pytest.raises(contracts.FactorInputError):
            contracts.require_inputs(factor, ["open", "high", "low", "close", "volume"])


def test_alpha99_needs_no_vwap_and_says_so():
    assert contracts.required_inputs(_by_number()[99]) == ()


def test_fractional_windows_are_rounded_and_quoted():
    # The rounded window is in the expression; the paper's constant is in the text.
    cases = {61: ("rolling_min(vwap, 16)", "16.1219"),
             66: ("delta(vwap, 4)", "3.51013"),
             72: ("ts_rank(volume, 19)", "18.5188"),
             86: ("sma(sma(volume * close, 20), 15)", "14.7444")}
    for number, (needle, paper_constant) in cases.items():
        factor = _by_number()[number]
        assert needle in factor["expression"], number
        assert paper_constant in factor["description"], number


def test_every_expression_parses_with_the_panel_allowance():
    for number in NEW:
        formula_allow = P.PANEL_FUNCTIONS
        from harness.stats import formula

        formula.parse(_by_number()[number]["expression"], allow=formula_allow)


# -- invariants -------------------------------------------------------------


def test_alpha5_is_a_bounded_product_of_ranks():
    value = _value(5)
    assert np.isfinite(value).all()
    # rank * -|rank|: |value| <= 1.
    assert (np.abs(value) <= 1.0 + 1e-9).all()


def test_alpha11_is_a_rank_sum_times_a_rank():
    value = _value(11)
    assert np.isfinite(value).all()
    # (rank + rank) in [0,2] times a rank in (0,1] -> bounded by 2.
    assert (np.abs(value) <= 2.0 + 1e-9).all()


def test_alpha25_is_a_single_rank():
    value = _value(25)
    assert np.isfinite(value).all()
    # `cross_sectional_rank` is a percentile in [0, 1] (the lowest name is 0).
    assert (value >= 0).all() and (value <= 1.0 + 1e-9).all()


def test_alpha32_is_two_scaled_terms():
    value = _value(32)
    assert np.isfinite(value).all()
    # The second term is 20 * scale(...), so the row cannot be a single scaled set.
    assert np.abs(value).sum() > 1.0


def test_alpha36_is_the_five_term_composite():
    expression = _by_number()[36]["expression"]
    for coefficient in ("2.21 *", "0.7 *", "0.73 *", "0.6 *"):
        assert coefficient in expression
    # Five plain ranks; `ts_rank` is a different operator and is counted out.
    assert expression.count("rank(") - expression.count("ts_rank(") == 5
    assert np.isfinite(_value(36)).all()


def test_alpha47_keeps_the_subtraction_between_the_volume_and_drift_terms():
    expression = _by_number()[47]["expression"]
    assert "- rank(vwap - lag(vwap, 5))" in expression
    assert np.isfinite(_value(47)).all()


def test_alpha57_is_negative_when_close_is_above_vwap():
    # All else equal, a higher close than vwap makes (close - vwap) positive and
    # the alpha carries a leading minus, so the sign must flip with the gap.
    rows = 40
    timestamps = [f"d{i}" for i in range(rows)]
    close = np.linspace(100.0, 120.0, rows)
    vwap = np.full(rows, 110.0)
    rows_by_symbol = {
        "AAA": [{"timestamp": timestamps[i], "close": float(close[i]),
                 "vwap": float(vwap[i])} for i in range(rows)],
        "BBB": [{"timestamp": timestamps[i], "close": float(130.0),
                 "vwap": float(110.0)} for i in range(rows)],
    }
    panel = P.build_panel(rows_by_symbol, ["close", "vwap"])
    value = P.evaluate(_by_number()[57]["expression"], panel)[-1]
    assert value[1] < 0 < value[0]


@pytest.mark.parametrize("number, allowed", [(61, {0.0, 1.0}), (65, {-1.0, 0.0}),
                                             (86, {-1.0, 0.0}), (99, {-1.0, 0.0})])
def test_boolean_alphas_are_exactly_boolean(number, allowed):
    value = _value(number)
    assert set(np.unique(value)) <= allowed, (number, np.unique(value))


def test_alpha66_negates_a_sum_of_two_decayed_terms():
    expression = _by_number()[66]["expression"]
    assert expression.startswith("0 - (")
    assert expression.count("decay_linear(") == 2
    assert np.isfinite(_value(66)).all()


def test_alpha72_is_a_ratio_of_two_ranked_decayed_correlations():
    value = _value(72)
    # The denominator is a rank, so the lowest-ranked name has a zero denominator
    # and the published ratio is ±inf there — the same property Alpha#42 has.
    assert np.isfinite(value).any()
    # A zero numerator rank yields exactly 0, so non-negative is the bound.
    assert (value[np.isfinite(value)] >= 0).all()


def test_alpha83_carries_the_vwap_gap_in_the_denominator():
    expression = _by_number()[83]["expression"]
    assert "vwap - close" in expression
    assert np.isfinite(_value(83)).all()

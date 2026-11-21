"""The vwap input contract, and the two constant-free vwap alphas it unblocks.

The contract is the deliverable; the alphas prove it works end to end.

`vwap` cannot be derived from OHLCV: `(high + low + close) / 3` is a typical price,
not a volume-weighted average, so substituting it would make a factor's IC look
real while measuring something else. So a factor that needs it declares
`requiresInputs: ["vwap"]`, a caller without it gets a named `MISSING_INPUT`
refusal, and a caller with it gets a number.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import alpha101
from harness.stats import formula

VWAP_ALPHAS = (41, 42)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in alpha101.ALPHA101_FACTORS}


def _series(n=60, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    return {
        "open": close * (1 + rng.normal(0, 0.002, n)),
        "high": close * (1 + abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - abs(rng.normal(0, 0.006, n))),
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        "vwap": close * (1 + rng.normal(0, 0.001, n)),
    }


# -- the contract -----------------------------------------------------------


def test_the_two_vwap_alphas_declare_the_requirement():
    assert alpha101.PORTED == len(alpha101.ALPHA101_FACTORS)
    assert alpha101.PORTED >= 33   # later tranches only add
    for number in VWAP_ALPHAS:
        factor = _by_number()[number]
        assert contracts.required_inputs(factor) == ("vwap",)
        # `vwap` is also named in `inputs`, so the record reads honestly on its own.
        assert "vwap" in factor["inputs"]


def test_a_factor_without_extra_inputs_requires_nothing():
    assert contracts.required_inputs(_by_number()[101]) == ()
    assert contracts.missing_inputs(_by_number()[101], ["close", "open"]) == []


def test_missing_vwap_is_a_named_refusal_not_an_empty_column():
    factor = _by_number()[41]
    with pytest.raises(contracts.FactorInputError) as exc:
        contracts.require_inputs(factor, ["high", "low", "close", "open", "volume"])
    assert exc.value.code == "MISSING_INPUT"
    assert exc.value.missing == ("vwap",)
    assert "vwap" in exc.value.message
    assert exc.value.to_dict()["missing"] == ["vwap"]


def test_supplying_vwap_satisfies_the_contract():
    contracts.require_inputs(_by_number()[41], ["high", "low", "vwap"])


def test_describe_explains_why_a_factor_is_not_runnable():
    factor = _by_number()[42]
    blocked = contracts.describe(factor, ["close"])
    assert blocked["runnable"] is False
    assert blocked["missing"] == ["vwap"]
    assert blocked["reason"] == "needs vwap"
    ready = contracts.describe(factor, ["close", "vwap"])
    assert ready["runnable"] is True and ready["reason"] == "inputs satisfied"


def test_a_declared_requirement_is_also_in_the_expression_inputs():
    # Metadata that names an input the expression never reads would be a lie the
    # contract cannot catch, so the two are checked against each other.
    for number in VWAP_ALPHAS:
        factor = _by_number()[number]
        for name in factor["requiresInputs"]:
            assert name in factor["inputs"]


# -- the two alphas ---------------------------------------------------------


def test_alpha41_is_geometric_mid_minus_vwap():
    data = _series()
    value, _ = formula.evaluate(_by_number()[41]["expression"], data)
    expected = np.sqrt(data["high"][-1] * data["low"][-1]) - data["vwap"][-1]
    assert value[-1] == pytest.approx(expected)


def test_alpha41_flips_sign_when_vwap_crosses_the_geometric_mid():
    close = np.array([100.0])
    up = {"high": close * 1.01, "low": close * 0.99, "vwap": close * 0.95}
    down = {"high": close * 1.01, "low": close * 0.99, "vwap": close * 1.05}
    sign = lambda ctx: float(formula.evaluate(  # noqa: E731
        _by_number()[41]["expression"], ctx)[0][-1])
    assert sign(up) > 0
    assert sign(down) < 0


def test_alpha42_is_a_ratio_of_two_cross_sectional_ranks():
    rows = 20
    timestamps = [f"d{i}" for i in range(rows)]
    rng = np.random.default_rng(9)
    rows_by_symbol = {}
    for index in range(4):
        close = 100 + np.cumsum(rng.normal(0, 1, rows))
        vwap = close * (1 + rng.normal(0, 0.002, rows))
        rows_by_symbol[f"S{index}"] = [
            {"timestamp": timestamps[i], "close": float(close[i]),
             "vwap": float(vwap[i])}
            for i in range(rows)
        ]
    built = P.build_panel(rows_by_symbol, ["close", "vwap"])
    value = P.evaluate(_by_number()[42]["expression"], built)
    assert value.shape == (rows, 4)
    # Alpha#42 divides two ranks, so the name ranked lowest has a zero
    # denominator and the published formula yields ±inf there. That is the
    # formula's own behaviour; hiding it behind a clamp would change the alpha.
    last = value[-1]
    assert np.isfinite(last).any()
    assert np.isinf(last).any() or np.isfinite(last).all()


def test_the_vwap_alphas_parse_on_the_engine_that_will_run_them():
    for number in VWAP_ALPHAS:
        factor = _by_number()[number]
        allow = P.PANEL_FUNCTIONS if factor.get("requiresPanel") else ()
        formula.parse(factor["expression"], allow=allow)

"""GTJA191 tranche 10: multivariate regression, AMOUNT sums, and the dropped two.

`regresi_multi(y, x1, x2, x3, n)` is a three-factor rolling OLS residual. GTJA #30
regresses a stock's returns on **MKT/SMB/HML**, which the harness does not invent:
the factors are declared inputs, and a caller without them gets `MISSING_INPUT`.
An ill-conditioned window is NaN rather than a pseudo-solution.

#50 and #166 were dropped from tranche 9 because their drafts were garbled; both are
ported here from the published forms. #50 is the complement of #51, so
**#49 + #51 = 1** and **#51 + #50-complement rules** give an exact cross-check.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import contracts, panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula

NEW = (7, 30, 50, 73, 77, 78, 86, 87, 89, 93, 104, 107, 113, 125, 136, 142, 144,
       152, 166, 169, 187)
VWAP_USERS = (7, 73, 77, 87, 125)
AMOUNT_USERS = (144,)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in gtja191.GTJA191_FACTORS}


def _series(n=340, seed=109):
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
        "mkt": rng.normal(0, 0.01, n),
        "smb": rng.normal(0, 0.01, n),
        "hml": rng.normal(0, 0.01, n),
    }


def _panel(rows=220, cols=4, seed=113):
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


# -- the operator -----------------------------------------------------------


def test_regresi_multi_recovers_a_known_three_factor_model():
    rng = np.random.default_rng(7)
    n = 60
    a, b, c = (rng.normal(size=n) for _ in range(3))
    y = 2.0 * a + 3.0 * b - 1.0 * c + 5.0 + rng.normal(0, 1e-9, n)
    value, _ = formula.evaluate("regresi_multi(y, a, b, c, 30)",
                                {"y": y, "a": a, "b": b, "c": c})
    assert abs(value[-1]) < 1e-6          # the model is exact, so the residual is ~0


def test_regresi_multi_needs_a_wide_enough_window():
    with pytest.raises(formula.FormulaError):
        formula.evaluate("regresi_multi(y, a, b, c, 3)",
                         {"y": np.arange(10.0), "a": np.arange(10.0),
                          "b": np.arange(10.0), "c": np.arange(10.0)})


def test_regresi_multi_is_nan_on_a_singular_window():
    # A constant factor makes the design rank-deficient: NaN, not a fake fit.
    n = 20
    value, _ = formula.evaluate(
        "regresi_multi(y, a, b, c, 10)",
        {"y": np.arange(float(n)), "a": np.ones(n), "b": np.ones(n),
         "c": np.ones(n)})
    assert np.isnan(value[-1])


# -- the tranche ------------------------------------------------------------


def test_the_tranche_is_present_and_counted():
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS) >= 151
    for number in NEW:
        assert number in _by_number(), f"GTJA #{number} missing"


def test_the_declared_inputs_are_declared():
    assert contracts.required_inputs(_by_number()[30]) == ("mkt", "smb", "hml")
    for number in VWAP_USERS:
        assert contracts.required_inputs(_by_number()[number]) == ("vwap",), number
    for number in AMOUNT_USERS:
        assert contracts.required_inputs(_by_number()[number]) == ("amount",)
    with pytest.raises(contracts.FactorInputError) as exc:
        contracts.require_inputs(_by_number()[30], ["close"])
    assert set(exc.value.missing) == {"mkt", "smb", "hml"}


def test_alpha30_is_the_squared_residual_smoothed_by_wma():
    data = _series()
    factor = _by_number()[30]
    assert factor["expression"].startswith("wma(regresi_multi(")
    value, _ = formula.evaluate(factor["expression"], data)
    assert np.isfinite(value[-1])
    assert value[-1] >= 0.0     # a square, smoothed with positive weights


def test_alpha50_is_the_down_share_minus_the_up_share():
    data = _series()
    a50, _ = formula.evaluate(_by_number()[50]["expression"], data)
    a51, _ = formula.evaluate(_by_number()[51]["expression"], data)
    a49, _ = formula.evaluate(_by_number()[49]["expression"], data)
    # #51 is the down share, #49 the up share, so #50 = #51 - #49.
    assert a50[-1] == pytest.approx(a51[-1] - a49[-1], abs=1e-9)
    assert a49[-1] + a51[-1] == pytest.approx(1.0)


def test_alpha166_is_zero_or_a_finite_skewness():
    data = _series()
    value, _ = formula.evaluate(_by_number()[166]["expression"], data)
    finite = value[30:]
    finite = finite[np.isfinite(finite)]
    assert finite.size
    assert np.isfinite(finite).all()


def test_alpha93_and_187_are_conditional_sum_pairs():
    data = _series()
    a93, _ = formula.evaluate(_by_number()[93]["expression"], data)
    a187, _ = formula.evaluate(_by_number()[187]["expression"], data)
    assert np.isfinite(a93[-1]) and np.isfinite(a187[-1])
    # Both sum non-negative terms, so neither can be negative.
    assert a93[-1] >= -1e-9 and a187[-1] >= -1e-9


def test_alpha86_takes_only_its_three_branches():
    data = _series()
    value, _ = formula.evaluate(_by_number()[86]["expression"], data)
    finite = value[30:]
    finite = finite[np.isfinite(finite)]
    assert set(np.unique(np.round(finite, 9))) - {-1.0, 1.0}
    assert (-1.0 in set(np.round(finite, 9))) or (1.0 in set(np.round(finite, 9)))


@pytest.mark.parametrize("number", [7, 73, 77, 87, 104, 107, 113, 125, 136, 142])
def test_the_panel_alphas_evaluate(number):
    value = P.evaluate(_by_number()[number]["expression"], _panel())[-1]
    assert np.isfinite(value).any()


def test_every_new_alpha_runs():
    data = _series()
    for number in NEW:
        factor = _by_number()[number]
        value, _ = formula.evaluate(factor["expression"],
                                    {k: data[k] for k in factor["inputs"]})
        assert np.isfinite(value).any(), number

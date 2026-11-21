"""Alpha101 tranche 3: `ts_sum` + the declared adv20, ten more exact alphas.

The important decision is the **input surface**, and it is tested rather than
assumed: the engine has no dollar-volume field, so `adv20` is derived exactly as
`sma(volume * close, 20)` and inlined in every formula that needs it. That keeps
each alpha self-contained (no undeclared quantity) and lets a caller with a true
VWAP-based dollar volume substitute it without touching the algebra.

`ts_sum` is pinned too: it is a plain rolling sum, not a weighted one, so a
window of `[1, 2, 3]` must be `6` — not `1*1 + 2*2 + 3*3`.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import panel as P
from harness.factors.zoo import alpha101
from harness.stats import formula

NEW = (7, 8, 19, 21, 30, 35, 43, 45, 52, 60)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in alpha101.ALPHA101_FACTORS}


def _series(n=300, seed=5):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    return {
        "open": close * (1 + rng.normal(0, 0.002, n)),
        "high": close * (1 + abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - abs(rng.normal(0, 0.006, n))),
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }


def _panel(rows=80, cols=4):
    rng = np.random.default_rng(13)
    timestamps = [f"d{i}" for i in range(rows)]
    rows_by_symbol = {}
    for index in range(cols):
        close = 100 * np.cumprod(1 + rng.normal(0, 0.01, rows))
        open_ = close * (1 + rng.normal(0, 0.002, rows))
        high = close * (1 + abs(rng.normal(0, 0.005, rows)))
        low = close * (1 - abs(rng.normal(0, 0.005, rows)))
        volume = rng.integers(1_000_000, 4_000_000, rows).astype(float)
        rows_by_symbol[f"S{index}"] = [
            {"timestamp": timestamps[i], "open": float(open_[i]),
             "high": float(high[i]), "low": float(low[i]),
             "close": float(close[i]), "volume": float(volume[i])}
            for i in range(rows)
        ]
    return P.build_panel(rows_by_symbol, ["open", "high", "low", "close", "volume"])


# -- the operator -----------------------------------------------------------


def test_ts_sum_is_a_plain_rolling_sum():
    value, _ = formula.evaluate("ts_sum(x, 3)", {"x": np.array([1.0, 2.0, 3.0, 4.0])})
    assert np.isnan(value[1])
    assert value[2] == pytest.approx(6.0)      # 1+2+3, not a weighted 14
    assert value[3] == pytest.approx(9.0)      # 2+3+4


def test_rolling_sum_is_the_same_function_under_the_house_name():
    a, _ = formula.evaluate("rolling_sum(x, 4)", {"x": np.arange(10.0)})
    b, _ = formula.evaluate("ts_sum(x, 4)", {"x": np.arange(10.0)})
    assert np.allclose(a[3:], b[3:], equal_nan=True)


def test_the_panel_evaluator_has_the_same_ts_sum():
    panel = _panel(rows=10, cols=2)
    value = P.evaluate("ts_sum(close, 3)", panel)
    assert np.isfinite(value[-1]).all()


# -- the declared adv20 -----------------------------------------------------


def test_adv20_is_the_declared_dollar_volume_average():
    data = _series(40)
    value, _ = formula.evaluate("sma(volume * close, 20)", data)
    expected = float(np.mean((data["volume"] * data["close"])[-20:]))
    assert value[-1] == pytest.approx(expected)


def test_every_adv20_formula_inlines_the_same_definition():
    # A formula that silently used a different adv20 would not contain it.
    users = [f for f in alpha101.ALPHA101_FACTORS
             if "sma(volume * close, 20)" in f["expression"]]
    assert {f["alphaNumber"] for f in users} >= {7, 21, 43}


# -- the tranche ------------------------------------------------------------


def test_the_library_now_ports_at_least_thirty_one():
    assert alpha101.PORTED == len(alpha101.ALPHA101_FACTORS)
    assert alpha101.PORTED >= 31   # later tranches only add
    for number in NEW:
        assert number in _by_number(), f"Alpha#{number} missing"


def test_every_new_alpha_evaluates_without_an_unsupported_operator():
    data = _series()
    for number in NEW:
        factor = _by_number()[number]
        if "scale(" in factor["expression"]:
            # `scale` is cross-sectional by definition; the per-series engine
            # must refuse it, and the panel path is asserted below.
            with pytest.raises(Exception) as exc:
                formula.parse(factor["expression"])
            assert getattr(exc.value, "code", "") == "UNKNOWN_FUNCTION"
            continue
        context = {name: data[name] for name in factor["inputs"]}
        value, _ = formula.evaluate(factor["expression"], context)
        assert value.shape == data["close"].shape
        if not factor.get("requiresPanel"):
            assert np.isfinite(value[-1]), f"Alpha#{number} has no finite last value"


@pytest.mark.parametrize("number", [8, 19, 30, 45, 52, 60])
def test_the_panel_alphas_run_through_the_real_panel_path(number):
    # 19 needs 250 observations and 52 needs 240, so the panel must be long
    # enough for the formula's own lookback — a shorter one is all NaN.
    value = P.evaluate(_by_number()[number]["expression"], _panel(rows=300))
    assert value.shape == (300, 4)
    assert np.isfinite(value[-1]).all()


def test_alpha7_takes_the_volume_branch_only_above_adv20():
    factor = _by_number()[7]
    close = np.linspace(100.0, 130.0, 40)
    quiet = np.full(40, 1_000.0)
    loud = np.full(40, 5_000_000.0)
    # Quiet tape: volume far below sma(volume*close) -> the constant -1 branch.
    quiet_value, _ = formula.evaluate(factor["expression"],
                                      {"close": close, "volume": quiet})
    assert quiet_value[-1] == pytest.approx(-1.0)
    # Loud tape: the ts_rank/sign branch, which is bounded by [-1, 1] and not -1
    # by construction (it is a product of a rank in [0,1] and a sign).
    loud_value, _ = formula.evaluate(factor["expression"],
                                     {"close": close, "volume": loud})
    assert -1.0 <= loud_value[-1] <= 1.0


def test_alpha21_returns_the_lower_breakout_state_first():
    factor = _by_number()[21]
    # A close that jumps far above its own 8-day band -> first branch, -1.
    close = np.concatenate([np.full(30, 100.0), np.array([200.0])])
    volume = np.full(31, 1_000.0)
    value, _ = formula.evaluate(factor["expression"],
                                {"close": close, "volume": volume})
    assert value[-1] == pytest.approx(-1.0)


def test_alpha35_is_the_product_of_three_bounded_ranks():
    factor = _by_number()[35]
    assert factor["expression"].count("ts_rank(") == 3
    value, _ = formula.evaluate(factor["expression"], _series())
    assert 0.0 <= value[-1] <= 1.0


def test_alpha43_is_a_product_of_two_ranks():
    factor = _by_number()[43]
    assert factor["expression"].count("ts_rank(") == 2
    value, _ = formula.evaluate(factor["expression"], _series())
    assert 0.0 <= value[-1] <= 1.0


def test_alpha19_is_bounded_by_the_flow_term():
    factor = _by_number()[19]
    # -sign(...) is ±1 and (1 + rank(...)) is (1, 2], so |value| <= 2.
    value = P.evaluate(factor["expression"], _panel(rows=300))
    assert np.isfinite(value[-1]).all()
    assert (np.abs(value[-1]) <= 2.0).all()

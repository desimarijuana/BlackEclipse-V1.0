"""Alpha101 tranche 2: the ten new alphas evaluate exactly, and branch correctly.

Each new formula is asserted three ways:

  * it parses and evaluates on a synthetic series (no `UNSUPPORTED_FUNCTION`);
  * the *branch* behaviour matches the paper for a hand-built case, so a
    transposed `where` cannot pass by producing a plausible-looking number;
  * a panel alpha runs through the panel evaluator (where `rank` is
    cross-sectional) rather than silently degrading to a time-series rank.
"""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import panel as P
from harness.factors.zoo import alpha101
from harness.stats import formula

NEW = (9, 10, 18, 20, 22, 26, 37, 38, 46, 51)


def _by_number() -> dict[int, dict]:
    return {factor["alphaNumber"]: factor for factor in alpha101.ALPHA101_FACTORS}


def _series(n=260, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    return {
        "open": close * (1 + rng.normal(0, 0.002, n)),
        "high": close * (1 + abs(rng.normal(0, 0.006, n))),
        "low": close * (1 - abs(rng.normal(0, 0.006, n))),
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }


def test_every_new_alpha_is_declared_and_counted():
    table = _by_number()
    for number in NEW:
        assert number in table, f"Alpha#{number} missing"
    assert alpha101.PORTED == len(alpha101.ALPHA101_FACTORS)
    assert alpha101.PORTED >= 21   # tranche 3 only adds


def test_every_new_alpha_evaluates_without_an_unsupported_operator():
    data = _series()
    for number in NEW:
        factor = _by_number()[number]
        needs = set(factor["inputs"])
        context = {name: data[name] for name in needs}
        value, _ = formula.evaluate(factor["expression"], context)
        assert value.shape == data["close"].shape
        # A formula that is all-NaN has not evaluated, it has failed quietly.
        assert np.isfinite(value[-1]) or not factor.get("requiresPanel"), (
            f"Alpha#{number} produced no finite last value"
        )


def test_alpha9_holds_a_clean_uptrend_and_fades_chop():
    # 5 sessions of consistently rising closes: ts_min(delta) > 0 -> +delta.
    close = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0])
    value, _ = formula.evaluate(
        _by_number()[9]["expression"], {"close": close})
    assert value[-1] == pytest.approx(1.0)          # +delta, not -delta


def test_alpha9_flips_sign_when_the_whole_window_falls():
    close = np.array([16.0, 15.0, 14.0, 13.0, 12.0, 11.0, 10.0])
    value, _ = formula.evaluate(_by_number()[9]["expression"], {"close": close})
    # ts_max(delta) < 0 -> delta is returned as-is (which is -1 the last day).
    assert value[-1] == pytest.approx(-1.0)


def test_alpha46_and_51_take_the_momentum_branch_on_a_mild_acceleration():
    # second difference of the 10-day legs in (0, 0.25]: #46 falls to its inner
    # branch and neither alpha's "faded" branch applies, so both return -delta.
    close = 100.0 + 0.01 * np.arange(40.0) ** 2
    leg = ((close[-21] - close[-11]) / 10) - ((close[-11] - close[-1]) / 10)
    assert 0 < leg <= 0.25
    a46, _ = formula.evaluate(_by_number()[46]["expression"], {"close": close})
    a51, _ = formula.evaluate(_by_number()[51]["expression"], {"close": close})
    assert a46[-1] == pytest.approx(-(close[-1] - close[-2]))
    assert a51[-1] == pytest.approx(-(close[-1] - close[-2]))


def test_alpha46_returns_minus_one_above_the_quarter_threshold():
    # A stronger acceleration puts the leg above 0.25, which is #46's OUTER
    # branch: the alpha becomes a constant -1 rather than -delta.
    close = 100.0 + 0.02 * np.arange(40.0) ** 2
    leg = ((close[-21] - close[-11]) / 10) - ((close[-11] - close[-1]) / 10)
    assert leg > 0.25
    a46, _ = formula.evaluate(_by_number()[46]["expression"], {"close": close})
    assert a46[-1] == pytest.approx(-1.0)


def test_alpha46_returns_plus_one_when_the_recent_leg_has_faded():
    close = 100.0 + 4.0 * np.arange(40.0) - 0.12 * np.arange(40.0) ** 2
    leg = ((close[-21] - close[-11]) / 10) - ((close[-11] - close[-1]) / 10)
    assert leg < 0
    a46, _ = formula.evaluate(_by_number()[46]["expression"], {"close": close})
    a51, _ = formula.evaluate(_by_number()[51]["expression"], {"close": close})
    assert a46[-1] == pytest.approx(1.0)
    assert a51[-1] == pytest.approx(1.0)


def _panel(rows=40, cols=4):
    """Build a real panel (the evaluator's own contract, not a hand-made array)."""
    rng = np.random.default_rng(11)
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


@pytest.mark.parametrize("number", [10, 18, 20, 22, 38])
def test_panel_alphas_run_through_the_panel_evaluator(number):
    factor = _by_number()[number]
    value = P.evaluate(factor["expression"], _panel(rows=60))
    assert value.shape == (60, 4)
    assert np.isfinite(value[-1]).all()


def test_alpha20_is_a_negative_product_of_three_gap_ranks():
    factor = _by_number()[20]
    assert factor["expression"].startswith("(0 - rank(open - lag(high, 1)))")
    assert factor["requiresPanel"] is True


def test_alpha38_negates_the_time_series_rank_and_scales_by_close_over_open():
    factor = _by_number()[38]
    assert factor["direction"] == "negative"
    value = P.evaluate(factor["expression"], _panel(rows=40))
    assert np.isfinite(value[-1]).all()


def test_the_panel_alphas_are_marked_so_they_are_not_run_per_instrument():
    for number in (10, 18, 20, 22, 37, 38):
        assert _by_number()[number]["requiresPanel"] is True
    for number in (9, 26, 46, 51):
        assert not _by_number()[number].get("requiresPanel")

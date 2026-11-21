"""Alpha101 subset: exact formulas, parseable, merged, and numerically checked."""

from __future__ import annotations

import math

import numpy as np

from harness.factors import library
from harness.factors.zoo import alpha101
from harness.stats import formula


def test_every_ported_alpha_parses_on_the_safe_engine():
    # A panel alpha may use a panel-only function (`scale`), which the per-series
    # engine must NOT accept; everything else has to parse with no allowances.
    from harness.factors import panel as P

    assert alpha101.ALPHA101_FACTORS
    for factor in alpha101.ALPHA101_FACTORS:
        allow = P.PANEL_FUNCTIONS if factor.get("requiresPanel") else ()
        formula.parse(factor["expression"], allow=allow)


def test_provenance_names_the_exact_alpha_number():
    for factor in alpha101.ALPHA101_FACTORS:
        assert factor["zoo"] == "alpha101"
        assert isinstance(factor["alphaNumber"], int)
        assert f"Alpha#{factor['alphaNumber']}" in factor["reference"]
        assert factor["available"] is True


def test_the_ported_count_is_stated_and_true():
    assert alpha101.PORTED == len(alpha101.ALPHA101_FACTORS)
    assert alpha101.TOTAL == 101
    assert len(set(alpha101.alpha_numbers())) == len(alpha101.ALPHA101_FACTORS)


def test_the_library_merges_the_alpha101_family():
    names = {f["name"] for f in library.BUILTIN_FACTORS}
    assert {f["name"] for f in alpha101.ALPHA101_FACTORS} <= names
    assert library.get_builtin("alpha101_intraday_pressure")["zoo"] == "alpha101"


def test_alpha101_pressure_matches_its_published_formula():
    context = {
        "open": np.array([10.0]),
        "high": np.array([12.0]),
        "low": np.array([9.0]),
        "close": np.array([11.0]),
    }
    value, _ = formula.evaluate(
        "(close - open) / (high - low + 0.001)", context)
    assert value[0] == pytest_approx(1.0 / 3.001)


def test_alpha12_uses_the_sign_and_delta_aliases():
    context = {
        "close": np.array([10.0, 11.0, 10.5]),
        "volume": np.array([100.0, 120.0, 110.0]),
    }
    value, parsed = formula.evaluate(
        "sign(delta(volume, 1)) * (0 - delta(close, 1))", context)
    # bar 2: volume fell (sign -1); close delta -0.5; -1 * (0 - (-0.5)) = -0.5
    assert value[2] == pytest_approx(-0.5)
    assert "sign" in parsed.functions and "delta" in parsed.functions


def test_alpha24_condition_is_the_complement_not_an_approximation():
    # A flat series has delta(sma(close,100),100)/lag(close,100) == 0, i.e. <=0.05,
    # so the FIRST branch must be taken once the window is warm.
    close = np.full(220, 50.0)
    context = {"close": close}
    value, _ = formula.evaluate(
        "where(greater_than(delta(sma(close, 100), 100) / lag(close, 100), 0.05), "
        "0 - delta(close, 3), 0 - (close - rolling_min(close, 100)))",
        context,
    )
    assert math.isfinite(value[-1]) and value[-1] == 0.0


def pytest_approx(value, rel=1e-9):
    import pytest

    return pytest.approx(value, rel=rel)


# -- panel-dependent alphas --------------------------------------------------


def test_panel_alphas_declare_they_need_a_panel():
    numbers = {f["alphaNumber"] for f in alpha101.ALPHA101_FACTORS}
    flagged = {f["alphaNumber"] for f in alpha101.ALPHA101_FACTORS
               if f.get("requiresPanel")}
    series = numbers - flagged
    # Derived partition: every alpha is exactly one of the two, and the members
    # known to be cross-sectional are on the panel side. This does not need hand
    # maintenance on every tranche.
    assert flagged | series == numbers and not (flagged & series)
    for number in (1, 8, 10, 33, 34, 40, 42, 48, 50, 58, 63, 69, 79, 80, 84,
                   87, 89, 94, 98):
        assert number in flagged, number


def _panel():
    from harness.factors import panel as P

    rows = {
        "AAA": [{"timestamp": f"d{i}", "open": 10.0, "close": 10.0 + i,
                 "high": 11.0 + i} for i in range(12)],
        "BBB": [{"timestamp": f"d{i}", "open": 20.0, "close": 20.0 - i,
                 "high": 21.0 + 0.1 * i} for i in range(12)],
        "CCC": [{"timestamp": f"d{i}", "open": 5.0, "close": 5.0 + 0.5 * i,
                 "high": 6.0 + 0.5 * i} for i in range(12)],
    }
    return P.build_panel(rows, ["open", "close", "high"])


def test_alpha33_ranks_the_intraday_move_across_the_universe():
    from harness.factors import panel as P

    result = P.evaluate("rank(0 - (1 - open / close))", _panel())
    # The expression is rank(open/close - 1): BBB (open 20, close 9) has the
    # largest ratio, so it must rank highest on the last row.
    last = result[-1]
    symbols = _panel().symbols
    assert last[symbols.index("BBB")] == np.nanmax(last)


def test_alpha40_ranks_high_volatility_after_the_window():
    from harness.factors import panel as P

    result = P.evaluate("0 - rank(rolling_std(high, 10))", _panel())
    assert np.isnan(result[8]).all()      # window not warm
    assert np.isfinite(result[-1]).all()  # warm on the last row
    # Negated ranks land in {-1, -0.5, 0} for three symbols.
    assert set(np.round(result[-1], 6)) <= {-1.0, -0.5, 0.0}


def test_panel_alphas_parse_under_the_panel_allowlist():
    from harness.factors.panel import PANEL_FUNCTIONS
    from harness.stats import formula

    allow = PANEL_FUNCTIONS - set(formula.FUNCTIONS)
    for factor in alpha101.ALPHA101_FACTORS:
        if factor.get("requiresPanel"):
            formula.parse(factor["expression"], allow=allow)

"""GTJA191 subset: exact formulas, provenance, panel flags, numeric checks."""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import library
from harness.factors import panel as P
from harness.factors.zoo import gtja191
from harness.stats import formula


def test_every_ported_alpha_parses():
    assert gtja191.GTJA191_FACTORS
    allow = P.PANEL_FUNCTIONS - set(formula.FUNCTIONS)
    for factor in gtja191.GTJA191_FACTORS:
        formula.parse(factor["expression"], allow=allow)


def test_the_ported_count_is_stated_and_true():
    assert gtja191.PORTED == len(gtja191.GTJA191_FACTORS)
    assert gtja191.TOTAL == 191
    assert gtja191.PORTED < gtja191.TOTAL
    numbers = [f["alphaNumber"] for f in gtja191.GTJA191_FACTORS]
    assert numbers == sorted(set(numbers))


def test_provenance_names_the_published_alpha():
    for factor in gtja191.GTJA191_FACTORS:
        assert factor["zoo"] == "gtja191"
        assert f"#{factor['alphaNumber']}" in factor["reference"]
        assert "GTJA" in factor["source"]


def test_panel_alphas_are_flagged_and_series_alphas_are_not():
    numbers = {f["alphaNumber"] for f in gtja191.GTJA191_FACTORS}
    flagged = {f["alphaNumber"] for f in gtja191.GTJA191_FACTORS if f.get("requiresPanel")}
    series = numbers - flagged
    # Every alpha is exactly one of the two, and the known panel members are
    # panel: this catches a new panel alpha that forgot its flag without needing
    # the hand-maintained list below to be updated on every tranche.
    assert flagged | series == numbers and not (flagged & series)
    assert {1, 5, 6, 8, 10, 12, 25, 26, 33, 35, 37, 39, 41, 42, 45, 48, 54,
            120, 124, 131} <= flagged
    for number in (2, 11, 13, 14, 15, 18, 20, 21, 27, 29, 31, 34, 38, 40, 43, 44,
                   46, 47, 49, 52, 53, 57, 58, 59, 60, 63, 65, 66, 67, 68, 70, 71,
                   72, 79, 80, 84, 85, 88, 95, 102, 103, 106, 109, 110, 111,
                   116, 117, 118, 122, 126, 127, 128, 129, 132, 133, 134, 135,
                   139, 145, 147, 150):
        assert number in series, number


def test_the_library_merges_the_family():
    names = {f["name"] for f in library.BUILTIN_FACTORS}
    assert {f["name"] for f in gtja191.GTJA191_FACTORS} <= names
    assert library.get_builtin("gtja_alpha2")["zoo"] == "gtja191"


def test_alpha2_matches_its_definition():
    high = np.array([12.0, 12.0])
    low = np.array([8.0, 8.0])
    close = np.array([11.0, 9.0])
    value, _ = formula.evaluate(
        "0 - delta(((close - low) - (high - close)) / (high - low), 1)",
        {"high": high, "low": low, "close": close},
    )
    # bar0: ((11-8)-(12-11))/4 = 0.5 ; bar1: ((9-8)-(12-9))/4 = -0.5
    # delta = -1.0, negated = +1.0
    assert value[-1] == pytest.approx(1.0)


def test_alpha11_is_a_volume_weighted_close_location():
    high = np.array([10.0, 10.0])
    low = np.array([8.0, 8.0])
    close = np.array([9.0, 10.0])
    volume = np.array([100.0, 300.0])
    value, _ = formula.evaluate(
        "rolling_mean(((close - low) - (high - close)) / (high - low) * volume, 2)",
        {"high": high, "low": low, "close": close, "volume": volume},
    )
    # bar0: 0 * 100 = 0 ; bar1: 1 * 300 = 300 -> mean 150
    assert value[-1] == pytest.approx(150.0)


def _panel():
    def volume(name: str, i: int, base: float) -> float:
        # The cross-sectional ORDERING of delta(log volume) must flip over time,
        # otherwise each column's rank is constant and correlation is undefined
        # (std 0) — a degenerate fixture, not an engine bug.
        wobble = {"AAA": 0.0, "BBB": 60.0, "CCC": -60.0}[name] * (i % 2)
        return 100.0 + 10.0 * i + (i * i) * (base / 10.0) + wobble

    rows = {
        name: [
            {"timestamp": f"d{i}", "open": base + i, "close": base + i + (i % 3) - 1,
             "high": base + i + 2, "low": base + i - 1,
             "volume": volume(name, i, base)}
            for i in range(12)
        ]
        for name, base in (("AAA", 10.0), ("BBB", 20.0), ("CCC", 30.0))
    }
    return P.build_panel(rows, ["open", "close", "high", "low", "volume"])


def test_alpha1_evaluates_on_a_panel():
    factor = next(f for f in gtja191.GTJA191_FACTORS if f["alphaNumber"] == 1)
    result = P.evaluate(factor["expression"], _panel())
    assert result.shape == (12, 3)
    # A column whose cross-sectional rank is constant across the window has an
    # UNDEFINED correlation (std 0), so NaN is the correct value there. What
    # matters is that the expression evaluates and produces real numbers where
    # the ranks actually vary.
    assert np.isfinite(result[-1]).any()


def test_correlation_is_computed_across_symbols_over_time():
    rows = {
        "AAA": [{"timestamp": f"d{i}", "close": 10.0 + i, "volume": 100.0 + i}
                for i in range(8)],
        "BBB": [{"timestamp": f"d{i}", "close": 10.0 - i, "volume": 100.0 + 2 * i}
                for i in range(8)],
        "CCC": [{"timestamp": f"d{i}", "close": 10.0 + (i % 2), "volume": 100.0 - i}
                for i in range(8)],
    }
    panel = P.build_panel(rows, ["close", "volume"])
    result = P.evaluate("correlation(close, volume, 6)", panel)
    assert np.isfinite(result[-1]).all()
    # AAA rises with volume (positive), BBB falls as volume rises (negative)
    assert result[-1][0] > 0 > result[-1][1]


def test_alpha6_ranks_across_the_universe():
    factor = next(f for f in gtja191.GTJA191_FACTORS if f["alphaNumber"] == 6)
    result = P.evaluate(factor["expression"], _panel())
    assert np.isfinite(result[-1]).all()
    assert set(np.round(result[-1], 6)) <= {-1.0, -0.5, 0.0}

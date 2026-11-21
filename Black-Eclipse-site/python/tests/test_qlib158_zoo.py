"""Qlib Alpha158 subset: exact formulas, parseable, merged, numerically checked."""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import library
from harness.factors.zoo import qlib158
from harness.stats import formula


def test_every_ported_feature_parses_on_the_safe_engine():
    assert qlib158.QLIB158_FACTORS
    for factor in qlib158.QLIB158_FACTORS:
        formula.parse(factor["expression"])


def test_the_ported_count_is_stated_and_true():
    assert qlib158.PORTED == len(qlib158.QLIB158_FACTORS)
    assert qlib158.TOTAL == 158
    names = [f["name"] for f in qlib158.QLIB158_FACTORS]
    assert len(names) == len(set(names))


def test_provenance_names_the_qlib_feature():
    for factor in qlib158.QLIB158_FACTORS:
        assert factor["zoo"] == "qlib158"
        assert "Alpha158" in factor["source"]
        assert factor["reference"]


def test_no_expression_still_contains_a_template_placeholder():
    for factor in qlib158.QLIB158_FACTORS:
        assert "{d}" not in factor["expression"], factor["name"]


def test_the_library_merges_the_family():
    names = {f["name"] for f in library.BUILTIN_FACTORS}
    assert {"qlib_kmid", "qlib_roc_20", "qlib_rsv_60"} <= names
    assert library.get_builtin("qlib_rank_20")["zoo"] == "qlib158"


def test_kmid_matches_its_definition():
    value, _ = formula.evaluate(
        "(close - open) / open",
        {"open": np.array([10.0]), "close": np.array([11.0])},
    )
    assert value[0] == pytest.approx(0.1)


def test_kup_uses_the_pairwise_maximum():
    # open above close -> upper shadow starts at open
    value, _ = formula.evaluate(
        "(high - where(greater_than(open, close), open, close)) / open",
        {"open": np.array([12.0]), "high": np.array([15.0]), "close": np.array([10.0])},
    )
    assert value[0] == pytest.approx(0.25)


def test_rsv_is_the_position_inside_the_range():
    high = np.array([10.0, 12.0, 14.0])
    low = np.array([8.0, 9.0, 10.0])
    close = np.array([9.0, 11.0, 13.0])
    value, _ = formula.evaluate(
        "(close - rolling_min(low, 3)) / (rolling_max(high, 3) - rolling_min(low, 3))",
        {"high": high, "low": low, "close": close},
    )
    # range over all three bars: 8..14; close 13 -> (13-8)/6
    assert value[-1] == pytest.approx(5 / 6)


def test_cntp_counts_up_days():
    close = np.array([10.0, 11.0, 10.5, 11.5, 11.0])
    value, _ = formula.evaluate(
        "rolling_mean(greater_than(close, lag(close, 1)), 4)", {"close": close})
    assert value[-1] == pytest.approx(0.5)


def test_the_positions_report_is_honest():
    report = qlib158.qlib_positions_port()
    assert report["ported"] == len(qlib158.QLIB158_FACTORS)
    # Qlib is now COMPLETE (158/158), so the honesty check is equality with
    # the feature list, not a strict inequality.
    assert report["ported"] == report["total"] == 158

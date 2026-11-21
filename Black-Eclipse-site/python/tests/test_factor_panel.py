"""Panel evaluation: cross-sectional rank/scale, causality, explicit support."""

from __future__ import annotations

import numpy as np
import pytest

from harness.factors import panel as P


def _rows(prices, start=0):
    return [
        {"timestamp": f"2024-01-{start + i + 1:02d}", "close": price, "high": price * 1.1}
        for i, price in enumerate(prices)
    ]


def _panel():
    return P.build_panel(
        {
            "AAA": _rows([10.0, 11.0, 12.0]),
            "BBB": _rows([20.0, 20.0, 10.0]),
            "CCC": _rows([30.0, 25.0, 15.0]),
        },
        ["close", "high"],
    )


def test_build_panel_aligns_common_timestamps():
    panel = _panel()
    assert panel.symbols == ("AAA", "BBB", "CCC")
    assert len(panel.timestamps) == 3
    assert panel.fields["close"].shape == (3, 3)
    assert panel.fields["close"][0].tolist() == [10.0, 20.0, 30.0]


def test_build_panel_refuses_symbols_with_no_shared_dates():
    with pytest.raises(P.PanelError) as exc:
        P.build_panel({"A": _rows([1.0]), "B": _rows([1.0], start=5)}, ["close"])
    assert exc.value.code == "NO_COMMON_DATES"


def test_rank_is_cross_sectional_per_date():
    panel = _panel()
    ranked = P.cross_sectional_rank(panel.fields["close"])
    # day 1: 10 < 20 < 30 -> 0, 0.5, 1
    assert ranked[0].tolist() == [0.0, 0.5, 1.0]
    # day 3: 12 > 10 and 12 < 15 -> 0.5 for AAA
    assert ranked[2].tolist() == [0.5, 0.0, 1.0]


def test_rank_averages_ties():
    values = np.array([[5.0, 5.0, 9.0]])
    ranked = P.cross_sectional_rank(values)
    assert ranked[0].tolist() == [0.25, 0.25, 1.0]


def test_rank_keeps_nan_out_of_the_ordering():
    values = np.array([[1.0, np.nan, 3.0]])
    ranked = P.cross_sectional_rank(values)
    assert ranked[0, 0] == 0.0 and ranked[0, 2] == 1.0
    assert np.isnan(ranked[0, 1])


def test_scale_normalizes_each_row_by_absolute_sum():
    scaled = P.cross_sectional_scale(np.array([[1.0, -1.0, 2.0]]), 4.0)
    assert np.allclose(scaled, np.array([[1.0, -1.0, 2.0]]))
    assert np.isclose(np.abs(scaled).sum(), 4.0)


def test_rolling_mean_is_per_column():
    panel = _panel()
    result = P.evaluate("rolling_mean(close, 2)", panel)
    assert np.isnan(result[0]).all()
    assert result[1].tolist() == pytest.approx([10.5, 20.0, 27.5])
    assert result[2].tolist() == pytest.approx([11.5, 15.0, 20.0])


def test_rank_of_delta_composes_across_axes():
    panel = _panel()
    result = P.evaluate("rank(delta(close, 1))", panel)
    assert np.isnan(result[0]).all()
    # day 2 deltas: +1, 0, -5 -> ranks 1, 0.5, 0
    assert result[1].tolist() == pytest.approx([1.0, 0.5, 0.0])


def test_scale_and_rank_do_not_look_ahead():
    panel = _panel()
    expression = "rank(close) * scale(close)"
    before = P.evaluate(expression, panel)
    mutated = dict(panel.fields)
    mutated["close"] = panel.fields["close"].copy()
    mutated["close"][2] = [999.0, 1.0, 1.0]
    after = P.evaluate(expression, P.Panel(panel.symbols, panel.timestamps, mutated))
    # rows 0 and 1 are untouched by a change on row 2
    assert np.allclose(before[:2], after[:2], equal_nan=True)


def test_unsupported_function_is_a_named_refusal():
    panel = _panel()
    with pytest.raises(P.PanelError) as exc:
        P.evaluate("atr(high, 14)", panel)
    assert exc.value.code == "UNSUPPORTED_FUNCTION"


def test_to_series_splits_the_panel_back():
    panel = _panel()
    result = P.evaluate("rolling_mean(close, 2)", panel)
    series = P.to_series(result, panel)
    assert set(series) == set(panel.symbols)
    assert series["AAA"][0] is None
    assert series["AAA"][1] == pytest.approx(10.5)

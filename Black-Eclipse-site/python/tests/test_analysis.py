"""Deterministic bar statistics for a bracket (no model arithmetic)."""

from __future__ import annotations

from harness.trade.analysis import atr, bar_summary, true_ranges


def _bar(high, low, close):
    return {"high": high, "low": low, "close": close, "open": low}


def test_true_range_uses_previous_close_for_gaps():
    bars = [
        _bar(10, 9, 9.5),
        _bar(12, 11, 11.5),   # gap up: TR = high - previous close = 12 - 9.5
    ]
    assert true_ranges(bars) == [1.0, 2.5]


def test_atr_is_the_mean_of_the_last_period():
    bars = [_bar(2, 0, 1), _bar(4, 0, 2), _bar(6, 0, 3)]
    assert atr(bars, 3) == 4.0


def test_atr_needs_a_full_window():
    assert atr([_bar(2, 0, 1)], 14) is None
    assert atr([], 14) is None
    assert atr([_bar(2, 0, 1)], 0) is None


def test_summary_reports_last_bar_and_lookback_range():
    bars = [_bar(10, 8, 9), _bar(12, 9, 11), _bar(11, 10, 10.5)]
    summary = bar_summary(bars, period=2, lookback=2)
    assert summary["lastClose"] == 10.5
    assert summary["lookbackHigh"] == 12
    assert summary["lookbackLow"] == 9
    assert summary["atrPeriod"] == 2
    assert summary["atr"] == 2.0
    assert summary["changePct"] is not None

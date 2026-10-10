"""Deterministic time-series transform tests — resampling and alignment."""

from __future__ import annotations

import pytest

from harness.quant.transform import TransformError, align_rows, interval_seconds, resample_rows


def _minute_bars() -> list[dict]:
    rows = []
    for i in range(12):
        minute = 5 * i
        rows.append({
            "timestamp": f"2026-01-02T09:{minute:02d}:00Z",
            "open": 100 + i, "high": 105 + i, "low": 95 + i,
            "close": 101 + i, "volume": 10 + i,
        })
    return rows


def test_interval_seconds_validation():
    assert interval_seconds("1h") == 3600
    with pytest.raises(TransformError):
        interval_seconds("7m")


def test_resample_5m_to_30m_aggregation():
    rows = [
        {"timestamp": "2026-01-02T09:00:00Z", "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 10},
        {"timestamp": "2026-01-02T09:05:00Z", "open": 100.5, "high": 102, "low": 100, "close": 101.5, "volume": 20},
        {"timestamp": "2026-01-02T09:10:00Z", "open": 101.5, "high": 103, "low": 98, "close": 102, "volume": 30},
    ]
    out = resample_rows(rows, "30m", source_interval="5m")
    assert out["metadata"]["outputBars"] == 1
    bar = out["rows"][0]
    assert bar["open"] == 100          # first
    assert bar["high"] == 103          # max
    assert bar["low"] == 98            # min
    assert bar["close"] == 102         # last
    assert bar["volume"] == 60         # sum
    assert bar["bars"] == 3


def test_resample_partial_bucket_is_flagged():
    rows = _minute_bars()[:2]  # only 2 of 5 five-minute bars in the hour
    out = resample_rows(rows, "1h", source_interval="5m")
    assert out["rows"][0]["partial"] is True
    assert out["metadata"]["partialBuckets"] == 1
    full = resample_rows(_minute_bars(), "1h", source_interval="5m")
    assert full["rows"][0]["partial"] is False


def test_resample_refuses_to_manufacture_intraday():
    daily = [{"timestamp": "2026-01-02T00:00:00Z", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
    with pytest.raises(TransformError):
        resample_rows(daily, "1h", source_interval="1d")


def test_resample_daily_to_weekly_bucketing():
    rows = [
        {"timestamp": "2026-01-05T00:00:00Z", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1},
        {"timestamp": "2026-01-06T00:00:00Z", "open": 11, "high": 15, "low": 10, "close": 14, "volume": 2},
        {"timestamp": "2026-01-12T00:00:00Z", "open": 14, "high": 16, "low": 13, "close": 15, "volume": 3},
    ]
    out = resample_rows(rows, "1w", source_interval="1d")
    assert out["metadata"]["outputBars"] == 2  # two ISO weeks
    first = out["rows"][0]
    assert first["open"] == 10 and first["close"] == 14 and first["high"] == 15


def test_align_inner_join_and_missing_counts():
    a = [{"timestamp": "2026-01-02T00:00:00Z", "close": 1},
         {"timestamp": "2026-01-03T00:00:00Z", "close": 2}]
    b = [{"timestamp": "2026-01-03T00:00:00Z", "close": 20},
         {"timestamp": "2026-01-04T00:00:00Z", "close": 30}]
    inner = align_rows({"A": a, "B": b}, join="inner")
    assert inner["timestamps"] == ["2026-01-03T00:00:00Z"]
    assert inner["series"]["A"] == [2.0]
    assert inner["series"]["B"] == [20.0]

    outer = align_rows({"A": a, "B": b}, join="outer")
    assert len(outer["timestamps"]) == 3
    assert outer["missing"]["A"] == 1  # 2026-01-04 missing for A
    assert outer["missing"]["B"] == 1  # 2026-01-02 missing for B


def test_align_fill_is_explicit_only():
    a = [{"timestamp": "2026-01-02T00:00:00Z", "close": 1},
         {"timestamp": "2026-01-04T00:00:00Z", "close": 3}]
    b = [{"timestamp": "2026-01-02T00:00:00Z", "close": 10},
         {"timestamp": "2026-01-03T00:00:00Z", "close": 20},
         {"timestamp": "2026-01-04T00:00:00Z", "close": 30}]
    default = align_rows({"A": a, "B": b}, join="outer")
    assert default["imputed"] is False
    assert None in default["series"]["A"]

    ffill = align_rows({"A": a, "B": b}, join="outer", fill="ffill")
    assert ffill["imputed"] is True
    assert ffill["series"]["A"] == [1.0, 1.0, 3.0]

    scalar = align_rows({"A": a, "B": b}, join="outer", fill=0.0)
    assert scalar["series"]["A"] == [1.0, 0.0, 3.0]


def test_align_rejects_bad_join():
    with pytest.raises(TransformError):
        align_rows({"A": []}, join="cross")

"""Attention velocity: robust, gated, and honest about short history."""

from __future__ import annotations

from datetime import date, timedelta

from harness.intel import attention

LAST = date(2026, 11, 17)


def _baseline(days: int, value: int, *, end: date = date(2026, 11, 10)) -> list[tuple[str, int]]:
    """`days` daily points ending on `end`, oldest first."""
    return [((end - timedelta(days=days - 1 - i)).isoformat(), value) for i in range(days)]


def _short(values: list[int], *, end: date = LAST) -> list[tuple[str, int]]:
    return [((end - timedelta(days=len(values) - 1 - i)).isoformat(), v) for i, v in enumerate(values)]


def test_article_candidates_try_the_exact_name_then_strip_the_suffix():
    candidates = attention.article_candidates("APPLE INC")
    assert candidates[0] == "APPLE INC"
    assert "Apple Inc" in candidates
    assert "Apple" in candidates
    assert len(candidates) == len(set(candidates))
    assert "" not in candidates


def test_article_candidates_handles_a_plain_name():
    assert attention.article_candidates("Nvidia") == ["Nvidia"]


def test_parse_pageviews_sorts_and_formats_days():
    payload = {"items": [
        {"timestamp": "2026111600", "views": 12},
        {"timestamp": "2026111500", "views": 10},
        {"timestamp": "bad", "views": 9},
        {"timestamp": "2026111700", "views": "nope"},
    ]}
    assert attention.parse_pageviews(payload) == [("2026-11-15", 10), ("2026-11-16", 12)]


def test_attention_spike_scores_far_from_baseline():
    series = _baseline(90, 100) + _short([400, 420, 410, 405, 415])
    reading = attention.robust_velocity(series, as_of=LAST.isoformat())
    assert reading is not None
    assert reading.zscore > 10
    assert reading.ratio > 3.9
    assert reading.short_days == 5


def test_attention_on_a_noisy_page_stays_near_zero():
    series = []
    for i in range(97):
        day = (LAST - timedelta(days=96 - i)).isoformat()
        series.append((day, 1000 + (i % 7) * 20))
    reading = attention.robust_velocity(series, as_of=LAST.isoformat())
    assert reading is not None
    assert abs(reading.zscore) < 1.0


def test_short_history_is_none_rather_than_a_fabricated_zero():
    series = _baseline(10, 100, end=LAST)
    assert attention.robust_velocity(series, as_of=LAST.isoformat()) is None


def test_a_missing_short_window_is_none():
    series = _baseline(90, 100, end=date(2026, 9, 1))
    assert attention.robust_velocity(series, as_of=LAST.isoformat()) is None


def test_flat_short_window_reports_no_change():
    series = _baseline(90, 500) + _short([500, 500, 500, 500, 500])
    reading = attention.robust_velocity(series, as_of=LAST.isoformat())
    assert reading is not None
    assert abs(reading.zscore) < 1.0
    assert abs(reading.ratio - 1.0) < 0.01


def test_fetch_reading_falls_through_to_the_next_candidate(monkeypatch):
    calls: list[str] = []

    def fake_fetch(url: str) -> str:
        calls.append(url)
        if "Apple_Inc" in url:
            raise OSError("404")
        return """{"items": [
            {"timestamp": "2026080100", "views": 100},
            {"timestamp": "2026111700", "views": 100}
        ]}"""

    monkeypatch.setattr(attention, "robust_velocity", lambda *a, **k: attention.AttentionReading(
        article="", zscore=3.0, ratio=2.0, short_mean=200, baseline_median=100,
        baseline_mad=5, sample_days=90, short_days=7, as_of="2026-11-17", method="m",
        provenance={},
    ))
    reading = attention.fetch_reading(
        fake_fetch, company_name="Apple Inc.", as_of="2026-11-17",
    )
    assert reading is not None
    assert len(calls) >= 2  # the 404 candidate was skipped
    assert reading.article

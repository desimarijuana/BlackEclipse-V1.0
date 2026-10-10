"""Persistent bar-series store tests."""

from __future__ import annotations

import pytest

from harness.market.series_store import SeriesStore
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path):
    mem = AgentMemoryStore(path=str(tmp_path / "agent-memory.db"))
    return SeriesStore(mem)


def _bars(base=100.0):
    return [
        {"timestamp": "2026-01-02T00:00:00Z", "open": base, "high": base + 2, "low": base - 1, "close": base, "volume": 10},
        {"timestamp": "2026-01-03T00:00:00Z", "open": base, "high": base + 3, "low": base - 1, "close": base + 1, "volume": 20},
    ]


def test_save_and_get_bars(store):
    assert store.save_bars("AAPL", "1d", "yahoo", True, _bars()) == 2
    rows = store.get_bars("AAPL", "1d", adjusted=True)
    assert len(rows) == 2
    assert rows[0]["close"] == 100.0
    assert rows[0]["knownAt"] is None


def test_upsert_is_idempotent(store):
    store.save_bars("AAPL", "1d", "yahoo", True, _bars())
    store.save_bars("AAPL", "1d", "yahoo", True, _bars())
    assert store.coverage("AAPL", "1d")["barCount"] == 2


def test_adjusted_flag_separates_series(store):
    store.save_bars("AAPL", "1d", "yahoo", True, _bars())
    store.save_bars("AAPL", "1d", "yahoo", False, _bars(200.0))
    assert store.coverage("AAPL", "1d", adjusted=True)["barCount"] == 2
    assert store.coverage("AAPL", "1d", adjusted=False)["barCount"] == 2
    raw = store.get_bars("AAPL", "1d", adjusted=False)
    assert raw[0]["close"] == 200.0


def test_range_filter_and_list(store):
    store.save_bars("AAPL", "1d", "yahoo", True, _bars())
    store.save_bars("MSFT", "1d", "yahoo", True, _bars(300.0))
    rows = store.get_bars("AAPL", "1d", start="2026-01-03")
    assert len(rows) == 1
    assert rows[0]["close"] == 101.0
    listing = store.list_series()
    assert {s["symbol"] for s in listing} == {"AAPL", "MSFT"}

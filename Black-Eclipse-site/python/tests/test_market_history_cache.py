"""Tests for the durable history cache.

The point: history the runtime has already paid for is kept on the machine, and
a later request for the same window is served from it - so the backtest, the
regimes, the Monte-Carlo, Pine and the trade-log analysis all read the SAME
local bars.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from harness.market.history_cache import HistoryCache
from harness.market.series_store import SeriesStore
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def cache(tmp_path) -> HistoryCache:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return HistoryCache(SeriesStore(ams))


def _rows(n=10, start=1700000000000, step=86400000):
    out = []
    for i in range(n):
        out.append({
            "timestamp": datetime.fromtimestamp(
                (start + i * step) / 1000.0, tz=timezone.utc).isoformat()
                .replace("+00:00", "Z"),
            "open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
            "close": 100.5 + i, "volume": 1000.0,
        })
    return out


def test_a_miss_is_a_miss_not_an_empty_answer(cache):
    assert cache.lookup("AAPL", "1d") is None


def test_fetched_bars_are_kept_and_served_back(cache):
    rows = _rows()
    cache.store("AAPL", "1d", "yahoo", True, rows)
    served = cache.lookup("AAPL", "1d", start=rows[0]["timestamp"],
                           end=rows[-1]["timestamp"])
    assert served is not None
    assert len(served) == len(rows)
    assert served[0]["close"] == 100.5


def test_a_cache_that_does_not_cover_the_window_is_a_miss(cache):
    rows = _rows()
    cache.store("AAPL", "1d", "yahoo", True, rows)
    # A window that starts BEFORE the cache does.
    earlier = (datetime.fromisoformat(rows[0]["timestamp"]) - timedelta(days=5)
               ).isoformat().replace("+00:00", "Z")
    assert cache.lookup("AAPL", "1d", start=earlier, end=rows[-1]["timestamp"]) is None
    # A window that ends AFTER the cache does.
    later = (datetime.fromisoformat(rows[-1]["timestamp"]) + timedelta(days=5)
             ).isoformat().replace("+00:00", "Z")
    assert cache.lookup("AAPL", "1d", start=rows[0]["timestamp"], end=later) is None


def test_a_stale_tail_is_refetched(cache):
    rows = _rows()
    cache.store("AAPL", "1d", "yahoo", True, rows)
    # The rows are from 2023; the market has moved on since.
    assert cache.lookup("AAPL", "1d") is None


def test_a_fresh_tail_serves_the_whole_history(cache):
    now = datetime.now(timezone.utc)
    fresh = [{"timestamp": (now - timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
              "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}]
    cache.store("AAPL", "1d", "yahoo", True, fresh)
    assert cache.lookup("AAPL", "1d") is not None


def test_the_adjusted_flag_is_part_of_the_key(cache):
    rows = _rows()
    cache.store("AAPL", "1d", "yahoo", True, rows)
    assert cache.lookup("AAPL", "1d", adjusted=False,
                        start=rows[0]["timestamp"], end=rows[-1]["timestamp"]) is None


def test_a_second_fetch_merges_rather_than_replaces(cache):
    rows = _rows(5)
    cache.store("AAPL", "1d", "yahoo", True, rows)
    more = _rows(8)[5:]
    cache.store("AAPL", "1d", "yahoo", True, more)
    served = cache.lookup("AAPL", "1d", start=rows[0]["timestamp"],
                           end=_rows(8)[-1]["timestamp"])
    assert served is not None
    assert len(served) == 8


def test_the_coverage_is_reportable(cache):
    rows = _rows()
    cache.store("AAPL", "1d", "yahoo", True, rows)
    coverage = cache.coverage("AAPL", "1d")
    assert coverage["barCount"] == len(rows)
    assert coverage["start"] == rows[0]["timestamp"]


async def test_the_quant_fetch_is_served_from_the_cache(tmp_path):
    """A repeat fetch must NOT go to the provider again."""
    from harness.quant.datasets import fetch_series

    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    cache = HistoryCache(SeriesStore(ams))

    class _Bar:
        def model_dump(self):
            return {"timestamp": self.timestamp, "open": self.open, "high": self.high,
                    "low": self.low, "close": self.close, "volume": self.volume}

        def __init__(self, i):
            self.timestamp = (datetime.fromtimestamp(
                1700000000000 / 1000.0, tz=timezone.utc) + timedelta(days=i)
            ).isoformat().replace("+00:00", "Z")
            self.open = 100.0 + i
            self.high = 101.0 + i
            self.low = 99.0 + i
            self.close = 100.5 + i
            self.volume = 1000.0

    class _Result:
        provider = "yahoo"
        bars = [_Bar(i) for i in range(20)]

    calls = {"n": 0}

    class _Gateway:
        history_cache = cache

        async def get_historical_prices(self, *_a, **_k):
            calls["n"] += 1
            return _Result()

    gateway = _Gateway()
    bars = [_Bar(i) for i in range(20)]
    window = {"start": bars[0].timestamp, "end": bars[-1].timestamp}
    first = await fetch_series(gateway, "AAPL", interval="1d", **window)
    assert calls["n"] == 1
    assert first.length == 20

    # The same window is served from the local history: no second fetch.
    second = await fetch_series(gateway, "AAPL", interval="1d", **window)
    assert calls["n"] == 1
    assert second.length == 20

    # An UNPINNED request asks for everything there is, so the tail is refetched
    # - the market has moved on and a cache that never refreshed would freeze
    # it. That is the honest behaviour, and it is the reason the cache serves
    # a pinned window rather than an open-ended one.
    await fetch_series(gateway, "AAPL", interval="1d")
    assert calls["n"] == 2

"""Tests for the gallery, the venue seam and the vault backfill."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.gallery.store import GalleryStore
from harness.persistence import AgentMemoryStore
from harness.quant.venues import get_venue, list_venues


@pytest.fixture()
def gallery(tmp_path) -> GalleryStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return GalleryStore(ams)


# ── the gallery ──────────────────────────────────────────────────────────────

def test_publishing_freezes_a_record(gallery):
    entry = gallery.publish(name="NQ cross", spec={"universe": {"symbols": ["NQ"]}},
                            strategy_id="ema_cross", strategy_version="1.0.0",
                            grade="B", score=72.5, summary="works in down_normal",
                            report="# Edge Report\n\nGrade B")
    assert entry.id.startswith("pub_")
    assert entry.grade == "B"
    assert entry.symbols == ["NQ"]
    stored = gallery.get(entry.id)
    assert stored is not None
    assert stored.report.startswith("# Edge Report")
    assert stored.spec["universe"]["symbols"] == ["NQ"]


def test_a_published_record_is_a_snapshot(gallery):
    entry = gallery.publish(name="NQ cross", spec={"version": "1.0.0"})
    stored = gallery.get(entry.id)
    stored.spec["version"] = "9.9.9"
    # The stored spec is frozen: mutating the returned object does not rewrite
    # the record.
    assert gallery.get(entry.id).spec["version"] == "1.0.0"


def test_favouriting_and_cloning_count(gallery):
    entry = gallery.publish(name="NQ cross", spec={})
    assert gallery.favourite(entry.id).favourites == 1
    assert gallery.favourite(entry.id).favourites == 2
    assert gallery.count_clone(entry.id).clones == 1


def test_an_unknown_published_record_is_not_found(gallery):
    assert gallery.get("pub_nope") is None
    assert gallery.favourite("pub_nope") is None
    assert gallery.remove("pub_nope") is False


def test_listing_is_newest_first(gallery):
    first = gallery.publish(name="first", spec={})
    second = gallery.publish(name="second", spec={})
    ids = [e.id for e in gallery.list()]
    assert ids.index(second.id) < ids.index(first.id)


async def test_cloning_makes_a_new_strategy_and_leaves_the_original(gallery):
    from harness.gallery.tools import clone_published_strategy
    from harness.quant.store import QuantStore

    ams = AgentMemoryStore(str(gallery._store.path))
    quant = QuantStore(ams, artifact_root="/tmp/does-not-matter")
    from harness.quant.strategy import parse_strategy

    spec = parse_strategy({
        "strategy": {"id": "ema_cross", "name": "EMA cross", "version": "1.0.0"},
        "universe": {"symbols": ["NQ"]},
        "indicators": [{"id": "ema_fast", "type": "ema", "params": {"period": 5}},
                       {"id": "ema_slow", "type": "ema", "params": {"period": 20}}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "ema_fast"}, "op": "cross_above",
             "right": {"ref": "ema_slow"}}]}},
            "exit": {"stop_loss": {"type": "atr", "value": 2},
                     "take_profit": {"type": "risk_reward", "value": 2}}},
        "position_sizing": {"type": "percent_equity", "value": 90},
    })
    entry = gallery.publish(name="NQ cross", spec=spec.model_dump())
    ctx = SimpleNamespace(gallery_store=gallery, quant_store=quant)
    text, data = await clone_published_strategy({"publishedId": entry.id}, ctx)
    assert data["status"] == "OK", data
    assert data["strategy"]["id"]
    # The clone is a NEW strategy; the published record is untouched.
    assert gallery.get(entry.id).clones == 1
    assert quant.get_strategy(data["strategy"]["id"])["spec"]["universe"]["symbols"] == ["NQ"]


async def test_publishing_without_a_strategy_is_refused(gallery):
    from harness.gallery.tools import publish_strategy

    ctx = SimpleNamespace(gallery_store=gallery, quant_store=None)
    text, data = await publish_strategy({}, ctx)
    assert data["status"] == "ERROR", data
    assert data["error"]["code"] == "STRATEGY_ID_REQUIRED"


# ── the venue seam ───────────────────────────────────────────────────────────

def test_every_venue_is_listed_with_its_real_availability():
    venues = list_venues()
    ids = [v["id"] for v in venues]
    assert ids == ["pine", "ninjascript", "powerlanguage", "easylanguage"]
    for venue in venues:
        assert "language" in venue
        if not venue["available"]:
            assert venue["reason"], venue["id"]


def test_a_venue_without_an_engine_says_why():
    venue = get_venue("ninjascript")
    assert venue.available is False
    assert "no NinjaScript engine is installed" in (venue.unavailable_reason or "")


def test_an_unknown_venue_is_refused():
    with pytest.raises(KeyError):
        get_venue("klingon")


def test_the_pine_venue_reports_the_engine_it_uses():
    venue = get_venue("pine")
    assert venue.engine == "pine-engine (pinets)"
    assert venue.extension == ".pine"


# ── the vault backfill ───────────────────────────────────────────────────────

async def test_the_backfill_fills_the_vault_and_reports_it(tmp_path):
    from harness.market.history_cache import HistoryCache
    from harness.market.series_store import SeriesStore
    from harness.market.tools import backfill_history

    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = SeriesStore(ams)
    cache = HistoryCache(store)

    class _Bar:
        def __init__(self, i):
            self.timestamp = f"2024-01-{i + 1:02d}T00:00:00Z"
            self.open = 100.0 + i
            self.high = 101.0 + i
            self.low = 99.0 + i
            self.close = 100.5 + i
            self.volume = 1000.0

    class _Result:
        provider = "yahoo"
        bars = [_Bar(i) for i in range(5)]

    class _Gateway:
        async def get_historical_prices(self, *_a, **_k):
            return _Result()

    ctx = SimpleNamespace(market_gateway=_Gateway(), market_series_store=store)
    text, data = await backfill_history({"symbols": ["AAPL", "MSFT"]}, ctx)
    assert data["status"] == "ok"
    assert data["count"] == 2
    assert store.coverage("AAPL")["barCount"] == 5
    assert store.coverage("MSFT")["barCount"] == 5
    assert "Bundled" in text


async def test_the_backfill_refuses_without_symbols(tmp_path):
    from harness.market.series_store import SeriesStore
    from harness.market.tools import backfill_history

    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = SeriesStore(ams)
    ctx = SimpleNamespace(market_gateway=object(), market_series_store=store)
    text, data = await backfill_history({}, ctx)
    assert data["status"] == "error"

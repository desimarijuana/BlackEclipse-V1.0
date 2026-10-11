"""Service layer — caching identity, persistence, formula, artifact spilling."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.stats import service
from harness.stats.cache import reset_cache
from harness.stats.service import build_args_for_tool
from harness.stats.store import StatsStore


@pytest.fixture()
def wired(tmp_path):
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = StatsStore(ams, artifact_root=str(tmp_path / "art"))
    service.set_stats_store(store)
    reset_cache()
    yield store
    service.set_stats_store(None)
    reset_cache()


def test_cache_miss_then_hit(wired):
    r1 = service.execute("calculate_returns", {"values": [1.0, 2.0, 4.0, 8.0]})
    r2 = service.execute("calculate_returns", {"values": [1.0, 2.0, 4.0, 8.0]})
    assert r1["cacheHit"] is False
    assert r2["cacheHit"] is True
    # every execution is persisted, cache hit or not
    assert len(wired.list_analyses()) == 2


def test_cache_identity_changes_with_input(wired):
    service.execute("calculate_returns", {"values": [1.0, 2.0, 4.0]})
    r = service.execute("calculate_returns", {"values": [1.0, 2.0, 4.0, 8.0]})
    assert r["cacheHit"] is False


def test_cache_can_be_bypassed(wired):
    service.execute("calculate_returns", {"values": [1.0, 2.0, 4.0]})
    r = service.execute("calculate_returns", {"values": [1.0, 2.0, 4.0]}, use_cache=False)
    assert r["cacheHit"] is False


def test_analysis_id_and_audit(wired):
    r = service.execute("calculate_returns", {"values": [1.0, 2.0, 4.0]})
    assert r["analysisId"]
    assert any(e["action"] == "analysis.run" for e in wired.list_audit())


def test_formula_validate_and_execute(wired):
    assert service.validate_formula("sma(close, 3)")["valid"] is True
    bad = service.validate_formula("nope(")
    assert bad["valid"] is False
    out = service.execute_formula("close * 2", {"close": [1.0, 2.0, 3.0]})
    assert out["status"] == "ok"
    assert out["values"] == [2.0, 4.0, 6.0]


def test_build_args_single_and_pair():
    frame = {"values": [1.0, 2.0, 3.0]}
    args = build_args_for_tool("calculate_returns", frame, {"method": "log"})
    assert args["values"] == [1.0, 2.0, 3.0] and args["method"] == "log"
    frame2 = {"symbols": ["A", "B"], "values": [[1.0, 2.0], [3.0, 4.0]]}
    pair = build_args_for_tool("calculate_correlation", frame2, {})
    assert pair["x"] == [1.0, 2.0] and pair["y"] == [3.0, 4.0]


def test_artifact_spills_large_series(wired):
    from harness.stats.tools import _maybe_artifact

    envelope = {"analysisId": "a1", "results": {"bigSeries": list(range(6000))}}
    _maybe_artifact(wired, envelope)
    ref = envelope["results"]["bigSeries"]
    assert "__artifact__" in ref
    stored = wired.get_artifact(ref["__artifact__"])
    assert len(stored["content"]["bigSeries"]) == 6000


def test_unknown_tool_raises(wired):
    from harness.stats.base import StatsError

    with pytest.raises(StatsError):
        service.execute("does_not_exist", {})


async def test_execute_with_data_assembles_and_persists(wired):
    from types import SimpleNamespace

    class FakeGateway:
        async def get_historical_prices(self, symbol, _u, *, start=None, end=None, interval="1d",
                                        adjusted=True):
            prices = [100.0, 101.0, 102.0, 103.0, 104.0]
            bars = [SimpleNamespace(timestamp=f"t{i}", close=p, open=p, high=p, low=p, volume=1)
                    for i, p in enumerate(prices)]
            return SimpleNamespace(bars=bars, provider="fake", interval=interval, adjusted=adjusted)

    out = await service.execute_with_data("calculate_returns", FakeGateway(), ["AAPL"])
    assert out["status"] == "ok"
    assert out["provenance"]["dataset"]["symbols"] == ["AAPL"]
    assert out["analysisId"]


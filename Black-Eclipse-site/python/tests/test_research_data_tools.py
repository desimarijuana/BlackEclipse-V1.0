"""Shared quantitative-research tool surface tests.

Every provider call goes through a fake bridge; no network. The tools route
through the real Market Data Gateway, verification engine, transforms and the
immutable dataset store.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.market.cache import MarketCache
from harness.market.gateway import MarketDataGateway
from harness.market.research_tools import RESEARCH_DATA_TOOLS, register_research_data_tools
from harness.market.router import ProviderRouter
from harness.market.store import MarketStore
from harness.persistence import AgentMemoryStore
from harness.quant.dataset_store import DatasetStore
from harness.tools import DataBridge, ToolContext, ToolRegistry


def _rows(base: float) -> list[dict[str, Any]]:
    return [
        {"timestamp": "2026-01-02T00:00:00Z", "open": base, "high": base + 2, "low": base - 1, "close": base, "volume": 10},
        {"timestamp": "2026-01-03T00:00:00Z", "open": base, "high": base + 3, "low": base - 1, "close": base + 1, "volume": 20},
        {"timestamp": "2026-01-04T00:00:00Z", "open": base, "high": base + 4, "low": base - 1, "close": base + 2, "volume": 30},
    ]


class FakeBridge(DataBridge):
    """Serves instrument identity + provider-specific historical series + FX."""

    def __init__(self, provider_series: dict[str, float] | None = None) -> None:
        self.provider_series = provider_series or {"yahoo": 100.0, "stooq": 100.2,
                                                   "polygon": 100.0, "finnhub": 100.0}
        self.corporate_actions = False

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        if capability == "market_snapshot":
            symbol = params.get("symbol", "AAPL")
            market = params.get("market") or "US"
            return {"status": "OK", "symbol": symbol, "market": market, "exchange": "NASDAQ",
                    "currency": "USD", "assetClass": "equity",
                    "instrumentId": f"{market}:{symbol}"}
        if capability == "market_data":
            target = params.get("capability")
            provider = params.get("provider") or "yahoo"
            if target == "fx":
                return {"status": "OK", "provider": provider,
                        "base": params.get("base"), "quote": params.get("quote"),
                        "mid": 278.5, "rate": 278.5}
            base = self.provider_series.get(provider, 100.0)
            payload = {"status": "OK", "provider": provider,
                       "interval": params.get("interval") or "1d", "adjusted": True,
                       "series": _rows(base)}
            if self.corporate_actions:
                payload["corporateActions"] = [{"type": "dividend", "exDate": "2026-01-03", "amount": 0.5}]
            return payload
        return {"status": "UNAVAILABLE", "failureClass": "no_data", "error": "unknown"}


@pytest.fixture()
def ctx(tmp_path):
    bridge = FakeBridge()
    gateway = MarketDataGateway(bridge, cache=MarketCache(), router=ProviderRouter())
    mem = AgentMemoryStore(path=str(tmp_path / "agent-memory.db"))
    return ToolContext(
        run_id="r1", log=lambda *a, **k: None, data_bridge=bridge,
        market_gateway=gateway, market_store=MarketStore(mem),
        dataset_store=DatasetStore(mem, artifact_root=str(tmp_path / "artifacts")),
    )


def _run(coro):
    return asyncio.run(coro)


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_research_data_tools(registry)
    return registry


def test_all_tools_register():
    registry = _registry()
    for name in RESEARCH_DATA_TOOLS:
        assert registry.get(name) is not None


def test_resolve_instrument(ctx):
    result = _run(_registry().execute("resolve_instrument", "c1", {"symbol": "AAPL"}, ctx))
    assert result.ok
    assert result.data["status"] == "OK"
    assert result.data["instrument"]["symbol"] == "AAPL"


def test_list_providers_and_health(ctx):
    providers = _run(_registry().execute("list_providers", "c1", {}, ctx))
    assert providers.ok
    assert any(p["id"] == "yahoo" for p in providers.data["providers"])
    health = _run(_registry().execute("get_provider_health", "c2", {}, ctx))
    assert health.ok


def test_get_market_data_returns_rows(ctx):
    result = _run(_registry().execute(
        "get_market_data", "c1",
        {"symbols": ["AAPL"], "interval": "1d", "verification_policy": "fresh_preferred"}, ctx))
    assert result.ok
    assert result.data["status"] == "OK"
    entry = result.data["results"][0]
    assert entry["symbol"] == "AAPL"
    assert entry["barCount"] == 3
    assert len(entry["rows"]) == 3
    # The model-visible text must show the actual bars, not only a count
    # (observed failure: "11,551 bars, no rows").
    assert "bar(s)" in result.text
    assert "O=" in result.text and "C=" in result.text
    assert "structured `rows` carries the last 3" in result.text


def test_get_market_data_cross_verified(ctx):
    result = _run(_registry().execute(
        "get_market_data", "c1",
        {"symbols": ["AAPL"], "interval": "1d", "verification_policy": "cross_verified"}, ctx))
    assert result.ok
    verification = result.data["results"][0]["verification"]
    assert verification["status"] == "verified"
    assert verification["verified"] is True


def test_get_market_data_conflict_under_strict(ctx):
    bridge = FakeBridge({"yahoo": 100.0, "stooq": 160.0, "polygon": 100.0, "finnhub": 100.0})
    gateway = MarketDataGateway(bridge, cache=MarketCache(), router=ProviderRouter())
    local = ToolContext(run_id="r", log=lambda *a, **k: None, data_bridge=bridge, market_gateway=gateway)
    result = _run(_registry().execute(
        "get_market_data", "c1",
        {"symbols": ["AAPL"], "interval": "1d", "verification_policy": "strict_research"}, local))
    assert result.ok
    verification = result.data["results"][0]["verification"]
    assert verification["status"] == "failed"
    assert verification["verified"] is False


def test_verify_market_data_records_outcome(ctx):
    result = _run(_registry().execute(
        "verify_market_data", "c1", {"symbols": ["AAPL"], "policy": "cross_verified"}, ctx))
    assert result.ok
    assert result.data["outcomes"][0]["symbol"] == "AAPL"


def test_resample_and_align(ctx):
    resampled = _run(_registry().execute(
        "resample_data", "c1",
        {"symbols": ["AAPL"], "interval": "1d", "target_interval": "1w"}, ctx))
    assert resampled.ok
    assert resampled.data["results"]["AAPL"]["metadata"]["targetInterval"] == "1w"

    aligned = _run(_registry().execute(
        "align_timeseries", "c2", {"symbols": ["AAPL"], "interval": "1d", "join": "inner"}, ctx))
    assert aligned.ok
    assert len(aligned.data["timestamps"]) == 3


def test_build_and_query_dataset(ctx):
    built = _run(_registry().execute(
        "build_research_dataset", "c1",
        {"symbols": ["AAPL"], "interval": "1d", "name": "demo"}, ctx))
    assert built.ok
    manifest = built.data["manifest"]
    assert manifest["version"] == "v1"
    assert manifest["immutable"] is True
    dataset_id = manifest["datasetId"]

    versions = _run(_registry().execute("get_dataset_versions", "c2", {"dataset_id": dataset_id}, ctx))
    assert versions.ok
    assert len(versions.data["versions"]) == 1

    queried = _run(_registry().execute(
        "query_dataset", "c3", {"dataset_id": dataset_id, "limit": 2}, ctx))
    assert queried.ok
    assert len(queried.data["series"]["AAPL"]) == 2


def _make_ctx(tmp_path, bridge):
    gateway = MarketDataGateway(bridge, cache=MarketCache(), router=ProviderRouter())
    mem = AgentMemoryStore(path=str(tmp_path / "am2.db"))
    return ToolContext(
        run_id="r1", log=lambda *a, **k: None, data_bridge=bridge,
        market_gateway=gateway, market_store=MarketStore(mem),
        dataset_store=DatasetStore(mem, artifact_root=str(tmp_path / "art2")),
    )


def test_trading_calendar(ctx):
    result = _run(_registry().execute(
        "get_trading_calendar", "c1", {"market": "us_equity", "year": 2026}, ctx))
    assert result.ok
    assert result.data["status"] == "OK"
    assert len(result.data["holidays"]) >= 8
    assert "openNow" in result.data


def test_currency_conversion(ctx):
    result = _run(_registry().execute(
        "get_currency_conversion", "c1", {"base": "USD", "quote": "PKR", "amount": 10}, ctx))
    assert result.ok
    assert result.data["converted"] == 2785.0
    assert result.data["derived"] is False


def test_corporate_actions_absent_is_honest(ctx):
    result = _run(_registry().execute(
        "get_corporate_actions", "c1", {"symbols": ["AAPL"]}, ctx))
    assert result.ok
    assert result.data["results"][0]["status"] == "UNAVAILABLE"


def test_corporate_actions_present(tmp_path):
    bridge = FakeBridge()
    bridge.corporate_actions = True
    local = _make_ctx(tmp_path, bridge)
    result = _run(_registry().execute(
        "get_corporate_actions", "c1", {"symbols": ["AAPL"]}, local))
    assert result.ok
    assert result.data["results"][0]["actions"][0]["type"] == "dividend"


def test_universe_marks_asof_unknown(ctx):
    result = _run(_registry().execute(
        "get_universe", "c1", {"symbols": ["AAPL", "MSFT"], "as_of": "2020-01-01"}, ctx))
    assert result.ok
    assert result.data["asOfUnknown"] is True
    assert result.data["membershipBasis"] == "current_identities"
    assert result.data["count"] == 2


def test_query_dataset_as_of_flags_pit_unknown(ctx):
    built = _run(_registry().execute(
        "build_research_dataset", "c1", {"symbols": ["AAPL"], "dataset_id": "ds_pit"}, ctx)).data["manifest"]
    result = _run(_registry().execute(
        "query_dataset", "c2", {"dataset_id": built["datasetId"], "as_of": "2020-01-01"}, ctx))
    assert result.ok
    assert result.data["pitUnknown"] is True


def test_export_and_refresh_dataset(tmp_path, ctx):
    built = _run(_registry().execute(
        "build_research_dataset", "c1", {"symbols": ["AAPL"], "interval": "1d", "dataset_id": "ds_ex"}, ctx)).data["manifest"]
    exported = _run(_registry().execute(
        "export_dataset", "c2",
        {"dataset_id": built["datasetId"], "format": "csv", "out_dir": str(tmp_path / "exp")}, ctx))
    assert exported.ok
    assert exported.data["rowCount"] == 3
    assert len(exported.data["files"]) == 1

    refreshed = _run(_registry().execute(
        "refresh_dataset", "c3", {"dataset_id": built["datasetId"]}, ctx))
    assert refreshed.ok
    assert refreshed.data["manifest"]["version"] == "v2"
    assert refreshed.data["diff"]["sameContent"] is True


def test_record_and_asof_universe(tmp_path, ctx):
    rec = _run(_registry().execute(
        "record_universe", "c1",
        {"universe_id": "sp500", "effective_from": "2020-01-01",
         "members": [{"symbol": "AAPL"}, {"symbol": "MSFT"}]}, ctx))
    assert rec.ok
    assert rec.data["recorded"] == 2

    # As-of inside the window → both members, real recorded membership.
    inside = _run(_registry().execute(
        "get_universe", "c2", {"universe_id": "sp500", "as_of": "2020-06-01"}, ctx))
    assert inside.ok
    assert inside.data["membershipBasis"] == "recorded_membership"
    assert inside.data["asOfUnknown"] is False
    assert inside.data["count"] == 2

    # Retire AAPL after 2021-01-01; a later as-of must not include it.
    _run(_registry().execute(
        "record_universe", "c3",
        {"universe_id": "sp500", "effective_from": "2021-01-01",
         "members": [{"symbol": "AAPL", "effectiveTo": "2022-01-01"}]}, ctx))
    later = _run(_registry().execute(
        "get_universe", "c4", {"universe_id": "sp500", "as_of": "2022-06-01"}, ctx))
    assert later.data["count"] == 1
    listed = _run(_registry().execute("list_universes", "c5", {}, ctx))
    assert listed.ok and listed.data["universes"][0]["universeId"] == "sp500"


def test_analyze_dataset(ctx):
    built = _run(_registry().execute(
        "build_research_dataset", "c1", {"symbols": ["AAPL"], "dataset_id": "ds_an"}, ctx)).data["manifest"]
    result = _run(_registry().execute(
        "analyze_dataset", "c2",
        {"dataset_id": built["datasetId"],
         "operations": ["summary", "volatility", "max_drawdown"]}, ctx))
    assert result.ok
    assert result.data["results"]["summary"]["AAPL"]["count"] == 3
    assert "AAPL" in result.data["results"]["volatility"]
    assert "AAPL" in result.data["results"]["max_drawdown"]


def test_dataset_comparison_across_versions(ctx):
    first = _run(_registry().execute(
        "build_research_dataset", "c1",
        {"symbols": ["AAPL"], "interval": "1d", "dataset_id": "ds_demo"}, ctx)).data["manifest"]
    second = _run(_registry().execute(
        "build_research_dataset", "c2",
        {"symbols": ["AAPL"], "interval": "1d", "dataset_id": "ds_demo", "force": True}, ctx)).data["manifest"]
    assert first["version"] == "v1" and second["version"] == "v2"
    diff = _run(_registry().execute(
        "compare_datasets", "c3",
        {"dataset_id": "ds_demo", "version_a": "v1", "version_b": "v2"}, ctx))
    assert diff.ok
    assert diff.data["diff"]["sameContent"] is True  # same data, forced fork

"""Financial Data Gateway tests — provider registry, rate limits, crypto source.

Covers the additive surface layered on the existing Financial Retrieval Layer:

  * the declarative provider registry (capabilities, credential refs, usage
    policy, implemented-vs-declared honesty),
  * the centralized rate-limit / quota manager (sliding window, concurrency,
    429 cooldowns) and its integration into the layer (a denied acquire never
    calls the provider and never fabricates a failure),
  * the crypto source (pair resolution, equity collision refusal, identity on
    every object),
  * the gateway agent tools (financial_providers, financial_resolve_entity,
    market_get_crypto).

Everything is driven through fakes — no network, no JDdS, no provider.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.retrieval import FinancialRetrievalLayer, FinancialRetrievalRequest
from harness.retrieval.authority import CRYPTO, effective_authority, authority_for
from harness.retrieval.crypto import CryptoSource
from harness.retrieval.ratelimit import RateLimitManager
from harness.retrieval.registry import (
    ProviderDescriptor,
    ProviderRegistry,
    RateLimitSpec,
    build_default_registry,
)
from harness.retrieval.sources import SourceOutcome
from harness.retrieval.structured import is_crypto, is_fx_or_crypto
from harness.tools import DataBridge, ToolContext, ToolRegistry
from harness.retrieval_tools import register_retrieval_tools


# ── Fakes ───────────────────────────────────────────────────────────────────


class FakeBridge(DataBridge):
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        value = self.responses.get(capability)
        if value is None:
            return {"status": "UNAVAILABLE", "error": "no fake"}
        if callable(value):
            result = value(params)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        return value


def _now_iso() -> str:
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _crypto_payload(base: str = "BTC", quote: str = "USD", price: float = 64000.0) -> dict[str, Any]:
    return {
        "status": "OK", "symbol": base, "base": base, "quote": quote,
        "pair": f"{base}-{quote}", "price": price, "changePct": 1.0, "volume": 10.0,
        "provider": "crypto",
        "observationTime": _now_iso(), "observationSource": "provider_asof",
    }


def _ctx(bridge: DataBridge, registry: ProviderRegistry | None = None) -> ToolContext:
    return ToolContext(run_id="t", log=lambda *a, **k: None, data_bridge=bridge,  # type: ignore[arg-type]
                       provider_registry=registry, memory_store=None)


# ── Registry ────────────────────────────────────────────────────────────────


def test_default_registry_has_one_implemented_row_per_real_source():
    registry = build_default_registry()
    implemented = {p.id for p in registry.all() if p.implemented}
    # The five runnable sources the layer constructs.
    assert implemented == {"JDDS", "LIVE_STRUCTURED", "SEC", "WEB", "CRYPTO"}


def test_declared_providers_are_not_faked():
    registry = build_default_registry()
    for pid in ("FMP", "POLYGON", "FINNHUB", "COINGECKO"):
        descriptor = registry.get(pid)
        assert descriptor is not None
        assert descriptor.implemented is False, f"{pid} must not claim a runnable adapter"
        assert descriptor.notes, "an unimplemented provider must name its dependency"


def test_registry_capability_index_and_crypto():
    registry = build_default_registry()
    crypto = registry.by_capability("crypto_market_data")
    implemented = [p.id for p in crypto if p.implemented]
    # The one runnable crypto source; the declared CoinGecko/CMC rows are listed
    # too but are honestly `implemented=False`.
    assert implemented == ["CRYPTO"]
    assert "crypto_market_data" in registry.get("CRYPTO").capabilities  # type: ignore[union-attr]


def test_registry_describe_never_contains_a_secret_value():
    registry = build_default_registry()
    for entry in registry.describe():
        assert "apiKey" not in entry
        # Only a reference (env var name) is ever exposed.
        if entry.get("credentialRef"):
            assert entry["credentialRef"].isupper()


def test_registry_summary_shape():
    summary = build_default_registry().summary()
    assert summary["providerCount"] >= 5
    assert summary["implementedCount"] == 5
    assert "current_quote" in summary["capabilities"]


# ── Rate limit manager ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_enforces_requests_per_minute():
    clock = {"t": 0.0}
    mgr = RateLimitManager(now=lambda: clock["t"])
    spec = RateLimitSpec(requests_per_minute=2, concurrency=8)
    assert (await mgr.acquire("P", spec)).allowed
    assert (await mgr.acquire("P", spec)).allowed
    denied = await mgr.acquire("P", spec)
    assert not denied.allowed
    assert denied.retry_after_s is not None
    # After the window slides, a new request is allowed.
    clock["t"] = 61.0
    assert (await mgr.acquire("P", spec)).allowed


@pytest.mark.asyncio
async def test_rate_limit_enforces_concurrency():
    mgr = RateLimitManager(now=lambda: 0.0)
    spec = RateLimitSpec(concurrency=1)
    assert (await mgr.acquire("P", spec)).allowed
    assert not (await mgr.acquire("P", spec)).allowed
    await mgr.release("P")
    assert (await mgr.acquire("P", spec)).allowed


@pytest.mark.asyncio
async def test_rate_limit_429_opens_cooldown():
    clock = {"t": 0.0}
    mgr = RateLimitManager(now=lambda: clock["t"])
    await mgr.record_429("P", 30)
    denied = await mgr.acquire("P")
    assert not denied.allowed
    assert "cooldown" in (denied.reason or "")
    clock["t"] = 31.0
    assert (await mgr.acquire("P")).allowed


@pytest.mark.asyncio
async def test_rate_limit_snapshot_is_observable():
    mgr = RateLimitManager(now=lambda: 0.0)
    await mgr.acquire("P", RateLimitSpec(requests_per_minute=10))
    snap = mgr.snapshot()
    assert snap["P"]["granted"] == 1
    assert snap["P"]["requestsPerMinute"] == 10


# ── Layer + rate-limit integration ───────────────────────────────────────────


class _StubSource:
    name = "STUB"
    tier = "structured"
    dataTypes = ("current_quote",)

    def __init__(self) -> None:
        self.calls = 0

class _Counting(_StubSource):
    def available(self, request):
        return True

    async def retrieve(self, request):
        self.calls += 1
        from harness.retrieval.contract import NormalizedFinancialObject, SourceReference
        ref = SourceReference(source="STUB", sourceType="structured")
        return SourceOutcome(source="STUB", status="OK", references=[ref],
                             objects=[NormalizedFinancialObject(name="price", value=1.0, source=ref)])


@pytest.mark.asyncio
async def test_layer_denies_provider_call_when_rate_limited():
    """A provider at its concurrency limit is NOT called; the outcome is categorized."""
    registry = ProviderRegistry()
    registry.register(ProviderDescriptor(
        id="STUB", label="stub", tier="structured",
        capabilities=("current_quote",), source_name="STUB",
        rate_limit=RateLimitSpec(concurrency=1),
    ))
    source = _Counting()
    layer = FinancialRetrievalLayer(None, registry=registry)
    layer._sources = {"STUB": source}  # type: ignore[assignment]
    # Occupy the single concurrency slot.
    assert (await layer.rate_limits.acquire("STUB", registry.get("STUB").rate_limit)).allowed  # type: ignore[union-attr]
    request = FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="X")
    outcome = await layer._retrieve_one(source, request)
    assert outcome.status == "UNAVAILABLE"
    assert "rate limited" in (outcome.error or "").lower()
    assert source.calls == 0, "a denied acquire must not call the provider"
    assert outcome.diagnostics[0]["category"] == "rate_limited"


# ── Crypto source ────────────────────────────────────────────────────────────


def test_is_crypto_distinguishes_crypto_from_fx_and_equity():
    def req(**kw):
        return FinancialRetrievalRequest(objective="q", dataType="current_quote", **kw)

    assert is_crypto(req(instrument="BTC-USD")) is True
    assert is_crypto(req(market="CRYPTO", instrument="BTC")) is True
    assert is_crypto(req(instrument="EURUSD=X")) is False
    assert is_crypto(req(market="FX", instrument="EURUSD")) is False
    assert is_crypto(req(instrument="AAPL")) is False
    # The broader classifier still catches both.
    assert is_fx_or_crypto(req(instrument="BTC-USD")) is True


def test_crypto_source_refuses_non_crypto_requests():
    bridge = FakeBridge({})
    source = CryptoSource(bridge)
    request = FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="AAPL")
    assert source.available(request) is False


@pytest.mark.asyncio
async def test_crypto_source_normalizes_with_identity():
    bridge = FakeBridge({"crypto_market_data": _crypto_payload()})
    source = CryptoSource(bridge)
    request = FinancialRetrievalRequest(objective="btc", dataType="current_quote", instrument="BTC-USD")
    assert source.available(request) is True
    outcome = await source.retrieve(request)
    assert outcome.status == "OK"
    price = next(o for o in outcome.objects if o.name == "price")
    assert price.value == 64000.0
    assert price.identity is not None
    assert price.identity.market == "CRYPTO"
    assert price.identity.symbol == "BTC-USD"
    assert price.identity.currency == "USD"
    assert price.observation_source == "provider_asof"


@pytest.mark.asyncio
async def test_crypto_source_unavailable_is_honest():
    bridge = FakeBridge({"crypto_market_data": {"status": "UNAVAILABLE", "error": "no ticker"}})
    source = CryptoSource(bridge)
    request = FinancialRetrievalRequest(objective="btc", dataType="current_quote", instrument="BTC")
    outcome = await source.retrieve(request)
    assert outcome.status == "UNAVAILABLE"
    assert outcome.error


def test_effective_authority_prepends_crypto_only_for_crypto():
    crypto_req = FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="BTC-USD")
    equity_req = FinancialRetrievalRequest(objective="q", dataType="current_quote", instrument="AAPL")
    crypto_auth = effective_authority(authority_for("current_quote"), crypto_req)
    equity_auth = effective_authority(authority_for("current_quote"), equity_req)
    assert crypto_auth.candidates[0] == CRYPTO
    assert CRYPTO not in equity_auth.candidates


@pytest.mark.asyncio
async def test_layer_routes_crypto_to_crypto_source_only():
    bridge = FakeBridge({
        "crypto_market_data": _crypto_payload(),
        "live_quote": {"status": "OK", "symbol": "BTC", "price": {"price": 1.0}},
    })
    layer = FinancialRetrievalLayer(bridge, registry=build_default_registry())
    request = FinancialRetrievalRequest(
        objective="btc price", dataType="current_quote", instrument="BTC-USD",
        market="CRYPTO", freshnessRequirement="realtime",
    )
    result = await layer.retrieve(request)
    assert result.status == "OK"
    # The vault/live provider must never be consulted for crypto.
    assert all(cap != "live_quote" for cap, _ in bridge.calls)


# ── Agent tools ──────────────────────────────────────────────────────────────


def _tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_retrieval_tools(registry)
    return registry


def test_gateway_tools_are_registered():
    registry = _tool_registry()
    for name in ("financial_providers", "financial_resolve_entity", "market_get_crypto"):
        assert registry.get(name) is not None, f"{name} is not registered"


@pytest.mark.asyncio
async def test_financial_providers_tool_lists_and_filters():
    registry = _tool_registry()
    bridge = FakeBridge({"provider_key_status": {"status": "OK", "configured": False}})
    ctx = _ctx(bridge, build_default_registry())
    tool = registry.get("financial_providers")
    text, data = await tool.handler({"capability": "crypto_market_data"}, ctx)  # type: ignore[misc]
    assert data["capability"] == "crypto_market_data"
    assert all("crypto_market_data" in p["capabilities"] for p in data["providers"])
    assert "CRYPTO" in text


@pytest.mark.asyncio
async def test_financial_providers_tool_probes_credential_presence_via_bridge():
    """A keyed provider's presence is resolved through the bridge, never a value."""
    registry = _tool_registry()
    bridge = FakeBridge({"provider_key_status": {"status": "OK", "configured": True}})
    ctx = _ctx(bridge, build_default_registry())
    tool = registry.get("financial_providers")
    _text, data = await tool.handler({"capability": "financial_statements"}, ctx)  # type: ignore[misc]
    fmp = next(p for p in data["providers"] if p["id"] == "FMP")
    assert fmp["configured"] is True
    # The bridge was asked for presence, by env-var NAME only (never a value).
    assert ("provider_key_status", {"envVar": "FINANCIALMODELINGPREP_API_KEY"}) in bridge.calls


@pytest.mark.asyncio
async def test_financial_resolve_entity_tool_never_guesses():
    registry = _tool_registry()
    bridge = FakeBridge({
        "market_snapshot": {
            "status": "OK", "symbol": "AAPL", "market": "US", "exchange": "NASDAQ",
            "currency": "USD", "securityType": "equity", "name": "Apple Inc.",
        }
    })
    ctx = _ctx(bridge)
    tool = registry.get("financial_resolve_entity")
    text, data = await tool.handler({"identifier": "AAPL"}, ctx)  # type: ignore[misc]
    assert data["status"] == "OK"
    assert data["identity"]["symbol"] == "AAPL"

    ambiguous = FakeBridge({"market_snapshot": {"status": "AMBIGUOUS", "failureClass": "ambiguous",
                                                 "candidates": ["US:FFC", "PSX:FFC"]}})
    text, data = await tool.handler({"identifier": "FFC"}, _ctx(ambiguous))  # type: ignore[misc]
    assert data["status"] == "AMBIGUOUS"

    missing = FakeBridge({"market_snapshot": {"status": "UNAVAILABLE", "failureClass": "not_found"}})
    text, data = await tool.handler({"identifier": "ZZZZ"}, _ctx(missing))  # type: ignore[misc]
    assert data["status"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_market_get_crypto_tool_routes_through_layer():
    registry = _tool_registry()
    bridge = FakeBridge({"crypto_market_data": _crypto_payload("ETH", "USD", 2500.0)})
    ctx = _ctx(bridge, build_default_registry())
    tool = registry.get("market_get_crypto")
    text, data = await tool.handler({"symbol": "ETH-USD"}, ctx)  # type: ignore[misc]
    assert data["status"] == "OK"
    assert ("crypto_market_data", {"symbol": "ETH-USD"}) in bridge.calls

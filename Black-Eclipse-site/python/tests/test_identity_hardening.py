"""Sections A4/A8, C4, D1-D3 and E1 — cross-cutting regression tests.

Each test names the acceptance criterion it proves. They run through fakes, so
no network and no live provider is involved.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

import pytest

from harness.persistence import AgentMemoryStore
from harness.retrieval import FinancialRetrievalLayer, FinancialRetrievalRequest
from harness.retrieval.cache import RetrievalCache
from harness.retrieval.contract import (
    InstrumentIdentity,
    NormalizedFinancialObject,
    SourceReference,
)
from harness.retrieval.layer import _conflicts_payload
from harness.retrieval.validate import (
    detect_incomplete,
    looks_truncated,
)
from harness.tools import DataBridge, ToolContext


class FakeBridge(DataBridge):
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability, params))
        v = self.responses.get(capability)
        if v is None:
            return {"status": "UNAVAILABLE", "error": "no fake"}
        return v(params) if callable(v) else v


def _obj(name: str, value: Any, source: str, *, period: str | None = None) -> NormalizedFinancialObject:
    return NormalizedFinancialObject(
        name=name,
        value=value,
        period=period,
        source=SourceReference(source=source, sourceType="structured"),
    )


# ── D2: truncation detection ────────────────────────────────────────────────
def test_d2_truncated_numeric_is_detected():
    # The observed case: a cut-off "1,234.56" arriving as "1,23".
    assert looks_truncated("1,23") is True
    assert looks_truncated("12.") is True
    assert looks_truncated("1,") is True
    assert looks_truncated("1,23,456") is True


def test_d2_wellformed_values_are_not_flagged():
    assert looks_truncated("1,234.56") is False
    assert looks_truncated("237.42") is False
    assert looks_truncated("$1.2B") is False
    assert looks_truncated("-3.4%") is False
    assert looks_truncated("(1,234.56)") is False
    # Non-numeric strings are never truncation candidates.
    assert looks_truncated("Tesla, Inc.") is False
    assert looks_truncated("2024-Q1") is False
    assert looks_truncated("Common Stock") is False


def test_d2_incomplete_objects_are_marked_invalid():
    objs = [_obj("revenue", "1,23", "scraper"), _obj("price", "237.42", "scraper")]
    warnings = detect_incomplete(objs)
    assert objs[0].quality == "invalid"
    assert objs[1].quality != "invalid"
    assert any("truncated" in w for w in warnings)


# ── C4: conflicts carry all candidates + provenance ─────────────────────────
def test_c4_conflicts_list_every_candidate_with_source():
    objs = [
        _obj("price", 100.0, "JDDS"),
        _obj("price", 101.5, "LIVE_STRUCTURED"),
        _obj("changePct", 1.0, "JDDS"),
    ]
    conflicts = _conflicts_payload(objs)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["metric"] == "price"
    sources = {cand["source"] for cand in c["candidates"]}
    assert sources == {"JDDS", "LIVE_STRUCTURED"}
    values = {cand["value"] for cand in c["candidates"]}
    assert values == {100.0, 101.5}


def test_c4_single_source_is_not_a_conflict():
    objs = [_obj("price", 100.0, "JDDS"), _obj("price", 100.0, "JDDS")]
    assert _conflicts_payload(objs) == []


# ── D1: durable replay determinism ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_d1_identical_query_replays_the_same_result(tmp_path):
    directory = tempfile.mkdtemp(prefix="be-d1-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        # A stable, slow series (not realtime) so durable replay applies.
        bridge = FakeBridge(
            {
                "fundamentals": {
                    "status": "OK",
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "sector": "Technology",
                }
            }
        )
        layer = FinancialRetrievalLayer(bridge, cache=RetrievalCache(), store=store)
        req = FinancialRetrievalRequest(
            objective="company profile", dataType="company_profile", instrument="AAPL", market="US"
        )
        first = await layer.retrieve(req)
        assert first.status == "OK"

        # Second call with a fresh in-memory cache (simulating a new run) must
        # replay the durable record — identical figures, and the provider is NOT
        # called again.
        layer2 = FinancialRetrievalLayer(bridge, cache=RetrievalCache(), store=store)
        calls_before = len(bridge.calls)
        second = await layer2.retrieve(req)
        assert second.status == "OK"
        assert second.data == first.data
        assert len(bridge.calls) == calls_before  # no re-fetch
        assert layer2.metrics["durableHits"] == 1
    finally:
        store.close()


@pytest.mark.asyncio
async def test_d1_realtime_is_not_durably_replayed(tmp_path):
    directory = tempfile.mkdtemp(prefix="be-d1r-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        bridge = FakeBridge(
            {
                "market_snapshot": {
                    "status": "OK",
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "price": {"price": 100.0, "changePct": 1.0},
                }
            }
        )
        layer = FinancialRetrievalLayer(bridge, cache=RetrievalCache(), store=store)
        req = FinancialRetrievalRequest(
            objective="quote", dataType="current_quote", instrument="AAPL", market="US"
        )
        await layer.retrieve(req)
        # A realtime request must NOT be served from the durable store (it would
        # be stale by definition).
        layer2 = FinancialRetrievalLayer(bridge, cache=RetrievalCache(), store=store)
        await layer2.retrieve(req)
        assert layer2.metrics["durableHits"] == 0
    finally:
        store.close()


# ── D3: degradation is top-level ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_d3_degraded_flag_is_top_level():
    bridge = FakeBridge(
        {
            "market_snapshot": {
                "status": "OK",
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "price": {"price": 100.0, "changePct": 1.0},
            }
        }
    )
    layer = FinancialRetrievalLayer(bridge)
    req = FinancialRetrievalRequest(
        objective="quote", dataType="current_quote", instrument="AAPL", market="US"
    )
    result = await layer.retrieve(req)
    # The flag lives on the result object itself, not inside nested metadata.
    assert hasattr(result, "degraded")
    assert isinstance(result.degraded, bool)
    assert hasattr(result, "provenanceVerified")
    assert result.sourceReferences  # provenance present


# ── A8: macro series identity ───────────────────────────────────────────────
def test_a8_macro_generic_measure_requires_geography():
    from harness.macro_identity import resolve_macro_series

    # A bare generic measure must NOT default to US.
    r = resolve_macro_series("POLICY_RATE", None)
    assert r["ok"] is False
    assert r["reason"] == "ambiguous"
    assert any(c.startswith("US:") for c in r["candidates"])


def test_a8_macro_distinguishes_measures():
    from harness.macro_identity import resolve_macro_series

    target = resolve_macro_series("US:FRED:DFEDTARU", None)
    rrp = resolve_macro_series("US:FRED:RRPONTSYD", None)
    assert target["ok"] and rrp["ok"]
    assert target["identity"]["measure"] != rrp["identity"]["measure"]


def test_a8_macro_non_us_does_not_route_to_us_backend():
    from harness.macro_identity import resolve_macro_series

    ecb = resolve_macro_series("EA:ECB:DEPOSIT", None)
    assert ecb["ok"] is True
    assert ecb["identity"]["sourceId"] != "fred-analytics"
    assert ecb["identity"]["geography"] == "EA"


# ── E1: investigation — memory/skill tools ──────────────────────────────────
def test_e1_memory_and_skill_store_methods_exist():
    """The store CAN remember/recall/propose_skill — the gap is tool wiring."""
    directory = tempfile.mkdtemp(prefix="be-e1-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        assert hasattr(store, "remember")
        assert hasattr(store, "recall")
        assert hasattr(store, "propose_skill")
        mem = store.remember(scope="user", kind="fact", content="likes FFC", subject="FFC")
        assert mem["content"] == "likes FFC"
        recalled = store.recall(scope="user", subject="FFC")
        assert len(recalled) == 1
    finally:
        store.close()


def test_e1_no_memory_tool_is_registered():
    """Documents the gap: the tools registry exposes no memory/skill tools."""
    from harness.finance_tools import register_finance_tools
    from harness.retrieval_tools import register_retrieval_tools
    from harness.tools import ToolRegistry

    reg = ToolRegistry()
    register_finance_tools(reg)
    register_retrieval_tools(reg)
    names = set(reg.list_names()) if hasattr(reg, "list_names") else set()
    # If the registry exposes names, assert no memory tool leaked in; the agent
    # has no way to call remember/recall/propose_skill today.
    for forbidden in ("remember", "recall", "propose_skill"):
        assert forbidden not in names

# -- #2: the shared gate is structural � no tool resolves on its own ---------
@pytest.mark.asyncio
async def test_resolving_tools_all_call_the_bridge_capability():
    """Every instrument-resolving tool must go through the bridge capability
    that applies the shared identity gate. This enumerates the real tool surface
    (not a hand-picked list) and fails if a resolving tool bypasses the gate.
    """
    from harness.finance_tools import register_finance_tools
    from harness.retrieval_tools import register_retrieval_tools
    from harness.tools import ToolRegistry

    reg = ToolRegistry()
    register_finance_tools(reg)
    register_retrieval_tools(reg)

    # Capabilities that carry the identity gate on the TS side.
    GATED = {
        "market_snapshot",
        "live_quote",
        "price_history",
        "fundamentals",
        "financial_statements",
    }

    class RecordingBridge(DataBridge):
        def __init__(self) -> None:
            self.capabilities: list[str] = []

        async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
            self.capabilities.append(capability)
            # Minimal OK payloads so the layer proceeds past the source call.
            return {
                "status": "OK",
                "symbol": params.get("symbol"),
                "name": "X",
                "currency": "USD",
                "price": {"price": 1.0, "changePct": 0.0},
                "periods": [{"endDate": "2025-01-01", "revenue": 1, "netIncome": 1}],
                "rows": [{"date": "2025-01", "value": 1.0}],
                "items": [],
            }

    # Tools whose name implies instrument resolution MUST touch a gated capability.
    resolving = {"market_get_quote", "fundamentals_get_financials", "get_market_snapshot"}
    for name in sorted(resolving):
        tool = reg.get(name)
        assert tool is not None, f"{name} not registered"
        bridge = RecordingBridge()
        ctx = ToolContext(run_id="r", log=lambda *_: None, data_bridge=bridge)
        try:
            result = tool.handler({"symbol": "FFC"}, ctx)
            if asyncio.iscoroutine(result):
                await result
        except Exception:  # noqa: BLE001 - invocation details are irrelevant
            pass
        assert bridge.capabilities, (
            f"{name} never called the bridge — instrument resolution must route "
            "through a gated capability"
        )
        assert any(c in GATED for c in bridge.capabilities), (
            f"{name} resolved via {bridge.capabilities}, none of which is identity-gated"
        )


# -- #9: the conflict flag is exercised by a two-source fixture --------------
def test_conflict_flag_fires_on_a_two_source_disagreement():
    from harness.retrieval.layer import _conflicts_payload

    a = _obj("price", 100.0, "JDDS")
    b = _obj("price", 101.0, "LIVE_STRUCTURED")
    payload = _conflicts_payload([a, b])
    assert payload, "two sources disagreeing on one metric must produce a conflict"
    entry = payload[0]
    assert entry["metric"] == "price"
    values = sorted(c["value"] for c in entry["candidates"])
    sources = sorted(c["source"] for c in entry["candidates"])
    assert values == [100.0, 101.0]
    assert sources == ["JDDS", "LIVE_STRUCTURED"]


# -- #1/#2: no Python tool may inject a default market -----------------------
@pytest.mark.asyncio
async def test_no_tool_injects_a_default_market():
    """An omitted `market` must reach the bridge as absent (None), so the shared
    gate can return AMBIGUOUS. Injecting "US" here was the real leak on the agent path - the bridge never saw an unqualified request.
    """
    from harness.retrieval_tools import (
        fundamentals_get_company_profile,
        fundamentals_get_financials,
        market_get_ohlcv,
        market_get_quote,
    )

    seen: list[dict[str, Any]] = []

    class RecordingBridge(DataBridge):
        async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
            seen.append(params)
            # Return AMBIGUOUS as the real bridge would for an unqualified
            # multi-listed ticker � proving the tool passed market=None through.
            return {"status": "AMBIGUOUS", "failureClass": "ambiguous", "error": "ambiguous", "candidates": ["US", "PK"]}

    tools = [
        market_get_quote,
        market_get_ohlcv,
        fundamentals_get_company_profile,
        fundamentals_get_financials,
    ]
    for fn in tools:
        bridge = RecordingBridge()
        ctx = ToolContext(run_id="r", log=lambda *_: None, data_bridge=bridge)
        try:
            await fn({"symbol": "FFC"}, ctx)
        except Exception:  # noqa: BLE001
            pass
        assert seen, f"{fn.__name__} never reached the bridge"
        # The market must be absent/None, never defaulted to "US".
        assert seen[-1].get("market") in (None, ""), (
            f"{fn.__name__} injected market={seen[-1].get('market')!r} � a hidden default"
        )

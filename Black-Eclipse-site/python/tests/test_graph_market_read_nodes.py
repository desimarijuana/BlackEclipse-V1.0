"""Graph runtime — gateway-backed market-read nodes.

The nodes are thin adapters over the EXISTING market gateway. These tests pin
the things that could regress silently: every read is registered and executable,
provenance comes from the record's own meta, a missing symbol/address fails
honestly, and a gateway failure is a node failure rather than a placeholder.
"""

from __future__ import annotations

import pytest

from harness.graph_runtime import finance_nodes
from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.model import ExecutionMode, RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()

GATEWAY_TYPES = [
    "finance.instrument",
    "finance.orderbook",
    "finance.trades",
    "finance.volume",
    "finance.market_cap",
    "finance.fx_rate",
    "finance.options_chain",
    "finance.bond",
    "finance.funding_rate",
    "finance.open_interest",
    "finance.supply",
    "finance.tvl",
    "finance.onchain",
    "finance.liquidations",
    "finance.long_short_ratio",
]


class FakeGateway:
    """Records each call and returns a normalized record with real provenance."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail: set[str] = set()

    def _record(self, symbol: str | None, **fields):
        return {
            "meta": {
                "provider": "fake",
                "symbol": symbol,
                "asset_type": "equity",
                "freshness": "realtime",
                "quality": "valid",
                "data_status": "OK",
                "event_time": "2026-01-02T00:00:00Z",
                "retrieved_at": "2026-01-02T00:00:01Z",
                "warnings": [],
            },
            "timestamp": "2026-01-02T00:00:00Z",
            **fields,
        }

    async def _dispatch(self, capability, symbol, **kwargs):
        self.calls.append((capability, {"symbol": symbol, **kwargs}))
        if capability in self.fail:
            raise RuntimeError(f"{capability} provider exploded")
        return self._record(symbol, capability=capability, **kwargs)

    async def resolve_instrument(self, symbol, market=None):
        self.calls.append(("instrument", {"symbol": symbol, "market": market}))
        if "instrument" in self.fail:
            raise RuntimeError("bridge exploded")

        class Instrument:
            bridge_resolved = True

            def to_dict(self):
                return {
                    "instrumentId": f"EQ:{symbol}",
                    "symbol": symbol,
                    "assetType": "equity",
                    "market": market or "US",
                    "bridgeResolved": True,
                    "resolved": True,
                }

        return Instrument(), None

    async def get_orderbook(self, symbol, market=None, *, depth=20, freshness="realtime"):
        return await self._dispatch("orderbook", symbol, depth=depth, freshness=freshness)

    async def get_trades(self, symbol, market=None, *, limit=100, start=None, end=None, freshness="realtime"):
        return await self._dispatch("trades", symbol, limit=limit, start=start, end=end, freshness=freshness)

    async def get_volume(self, symbol, market=None, *, window="1d", freshness="intraday"):
        return await self._dispatch("volume", symbol, window=window, freshness=freshness)

    async def get_market_cap(self, symbol, market=None, *, freshness="daily"):
        return await self._dispatch("market_cap", symbol, freshness=freshness)

    async def get_fx_rate(self, base=None, quote=None, *, symbol=None, freshness="realtime"):
        return await self._dispatch("fx", symbol or f"{base}{quote}", freshness=freshness)

    async def get_options_chain(self, symbol, market=None, *, expiration=None, greeks=False, freshness="daily"):
        return await self._dispatch("options", symbol, expiration=expiration, greeks=greeks, freshness=freshness)

    async def get_bond_data(self, symbol, market=None, *, series_type=None, freshness="slow"):
        return await self._dispatch("bond", symbol, series_type=series_type, freshness=freshness)

    async def get_funding_rate(self, symbol, market=None, *, exchange=None, history=0, freshness="realtime"):
        return await self._dispatch("funding", symbol, exchange=exchange, history=history, freshness=freshness)

    async def get_open_interest(self, symbol, market=None, *, exchange=None, window="24h", freshness="intraday"):
        return await self._dispatch("open_interest", symbol, exchange=exchange, window=window, freshness=freshness)

    async def get_supply(self, symbol, market=None, *, freshness="daily"):
        return await self._dispatch("supply", symbol, freshness=freshness)

    async def get_tvl(self, symbol, market=None, *, chain=None, freshness="daily"):
        return await self._dispatch("tvl", symbol, chain=chain, freshness=freshness)

    async def get_onchain_metric(self, address, *, chain="ethereum", freshness="intraday"):
        return await self._dispatch("onchain", address, chain=chain, freshness=freshness)

    async def get_liquidations(self, symbol, market=None, *, exchange=None, window="24h", freshness="intraday"):
        return await self._dispatch("liquidations", symbol, exchange=exchange, window=window, freshness=freshness)

    async def get_long_short_ratio(self, symbol, market=None, *, exchange=None, interval="1h", limit=48, freshness="intraday"):
        return await self._dispatch("long_short", symbol, exchange=exchange, interval=interval, limit=limit, freshness=freshness)


@pytest.fixture()
def gateway():
    fake = FakeGateway()
    saved = finance_nodes._market_gateway  # noqa: SLF001 - deliberate save/restore
    finance_nodes.set_market_gateway(fake)
    try:
        yield fake
    finally:
        finance_nodes.set_market_gateway(saved)


def _context(node_type: str, *, inputs=None, config=None):
    return NodeExecContext(
        node_id="n1",
        run_id="run1",
        mode=ExecutionMode.RESEARCH,
        inputs=inputs or {},
        config=config or {},
    )


def _exec(node_type: str, *, inputs=None, config=None):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(_context(node_type, inputs=inputs, config=config))


def _node(node_id, node_type, config=None):
    return {
        "id": node_id, "type": node_type, "version": "1.0.0",
        "config": config or {}, "layout": {"x": 0, "y": 0},
    }


def _edge(edge_id, source, source_handle, target, target_handle):
    return {
        "id": edge_id, "source": source, "sourceHandle": source_handle,
        "target": target, "targetHandle": target_handle,
    }


def _ir(nodes, edges):
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_read", "name": "Read",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    })


# ── Registry contract ───────────────────────────────────────────────────────


def test_every_gateway_read_is_registered_executable_and_read_only():
    for node_type in GATEWAY_TYPES:
        definition = REGISTRY.get(node_type)
        assert definition is not None, node_type
        assert definition.executor is not None, node_type
        assert definition.available, node_type
        assert definition.capabilities == ("market.read",), node_type
        assert definition.side_effects.value == "read", node_type
        assert definition.category == "finance", node_type


# ── Provenance and happy paths ──────────────────────────────────────────────


def test_orderbook_returns_the_record_and_provenance(gateway):
    result = _exec("finance.orderbook", inputs={"symbol": "aapl"}, config={"depth": 5})
    assert result["book"]["capability"] == "orderbook"
    provenance = result["provenance"]
    assert provenance["provider"] == "fake"
    assert provenance["symbol"] == "AAPL"
    assert provenance["kind"] == "orderbook"
    assert provenance["asOf"] == "2026-01-02T00:00:00Z"
    assert provenance["retrievedAt"] == "2026-01-02T00:00:01Z"
    # A compact, readable digest rides alongside the full record.
    assert result["summary"]["symbol"] == "AAPL"
    assert result["summary"]["provider"] == "fake"
    assert result["summary"]["asOf"] == "2026-01-02T00:00:00Z"
    assert gateway.calls[-1] == ("orderbook", {"symbol": "AAPL", "depth": 5, "freshness": "realtime"})


def test_every_symbol_read_dispatches_the_expected_gateway_method(gateway):
    cases = [
        ("finance.trades", "trades"),
        ("finance.volume", "volume"),
        ("finance.market_cap", "market_cap"),
        ("finance.options_chain", "options"),
        ("finance.bond", "bond"),
        ("finance.funding_rate", "funding"),
        ("finance.open_interest", "open_interest"),
        ("finance.supply", "supply"),
        ("finance.tvl", "tvl"),
        ("finance.liquidations", "liquidations"),
        ("finance.long_short_ratio", "long_short"),
    ]
    for node_type, capability in cases:
        _exec(node_type, inputs={"symbol": "AAPL"})
        assert gateway.calls[-1][0] == capability, node_type


def test_fx_accepts_a_pair_or_base_and_quote(gateway):
    pair = _exec("finance.fx_rate", inputs={"symbol": "eurusd"})
    assert pair["rate"]["capability"] == "fx"
    assert pair["provenance"]["symbol"] == "EURUSD"

    split = _exec("finance.fx_rate", config={"base": "EUR", "quote": "USD"})
    assert split["provenance"]["symbol"] == "EURUSD"
    assert gateway.calls[-1][0] == "fx"


def test_onchain_reads_the_address(gateway):
    result = _exec("finance.onchain", inputs={"address": "0xabc"}, config={"chain": "base"})
    assert result["metrics"]["capability"] == "onchain"
    assert gateway.calls[-1] == ("onchain", {"symbol": "0xabc", "chain": "base", "freshness": "intraday"})


def test_instrument_resolves_and_labels_the_bridge(gateway):
    result = _exec("finance.instrument", inputs={"symbol": "aapl"}, config={"market": "US"})
    assert result["instrument"]["symbol"] == "AAPL"
    assert result["provenance"]["kind"] == "instrument"
    assert result["provenance"]["bridgeResolved"] is True
    assert result["provenance"]["assetType"] == "equity"


# ── Honest failures ─────────────────────────────────────────────────────────


def test_missing_symbol_is_a_clear_failure(gateway):
    with pytest.raises(ValueError, match="no symbol"):
        _exec("finance.orderbook")


def test_missing_address_is_a_clear_failure(gateway):
    with pytest.raises(ValueError, match="no address"):
        _exec("finance.onchain")


def test_fx_needs_a_pair_or_both_legs(gateway):
    with pytest.raises(ValueError, match="fx pair"):
        _exec("finance.fx_rate")


def test_a_gateway_exception_becomes_a_node_failure(gateway):
    gateway.fail.add("orderbook")
    with pytest.raises(ValueError, match="get_orderbook unavailable"):
        _exec("finance.orderbook", inputs={"symbol": "AAPL"})


def test_an_unconfigured_gateway_fails_honestly():
    saved = finance_nodes._market_gateway  # noqa: SLF001
    finance_nodes.set_market_gateway(None)
    try:
        with pytest.raises(ValueError, match="not configured"):
            _exec("finance.volume", inputs={"symbol": "AAPL"})
    finally:
        finance_nodes.set_market_gateway(saved)


# ── The nodes actually run inside a graph ───────────────────────────────────


def test_a_read_node_runs_in_a_test_run(gateway):
    graph = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "AAPL"}),
            _node("book", "finance.orderbook", {"depth": 10}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "book", "symbol"),
            _edge("e2", "book", "provenance", "out", "value"),
        ],
    )
    plan = compile_workflow(graph, REGISTRY, RunGrants(test_run=True))
    assert plan.executable, [diagnostic.message for diagnostic in plan.diagnostics]
    run = GraphExecutor(graph, plan, REGISTRY, run_id="grun_read").execute()
    assert run.status == RunStatus.SUCCEEDED
    by_node = {item.node_id: item for item in run.node_runs}
    assert by_node["book"].outputs["provenance"]["provider"] == "fake"
    assert by_node["out"].inputs["value"]["kind"] == "orderbook"

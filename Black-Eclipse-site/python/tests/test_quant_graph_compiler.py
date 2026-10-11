"""Strategy graph compiler: node registry, compilation, validation, determinism."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant.compiler import compile_graph
from harness.quant.nodes import REGISTRY, NodeRegistry
from harness.quant.store import QuantStore
from harness.quant.tools import register_quant_tools
from harness.tools import ToolContext, ToolRegistry


def _graph(**overrides):
    base = {
        "schemaVersion": "1.0.0",
        "strategy": {"id": "ema_x", "name": "EMA X", "version": "1.0.0"},
        "nodes": [
            {"id": "u", "type": "data.universe",
             "config": {"symbols": ["TESTUSDT"], "primary": "1d"}},
            {"id": "f", "type": "indicator.ema", "config": {"period": 5, "id": "ema_f"}},
            {"id": "s", "type": "indicator.ema", "config": {"period": 20, "id": "ema_s"}},
            {"id": "x", "type": "indicator.atr", "config": {"period": 14, "id": "atr"}},
            {"id": "c", "type": "logic.cross", "config": {"direction": "above"}},
            {"id": "e", "type": "trade.entry", "config": {"side": "long"}},
            {"id": "sl", "type": "stop.loss", "config": {"type": "atr", "value": 2, "atrIndicator": "atr"}},
            {"id": "sz", "type": "sizing.position", "config": {"type": "percent_equity", "value": 90}},
        ],
        "edges": [
            {"from": "f", "to": "c", "toPort": "left"},
            {"from": "s", "to": "c", "toPort": "right"},
            {"from": "c", "to": "e", "toPort": "in"},
        ],
    }
    base.update(overrides)
    return base


# ── Registry ─────────────────────────────────────────────────────────────────

def test_registry_has_all_categories():
    cats = {n.category for n in REGISTRY.all()}
    assert {"data", "indicator", "logic", "trading", "sizing", "risk"} <= cats
    assert "indicator.ema" in REGISTRY.types()
    for describe in REGISTRY.describe_all():
        assert describe["type"] and describe["title"] and describe["category"]


def test_node_version_compatibility():
    assert NodeRegistry.version_supported(None, "1.0.0") is True
    assert NodeRegistry.version_supported("1.3.0", "1.0.0") is True
    assert NodeRegistry.version_supported("2.0.0", "1.0.0") is False


# ── Compilation ──────────────────────────────────────────────────────────────

def test_compile_ema_cross_is_valid_and_runs():
    result = compile_graph(_graph())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    spec = result.spec
    assert spec.id == "ema_x"
    assert {i.id for i in spec.indicators} == {"ema_f", "ema_s", "atr"}
    assert result.source_map["rules.entry.long"] == "e"
    assert result.source_map["rules.exit.stop_loss"] == "sl"

    rows = F.bull_market("TESTUSDT", n=200)
    ds = D.build_dataset({"TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})
    res = E.run_backtest(spec, ds, E.BacktestConfig(initial_capital=100_000))
    assert res.status.upper() == "OK"
    assert res.metrics.get("trade_count") is not None


def test_compile_is_deterministic():
    r1 = compile_graph(_graph())
    r2 = compile_graph(_graph())
    assert r1.spec.to_json() == r2.spec.to_json()
    assert r1.ordering == r2.ordering


def test_group_and_multiple_indicators():
    g = _graph(
        nodes=[
            {"id": "u", "type": "data.universe", "config": {"symbols": ["A"]}},
            {"id": "r", "type": "indicator.rsi", "config": {"period": 14, "id": "rsi"}},
            {"id": "thirty", "type": "logic.constant", "config": {"value": 30}},
            {"id": "gt", "type": "logic.compare", "config": {"op": ">"}},
            {"id": "f", "type": "indicator.ema", "config": {"period": 20, "id": "ema_f"}},
            {"id": "s", "type": "indicator.ema", "config": {"period": 50, "id": "ema_s"}},
            {"id": "cr", "type": "logic.cross", "config": {"direction": "above"}},
            {"id": "grp", "type": "logic.group", "config": {"combine": "all"}},
            {"id": "e", "type": "trade.entry", "config": {"side": "long"}},
        ],
        edges=[
            {"from": "r", "to": "gt", "toPort": "left"},
            {"from": "thirty", "to": "gt", "toPort": "right"},
            {"from": "f", "to": "cr", "toPort": "left"},
            {"from": "s", "to": "cr", "toPort": "right"},
            {"from": "gt", "to": "grp", "toPort": "in"},
            {"from": "cr", "to": "grp", "toPort": "in"},
            {"from": "grp", "to": "e", "toPort": "in"},
        ],
    )
    result = compile_graph(g)
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    entry = result.spec.rules.entry.long
    assert entry.combine == "all" and len(entry.conditions) == 2


def test_bollinger_and_macd_output_selection():
    g = _graph(
        nodes=[
            {"id": "u", "type": "data.universe", "config": {"symbols": ["A"]}},
            {"id": "bb", "type": "indicator.bollinger",
             "config": {"period": 20, "num_std": 2, "output": "upper", "id": "bb"}},
            {"id": "mc", "type": "indicator.macd",
             "config": {"fast": 12, "slow": 26, "signal": 9, "output": "signal", "id": "macd"}},
            {"id": "cmp", "type": "logic.compare", "config": {"op": ">"}},
            {"id": "e", "type": "trade.entry", "config": {"side": "long"}},
        ],
        edges=[
            {"from": "bb", "to": "cmp", "toPort": "left"},
            {"from": "mc", "to": "cmp", "toPort": "right"},
            {"from": "cmp", "to": "e", "toPort": "in"},
        ],
    )
    result = compile_graph(g)
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    refs = {r for c in result.spec.rules.entry.long.conditions for r in (c.left.ref, c.right.ref)}
    assert "bb_upper" in refs
    assert "macd_signal" in refs


# ── Diagnostics ──────────────────────────────────────────────────────────────

def test_unknown_node_type():
    r = compile_graph(_graph(nodes=[{"id": "z", "type": "nope.nope", "config": {}}], edges=[]))
    assert not r.ok
    assert any(d.code == "UNKNOWN_NODE_TYPE" for d in r.diagnostics)


def test_unsupported_node_version():
    nodes = _graph()["nodes"]
    nodes[1] = {"id": "f", "type": "indicator.ema", "version": "2.0.0", "config": {"period": 5}}
    r = compile_graph(_graph(nodes=nodes))
    assert any(d.code == "UNSUPPORTED_NODE_VERSION" for d in r.diagnostics)


def test_type_mismatch():
    g = _graph(
        nodes=[
            {"id": "k", "type": "logic.constant", "config": {"value": 1}},
            {"id": "e", "type": "trade.entry", "config": {"side": "long"}},
        ],
        edges=[{"from": "k", "to": "e", "toPort": "in"}],
    )
    r = compile_graph(g)
    assert any(d.code == "TYPE_MISMATCH" for d in r.diagnostics)


def test_missing_required_input():
    g = _graph(
        nodes=[
            {"id": "u", "type": "data.universe", "config": {"symbols": ["A"]}},
            {"id": "e", "type": "trade.entry", "config": {"side": "long"}},
        ],
        edges=[],
    )
    r = compile_graph(g)
    assert any(d.code == "MISSING_INPUT" for d in r.diagnostics)


def test_cycle_detected():
    g = _graph(
        nodes=[
            {"id": "g1", "type": "logic.group", "config": {"combine": "all"}},
            {"id": "g2", "type": "logic.group", "config": {"combine": "all"}},
        ],
        edges=[
            {"from": "g1", "to": "g2", "toPort": "in"},
            {"from": "g2", "to": "g1", "toPort": "in"},
        ],
    )
    r = compile_graph(g)
    assert any(d.code == "CYCLE_DETECTED" for d in r.diagnostics)


def test_duplicate_node_id():
    nodes = _graph()["nodes"] + [{"id": "f", "type": "indicator.sma", "config": {"period": 3}}]
    r = compile_graph(_graph(nodes=nodes))
    assert any(d.code == "DUPLICATE_NODE_ID" for d in r.diagnostics)


def test_ir_validation_surfaces_no_entry():
    g = _graph(
        nodes=[{"id": "u", "type": "data.universe", "config": {"symbols": ["A"]}}],
        edges=[],
    )
    r = compile_graph(g)
    assert any(d.code == "EMPTY_UNIVERSE" or d.code == "NO_ENTRY_RULES" for d in r.diagnostics)


def test_bad_graph_shape():
    r = compile_graph({"schemaVersion": "1.0.0"})  # missing strategy
    assert not r.ok


# ── Tools ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def env(tmp_path):
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = QuantStore(ams, artifact_root=str(tmp_path / "art"))
    registry = ToolRegistry()
    register_quant_tools(registry)
    ctx = ToolContext(run_id="t", log=lambda *a, **k: None, quant_store=store)
    return registry, ctx


async def _call(registry, ctx, name, args):
    return await registry.execute(name, f"c_{name}", args, ctx)


async def test_tool_compile_and_list(env):
    registry, ctx = env
    r = await _call(registry, ctx, "compile_strategy_graph", {"graph": _graph()})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["spec"]["id"] == "ema_x"
    r2 = await _call(registry, ctx, "list_strategy_nodes", {})
    assert r2.ok and any(n["type"] == "indicator.ema" for n in r2.data["nodes"])
    r3 = await _call(registry, ctx, "validate_strategy_graph", {"graph": _graph()})
    assert r3.data["ok"] is True

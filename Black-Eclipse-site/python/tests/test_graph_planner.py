"""Chat-to-graph validation: a proposal only becomes an IR when it uses real
nodes, real ports, valid configs and compiles."""

from __future__ import annotations

import pytest

from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.planner import _catalog, plan_graph, validate_plan

REGISTRY = build_default_registry()


def _plan(nodes, edges, name="Generated workflow"):
    return {
        "name": name,
        "summary": "A tiny plan.",
        "nodes": nodes,
        "edges": edges,
        "warnings": [],
    }


def _minimal():
    return _plan(
        [
            {"id": "trig", "type": "trigger.manual", "config": {"seed": "AAPL"}},
            {"id": "out", "type": "output.result", "config": {"label": "Result"}},
        ],
        [
            {"id": "e1", "source": "trig", "sourceHandle": "start", "target": "out", "targetHandle": "value"},
        ],
    )


def test_catalog_contains_only_registered_types():
    catalog = _catalog(REGISTRY)
    types = {item["type"] for item in catalog}
    assert "trigger.manual" in types
    assert "output.result" in types
    assert len(catalog) == len(REGISTRY.definitions())


def test_a_valid_plan_becomes_a_research_ir():
    result = validate_plan(_minimal(), REGISTRY)
    assert result["ok"] is True
    assert result["executionMode"] == "research"
    assert result["ir"]["nodes"][0]["id"] == "trig"
    assert result["ir"]["requiredCapabilities"] == []


def test_plan_accepts_common_edge_aliases_and_object_handles():
    plan = _plan(
        [
            {"id": "trig", "type": "trigger.manual", "config": {}},
            {"id": "out", "type": "output.result", "config": {}},
        ],
        [
            {
                "id": "e1",
                "from": {"node": "trig", "port": "start"},
                "to": {"node": "out", "port": "value"},
            },
        ],
    )
    result = validate_plan(plan, REGISTRY)
    assert result["ok"] is True, result["errors"]
    assert result["ir"]["edges"][0]["sourceHandle"] == "start"
    assert result["ir"]["edges"][0]["targetHandle"] == "value"


def test_a_plan_without_a_name_still_gets_a_default():
    plan = _minimal()
    plan.pop("name")
    result = validate_plan(plan, REGISTRY)
    assert result["ok"] is True
    assert result["ir"]["name"] == "Generated workflow"


def test_unknown_node_types_and_ports_are_rejected():
    unknown = _minimal()
    unknown["nodes"][0]["type"] = "does.not.exist"
    result = validate_plan(unknown, REGISTRY)
    assert result["ok"] is False
    assert "unknown node type" in result["errors"][0]["message"]

    bad_port = _minimal()
    bad_port["edges"][0]["targetHandle"] = "missing"
    result = validate_plan(bad_port, REGISTRY)
    assert result["ok"] is False
    assert "port" in result["errors"][0]["message"]


def test_an_invalid_config_is_rejected():
    plan = _minimal()
    plan["nodes"][0]["config"] = {"seed": 42}
    result = validate_plan(plan, REGISTRY)
    assert result["ok"] is False
    assert "invalid config" in result["errors"][0]["message"]


def test_a_trading_plan_forces_paper_mode():
    plan = _plan(
        [
            {"id": "trig", "type": "trigger.manual", "config": {}},
            {"id": "risk", "type": "trading.risk_check", "config": {"price": 100, "maxPositionPct": 10}},
            {"id": "order", "type": "trading.paper_order", "config": {"price": 100}},
            {"id": "out", "type": "output.result", "config": {}},
        ],
        [
            {"id": "e1", "source": "trig", "sourceHandle": "start", "target": "risk", "targetHandle": "intent"},
            {"id": "e2", "source": "risk", "sourceHandle": "intent", "target": "order", "targetHandle": "intent"},
            {"id": "e3", "source": "order", "sourceHandle": "fill", "target": "out", "targetHandle": "value"},
        ],
    )
    result = validate_plan(plan, REGISTRY)
    assert result["ok"] is True
    assert result["executionMode"] == "paper"
    assert "trading.paper" in result["ir"]["requiredCapabilities"]


def test_a_plan_without_nodes_or_a_model_is_refused():
    assert validate_plan({"nodes": [], "edges": []}, REGISTRY)["ok"] is False
    with pytest.raises(ValueError, match="objective"):
        import asyncio

        asyncio.run(plan_graph("", model_settings={"provider": "x", "model": "m"}, registry=REGISTRY))
    with pytest.raises(ValueError, match="model provider"):
        import asyncio

        asyncio.run(plan_graph("build a scan", model_settings=None, registry=REGISTRY))

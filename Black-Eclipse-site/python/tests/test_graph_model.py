"""Graph runtime — IR contracts, config validation and the safe formula language."""

from __future__ import annotations

import pytest

from harness.graph_runtime.model import PortType, WorkflowIR
from harness.graph_runtime.nodes import FormulaError, build_default_registry, evaluate_formula, render_template
from harness.graph_runtime.registry import validate_config, validate_port_value


def _ir(**overrides):
    base = {
        "irVersion": 1,
        "id": "wf_test",
        "name": "Test",
        "description": "",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [],
        "edges": [],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    }
    base.update(overrides)
    return WorkflowIR.model_validate(base)


# ── IR parsing ──────────────────────────────────────────────────────────────


def test_ir_parses_camel_case_fields():
    ir = _ir(nodes=[{
        "id": "a", "type": "trigger.manual", "version": "1.0.0",
        "config": {"seed": "AAPL"}, "layout": {"x": 1, "y": 2},
    }], edges=[{
        "id": "e1", "source": "a", "sourceHandle": "start",
        "target": "b", "targetHandle": "value",
    }])
    assert ir.nodes[0].config["seed"] == "AAPL"
    assert ir.edges[0].source_handle == "start"
    assert ir.edges[0].target_handle == "value"
    assert ir.settings.execution_mode.value == "research"
    assert ir.model_dump(by_alias=True)["irVersion"] == 1


def test_ir_rejects_missing_required_fields():
    with pytest.raises(Exception):
        WorkflowIR.model_validate({"id": "x"})


# ── Port value validation ───────────────────────────────────────────────────


def test_primitive_port_validation():
    assert validate_port_value(PortType.NUMBER, 3) is None
    assert validate_port_value(PortType.NUMBER, True) is not None  # bool is not a number
    assert validate_port_value(PortType.STRING, "x") is None
    assert validate_port_value(PortType.STRING, 3) is not None
    assert validate_port_value(PortType.BOOLEAN, False) is None
    assert validate_port_value(PortType.OBJECT, {}) is None
    assert validate_port_value(PortType.ARRAY, []) is None
    assert validate_port_value(PortType.DATETIME, "2026-01-02T03:04:05Z") is None
    assert validate_port_value(PortType.DATETIME, "not-a-date") is not None
    assert validate_port_value(PortType.ANY, object()) is None
    assert validate_port_value(PortType.NUMBER, None) is None  # null always allowed


def test_domain_port_validation_is_structural():
    assert validate_port_value(PortType.OHLCV, [{"o": 1, "h": 2, "l": 0, "c": 1}]) is None
    assert validate_port_value(PortType.OHLCV, 12) is not None
    assert validate_port_value(PortType.INDICATOR, [1.0, 2.0]) is None
    assert validate_port_value(PortType.INDICATOR, {"values": [1, 2]}) is None
    assert validate_port_value(PortType.INDICATOR, "sma") is not None
    assert validate_port_value(PortType.INSTRUMENT, {"symbol": "AAPL"}) is None
    assert validate_port_value(PortType.INSTRUMENT, "AAPL") is not None
    assert validate_port_value(PortType.ORDER_INTENT, {"symbol": "AAPL", "side": "buy"}) is None


# ── Registry + config ───────────────────────────────────────────────────────


def test_every_registered_node_has_valid_defaults():
    registry = build_default_registry()
    assert len(registry.definitions()) >= 13
    for definition in registry.definitions():
        assert validate_config(definition, {}) == [], f"{definition.type} defaults must validate"


def test_config_validation_reports_real_problems():
    registry = build_default_registry()
    indicator = registry.get("finance.indicator")
    assert indicator is not None
    problems = validate_config(indicator, {"kind": "not-a-kind", "period": 9_999})
    assert any("kind" in p for p in problems)
    assert any("period" in p for p in problems)
    assert validate_config(indicator, {"kind": "sma", "period": 20}) == []


def test_unavailable_nodes_are_registered_with_a_phase():
    """Nodes whose executor a later phase still owes must be REGISTERED and name
    that phase, so the compiler can refuse them with an actionable message."""
    registry = build_default_registry()
    # The video render node is the remaining declared-only node; it names its
    # phase so the compiler can refuse it with an actionable message.
    video = registry.get("video.render")
    assert video is not None
    assert video.executor is None
    assert video.since_phase
    # The HTTP and agent nodes are executable now; they are gated by the
    # operator-run network envelope.
    for node_type in ("integration.http", "agent.research"):
        definition = registry.get(node_type)
        assert definition is not None and definition.executor is not None
        assert definition.side_effects.value == "network"
    # The finance/quant pack gained real executors in Phase 5.
    for node_type in ("finance.market_data", "finance.indicator", "quant.returns", "quant.zscore", "quant.volatility"):
        definition = registry.get(node_type)
        assert definition is not None and definition.available, node_type


# ── Formula language ────────────────────────────────────────────────────────


def test_formula_evaluates_arithmetic_and_functions():
    assert evaluate_formula("x * 2 + 1", {"x": 3}) == 7
    assert evaluate_formula("(x + y) / 2", {"x": 1, "y": 4}) == 2.5
    assert evaluate_formula("2 ** 3", {}) == 8
    assert evaluate_formula("min(x, 5) + abs(-2)", {"x": 9}) == 7
    assert evaluate_formula("-x", {"x": 2}) == -2
    assert evaluate_formula("pi", {}) == pytest.approx(3.141592653589793)


def test_formula_refuses_unsafe_or_invalid_input():
    for expression in ("x / 0", "unknownfn(1)", "z + 1", "1 +", "x ** 100000", ""):
        with pytest.raises(FormulaError):
            evaluate_formula(expression, {"x": 2}, )
    with pytest.raises(FormulaError):
        evaluate_formula("__import__('os')", {})
    with pytest.raises(FormulaError):
        evaluate_formula("x" * 500, {})


def test_template_renders_and_refuses_unknown_names():
    assert render_template("{{a}}-{{b}}", {"a": "x", "b": 2}) == "x-2"
    assert render_template("{{ a }}", {"a": {"z": 1}}) == '{"z": 1}'
    with pytest.raises(ValueError):
        render_template("{{missing}}", {"a": 1})

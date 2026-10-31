"""Graph runtime — the compiler: structure, modes and the permission envelope."""

from __future__ import annotations

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, PortDef, PortType, SideEffect, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeDef, NodeRegistry


def _node(node_id, node_type, config=None, version="1.0.0"):
    return {"id": node_id, "type": node_type, "version": version, "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _ir(nodes, edges=None, *, mode="research", required=None):
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_test", "name": "Test",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges or [],
        "settings": {"executionMode": mode, "failFast": False, "maxConcurrency": 2, "timeoutMs": 0},
        "requiredCapabilities": required or [],
    })


def _codes(plan):
    return [d.code for d in plan.diagnostics]


REGISTRY = build_default_registry()


def test_blank_graph_compiles_into_layers():
    ir = _ir(
        [_node("trig", "trigger.manual"), _node("out", "output.result")],
        [_edge("e1", "trig", "start", "out", "value")],
    )
    plan = compile_workflow(ir, REGISTRY)
    assert plan.executable is True
    assert plan.diagnostics == []
    assert plan.layers == [["trig"], ["out"]]
    assert plan.order == ["trig", "out"]
    assert plan.nodes[1].layer == 1
    assert plan.test_run is True


def test_independent_nodes_land_in_the_same_layer():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("f1", "transform.formula", {"expression": "1"}),
            _node("f2", "transform.formula", {"expression": "2"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "f1", "x"),
            _edge("e2", "trig", "start", "f2", "x"),
            _edge("e3", "f1", "result", "out", "value"),
        ],
    )
    plan = compile_workflow(ir, REGISTRY)
    assert plan.executable is True
    assert plan.layers[0] == ["trig"]
    assert plan.layers[1] == ["f1", "f2"]  # parallelizable
    assert "undeclared_capability" in _codes(plan)  # compute.safe not declared on the IR


def test_incompatible_ports_are_rejected():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("f", "transform.formula"),
            _node("p", "data.json.parse"),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "f", "x"),
            _edge("e2", "f", "result", "p", "text"),   # number → string
            _edge("e3", "p", "value", "out", "value"),
        ],
    )
    plan = compile_workflow(ir, REGISTRY)
    assert plan.executable is False
    assert "incompatible_ports" in _codes(plan)


def test_missing_required_input_is_reported():
    ir = _ir([_node("trig", "trigger.manual"), _node("out", "output.result")], [])
    plan = compile_workflow(ir, REGISTRY)
    codes = _codes(plan)
    assert "missing_required_input" in codes
    assert "missing_terminal" not in codes  # the terminal exists, it is just unlinked


def test_cycles_are_rejected():
    ir = _ir(
        [_node("a", "logic.merge"), _node("b", "logic.merge")],
        [
            _edge("e1", "a", "value", "b", "a"),
            _edge("e2", "b", "value", "a", "a"),
        ],
    )
    plan = compile_workflow(ir, REGISTRY)
    assert plan.executable is False
    assert "illegal_cycle" in _codes(plan)


def test_missing_trigger_and_terminal():
    ir = _ir([_node("f", "transform.formula")], [])
    codes = _codes(compile_workflow(ir, REGISTRY))
    assert "missing_trigger" in codes
    assert "missing_terminal" in codes


def test_duplicate_node_and_edge_ids():
    ir = _ir(
        [_node("x", "trigger.manual"), _node("x", "trigger.manual"), _node("out", "output.result")],
        [
            _edge("e", "x", "start", "out", "value"),
            _edge("e", "x", "start", "out", "value"),
        ],
    )
    codes = _codes(compile_workflow(ir, REGISTRY))
    assert "duplicate_node_id" in codes
    assert "duplicate_edge_id" in codes


def test_unknown_node_type_and_bad_config():
    ir = _ir(
        [_node("trig", "trigger.manual"), _node("nope", "does.not.exist"), _node("f", "transform.formula", {"expression": "x" * 500})],
        [],
    )
    codes = _codes(compile_workflow(ir, REGISTRY))
    assert "missing_node_type" in codes
    assert "invalid_config" in codes


def test_test_run_denies_effects_and_names_the_phase():
    ir = _ir(
        [_node("trig", "trigger.manual"), _node("http", "integration.http"), _node("agent", "agent.research")],
        [],
    )
    plan = compile_workflow(ir, REGISTRY, RunGrants(test_run=True))
    messages = " ".join(d.message for d in plan.diagnostics)
    codes = _codes(plan)
    assert plan.executable is False
    assert "permission_denied" in codes          # the HTTP node is network
    # Both nodes are executable; the test-run envelope refuses the HTTP node by
    # effect. The agent node is a MODEL effect and is allowed in a dry run.
    assert "executor_unavailable" not in codes
    assert "network" in messages
    assert not any(
        d.code == "permission_denied" and d.node_id == "agent" for d in plan.diagnostics
    )


def test_capability_is_required_for_effectful_nodes():
    ir = _ir([_node("trig", "trigger.manual"), _node("mkt", "finance.market_data")], [])
    denied = compile_workflow(ir, REGISTRY, RunGrants(test_run=False, granted_capabilities=frozenset()))
    assert "capability_denied" in _codes(denied)
    granted = compile_workflow(
        ir, REGISTRY,
        RunGrants(test_run=False, granted_capabilities=frozenset({"market.read"}), allow_network=True),
    )
    assert "capability_denied" not in _codes(granted)


def test_mode_is_enforced_from_a_custom_registry():
    registry = NodeRegistry()
    registry.register(NodeDef(
        type="trigger.manual", version="1.0.0", label="Trigger", category="trigger",
        outputs=(PortDef(id="start", name="Start", type=PortType.ANY),),
        allowed_modes=tuple(ExecutionMode), executor=lambda _ctx: {"start": None},
    ))
    registry.register(NodeDef(
        type="broker.order", version="1.0.0", label="Place order", category="output",
        inputs=(PortDef(id="value", name="Value", type=PortType.ANY),),
        side_effects=SideEffect.TRADING, allowed_modes=(ExecutionMode.PAPER, ExecutionMode.LIVE),
        terminal=True, executor=lambda _ctx: {},
    ))
    ir = _ir([_node("trig", "trigger.manual"), _node("ord", "broker.order")],
             [_edge("e1", "trig", "start", "ord", "value")], mode="research")
    codes = _codes(compile_workflow(ir, registry))
    assert "invalid_execution_mode" in codes
    assert "permission_denied" in codes  # trading is never authorized by default

    paper = _ir([_node("trig", "trigger.manual"), _node("ord", "broker.order")],
                [_edge("e1", "trig", "start", "ord", "value")], mode="paper")
    plan = compile_workflow(paper, registry, RunGrants(test_run=False, allow_trading=True))
    assert "invalid_execution_mode" not in _codes(plan)
    assert "permission_denied" not in _codes(plan)
    assert plan.executable is True


def test_unsupported_ir_version_is_refused():
    payload = {
        "irVersion": 99, "id": "wf", "name": "x",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [], "edges": [],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    }
    plan = compile_workflow(WorkflowIR.model_validate(payload), REGISTRY)
    assert "unsupported_ir_version" in _codes(plan)
    assert plan.executable is False

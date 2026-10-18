"""Graph runtime — Phase 4 control flow: gates, switch, loop primitives, stop,
wait bounds and the required-control-input rule."""

from __future__ import annotations

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.model import NodeStatus, PortDef, PortType, RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeDef

REGISTRY = build_default_registry()


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _ir(nodes, edges):
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_flow", "name": "Flow",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    })


def _run(ir, registry=REGISTRY, grants=None):
    plan = compile_workflow(ir, registry, grants)
    assert plan.executable, [d.message for d in plan.diagnostics]
    return GraphExecutor(ir, plan, registry, run_id="grun_flow").execute()


def _by_node(run):
    return {r.node_id: r for r in run.node_runs}


def test_if_else_gates_only_the_taken_branch():
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "yes"}),
            _node("cond", "logic.condition", {"operator": "eq", "compareTo": "yes"}),
            _node("takenGate", "flow.gate"),
            _node("skippedGate", "flow.gate"),
            _node("taken", "output.result", {"label": "taken"}),
            _node("skipped", "output.result", {"label": "skipped"}),
        ],
        [
            _edge("e1", "trig", "start", "cond", "value"),
            _edge("e2", "cond", "true", "takenGate", "in"),
            _edge("e3", "cond", "false", "skippedGate", "in"),
            _edge("e4", "trig", "start", "takenGate", "value"),
            _edge("e5", "trig", "start", "skippedGate", "value"),
            _edge("e6", "takenGate", "value", "taken", "value"),
            _edge("e7", "skippedGate", "value", "skipped", "value"),
        ],
    )
    run = _run(ir)
    nodes = _by_node(run)
    assert run.status == RunStatus.SUCCEEDED
    assert nodes["cond"].outputs["result"] is True
    assert nodes["takenGate"].status == NodeStatus.SUCCEEDED
    assert nodes["skippedGate"].status == NodeStatus.SKIPPED
    assert nodes["skippedGate"].error_code == "control_not_fired"
    assert nodes["taken"].status == NodeStatus.SUCCEEDED
    assert nodes["taken"].inputs["value"] == "yes"
    assert nodes["skipped"].status == NodeStatus.SKIPPED


def test_switch_fires_matched_and_reports_the_case():
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "b"}),
            _node("sw", "logic.switch", {"cases": "a, b, c"}),
            _node("onMatch", "flow.gate"),
            _node("onDefault", "flow.gate"),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "sw", "value"),
            _edge("e2", "sw", "matched", "onMatch", "in"),
            _edge("e3", "sw", "default", "onDefault", "in"),
            _edge("e4", "sw", "caseIndex", "out", "value"),
            _edge("e5", "trig", "start", "onMatch", "value"),
        ],
    )
    run = _run(ir)
    nodes = _by_node(run)
    assert run.status == RunStatus.SUCCEEDED
    assert nodes["sw"].outputs["caseIndex"] == 1
    assert nodes["onMatch"].status == NodeStatus.SUCCEEDED
    assert nodes["onDefault"].status == NodeStatus.SKIPPED
    assert nodes["out"].inputs["value"] == 1


def test_map_filter_reduce_are_bounded_and_deterministic():
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "[1, 2, 3, 4]"}),
            _node("parse", "data.json.parse"),
            _node("mapped", "logic.map", {"expression": "value * value"}),
            _node("kept", "logic.filter", {"expression": "value > 4"}),
            _node("sum", "logic.reduce", {"expression": "acc + value", "initial": 0}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "parse", "text"),
            _edge("e2", "parse", "value", "mapped", "items"),
            _edge("e3", "mapped", "items", "kept", "items"),
            _edge("e4", "kept", "items", "sum", "items"),
            _edge("e5", "sum", "value", "out", "value"),
        ],
    )
    run = _run(ir)
    nodes = _by_node(run)
    assert run.status == RunStatus.SUCCEEDED
    assert nodes["mapped"].outputs["items"] == [1.0, 4.0, 9.0, 16.0]
    assert nodes["kept"].outputs["items"] == [9.0, 16.0]
    assert nodes["kept"].outputs["dropped"] == 2
    assert nodes["sum"].outputs["value"] == 25.0


def test_stop_ends_the_run_and_skips_downstream():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("stop", "logic.stop", {"message": "enough"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "stop", "stopped", "out", "value"),
        ],
    )
    run = _run(ir)
    nodes = _by_node(run)
    assert run.status == RunStatus.SUCCEEDED
    assert nodes["stop"].status == NodeStatus.SUCCEEDED
    assert nodes["out"].status == NodeStatus.SKIPPED
    assert any(e.kind == "run.stopped" for e in run.events)


def test_test_run_tightens_the_wait_bound():
    ir = _ir(
        [_node("trig", "trigger.manual"), _node("wait", "logic.wait", {"ms": 20_000}), _node("out", "output.result")],
        [_edge("e1", "wait", "waitedMs", "out", "value")],
    )
    plan = compile_workflow(ir, REGISTRY, RunGrants(test_run=True))
    assert plan.executable is False
    assert [d.code for d in plan.diagnostics].count("test_run_limit") == 1
    # The same graph is fine outside a test run.
    assert compile_workflow(ir, REGISTRY, RunGrants(test_run=False)).executable is True


def test_wait_actually_waits_a_bounded_time():
    ir = _ir(
        [_node("trig", "trigger.manual"), _node("wait", "logic.wait", {"ms": 20}), _node("out", "output.result")],
        [_edge("e1", "wait", "waitedMs", "out", "value")],
    )
    run = _run(ir)
    assert run.status == RunStatus.SUCCEEDED
    assert _by_node(run)["wait"].outputs["waitedMs"] == 20


def test_gate_requires_its_control_input():
    ir = _ir(
        [_node("trig", "trigger.manual"), _node("gate", "flow.gate"), _node("out", "output.result")],
        [_edge("e1", "trig", "start", "gate", "value"), _edge("e2", "gate", "value", "out", "value")],
    )
    plan = compile_workflow(ir, REGISTRY)
    assert plan.executable is False
    codes = [d.code for d in plan.diagnostics]
    assert "missing_required_input" in codes


def test_loop_primitives_are_bounded():
    registry = build_default_registry()
    registry.register(NodeDef(
        type="test.big_array", version="1.0.0", label="Big array", category="data",
        outputs=(PortDef(id="items", name="Items", type=PortType.ARRAY),),
        executor=lambda _ctx: {"items": list(range(10_001))},
    ))
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("big", "test.big_array"),
            _node("mapped", "logic.map", {"expression": "value + 1"}),
            _node("out", "output.result"),
        ],
        [_edge("e1", "mapped", "items", "out", "value"), _edge("e2", "big", "items", "mapped", "items")],
    )
    run = _run(ir, registry)
    assert run.status == RunStatus.FAILED
    assert "bounded to" in (_by_node(run)["mapped"].error or "")


def test_loop_primitives_reject_non_numeric_arrays():
    registry = build_default_registry()
    registry.register(NodeDef(
        type="test.text_array", version="1.0.0", label="Text array", category="data",
        outputs=(PortDef(id="items", name="Items", type=PortType.ARRAY),),
        executor=lambda _ctx: {"items": ["a", "b"]},
    ))
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("text", "test.text_array"),
            _node("mapped", "logic.map", {"expression": "value + 1"}),
            _node("out", "output.result"),
        ],
        [_edge("e1", "mapped", "items", "out", "value"), _edge("e2", "text", "items", "mapped", "items")],
    )
    run = _run(ir, registry)
    assert run.status == RunStatus.FAILED
    assert "numeric arrays" in (_by_node(run)["mapped"].error or "")

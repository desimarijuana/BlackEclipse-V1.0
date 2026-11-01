"""Remaining logic-pack behaviour: switch routing, gate AND, dedupe modes, loop scope."""

from __future__ import annotations

import pytest

from harness.graph_runtime.compiler import compile_workflow
from harness.graph_runtime.executor import GraphExecutor, _loop_scope
from harness.graph_runtime.model import ExecutionMode, NodeStatus, RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()


def _exec(node_type: str, inputs: dict, config: dict | None = None, **context) -> dict:
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs, config=config or {}, **context,
    ))


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _run(nodes, edges):
    ir = WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_logic_pack", "name": "Logic pack",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": [],
    })
    plan = compile_workflow(ir, REGISTRY)
    assert plan.executable, [d.message for d in plan.diagnostics]
    return GraphExecutor(ir, plan, REGISTRY, run_id="grun_logic").execute()


# ── D7: switch routes to a per-case output ──────────────────────────────────

def test_switch_fires_matched_and_the_matching_case_output():
    result = _exec("logic.switch", {"value": "b"}, {"cases": "a, b, c"})
    assert result["caseIndex"] == 1
    assert result["_control"] == ["matched", "case2"]


def test_switch_case_outputs_stop_at_eight():
    cases = ", ".join(str(index) for index in range(1, 11))
    result = _exec("logic.switch", {"value": "9"}, {"cases": cases})
    assert result["caseIndex"] == 8
    # Case 9 has no declared output; `matched` alone still routes legacy graphs.
    assert result["_control"] == ["matched"]


def test_switch_default_when_nothing_matches():
    result = _exec("logic.switch", {"value": "z"}, {"cases": "a, b"})
    assert result["caseIndex"] == -1
    assert result["_control"] == ["default"]


# ── flow.gate `require: all` is a join ──────────────────────────────────────

def test_gate_all_skips_when_a_wired_input_did_not_fire():
    result = _exec("flow.gate", {"value": 1}, {"require": "all"},
                   control_fired={"in": True, "in2": False})
    assert result["_skip"].startswith("not all control inputs fired")
    assert "in2" in result["_skip"]


def test_gate_all_passes_when_every_wired_input_fired():
    result = _exec("flow.gate", {"value": 1}, {"require": "all"},
                   control_fired={"in": True, "in2": True})
    assert result["_control"] == ["done"]


def test_gate_any_is_unchanged():
    result = _exec("flow.gate", {"value": 1}, {"require": "any"},
                   control_fired={"in": True, "in2": False})
    assert result["_control"] == ["done"]


def test_gate_all_marks_the_node_skipped_in_a_run():
    nodes = [
        _node("trig", "trigger.manual"),
        _node("v", "data.value", {"dataType": "number", "value": "5"}),
        _node("yes", "logic.condition", {"operator": "gt", "compareTo": "1"}),
        _node("no", "logic.condition", {"operator": "gt", "compareTo": "100"}),
        _node("gate", "flow.gate", {"require": "all"}),
        _node("out", "output.result"),
    ]
    edges = [
        _edge("e1", "trig", "start", "v", "in"),
        _edge("e2", "v", "value", "yes", "value"),
        _edge("e3", "v", "value", "no", "value"),
        _edge("e4", "yes", "true", "gate", "in"),
        _edge("e5", "no", "true", "gate", "in2"),
        _edge("e6", "v", "value", "gate", "value"),
        _edge("e7", "gate", "value", "out", "value"),
    ]
    run = _run(nodes, edges)
    records = {record.node_id: record for record in run.node_runs}
    assert records["gate"].status == NodeStatus.SKIPPED
    assert records["gate"].error_code == "skipped_by_node"
    assert records["out"].status == NodeStatus.SKIPPED


# ── deduplicate keep modes ──────────────────────────────────────────────────

def test_deduplicate_keep_last_and_case_insensitive():
    rows = [{"symbol": "AAPL", "v": 1}, {"symbol": "aapl", "v": 2}]
    exact = _exec("logic.deduplicate", {"items": rows}, {"keys": "symbol"})
    # Text keys compare exactly unless caseInsensitive is on.
    assert exact["items"] == rows
    assert exact["dropped"] == 0

    folded = _exec("logic.deduplicate", {"items": rows},
                   {"keys": "symbol", "caseInsensitive": True, "keep": "last"})
    assert folded["items"] == [{"symbol": "aapl", "v": 2}]
    assert folded["dropped"] == 1


def test_deduplicate_refuses_an_unknown_keep_policy():
    with pytest.raises(ValueError, match="keep policy"):
        _exec("logic.deduplicate", {"items": [{"a": 1}]}, {"keys": "a", "keep": "middle"})


# ── D8: a loop condition can read an object state ───────────────────────────

def test_loop_scope_exposes_object_fields_and_booleans():
    scope = _loop_scope({"done": True, "value": 3}, 0)
    assert scope["done"] == 1.0
    assert scope["value"] == 3.0
    assert scope["index"] == 0.0


def test_loop_scope_keeps_the_legacy_numeric_projection():
    assert _loop_scope(7, 2)["value"] == 7.0
    # An object with no numeric projection still exposes `value` (legacy),
    # but now also exposes its own boolean fields (`done`).
    scope = _loop_scope({"done": True}, 4)
    assert scope["done"] == 1.0
    assert scope["value"] == 0.0
    assert scope["iterations"] == 4.0

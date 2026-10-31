"""Per-port literal values (IR v2).

A node can carry a literal for an input port so the step is usable without a
producer wire. The rules are deliberately narrow:

* a literal satisfies a REQUIRED DATA input for validation/compilation;
* a connected wire always wins over the literal;
* CONTROL inputs never take a literal (they gate execution, not values);
* the value is persisted in the IR as ``inputValues`` (alias of input_values).
"""

from __future__ import annotations

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.model import NodeStatus, RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry


def _node(node_id: str, node_type: str, config: dict | None = None, input_values: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "version": "1.0.0",
        "config": config or {},
        "inputValues": input_values or {},
        "layout": {"x": 0, "y": 0},
    }


def _edge(edge_id: str, source: str, source_handle: str, target: str, target_handle: str) -> dict:
    return {
        "id": edge_id,
        "source": source,
        "sourceHandle": source_handle,
        "target": target,
        "targetHandle": target_handle,
    }


def _ir(nodes: list[dict], edges: list[dict]) -> WorkflowIR:
    return WorkflowIR.model_validate({
        "irVersion": 2,
        "id": "wf_literals",
        "name": "Literals",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes,
        "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
    })


def _run(ir: WorkflowIR, run_input=None):
    registry = build_default_registry()
    plan = compile_workflow(ir, registry, RunGrants(test_run=True))
    assert plan.executable, [d.message for d in plan.diagnostics]
    run = GraphExecutor(ir, plan, registry, run_id="grun_literals", run_input=run_input).execute()
    return run, {record.node_id: record for record in run.node_runs}


def test_required_input_is_satisfied_by_a_literal():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("parse", "data.json.parse", {"strict": True}, {"text": '{"a": 1}'}),
            _node("out", "output.result"),
        ],
        [_edge("e1", "parse", "value", "out", "value")],
    )
    run, by_id = _run(ir)
    assert run.status == RunStatus.SUCCEEDED
    assert by_id["parse"].status == NodeStatus.SUCCEEDED
    assert by_id["parse"].outputs["value"] == {"a": 1}
    assert by_id["out"].inputs["value"] == {"a": 1}


def test_a_wire_wins_over_the_literal():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("parse", "data.json.parse", {"strict": True}, {"text": '{"literal": true}'}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "parse", "text"),
            _edge("e2", "parse", "value", "out", "value"),
        ],
    )
    run, by_id = _run(ir, run_input='{"wire": true}')
    assert run.status == RunStatus.SUCCEEDED
    assert by_id["parse"].outputs["value"] == {"wire": True}


def test_false_and_null_literals_are_present_values():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("parse", "data.json.parse", {"strict": True}, {"text": "null"}),
            _node("out", "output.result"),
        ],
        [_edge("e1", "parse", "value", "out", "value")],
    )
    run, by_id = _run(ir)
    assert run.status == RunStatus.SUCCEEDED
    assert by_id["parse"].outputs["value"] is None


def test_compiler_accepts_a_config_fallback_for_parse_json():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("parse", "data.json.parse", {"text": '{"from": "config"}', "strict": True}),
            _node("out", "output.result"),
        ],
        [_edge("e1", "parse", "value", "out", "value")],
    )
    registry = build_default_registry()
    plan = compile_workflow(ir, registry, RunGrants(test_run=True))
    assert plan.executable, [d.message for d in plan.diagnostics]
    run = GraphExecutor(ir, plan, registry, run_id="grun_config_fallback").execute()
    by_id = {record.node_id: record for record in run.node_runs}
    assert run.status == RunStatus.SUCCEEDED
    assert by_id["parse"].outputs["value"] == {"from": "config"}


def test_compiler_does_not_accept_a_literal_for_a_control_input():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("gate", "flow.gate", input_values={"in": True}),
            _node("out", "output.result"),
        ],
        [],
    )
    plan = compile_workflow(ir, build_default_registry(), RunGrants(test_run=True))
    assert plan.executable is False
    assert "missing_required_input" in {d.code for d in plan.diagnostics}


def test_ir_v1_still_parses_without_input_values():
    ir = WorkflowIR.model_validate({
        "irVersion": 1,
        "id": "wf_v1",
        "name": "V1",
        "nodes": [{"id": "n", "type": "trigger.manual", "version": "1.0.0", "config": {}, "layout": {"x": 0, "y": 0}}],
        "edges": [],
    })
    assert ir.nodes[0].input_values == {}

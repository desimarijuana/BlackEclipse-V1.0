"""Bounded loop nodes (Phase 4): for_each / repeat / while + checkpoint reuse."""

from __future__ import annotations

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.model import NodeStatus, RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry

REGISTRY = build_default_registry()


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {
        "id": node_id, "type": node_type, "version": "1.0.0",
        "config": config or {}, "layout": {"x": 0, "y": 0},
    }


def _edge(edge_id: str, source: str, source_handle: str, target: str, target_handle: str) -> dict:
    return {
        "id": edge_id, "source": source, "sourceHandle": source_handle,
        "target": target, "targetHandle": target_handle,
    }


def _ir(workflow_id: str, nodes: list[dict], edges: list[dict]) -> WorkflowIR:
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": workflow_id, "name": workflow_id,
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 2, "timeoutMs": 0},
        "requiredCapabilities": [],
    })


def _passthrough_body() -> WorkflowIR:
    return _ir("wf_body", [
        _node("trig", "trigger.manual"),
        _node("out", "output.result"),
    ], [_edge("e1", "trig", "start", "out", "value")])


def _increment_body() -> WorkflowIR:
    return _ir("wf_inc", [
        _node("trig", "trigger.manual"),
        _node("inc", "transform.formula", {"expression": "x + 1"}),
        _node("out", "output.result"),
    ], [
        _edge("e1", "trig", "start", "inc", "x"),
        _edge("e2", "inc", "result", "out", "value"),
    ])


def _for_each_parent(body_id: str = "wf_body") -> WorkflowIR:
    return _ir("wf_loop", [
        _node("trig", "trigger.manual", {"seed": "[1,2,3]"}),
        _node("value", "data.value", {"dataType": "array", "value": ""}),
        _node("loop", "flow.for_each", {"workflowId": body_id, "version": 1, "maxIterations": 10}),
        _node("out", "output.result"),
    ], [
        _edge("e1", "trig", "start", "value", "in"),
        _edge("e2", "value", "value", "loop", "items"),
        _edge("e3", "loop", "results", "out", "value"),
    ])


def _state_parent(node_type: str, config: dict) -> WorkflowIR:
    return _ir("wf_loop", [
        _node("trig", "trigger.manual", {"seed": "0"}),
        _node("value", "data.value", {"dataType": "number", "value": "0"}),
        _node("loop", node_type, config),
        _node("out", "output.result"),
    ], [
        _edge("e1", "trig", "start", "value", "in"),
        _edge("e2", "value", "value", "loop", "input"),
        _edge("e3", "loop", "state", "out", "value"),
    ])


def _run(parent: WorkflowIR, bundle: dict, *, run_id="grun_loop", loader=None):
    plan = compile_workflow(parent, REGISTRY, RunGrants(test_run=True), bundle)
    assert plan.executable, [d.message for d in plan.diagnostics]
    return GraphExecutor(
        parent, plan, REGISTRY, run_id=run_id,
        subworkflows=bundle, load_child_run=loader,
    ).execute()


def test_for_each_runs_the_body_once_per_item():
    run = _run(_for_each_parent(), {"wf_body@1": _passthrough_body()})
    assert run.status == RunStatus.SUCCEEDED
    loop = next(record for record in run.node_runs if record.node_id == "loop")
    assert loop.status == NodeStatus.SUCCEEDED
    assert loop.outputs["results"] == [1, 2, 3]
    assert loop.outputs["iterations"] == 3
    assert loop.outputs["stopped"] is False


def test_for_each_stops_at_the_iteration_cap():
    parent = _for_each_parent()
    loop_node = next(node for node in parent.nodes if node.id == "loop")
    loop_node.config["maxIterations"] = 2
    run = _run(parent, {"wf_body@1": _passthrough_body()})
    loop = next(record for record in run.node_runs if record.node_id == "loop")
    assert loop.outputs["results"] == [1, 2]
    assert loop.outputs["iterations"] == 2
    assert loop.outputs["stopped"] is True


def test_repeat_passes_the_previous_output_on():
    run = _run(
        _state_parent("flow.repeat", {"workflowId": "wf_inc", "version": 1, "count": 3}),
        {"wf_inc@1": _increment_body()},
    )
    loop = next(record for record in run.node_runs if record.node_id == "loop")
    assert loop.outputs["state"] == 3
    assert loop.outputs["iterations"] == 3


def test_while_stops_when_the_condition_becomes_false():
    run = _run(
        _state_parent("flow.while", {
            "workflowId": "wf_inc", "version": 1,
            "condition": "value < 3", "maxIterations": 100,
        }),
        {"wf_inc@1": _increment_body()},
    )
    loop = next(record for record in run.node_runs if record.node_id == "loop")
    assert loop.outputs["state"] == 3
    assert loop.outputs["iterations"] == 3
    assert loop.outputs["stopped"] is False


def test_a_succeeded_iteration_checkpoint_is_reused():
    def loader(child_run_id: str):
        if child_run_id.endswith(":loop:i0"):
            return {"status": "succeeded", "output": 99}
        return None

    run = _run(
        _for_each_parent(), {"wf_body@1": _passthrough_body()}, loader=loader,
    )
    loop = next(record for record in run.node_runs if record.node_id == "loop")
    assert loop.outputs["results"][0] == 99
    assert loop.outputs["results"][1:] == [2, 3]


def test_a_loop_without_a_pinned_body_is_invalid():
    parent = _for_each_parent()
    loop_node = next(node for node in parent.nodes if node.id == "loop")
    loop_node.config["workflowId"] = ""
    plan = compile_workflow(parent, REGISTRY, RunGrants(test_run=True), {})
    assert plan.executable is False
    assert any(d.code == "invalid_subworkflow" for d in plan.diagnostics)

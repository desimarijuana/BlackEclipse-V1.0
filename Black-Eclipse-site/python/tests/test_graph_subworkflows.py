"""Subworkflow nodes: pinned nested runs, input delivery, terminal output,
same-grants authority, cycle/depth refusal.
"""

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


def _child(workflow_id: str = "wf_child", *, nested: tuple[str, int] | None = None) -> WorkflowIR:
    nodes = [_node("trig", "trigger.manual"), _node("out", "output.result", {"label": "Out"})]
    edges = [_edge("e1", "trig", "start", "out", "value")]
    if nested is not None:
        nodes.append(_node("sub", "flow.subworkflow", {"workflowId": nested[0], "version": nested[1]}))
        edges.append(_edge("e2", "trig", "start", "sub", "input"))
        edges.append(_edge("e3", "sub", "output", "out", "value"))
    return _ir(workflow_id, nodes, edges)


def _main(workflow_id: str, child_id: str = "wf_child", version: int = 1) -> WorkflowIR:
    return _ir(workflow_id, [
        _node("trig", "trigger.manual"),
        _node("sub", "flow.subworkflow", {"workflowId": child_id, "version": version}),
        _node("out", "output.result", {"label": "Main out"}),
    ], [
        _edge("e1", "trig", "start", "sub", "input"),
        _edge("e2", "sub", "output", "out", "value"),
    ])


def test_subworkflow_delivers_input_and_returns_terminal_output():
    child = _child()
    main = _main("wf_main")
    bundle = {"wf_child@1": child}
    plan = compile_workflow(main, REGISTRY, RunGrants(test_run=True), bundle)
    assert plan.executable, [d.message for d in plan.diagnostics]

    run = GraphExecutor(
        main, plan, REGISTRY, run_id="grun_main",
        subworkflows=bundle, run_input={"symbol": "AAPL"},
    ).execute()
    assert run.status == RunStatus.SUCCEEDED
    assert run.output == {"symbol": "AAPL"}
    by_id = {record.node_id: record for record in run.node_runs}
    assert by_id["sub"].status == NodeStatus.SUCCEEDED
    assert "output" in by_id["sub"].outputs
    assert "runId" in by_id["sub"].outputs
    assert any(event.kind == "subworkflow.event" for event in run.events)


def test_a_nested_run_gets_its_own_durable_row(tmp_path):
    from harness.graph_runtime.service import GraphService
    from harness.graph_runtime.store import GraphRunStore
    from harness.persistence import AgentMemoryStore

    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    service = GraphService(GraphRunStore(memory))
    try:
        run = service.run_sync(_main("wf_main"), subworkflows={"wf_child@1": _child()})
        assert run.status == RunStatus.SUCCEEDED
        child = service.get_run(f"{run.id}:sub")
        assert child is not None
        assert child["workflowId"] == "wf_child"
        assert child["status"] == "succeeded"
        assert any(node["nodeId"] == "out" for node in child["nodeRuns"])
        assert any(event["kind"] == "run.succeeded" for event in child["events"])
    finally:
        memory.close()


def test_missing_subworkflow_is_a_compile_error():
    plan = compile_workflow(_main("wf_main"), REGISTRY, RunGrants(test_run=True), {})
    assert plan.executable is False
    assert "missing_subworkflow" in [d.code for d in plan.diagnostics]


def test_subworkflow_cycle_is_refused():
    cycle = _child("wf_cycle", nested=("wf_cycle", 1))
    plan = compile_workflow(
        _main("wf_main", "wf_cycle"), REGISTRY, RunGrants(test_run=True),
        {"wf_cycle@1": cycle},
    )
    assert plan.executable is False
    assert "subworkflow_cycle" in [d.code for d in plan.diagnostics]


def test_subworkflow_depth_is_bounded():
    bundle = {}
    for index in range(7):
        next_ref = (f"wf_{index + 1}", 1) if index < 6 else None
        bundle[f"wf_{index}@1"] = _child(f"wf_{index}", nested=next_ref)
    plan = compile_workflow(
        _main("wf_main", "wf_0"), REGISTRY, RunGrants(test_run=True), bundle,
    )
    assert plan.executable is False
    assert "subworkflow_depth" in [d.code for d in plan.diagnostics]


def test_subworkflow_cannot_widen_authority():
    child = _ir("wf_http", [
        _node("trig", "trigger.manual"),
        _node("http", "integration.http", {"url": "https://example.com", "method": "GET"}),
        _node("out", "output.result"),
    ], [
        _edge("e1", "trig", "start", "http", "body"),
        _edge("e2", "http", "body", "out", "value"),
    ])
    plan = compile_workflow(
        _main("wf_main", "wf_http"), REGISTRY, RunGrants(test_run=True),
        {"wf_http@1": child},
    )
    assert plan.executable is False
    assert "subworkflow_invalid" in [d.code for d in plan.diagnostics]
    assert any("network" in d.message for d in plan.diagnostics)


def test_subworkflow_requires_a_pinned_version():
    plan = compile_workflow(_main("wf_main", version=0), REGISTRY, RunGrants(test_run=True), {})
    assert "invalid_subworkflow" in [d.code for d in plan.diagnostics]

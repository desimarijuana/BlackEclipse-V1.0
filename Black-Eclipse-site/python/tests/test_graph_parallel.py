"""flow.parallel: bounded concurrent map over a pinned body workflow."""

from __future__ import annotations

import time

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.executor import GraphExecutor, parallel_workers
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


def _ir(workflow_id: str, nodes: list[dict], edges: list[dict], *, max_concurrency: int = 4) -> WorkflowIR:
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": workflow_id, "name": workflow_id,
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {
            "executionMode": "research", "failFast": False,
            "maxConcurrency": max_concurrency, "timeoutMs": 0,
        },
        "requiredCapabilities": [],
    })


def _double_body() -> WorkflowIR:
    return _ir("wf_double", [
        _node("trig", "trigger.manual"),
        _node("double", "transform.formula", {"expression": "x * 2"}),
        _node("out", "output.result"),
    ], [
        _edge("e1", "trig", "start", "double", "x"),
        _edge("e2", "double", "result", "out", "value"),
    ])


def _assert_body() -> WorkflowIR:
    """Fails for a falsy item — proves per-item failure is data."""
    return _ir("wf_assert", [
        _node("trig", "trigger.manual"),
        _node("check", "logic.assert", {"expect": "truthy", "message": "item is falsy"}),
        _node("out", "output.result"),
    ], [
        _edge("e1", "trig", "start", "check", "value"),
        _edge("e2", "check", "value", "out", "value"),
    ])


def _parent(body_id: str, config: dict | None = None, seed: str = "[1,2,3]") -> WorkflowIR:
    return _ir("wf_par", [
        _node("trig", "trigger.manual", {"seed": seed}),
        _node("value", "data.value", {"dataType": "array", "value": ""}),
        _node("par", "flow.parallel", {"workflowId": body_id, "version": 1, **(config or {})}),
        _node("out", "output.result"),
    ], [
        _edge("e1", "trig", "start", "value", "in"),
        _edge("e2", "value", "value", "par", "items"),
        _edge("e3", "par", "results", "out", "value"),
    ])


def _run(parent: WorkflowIR, bundle: dict, *, run_id: str = "grun_par", loader=None):
    plan = compile_workflow(parent, REGISTRY, RunGrants(test_run=True), bundle)
    assert plan.executable, [d.message for d in plan.diagnostics]
    return GraphExecutor(
        parent, plan, REGISTRY, run_id=run_id,
        subworkflows=bundle, load_child_run=loader,
    ).execute()


def _par(run):
    return next(record for record in run.node_runs if record.node_id == "par")


def test_parallel_maps_every_item_and_keeps_input_order():
    run = _run(_parent("wf_double"), {"wf_double@1": _double_body()})
    assert run.status == RunStatus.SUCCEEDED
    record = _par(run)
    assert record.status == NodeStatus.SUCCEEDED
    assert record.outputs["results"] == [2, 4, 6]
    assert record.outputs["summary"]["total"] == 3
    assert record.outputs["summary"]["succeeded"] == 3
    assert record.outputs["summary"]["failed"] == 0
    assert record.outputs["summary"]["concurrency"] == 3  # min(config 4, plan 4, items 3)


def test_a_failed_item_is_data_with_continue_on_error():
    run = _run(_parent("wf_assert", {"continueOnError": True}, seed="[1,0,3]"),
               {"wf_assert@1": _assert_body()})
    assert run.status == RunStatus.SUCCEEDED
    record = _par(run)
    results = record.outputs["results"]
    assert results[0] == 1
    assert "error" in results[1] and "item is falsy" in results[1]["error"]
    assert results[2] == 3
    assert record.outputs["summary"]["failed"] == 1
    assert record.outputs["summary"]["succeeded"] == 2
    assert record.outputs["summary"]["failures"][0]["index"] == 1


def test_a_failed_item_fails_the_node_when_continue_on_error_is_off():
    run = _run(_parent("wf_assert", {"continueOnError": False}, seed="[1,0,3]"),
               {"wf_assert@1": _assert_body()})
    assert run.status == RunStatus.FAILED
    record = _par(run)
    assert record.status == NodeStatus.FAILED
    assert "parallel item 1 failed" in (record.error or "")


def test_max_items_truncates_and_reports_it():
    run = _run(_parent("wf_double", {"maxItems": 2}), {"wf_double@1": _double_body()})
    record = _par(run)
    assert record.outputs["results"] == [2, 4]
    assert record.outputs["summary"]["truncated"] is True


def test_an_empty_item_list_succeeds_with_no_runs():
    run = _run(_parent("wf_double", seed="[]"), {"wf_double@1": _double_body()})
    assert run.status == RunStatus.SUCCEEDED
    assert _par(run).outputs["results"] == []
    assert _par(run).outputs["summary"]["total"] == 0


def test_a_missing_body_is_a_compile_error():
    plan = compile_workflow(_parent("wf_missing"), REGISTRY, RunGrants(test_run=True), {})
    assert not plan.executable
    assert any(d.code == "missing_subworkflow" for d in plan.diagnostics)


def test_a_succeeded_child_is_reused_on_a_resumed_parent():
    reused = {1: "from-the-checkpoint"}  # item index -> prior output

    class _Loader:
        def __call__(self, child_id: str):
            for index, output in reused.items():
                if child_id.endswith(f":i{index}"):
                    return {"status": "succeeded", "output": output}
            return None

    run = _run(_parent("wf_assert", {"continueOnError": True}, seed="[1,0,3]"),
               {"wf_assert@1": _assert_body()}, loader=_Loader())
    # Item 1 would FAIL (0 is falsy) but its child succeeded earlier, so the
    # resumed parent reuses it instead of re-running the body.
    assert _par(run).outputs["results"] == [1, "from-the-checkpoint", 3]
    assert _par(run).outputs["summary"]["failed"] == 0


def test_concurrency_is_capped_by_config_budget_and_a_hard_limit():
    assert parallel_workers(4, 4, 10) == 4
    assert parallel_workers(16, 4, 10) == 4      # never above the plan budget
    assert parallel_workers(4, 64, 2) == 2       # never above the item count
    assert parallel_workers(64, 64, 100) == 8    # hard cap for this machine
    assert parallel_workers(0, 4, 10) == 1
    with pytest.raises(ValueError, match="whole number"):
        parallel_workers("many", 4, 3)


def test_parallel_actually_runs_items_concurrently():
    """A body that sleeps proves more than one item is in flight at a time."""
    body = _ir("wf_sleep", [
        _node("trig", "trigger.manual"),
        _node("wait", "logic.wait", {"ms": 300}),
        _node("out", "output.result"),
    ], [
        # No control edge: `wait` has an optional control input, exactly like the
        # durable-wait test. Only the data wire matters here.
        _edge("e2", "wait", "waitedMs", "out", "value"),
    ])
    started = time.monotonic()
    run = _run(_parent("wf_sleep", {"concurrency": 3}, seed="[1,2,3]"),
               {"wf_sleep@1": body})
    elapsed = time.monotonic() - started
    assert run.status == RunStatus.SUCCEEDED
    assert _par(run).outputs["results"] == [300, 300, 300]
    # Three 300 ms waits at concurrency 3 finish well under the 900 ms serial cost.
    assert elapsed < 0.85

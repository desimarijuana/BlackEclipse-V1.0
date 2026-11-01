"""Graph runtime — Phase 4 control flow: gates, switch, loop primitives, stop,
wait bounds and the required-control-input rule."""

from __future__ import annotations

import time

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.model import (
    ExecutionMode,
    NodeStatus,
    PortDef,
    PortType,
    RunDeferred,
    RunStatus,
    WorkflowIR,
)
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeDef, NodeExecContext

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


def test_loop_primitives_bind_object_fields():
    registry = build_default_registry()
    registry.register(NodeDef(
        type="test.rows", version="1.0.0", label="Rows", category="data",
        outputs=(PortDef(id="items", name="Items", type=PortType.ARRAY),),
        executor=lambda _ctx: {"items": [
            {"open": 1.0, "close": 2.0},
            {"open": 4.0, "close": 3.0},
            {"open": 2.0, "close": 2.5},
        ]},
    ))
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("rows", "test.rows"),
            _node("mapped", "logic.map", {"expression": "close - open"}),
            _node("kept", "logic.filter", {"expression": "value > 0"}),
            _node("sum", "logic.reduce", {"expression": "acc + value", "initial": 0}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "rows", "items", "mapped", "items"),
            _edge("e2", "mapped", "items", "kept", "items"),
            _edge("e3", "kept", "items", "sum", "items"),
            _edge("e4", "sum", "value", "out", "value"),
        ],
    )
    run = _run(ir, registry)
    assert run.status == RunStatus.SUCCEEDED
    assert run.output == 1.5


def test_a_durable_wait_defers_the_run_instead_of_blocking():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("wait", "logic.wait", {"ms": 60_000}),
            _node("out", "output.result"),
        ],
        [
            _edge("e2", "wait", "waitedMs", "out", "value"),
        ],
    )
    plan = compile_workflow(ir, REGISTRY, RunGrants(test_run=False))
    assert plan.executable

    with pytest.raises(RunDeferred) as info:
        GraphExecutor(ir, plan, REGISTRY, run_id="grun_wait", allow_defer=True).execute()
    deferred = info.value
    assert deferred.run.status == RunStatus.QUEUED
    assert deferred.wake_after_seconds == 60.0
    by_node = {record.node_id: record for record in deferred.run.node_runs}
    assert by_node["wait"].status == NodeStatus.SUCCEEDED
    assert by_node["wait"].outputs == {"waitedMs": 60000}
    assert by_node["out"].status == NodeStatus.PENDING


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

# ── Wave 0 regressions ───────────────────────────────────────────────────────


def test_stop_with_failed_status_fails_the_run():
    """`status` was declared in both registries and ignored by the executor."""
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("stop", "logic.stop", {"status": "failed", "message": "guard tripped"}),
        ],
        [],
    )
    run = _run(ir)
    assert run.status == RunStatus.FAILED
    assert run.error == "guard tripped"
    # The NODE succeeded (that is what `stops_run` keys off); the RUN failed.
    assert _by_node(run)["stop"].status == NodeStatus.SUCCEEDED
    assert any(e.kind == "run.stopped" and "guard tripped" in e.message for e in run.events)


def test_stop_carries_a_value_as_the_run_output():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("val", "data.value", {"value": "done", "dataType": "string"}),
            _node("stop", "logic.stop"),
        ],
        [
            _edge("e2", "trig", "start", "val", "in"),
            _edge("e3", "val", "value", "stop", "value"),
        ],
    )
    run = _run(ir)
    assert run.status == RunStatus.SUCCEEDED
    assert run.output == "done"


def test_wait_stops_early_when_the_run_is_cancelled():
    definition = REGISTRY.get("logic.wait")
    context = NodeExecContext(
        node_id="wait", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={}, config={"ms": 5_000}, should_cancel=lambda: True,
    )
    started = time.monotonic()
    result = definition.executor(context)
    assert time.monotonic() - started < 1.0
    # Truthful: it reports what it waited, not what it was asked for.
    assert 0 <= result["waitedMs"] < 5_000


def test_a_skipped_branch_names_the_wire_that_did_not_fire():
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "no"}),
            _node("cond", "logic.condition", {"operator": "eq", "compareTo": "yes"}),
            _node("gate", "flow.gate"),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "cond", "value"),
            _edge("e2", "cond", "true", "gate", "in"),
            _edge("e3", "trig", "start", "gate", "value"),
            _edge("e4", "gate", "value", "out", "value"),
        ],
    )
    run = _run(ir)
    assert _by_node(run)["gate"].status == NodeStatus.SKIPPED
    error = _by_node(run)["gate"].error or ""
    assert "cond" in error and "did not fire" in error


def test_map_does_not_invent_zero_for_a_missing_field():
    """A row without the referenced field must fail, never read as 0."""
    definition = REGISTRY.get("logic.map")
    context = NodeExecContext(
        node_id="map", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={"items": [{"symbol": "AAPL"}]}, config={"expression": "price"},
    )
    with pytest.raises(ValueError, match="unknown name"):
        definition.executor(context)


def test_filter_on_a_text_field_does_not_silently_drop_every_row():
    definition = REGISTRY.get("logic.filter")
    context = NodeExecContext(
        node_id="filter", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={"items": [{"symbol": "AAPL"}, {"symbol": "MSFT"}]},
        config={"expression": "value"},
    )
    with pytest.raises(ValueError):
        definition.executor(context)

def test_a_branch_that_fires_into_nothing_says_so():
    """A condition whose branches are both unwired must not look like success."""
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "5"}),
            _node("cond", "logic.condition", {"operator": "eq", "compareTo": "5"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "cond", "value"),
            # The boolean is wired to the terminal, but neither BRANCH is wired.
            _edge("e2", "cond", "result", "out", "value"),
        ],
    )
    run = _run(ir)
    assert run.status == RunStatus.SUCCEEDED
    messages = [e.message for e in run.events if e.kind == "node.log"]
    assert any("fired but nothing is connected" in message for message in messages), messages


def test_an_unwired_done_is_not_reported_as_a_dead_branch():
    """`done` is a convenience control, not a choice between alternatives."""
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "1"}),
            _node("f", "transform.formula", {"expression": "x"}),
            _node("gate", "flow.gate"),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "f", "x"),
            _edge("e2", "f", "done", "gate", "in"),
            _edge("e3", "f", "result", "gate", "value"),
            _edge("e4", "gate", "value", "out", "value"),
        ],
    )
    run = _run(ir)
    messages = [e.message for e in run.events if e.kind == "node.log"]
    assert not any("fired but nothing is connected" in message for message in messages), messages

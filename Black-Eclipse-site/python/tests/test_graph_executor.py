"""Graph runtime — the deterministic executor: lifecycle, determinism, errors,
timeouts, retries, cancellation and output-schema enforcement."""

from __future__ import annotations

import threading
import time

from harness.graph_runtime.compiler import compile_workflow
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.model import NodeStatus, PortDef, PortType, RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeDef, NodeRegistry


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _ir(nodes, edges, max_concurrency=1):
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_exec", "name": "Exec",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": nodes, "edges": edges,
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": max_concurrency, "timeoutMs": 0},
        "requiredCapabilities": [],
    })


def _execute(ir, registry=None, **kwargs):
    registry = registry or build_default_registry()
    plan = compile_workflow(ir, registry)
    assert plan.executable, [d.message for d in plan.diagnostics]
    executor = GraphExecutor(ir, plan, registry, run_id="grun_test", **kwargs)
    return executor.execute()


def _status(run):
    return {r.node_id: r for r in run.node_runs}


def test_end_to_end_pure_graph():
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "3"}),
            _node("v", "data.value", {"dataType": "number", "value": "0"}),
            _node("f", "transform.formula", {"expression": "x * 2 + 1"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "f", "x"),
            _edge("e3", "f", "result", "out", "value"),
        ],
    )
    run = _execute(ir)
    assert run.status == RunStatus.SUCCEEDED
    runs = _status(run)
    assert runs["trig"].status == NodeStatus.SUCCEEDED
    assert runs["v"].outputs["value"] == 3.0  # seed string coerced by dataType
    assert runs["f"].outputs["result"] == 7.0
    assert runs["out"].inputs["value"] == 7.0
    assert all(r.duration_ms is not None for r in run.node_runs)
    assert run.plan is not None and run.plan.executable


def test_same_inputs_produce_identical_outputs():
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "2"}),
            _node("v", "data.value", {"dataType": "number", "value": "0"}),
            _node("f", "transform.formula", {"expression": "x ** 3"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "f", "x"),
            _edge("e3", "f", "result", "out", "value"),
        ],
    )
    a = _execute(ir)
    b = _execute(ir)
    assert _status(a)["out"].inputs == _status(b)["out"].inputs
    assert _status(a)["f"].outputs == _status(b)["f"].outputs


def test_json_parse_node_validates_object_output():
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": '{"a": 1}'}),
            _node("v", "data.value", {"value": "{}", "dataType": "string"}),
            _node("p", "data.json.parse"),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "p", "text"),
            _edge("e3", "p", "value", "out", "value"),
        ],
    )
    run = _execute(ir)
    assert run.status == RunStatus.SUCCEEDED
    assert _status(run)["out"].inputs["value"] == {"a": 1}


def test_condition_and_merge_routing():
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "5"}),
            _node("v", "data.value", {"value": "", "dataType": "string"}),
            _node("c", "logic.condition", {"operator": "eq", "compareTo": "5"}),
            _node("m", "logic.merge", {"strategy": "first"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "c", "value"),
            _edge("e3", "c", "result", "m", "a"),
            _edge("e4", "m", "value", "out", "value"),
        ],
    )
    run = _execute(ir)
    assert run.status == RunStatus.SUCCEEDED
    assert _status(run)["out"].inputs["value"] is True


def test_failed_node_is_inspectable_and_downstream_is_skipped():
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "4"}),
            _node("v", "data.value", {"dataType": "number", "value": "0"}),
            _node("f", "transform.formula", {"expression": "x / 0"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "v", "in"),
            _edge("e2", "v", "value", "f", "x"),
            _edge("e3", "f", "result", "out", "value"),
        ],
    )
    run = _execute(ir)
    runs = _status(run)
    assert run.status == RunStatus.FAILED
    assert runs["f"].status == NodeStatus.FAILED
    assert runs["f"].error_code == "execution_error"
    assert "division by zero" in (runs["f"].error or "")
    assert runs["out"].status == NodeStatus.SKIPPED
    assert run.error


def test_output_schema_violation_fails_the_node():
    registry = build_default_registry()
    registry.register(NodeDef(
        type="test.bad_output", version="1.0.0", label="Bad output", category="transform",
        inputs=(PortDef(id="in", name="In", type=PortType.ANY),),
        outputs=(PortDef(id="out", name="Out", type=PortType.NUMBER),),
        executor=lambda _ctx: {"out": "not a number"},
    ))
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("bad", "test.bad_output"),
            _node("out", "output.result"),
        ],
        [
            _edge("e1", "trig", "start", "bad", "in"),
            _edge("e2", "bad", "out", "out", "value"),
        ],
    )
    run = _execute(ir, registry)
    runs = _status(run)
    assert run.status == RunStatus.FAILED
    assert runs["bad"].error_code == "output_schema"
    assert "expected a number" in (runs["bad"].error or "")


def test_node_timeout_is_enforced():
    registry = build_default_registry()
    registry.register(NodeDef(
        type="test.slow", version="1.0.0", label="Slow", category="transform",
        inputs=(PortDef(id="in", name="In", type=PortType.ANY),),
        outputs=(PortDef(id="out", name="Out", type=PortType.ANY),),
        timeout_ms=50,
        executor=lambda _ctx: (time.sleep(0.4), {"out": 1})[1],
    ))
    ir = _ir(
        [_node("trig", "trigger.manual"), _node("slow", "test.slow"), _node("out", "output.result")],
        [_edge("e1", "trig", "start", "slow", "in"), _edge("e2", "slow", "out", "out", "value")],
    )
    run = _execute(ir, registry)
    assert run.status == RunStatus.FAILED
    assert _status(run)["slow"].error_code == "timeout"


def test_retry_succeeds_on_the_second_attempt():
    attempts = {"count": 0}

    def flaky(_ctx):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient")
        return {"out": 42}

    registry = build_default_registry()
    registry.register(NodeDef(
        type="test.flaky", version="1.0.0", label="Flaky", category="transform",
        inputs=(PortDef(id="in", name="In", type=PortType.ANY),),
        outputs=(PortDef(id="out", name="Out", type=PortType.NUMBER),),
        max_attempts=2, executor=flaky,
    ))
    ir = _ir(
        [_node("trig", "trigger.manual"), _node("f", "test.flaky"), _node("out", "output.result")],
        [_edge("e1", "trig", "start", "f", "in"), _edge("e2", "f", "out", "out", "value")],
    )
    run = _execute(ir, registry)
    assert run.status == RunStatus.SUCCEEDED
    assert _status(run)["f"].attempt == 2
    assert _status(run)["f"].outputs["out"] == 42


def test_cancellation_marks_nodes_cancelled():
    ir = _ir(
        [_node("trig", "trigger.manual"), _node("out", "output.result")],
        [_edge("e1", "trig", "start", "out", "value")],
    )
    cancel = threading.Event()
    cancel.set()
    run = _execute(ir, cancel_event=cancel)
    assert run.status == RunStatus.CANCELLED
    assert all(r.status == NodeStatus.CANCELLED for r in run.node_runs)


def test_parallel_layer_runs_all_nodes():
    ir = _ir(
        [
            _node("trig", "trigger.manual", {"seed": "1"}),
            _node("v", "data.value", {"dataType": "number", "value": "0"}),
            _node("a", "transform.formula", {"expression": "x + 1"}),
            _node("b", "transform.formula", {"expression": "x + 2"}),
            _node("m", "logic.merge", {"strategy": "object"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e0", "trig", "start", "v", "in"),
            _edge("e1", "v", "value", "a", "x"),
            _edge("e2", "v", "value", "b", "x"),
            _edge("e3", "a", "result", "m", "a"),
            _edge("e4", "b", "result", "m", "b"),
            _edge("e5", "m", "value", "out", "value"),
        ],
        max_concurrency=2,
    )
    run = _execute(ir)
    assert run.status == RunStatus.SUCCEEDED
    assert _status(run)["out"].inputs["value"] == {"a": 2.0, "b": 3.0}

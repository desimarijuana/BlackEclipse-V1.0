"""Graph runtime — the deterministic executor: lifecycle, determinism, errors,
timeouts, retries, cancellation and output-schema enforcement."""

from __future__ import annotations

import threading
import time

import pytest

from harness.graph_runtime.compiler import compile_workflow
from harness.graph_runtime.executor import GraphExecutor
from harness.graph_runtime.model import ExecutionMode, NodeStatus, PortDef, PortKind, PortType, RunStatus, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeDef, NodeExecContext, NodeRegistry


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


def test_manual_trigger_is_zero_config_but_honours_legacy_defaults():
    definition = build_default_registry().get("trigger.manual")
    assert definition is not None and definition.executor is not None
    assert definition.config_fields == ()

    def emit(config, run_input=None):
        return definition.executor(
            NodeExecContext(
                node_id="trig",
                run_id="run",
                mode=ExecutionMode.RESEARCH,
                inputs={},
                config=config,
                run_input=run_input,
            )
        )

    # Zero-config: Start is the run input, or null.
    assert emit({}) == {"start": None}
    assert emit({}, run_input={"anything": True}) == {"start": {"anything": True}}
    # Legacy saved graphs keep their stored defaults.
    # A run input wins over everything.
    assert emit(
        {"seed": "AAPL", "payload": {"symbol": "MSFT"}, "payloadType": "auto"},
        run_input={"symbol": "TSLA"},
    ) == {"start": {"symbol": "TSLA"}}
    # A configured payload wins over the legacy seed.
    assert emit({"seed": "AAPL", "payload": {"symbol": "MSFT"}, "payloadType": "auto"}) == {
        "start": {"symbol": "MSFT"}
    }
    # payloadType coerces the payload (the schema is not inferred silently).
    assert emit({"seed": "AAPL", "payload": 42, "payloadType": "string"}) == {"start": "42"}
    # Empty payload falls back to the seed; an empty seed emits null.
    assert emit({"seed": "AAPL", "payload": None, "payloadType": "auto"}) == {"start": "AAPL"}
    assert emit({"seed": "", "payload": None, "payloadType": "auto"}) == {"start": None}


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


def test_firing_an_undeclared_control_output_fails_the_node():
    registry = build_default_registry()
    registry.register(NodeDef(
        type="test.bad_control", version="1.0.0", label="Bad control", category="transform",
        inputs=(PortDef(id="in", name="In", type=PortType.ANY),),
        outputs=(
            PortDef(id="out", name="Out", type=PortType.NUMBER),
            PortDef(id="done", name="Done", type=PortType.ANY, kind=PortKind.CONTROL),
        ),
        executor=lambda _ctx: {"out": 1.0, "_control": ["nope"]},
    ))
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("bad", "test.bad_control"),
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
    assert "not declared" in (runs["bad"].error or "")


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


# ── control ports on transform nodes ────────────────────────────────────────
# A control input gates EXECUTION; a control output fires downstream control
# inputs. The transform nodes carry both an optional `in` and a `done` output,
# so a branch can own them without a helper gate node.

def _gated_formula(threshold: float):
    return _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"dataType": "number", "value": str(threshold)}),
            _node("cond", "logic.condition", {"operator": "gt", "compareTo": "1"}),
            _node("f", "transform.formula", {"expression": "x * 2"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e0", "trig", "start", "v", "in"),
            _edge("e1", "v", "value", "cond", "value"),
            _edge("e2", "cond", "true", "f", "in"),
            _edge("e3", "v", "value", "f", "x"),
            _edge("e4", "f", "result", "out", "value"),
        ],
    )


def test_a_wired_control_input_gates_a_transform_node():
    run = _execute(_gated_formula(5))
    runs = _status(run)
    assert runs["f"].status == NodeStatus.SUCCEEDED
    assert runs["out"].inputs["value"] == 10.0

    skipped = _execute(_gated_formula(0))
    runs = _status(skipped)
    assert runs["cond"].status == NodeStatus.SUCCEEDED
    assert runs["f"].status == NodeStatus.SKIPPED
    assert runs["f"].error_code == "control_not_fired"
    assert runs["out"].status == NodeStatus.SKIPPED


def test_a_transform_node_fires_its_done_control_output():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"dataType": "array", "value": '[{"a": 2}, {"a": 1}]'}),
            _node("sel", "transform.select", {"fields": "a"}),
            _node("srt", "transform.sort_limit", {"field": "a"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e0", "trig", "start", "v", "in"),
            _edge("e1", "v", "value", "sel", "rows"),
            _edge("e2", "sel", "done", "srt", "in"),
            _edge("e3", "sel", "rows", "srt", "rows"),
            _edge("e4", "srt", "rows", "out", "value"),
        ],
    )
    run = _execute(ir)
    runs = _status(run)
    assert runs["srt"].status == NodeStatus.SUCCEEDED, runs["srt"].error
    assert runs["out"].inputs["value"] == [{"a": 1.0}, {"a": 2.0}]


def test_an_unwired_control_input_still_runs_on_dataflow():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"dataType": "number", "value": "2"}),
            _node("f", "transform.formula", {"expression": "x + 1"}),
            _node("out", "output.result"),
        ],
        [
            _edge("e0", "trig", "start", "v", "in"),
            _edge("e1", "v", "value", "f", "x"),
            _edge("e2", "f", "result", "out", "value"),
        ],
    )
    run = _execute(ir)
    assert _status(run)["f"].status == NodeStatus.SUCCEEDED


# ── stop + the logic/flow control surface ───────────────────────────────────

def test_stop_honours_its_status():
    def graph(status: str):
        return _ir(
            [
                _node("trig", "trigger.manual"),
                _node("v", "data.value", {"dataType": "number", "value": "5"}),
                _node("cond", "logic.condition", {"operator": "gt", "compareTo": "1"}),
                _node("stop", "logic.stop", {"status": status, "message": "halted by guard"}),
                _node("out", "output.result"),
            ],
            [
                _edge("e0", "trig", "start", "v", "in"),
                _edge("e1", "v", "value", "cond", "value"),
                _edge("e2", "cond", "true", "stop", "in"),
                _edge("e3", "stop", "stopped", "out", "value"),
            ],
        )

    stopped = _execute(graph("succeeded"))
    assert stopped.status == RunStatus.SUCCEEDED
    assert _status(stopped)["stop"].status == NodeStatus.SUCCEEDED
    assert _status(stopped)["out"].status == NodeStatus.SKIPPED

    failed = _execute(graph("failed"))
    assert failed.status == RunStatus.FAILED
    assert failed.error == "halted by guard"
    assert _status(failed)["out"].status == NodeStatus.SKIPPED


def test_merge_fires_done_and_can_gate_a_gate_and_a_wait():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"dataType": "number", "value": "2"}),
            _node("merge", "logic.merge", {"strategy": "first"}),
            _node("gate", "flow.gate"),
            _node("wait", "logic.wait", {"ms": 0}),
            _node("out", "output.result"),
        ],
        [
            _edge("e0", "trig", "start", "v", "in"),
            _edge("e1", "v", "value", "merge", "a"),
            _edge("e2", "merge", "done", "gate", "in"),
            _edge("e3", "v", "value", "gate", "value"),
            _edge("e4", "gate", "done", "wait", "in"),
            _edge("e5", "merge", "value", "out", "value"),
        ],
    )
    run = _execute(ir)
    runs = _status(run)
    assert runs["merge"].status == NodeStatus.SUCCEEDED
    assert runs["gate"].status == NodeStatus.SUCCEEDED
    assert runs["wait"].status == NodeStatus.SUCCEEDED
    assert runs["out"].inputs["value"] == 2.0


def test_condition_can_be_gated_by_another_condition():
    ir = _ir(
        [
            _node("trig", "trigger.manual"),
            _node("v", "data.value", {"dataType": "number", "value": "0"}),
            _node("first", "logic.condition", {"operator": "gt", "compareTo": "1"}),
            _node("second", "logic.condition", {"operator": "truthy"}),
            _node("gate", "flow.gate"),
            _node("out", "output.result"),
        ],
        [
            _edge("e0", "trig", "start", "v", "in"),
            _edge("e1", "v", "value", "first", "value"),
            # 0 > 1 is false, so the TRUE branch never fires and `second` is skipped.
            _edge("e2", "first", "true", "second", "in"),
            _edge("e3", "v", "value", "second", "value"),
            _edge("e4", "second", "true", "gate", "in"),
            _edge("e5", "v", "value", "gate", "value"),
            _edge("e6", "gate", "value", "out", "value"),
        ],
    )
    run = _execute(ir)
    runs = _status(run)
    assert runs["first"].status == NodeStatus.SUCCEEDED
    assert runs["second"].status == NodeStatus.SKIPPED
    assert runs["second"].error_code == "control_not_fired"
    assert runs["gate"].status == NodeStatus.SKIPPED
    assert runs["out"].status == NodeStatus.SKIPPED


def test_switch_accepts_a_json_case_list_with_commas():
    definition = build_default_registry().get("logic.switch")
    assert definition is not None and definition.executor is not None
    result = definition.executor(NodeExecContext(
        node_id="switch", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={"value": "a,b"},
        config={"cases": '["a,b", "c"]'},
    ))
    assert result["caseIndex"] == 0
    assert result["_control"] == ["matched", "case1"]

def test_merge_prefers_a_present_branch_over_an_empty_one():
    definition = build_default_registry().get("logic.merge")
    assert definition is not None and definition.executor is not None

    def merge(inputs, strategy):
        return definition.executor(NodeExecContext(
            node_id="m", run_id="r", mode=ExecutionMode.RESEARCH,
            inputs=inputs, config={"strategy": strategy},
        ))["value"]

    rows = [{"symbol": "AAPL"}]
    # An empty `a` no longer shadows a populated `b`...
    assert merge({"a": [], "b": rows}, "first_present") == rows
    # ...and the legacy name means the same thing.
    assert merge({"a": [], "b": rows}, "first") == rows
    # 0 and false are REAL values, not absent ones.
    assert merge({"a": 0, "b": 5}, "first_present") == 0
    assert merge({"a": False, "b": True}, "first_present") is False
    # Nothing present at all falls through to the last input.
    assert merge({"a": None, "b": ""}, "first_present") == ""


def test_merge_rejects_an_unknown_strategy():
    definition = build_default_registry().get("logic.merge")
    context = NodeExecContext(
        node_id="m", run_id="r", mode=ExecutionMode.RESEARCH,
        inputs={"a": 1}, config={"strategy": "sideways"},
    )
    with pytest.raises(ValueError, match="unsupported merge strategy"):
        definition.executor(context)

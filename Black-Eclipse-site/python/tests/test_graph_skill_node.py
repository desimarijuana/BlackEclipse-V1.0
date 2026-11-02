"""Skill node: thin adapter over the existing skill runtime, honest statuses."""

from __future__ import annotations

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.skill_nodes import set_skill_runner

REGISTRY = build_default_registry()


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _ir():
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_skill", "name": "Skill",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            _node("trig", "trigger.manual", {"seed": {"symbol": "AAPL"}}),
            _node("skill", "skill.invoke", {"skillId": "deep-research"}),
            _node("out", "output.result"),
        ],
        "edges": [
            _edge("e1", "trig", "start", "skill", "input"),
            _edge("e2", "skill", "output", "out", "value"),
        ],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": ["agent.run"],
    })


def _exec(config: dict, inputs: dict | None = None):
    definition = REGISTRY.get("skill.invoke")
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id="skill", run_id="grun", mode=ExecutionMode.RESEARCH,
        inputs=inputs or {}, config=config,
    ))


def _result(status="completed", **overrides):
    payload = {
        "status": status,
        "skillId": "deep-research",
        "version": "1.2.0",
        "runId": "graph:grun:skill",
        "traceId": "graph:grun:skill",
        "output": "AAPL is expensive at 32x.",
        "outputValidated": True,
        "error": None,
        "evidence": [{"ref": "10-K", "quote": "margins fell"}],
        "warnings": [],
        "missingData": [],
        "limitations": [],
        "metrics": {"toolCalls": 3},
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def fake_runner():
    captured = {}

    def runner(context, config):
        captured.update({"config": config, "operator": context.operator})
        return _result()

    set_skill_runner(runner)
    try:
        yield captured
    finally:
        set_skill_runner(None)


def test_completed_skill_returns_its_outputs(fake_runner):
    result = _exec({"skillId": "deep-research"})
    assert result["output"] == "AAPL is expensive at 32x."
    assert result["result"]["version"] == "1.2.0"
    assert result["result"]["outputValidated"] is True
    assert result["result"]["metrics"] == {"toolCalls": 3}
    assert result["evidence"] == [{"ref": "10-K", "quote": "margins fell"}]
    assert fake_runner["config"]["skillId"] == "deep-research"
    assert fake_runner["config"]["version"] is None


def test_a_pinned_version_reaches_the_runtime(fake_runner):
    _exec({"skillId": "deep-research", "version": "1.1.0"})
    assert fake_runner["config"]["version"] == "1.1.0"


def test_the_wire_overrides_the_configured_payload_per_key(fake_runner):
    _exec(
        {"skillId": "deep-research", "inputJson": '{"symbol": "MSFT", "depth": 2}'},
        {"input": {"symbol": "AAPL"}},
    )
    assert fake_runner["config"]["input"] == {"symbol": "AAPL", "depth": 2}


def test_the_configured_payload_is_used_without_a_wire(fake_runner):
    _exec({"skillId": "deep-research", "inputJson": '{"symbol": "AAPL"}'})
    assert fake_runner["config"]["input"] == {"symbol": "AAPL"}


def test_a_skill_needs_to_be_chosen():
    with pytest.raises(ValueError, match="pick one"):
        _exec({})


def test_a_skill_needs_a_bound_runtime():
    set_skill_runner(None)
    with pytest.raises(ValueError, match="skill runtime"):
        _exec({"skillId": "deep-research"})


def test_bad_payload_json_is_named():
    with pytest.raises(ValueError, match="not valid JSON"):
        _exec({"skillId": "deep-research", "inputJson": "{not json"}, {})


def test_a_non_object_payload_is_refused():
    with pytest.raises(ValueError, match="must be an object"):
        _exec({"skillId": "deep-research", "inputJson": "[]"})
    with pytest.raises(ValueError, match="must be an object"):
        _exec({"skillId": "deep-research"}, {"input": ["AAPL"]})


@pytest.mark.parametrize("status", ["blocked", "denied", "failed", "cancelled", "unavailable"])
def test_any_non_completed_status_fails_the_node_with_its_code(status):
    set_skill_runner(lambda _context, _config: _result(
        status,
        output="partial transcript",
        error={"code": "SKILL_NOT_EXECUTABLE", "message": "skill status 'draft' is not executable"},
    ))
    try:
        with pytest.raises(ValueError) as exc:
            _exec({"skillId": "deep-research"})
    finally:
        set_skill_runner(None)
    message = str(exc.value)
    assert "SKILL_NOT_EXECUTABLE" in message
    assert "not executable" in message
    # A failed skill never leaks its partial transcript as an output.
    assert "partial transcript" not in message


def test_a_failure_without_a_structured_error_still_names_the_status():
    set_skill_runner(lambda _context, _config: _result("blocked", error=None))
    try:
        with pytest.raises(ValueError, match="blocked"):
            _exec({"skillId": "deep-research"})
    finally:
        set_skill_runner(None)


def test_a_skill_node_runs_in_a_test_run_with_a_model_effect():
    """A model call is not a world effect; the runner narrows tools instead."""
    dry = compile_workflow(_ir(), REGISTRY, RunGrants(test_run=True))
    assert dry.executable is True, [d.message for d in dry.diagnostics]
    assert not any(d.code == "permission_denied" for d in dry.diagnostics)

    allowed = compile_workflow(
        _ir(), REGISTRY,
        RunGrants(test_run=False, granted_capabilities=frozenset({"agent.run"}), allow_network=True),
    )
    assert allowed.executable is True, [d.message for d in allowed.diagnostics]


def test_the_operator_flag_defaults_to_false_and_is_carried_in_the_context():
    context = NodeExecContext(node_id="skill", run_id="r", mode=ExecutionMode.RESEARCH, inputs={}, config={})
    assert context.operator is False
    assert context.model_settings is None

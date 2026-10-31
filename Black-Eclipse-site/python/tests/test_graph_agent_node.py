"""Agent node: thin adapter over the existing run plane, operator-gated."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.agents import DRY_RUN_TOOLS, dry_run_tools
from harness.graph_runtime.agent_nodes import (
    agent_result_payload,
    agent_run_identity,
    set_agent_runner,
    set_plan_runner,
)
from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _ir():
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_agent", "name": "Agent",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            _node("trig", "trigger.manual", {"seed": "Research AAPL"}),
            _node("agent", "agent.research", {"agent": "eclipse-agent", "maxSteps": 4}),
            _node("out", "output.result"),
        ],
        "edges": [
            _edge("e1", "trig", "start", "agent", "query"),
            _edge("e2", "agent", "finding", "out", "value"),
        ],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": ["agent.run"],
    })


def _exec(config: dict, query: str = "Research AAPL"):
    definition = REGISTRY.get("agent.research")
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id="agent", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs={"query": query}, config=config,
    ))


@pytest.fixture()
def fake_runner():
    captured = {}

    def runner(context, config, objective):
        captured.update({"config": config, "objective": objective, "model": context.model_settings})
        return {
            "finding": {"text": "AAPL looks expensive", "runId": "run_1"},
            "evidence": {"evidenceCount": 2},
        }

    set_agent_runner(runner)
    try:
        yield captured
    finally:
        set_agent_runner(None)


def test_agent_node_returns_structured_finding(fake_runner):
    result = _exec({"agent": "eclipse-agent", "maxSteps": 4})
    assert result["finding"]["text"] == "AAPL looks expensive"
    assert result["evidence"]["evidenceCount"] == 2
    assert fake_runner["objective"] == "Research AAPL"
    assert fake_runner["config"]["maxSteps"] == 4


def test_agent_node_requires_an_objective():
    with pytest.raises(ValueError, match="query"):
        _exec({}, query="")


def test_agent_node_requires_a_bound_runtime():
    set_agent_runner(None)
    with pytest.raises(ValueError, match="agent runtime"):
        _exec({})


def _exec_type(node_type: str, config: dict, inputs: dict):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs, config=config,
    ))


def test_plan_node_returns_the_structured_steps():
    set_plan_runner(lambda _context, objective: {
        "rationale": "two independent checks",
        "steps": [
            {"id": "step_1", "title": "Check filings", "objective": "Read the 10-K", "dependsOn": []},
            {"id": "step_2", "title": "Check prices", "objective": "Read the bars", "dependsOn": []},
        ],
    })
    try:
        result = _exec_type("agent.plan", {}, {"objective": "Review AAPL"})
    finally:
        set_plan_runner(None)
    assert result["summary"]["stepCount"] == 2
    assert result["steps"][0]["title"] == "Check filings"


def test_plan_node_needs_a_bound_planner():
    set_plan_runner(None)
    with pytest.raises(ValueError, match="step planner"):
        _exec_type("agent.plan", {"objective": "Review AAPL"}, {})


def test_delegate_runs_each_task_and_reports_a_failed_part(fake_runner):
    calls = []

    def runner(_context, config, objective):
        calls.append((config, objective))
        if "fail" in objective:
            raise ValueError("provider refused")
        return {"finding": {"text": f"done: {objective}"}, "evidence": {}}

    set_agent_runner(runner)
    try:
        result = _exec_type(
            "agent.delegate",
            {"agent": "eclipse-agent", "maxSteps": 3, "maxTasks": 3},
            {"tasks": ["check one", "fail this one"]},
        )
    finally:
        set_agent_runner(None)
    assert result["summary"] == {"status": "PARTIAL", "total": 2, "succeeded": 1, "failed": 1}
    assert result["findings"][0]["finding"]["text"] == "done: check one"
    assert "provider refused" in result["findings"][1]["error"]
    assert calls[0][0]["maxSteps"] == 3


def test_delegate_bounds_the_task_list_and_config():
    with pytest.raises(ValueError, match="bounded"):
        _exec_type(
            "agent.delegate", {"maxTasks": 1},
            {"tasks": ["one", "two"]},
        )
    with pytest.raises(ValueError, match="tasksJson"):
        _exec_type("agent.delegate", {"tasksJson": "{not json"}, {})


def _agent_result(status: str, *, output=None, error=None):
    return SimpleNamespace(
        status=SimpleNamespace(value=status) if isinstance(status, str) else status,
        output=output,
        error=error,
        runId="run_agent",
        research={"evidenceCount": 1},
        totalTokens=12,
        toolCalls=2,
    )


def test_completed_agent_run_maps_to_a_successful_finding():
    """The run plane's success status is `completed`; it must not fail the node."""
    payload = agent_result_payload(_agent_result("completed", output="AAPL is expensive"))
    assert payload["finding"]["text"] == "AAPL is expensive"
    assert payload["finding"]["status"] == "completed"
    assert payload["evidence"] == {"evidenceCount": 1}


def test_succeeded_remains_accepted_for_substitute_runtimes():
    payload = agent_result_payload(_agent_result("succeeded", output="ok"))
    assert payload["finding"]["text"] == "ok"


def test_failed_agent_run_uses_the_error_message_not_the_output():
    result = _agent_result(
        "failed",
        output="partial transcript",
        error=SimpleNamespace(message="provider rate limited"),
    )
    with pytest.raises(ValueError, match="provider rate limited") as exc:
        agent_result_payload(result)
    assert "partial transcript" not in str(exc.value)


def _ir_without_query(agent_config: dict | None = None):
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_agent", "name": "Agent",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            _node("trig", "trigger.manual", {"seed": "Research AAPL"}),
            _node("agent", "agent.research", agent_config or {"agent": "eclipse-agent", "objective": "Summarize AAPL"}),
            _node("out", "output.result"),
        ],
        "edges": [
            # Deliberately no trigger -> agent.query wire: the objective comes
            # from config, which the executor supports.
            _edge("e2", "agent", "finding", "out", "value"),
        ],
        "settings": {"executionMode": "research", "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": ["agent.run"],
    })


def _operator_grants():
    return RunGrants(
        test_run=False,
        granted_capabilities=frozenset({"agent.run"}),
        allow_network=True,
    )


def test_agent_objective_may_come_from_config_without_a_wire():
    plan = compile_workflow(_ir_without_query(), REGISTRY, _operator_grants())
    assert not any(d.code == "missing_required_input" for d in plan.diagnostics)
    assert not any(d.code == "missing_objective" for d in plan.diagnostics)
    assert plan.executable is True, [d.message for d in plan.diagnostics]


def test_agent_without_input_or_config_objective_is_still_invalid():
    plan = compile_workflow(
        _ir_without_query({"agent": "eclipse-agent", "objective": "   "}),
        REGISTRY,
        _operator_grants(),
    )
    assert any(d.code == "missing_objective" for d in plan.diagnostics)
    assert plan.executable is False


class _AgentRunStore:
    def __init__(self, run: dict | None) -> None:
        self._run = run

    def get_run(self, _run_id: str):
        return self._run


class _Lineage:
    def __init__(self, checkpoint: dict | None) -> None:
        self._checkpoint = checkpoint

    def latest_checkpoint(self, _run_id: str):
        return self._checkpoint


def test_a_crashed_agent_run_reenters_its_checkpoint():
    store = _AgentRunStore({"status": "running"})
    run_id, resume = agent_run_identity(
        store, "graph:grun:agent", lineage=_Lineage({"id": "ckpt_1"}),
    )
    assert run_id == "graph:grun:agent"
    assert resume == "ckpt_1"


def test_an_agent_run_without_a_checkpoint_starts_under_a_fresh_id():
    store = _AgentRunStore({"status": "running"})
    run_id, resume = agent_run_identity(store, "graph:grun:agent", lineage=_Lineage(None))
    assert run_id.startswith("graph:grun:agent:")
    assert resume is None


def test_a_terminal_agent_run_never_blocks_a_retry():
    store = _AgentRunStore({"status": "failed"})
    run_id, resume = agent_run_identity(store, "graph:grun:agent", lineage=_Lineage({"id": "x"}))
    assert run_id.startswith("graph:grun:agent:")
    assert resume is None


def test_a_fresh_agent_run_uses_the_stable_id():
    run_id, resume = agent_run_identity(_AgentRunStore(None), "graph:grun:agent")
    assert run_id == "graph:grun:agent"
    assert resume is None


def test_dry_run_tool_surface_can_only_remove_tools():
    declared = ["get_quote", "research_search", "browser_navigate", "order_submit"]
    narrowed = dry_run_tools(declared)
    assert "get_quote" in narrowed
    assert "research_search" not in narrowed
    assert "browser_navigate" not in narrowed
    assert "order_submit" not in narrowed
    # An agent with no declared allowlist gets exactly the read-only surface.
    assert set(dry_run_tools(None)) == set(DRY_RUN_TOOLS)


def test_agent_node_runs_in_a_test_run_with_a_model_effect():
    """A model call is not a world effect: a dry run may execute it."""
    dry = compile_workflow(_ir(), REGISTRY, RunGrants(test_run=True))
    assert dry.executable is True, [d.message for d in dry.diagnostics]
    assert not any(d.code == "permission_denied" for d in dry.diagnostics)

    allowed = compile_workflow(
        _ir(), REGISTRY,
        RunGrants(
            test_run=False,
            granted_capabilities=frozenset({"agent.run"}),
            allow_network=True,
        ),
    )
    assert allowed.executable is True, [d.message for d in allowed.diagnostics]

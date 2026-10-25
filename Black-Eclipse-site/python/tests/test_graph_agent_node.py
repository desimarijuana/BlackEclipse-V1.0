"""Agent node: thin adapter over the existing run plane, operator-gated."""

from __future__ import annotations

import pytest

from harness.graph_runtime.agent_nodes import set_agent_runner
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


def test_agent_node_is_gated_by_the_operator_envelope():
    denied = compile_workflow(_ir(), REGISTRY, RunGrants(test_run=True))
    assert denied.executable is False
    assert any(d.code == "permission_denied" for d in denied.diagnostics)

    allowed = compile_workflow(
        _ir(), REGISTRY,
        RunGrants(
            test_run=False,
            granted_capabilities=frozenset({"agent.run"}),
            allow_network=True,
        ),
    )
    assert allowed.executable is True, [d.message for d in allowed.diagnostics]

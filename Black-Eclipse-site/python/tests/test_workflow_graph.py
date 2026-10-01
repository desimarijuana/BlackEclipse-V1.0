"""Harness closeout Phase 5: the composable workflow graph.

Offline and deterministic. A workflow compiles onto the EXISTING `execute_run`
graph (one execution plane), a step's tool scope is enforced at the SAME
`ToolRegistry.execute(allowed=...)` seam, and validation rejects a cycle / an
unbounded fan-out / an out-of-scope step with a NAMED reason. An approval-gated
step consumes the single-use approval exactly once.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.mcp.approvals import ApprovalStore
from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolDefinition, ToolRegistry
from harness.workflows import (
    Workflow,
    WorkflowStep,
    WorkflowValidationError,
    WorkflowStore,
    compile_workflow,
    validate_workflow,
)


class ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if not self._responses:
            return AIMessage(content="done")
        return self._responses.pop(0)

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class ScopeModel:
    """Emits a tool call for `tool_name`, then a final answer."""

    def __init__(self, tool_name: str):
        self._tool = tool_name
        self._calls = 0

    def bind_tools(self, tools):
        self._bound = tools
        return self

    async def ainvoke(self, messages):
        self._calls += 1
        if self._calls == 1:
            return AIMessage(content="", tool_calls=[{"id": "c1", "name": self._tool, "args": {}}])
        return AIMessage(content="scope answer")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class FakeBridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-workflow-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _registry() -> ToolRegistry:
    reg = ToolRegistry()

    async def scoped_a(args, ctx):
        return "a-result", {"status": "OK"}

    async def scoped_b(args, ctx):
        return "b-result", {"status": "OK"}

    for name, handler in (("scoped_a", scoped_a), ("scoped_b", scoped_b)):
        reg.register(ToolDefinition(
            name=name, description=name, input_schema={"type": "object", "properties": {}},
            handler=handler, permission="read", risk="low",
        ))
    return reg


def _base_request(run_id: str = "wf_root") -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query="workflow"),
        agent=AgentConfig(
            id="wf-agent", name="WF", systemPrompt="sys",
            tools=["scoped_a", "scoped_b"], maxSteps=3,
        ),
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )


# ── Validation: named reasons ────────────────────────────────────────────────


def test_cycle_is_rejected_with_a_named_reason():
    wf = Workflow(id="cyclic", steps=[
        WorkflowStep(id="a", kind="agent", depends_on=["b"], terminal=True),
        WorkflowStep(id="b", kind="agent", depends_on=["a"]),
    ])
    with pytest.raises(WorkflowValidationError) as exc:
        validate_workflow(wf)
    assert "cycle" in exc.value.reason


def test_unbounded_fanout_is_rejected():
    wf = Workflow(id="wide", steps=[
        WorkflowStep(id="p", kind="parallel", branches=[f"b{i}" for i in range(20)], terminal=True),
    ])
    with pytest.raises(WorkflowValidationError) as exc:
        validate_workflow(wf)
    assert "fan-out" in exc.value.reason


def test_out_of_scope_step_is_rejected_at_validation():
    wf = Workflow(id="scope", steps=[
        WorkflowStep(id="a", kind="agent", tools=["not_a_real_tool"], terminal=True),
    ])
    with pytest.raises(WorkflowValidationError) as exc:
        validate_workflow(wf, known_tools=["scoped_a", "scoped_b"])
    assert "unknown tool" in exc.value.reason


def test_no_terminal_path_is_rejected():
    wf = Workflow(id="deadend", steps=[
        WorkflowStep(id="a", kind="agent"),
        WorkflowStep(id="b", kind="agent", depends_on=["a"]),
    ])
    with pytest.raises(WorkflowValidationError) as exc:
        validate_workflow(wf)
    assert "terminal" in exc.value.reason


def test_empty_workflow_is_rejected():
    with pytest.raises(WorkflowValidationError):
        validate_workflow(Workflow(id="empty", steps=[]))


def test_valid_workflow_passes_and_stores(store):
    wf = Workflow(id="ok", name="OK", steps=[
        WorkflowStep(id="a", kind="agent", instruction="step a", terminal=True),
    ])
    validate_workflow(wf, known_tools=["scoped_a", "scoped_b"])
    stored = WorkflowStore(store)
    stored.save(wf, known_tools=["scoped_a"])
    assert stored.get("ok").id == "ok"
    assert stored.get("ok").steps[0].id == "a"


# ── Execution over the existing graph ────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_executes_multi_step(store, monkeypatch):
    model = ScriptedModel([AIMessage(content="answer a"), AIMessage(content="answer b")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    wf = Workflow(id="multi", agent_id="wf-agent", steps=[
        WorkflowStep(id="s1", kind="agent", instruction="do s1"),
        WorkflowStep(id="s2", kind="agent", instruction="do s2", depends_on=["s1"], terminal=True),
    ])
    result = await compile_workflow(wf, _base_request(), _registry(), FakeBridge(), store)
    assert result.status == "completed"
    assert set(result.outputs) >= {"s1", "s2"}
    # Two child runs, each recording the workflow as its parent lineage.
    assert len(result.runIds) == 2
    for rid in result.runIds:
        run = store.get_run(rid)
        assert run["parentRunId"] == "wf_root"


@pytest.mark.asyncio
async def test_step_scope_is_enforced_at_the_registry_seam(store, monkeypatch):
    # The step declares ONLY scoped_a. The model tries scoped_b (which the AGENT
    # allowlist permits). The step's intersection forbids it.
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ScopeModel("scoped_b"))
    wf = Workflow(id="strict", agent_id="wf-agent", steps=[
        WorkflowStep(id="s1", kind="agent", instruction="try b", tools=["scoped_a"], terminal=True),
    ])
    result = await compile_workflow(wf, _base_request(), _registry(), FakeBridge(), store)
    # The refused call is visible as tool.failed TOOL_FORBIDDEN in the child trace.
    child = result.runIds[0]
    events = [e for e in store.list_events(child) if e["type"] == "tool.failed"]
    assert any(e["data"].get("code") == "TOOL_FORBIDDEN" for e in events)
    # The tool never executed (no tool.completed for scoped_b).
    completed = [e for e in store.list_events(child) if e["type"] == "tool.completed"]
    assert not any(e["data"].get("name") == "scoped_b" for e in completed)


@pytest.mark.asyncio
async def test_approval_step_consumes_single_use_approval_exactly_once(store, monkeypatch):
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: ScriptedModel([AIMessage(content="x")]))
    approvals = ApprovalStore(store)
    req = approvals.request(
        server_id="srv", tool="do_write", eclipse_tool="mcp__srv__do_write",
        effect="write", args={"amount": 5},
    )
    approvals.decide(req["id"], approve=True)

    wf = Workflow(id="approval-wf", steps=[
        WorkflowStep(id="gate", kind="approval", terminal=True,
                     approval={"server": "srv", "tool": "do_write", "args": {"amount": 5}}),
    ])
    first = await compile_workflow(wf, _base_request(), _registry(), FakeBridge(), store, approvals=approvals)
    assert first.status == "completed"
    # A replay fails — the approval is single-use.
    second = await compile_workflow(wf, _base_request("wf_root2"), _registry(), FakeBridge(), store, approvals=approvals)
    assert second.status == "failed"
    assert second.error["code"] == "TOOL_FORBIDDEN"


# ── §32 Company Research Pipeline, expressible over the existing code paths ──


@pytest.mark.asyncio
async def test_company_research_pipeline_is_expressible(store, monkeypatch):
    # A multi-leg research pipeline: retrieve → analyse → report → export. It uses
    # the existing graph, the existing retrieval/skill code paths, and NO new
    # provider code. Here the model is scripted, so the test asserts the PLAN
    # executes step-by-step with per-step scope and one terminal status.
    model = ScriptedModel([
        AIMessage(content="retrieved facts"),
        AIMessage(content="analysis"),
        AIMessage(content="memo"),
    ])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)
    pipeline = Workflow(
        id="company-research-pipeline", name="Company Research Pipeline", agent_id="wf-agent",
        steps=[
            WorkflowStep(id="retrieve", kind="agent", instruction="retrieve company facts", tools=["scoped_a", "scoped_b"]),
            WorkflowStep(id="analyse", kind="agent", instruction="analyse", tools=["scoped_a"], depends_on=["retrieve"]),
            WorkflowStep(id="report", kind="agent", instruction="write memo", depends_on=["analyse"], terminal=True),
        ],
    )
    validate_workflow(pipeline, known_tools=["scoped_a", "scoped_b"])
    result = await compile_workflow(pipeline, _base_request("pipeline_root"), _registry(), FakeBridge(), store)
    assert result.status == "completed"
    assert [s["id"] for s in result.steps] == ["retrieve", "analyse", "report"]
    # Per-step scope is recorded for observability.
    assert result.steps[0]["scope"] == ["scoped_a", "scoped_b"]
    assert result.steps[1]["scope"] == ["scoped_a"]

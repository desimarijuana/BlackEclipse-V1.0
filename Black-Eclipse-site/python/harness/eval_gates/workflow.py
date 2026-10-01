"""Workflow gate (Harness closeout Phase 8.3).

Offline and deterministic. A valid workflow, a cyclic one, an out-of-scope step,
and an approval replay each produce their documented outcome; assertions are on
STRUCTURED error codes / persisted rows, never on model prose.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from langchain_core.messages import AIMessage

from .. import graph as graph_module
from ..mcp.approvals import ApprovalStore
from ..persistence import AgentMemoryStore
from ..schemas import AgentConfig, ModelSettings, RunInput, RunRequest
from ..tools import DataBridge, ToolDefinition, ToolRegistry
from ..workflows import Workflow, WorkflowStep, WorkflowValidationError, compile_workflow, validate_workflow


class _Model:
    def __init__(self, tool_name=None):
        self._tool = tool_name
        self._calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self._calls += 1
        if self._tool and self._calls == 1:
            return AIMessage(content="", tool_calls=[{"id": "c1", "name": self._tool, "args": {}}])
        return AIMessage(content="answer")

    async def astream(self, messages):
        yield await self.ainvoke(messages)


class _Bridge(DataBridge):
    async def fetch(self, capability, params):
        return {"status": "UNAVAILABLE"}


def _registry() -> ToolRegistry:
    reg = ToolRegistry()

    async def handler(args, ctx):
        return "ok", {"status": "OK"}

    for name in ("tool_a", "tool_b"):
        reg.register(ToolDefinition(
            name=name, description=name, input_schema={"type": "object", "properties": {}},
            handler=handler, permission="read", risk="low",
        ))
    return reg


def _request(run_id: str) -> RunRequest:
    return RunRequest(
        runId=run_id,
        input=RunInput(query="wf"),
        agent=AgentConfig(id="wf", name="wf", systemPrompt="s", tools=["tool_a", "tool_b"], maxSteps=3),
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )


def run_gate() -> None:
    # 1. A VALID workflow executes.
    directory = tempfile.mkdtemp(prefix="be-gate-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    graph_module.build_chat_model = lambda settings: _Model()
    try:
        valid = Workflow(id="valid", agent_id="wf", steps=[
            WorkflowStep(id="a", kind="agent", instruction="a", terminal=True),
        ])
        validate_workflow(valid, known_tools=["tool_a", "tool_b"])
        result = asyncio.run(compile_workflow(valid, _request("gate_valid"), _registry(), _Bridge(), store))
        assert result.status == "completed", "a valid workflow must complete"

        # 2. A CYCLIC workflow is rejected with a named reason.
        cyclic = Workflow(id="cyclic", steps=[
            WorkflowStep(id="a", kind="agent", depends_on=["b"], terminal=True),
            WorkflowStep(id="b", kind="agent", depends_on=["a"]),
        ])
        try:
            validate_workflow(cyclic)
            raise AssertionError("cyclic workflow was not rejected")
        except WorkflowValidationError as exc:
            assert "cycle" in exc.reason, "the cycle rejection must name its reason"

        # 3. An OUT-OF-SCOPE step is rejected.
        out_of_scope = Workflow(id="scope", steps=[
            WorkflowStep(id="a", kind="agent", tools=["nope"], terminal=True),
        ])
        try:
            validate_workflow(out_of_scope, known_tools=["tool_a", "tool_b"])
            raise AssertionError("out-of-scope workflow was not rejected")
        except WorkflowValidationError as exc:
            assert "unknown tool" in exc.reason

        # 4. An approval-gated step consumes its single-use approval exactly once.
        approvals = ApprovalStore(store)
        req = approvals.request(server_id="s", tool="w", eclipse_tool="mcp__s__w",
                                effect="write", args={"x": 1})
        approvals.decide(req["id"], approve=True)
        gate_wf = Workflow(id="gate", steps=[
            WorkflowStep(id="g", kind="approval", terminal=True,
                         approval={"server": "s", "tool": "w", "args": {"x": 1}}),
        ])
        first = asyncio.run(compile_workflow(
            gate_wf, _request("gate_appr1"), _registry(), _Bridge(), store, approvals=approvals,
        ))
        assert first.status == "completed", "a granted approval must complete the step"
        replay = asyncio.run(compile_workflow(
            gate_wf, _request("gate_appr2"), _registry(), _Bridge(), store, approvals=approvals,
        ))
        assert replay.status == "failed", "an approval replay must fail"
        assert replay.error["code"] == "TOOL_FORBIDDEN", "an approval replay is a TOOL_FORBIDDEN"
    finally:
        store.close()


__all__ = ["run_gate"]

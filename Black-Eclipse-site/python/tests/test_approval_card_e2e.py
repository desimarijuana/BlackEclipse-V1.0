"""End-to-end: an effectful tool step PAUSES the graph and resumes on approval.

This is the integration proof for the approval card. Unlike the authorizer-level
tests, it drives the REAL `execute_run` graph with a scripted model that calls an
`ask`-classified `terminal_run`. The run must:
  1. emit `approval.requested`,
  2. stay blocked (not finish) until an operator decision,
  3. resume in place and complete after approval,
  4. refuse honestly after a denial.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from harness import graph as graph_module
from harness.agents import ECLIPSE_AGENT, CHAT_CODE_TOOLS
from harness.code import policy
from harness.code.tools import register_code_tools
from harness.code.workspace import ResolvedWorkspace
from harness.mcp.approvals import PENDING, ApprovalStore
from harness.persistence import AgentMemoryStore
from harness.schemas import ModelSettings, RunInput, RunRequest
from harness.tools import DataBridge, ToolRegistry
from harness.finance_tools import register_finance_tools

FIXTURES = Path(__file__).parent / "fixtures" / "code"


class ScriptedModel:
    """A chat model that emits one tool call, then answers."""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = list(responses)

    def bind_tools(self, tools: Any) -> "ScriptedModel":
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        if not self._responses:
            return AIMessage(content="(exhausted)")
        return self._responses.pop(0)

    async def astream(self, messages: Any):
        yield await self.ainvoke(messages)


class _Bridge(DataBridge):
    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "UNAVAILABLE"}


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-approval-card-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def _workspace(tmp_path: Path) -> ResolvedWorkspace:
    root = tmp_path / "project"
    shutil.copytree(FIXTURES, root)
    real = Path(os.path.realpath(root))
    binding = policy.WorkspaceBinding(id="ws_fixture", root=real, base_revision="unknown", strategy="checkout")
    return ResolvedWorkspace(id="ws_fixture", root=real, base_revision="unknown", strategy="checkout", binding=binding)


def _request(workspace: ResolvedWorkspace) -> RunRequest:
    # The chat shape: eclipse-agent + a code autonomy (edit_verify binds the write
    # and execute tools). `approvalMode="ask"` is what the front door now sends.
    return RunRequest(
        runId="run_approval_card",
        input=RunInput(query="run the tests"),
        agentId="eclipse-agent",
        autonomy="edit_verify",
        workspaceId=workspace.id,
        workspace={"root": str(workspace.root)},
        approvalMode="ask",
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_finance_tools(reg)
    register_code_tools(reg)
    return reg


def _tool_call(command: str) -> AIMessage:
    # `python` is safe, but a bare `python -c` with a quoted expression is fine too;
    # use a real `ask` program: `bash`/`powershell` are DENY, so pick an unknown
    # program name that classifies as `ask`.
    return AIMessage(
        content="",
        tool_calls=[{"id": "c1", "name": "terminal_run", "args": {"command": command}}],
    )


@pytest.mark.asyncio
async def test_ask_command_pauses_then_resumes_on_approval(store, tmp_path, monkeypatch):
    ws = _workspace(tmp_path)
    approvals = ApprovalStore(store)
    # Route the workspace resolution to our fixture (the run confirms the root).
    monkeypatch.setattr(
        graph_module, "resolve_workspace", lambda ref: ws,
    )
    model = ScriptedModel([_tool_call("frobnicate --now"), AIMessage(content="Done.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    events: list[tuple[str, dict[str, Any]]] = []

    class _Bus:
        def publish(self, event: dict[str, Any]) -> None:
            events.append((event["type"], event.get("data") or {}))

    run = asyncio.create_task(
        graph_module.execute_run(
            _request(ws), _registry(), _Bridge(), store, bus=_Bus(), approvals=approvals,
        )
    )

    # Wait for the run to reach the paused state (the approval is requested).
    for _ in range(200):
        if any(t == "approval.requested" for t, _ in events):
            break
        await asyncio.sleep(0.02)
    assert any(t == "approval.requested" for t, _ in events), "the card was never surfaced"
    assert not run.done(), "the run must be PAUSED, not finished, while the card is up"

    pending = approvals.list_kind("terminal_command", PENDING)
    assert pending, "a pending single-use approval must exist"
    approvals.decide(pending[-1]["id"], approve=True)

    # The resumed run does real work (surface resolution, the tool loop, the
    # answer seam), so the wait must be a GENEROUS bound rather than a race: a
    # 10s ceiling cancelled runs that finish at ~11s, and the cancellation then
    # surfaced as a `cancelled` status instead of the real outcome.
    result = await asyncio.wait_for(run, timeout=60)
    assert result.status == "completed"
    assert any(t == "approval.resolved" and d.get("approved") is True for t, d in events)


@pytest.mark.asyncio
async def test_ask_command_denial_refuses_honestly(store, tmp_path, monkeypatch):
    ws = _workspace(tmp_path)
    approvals = ApprovalStore(store)
    monkeypatch.setattr(graph_module, "resolve_workspace", lambda ref: ws)
    model = ScriptedModel([_tool_call("frobnicate --now"), AIMessage(content="I couldn't run it.")])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    events: list[tuple[str, dict[str, Any]]] = []

    class _Bus:
        def publish(self, event: dict[str, Any]) -> None:
            events.append((event["type"], event.get("data") or {}))

    run = asyncio.create_task(
        graph_module.execute_run(
            _request(ws), _registry(), _Bridge(), store, bus=_Bus(), approvals=approvals,
        )
    )
    for _ in range(200):
        if any(t == "approval.requested" for t, _ in events):
            break
        await asyncio.sleep(0.02)
    assert any(t == "approval.requested" for t, _ in events)

    pending = approvals.list_kind("terminal_command", PENDING)
    approvals.decide(pending[-1]["id"], approve=False)

    result = await asyncio.wait_for(run, timeout=10)
    assert result.status == "completed"
    assert any(t == "approval.resolved" and d.get("approved") is False for t, d in events)

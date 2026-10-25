"""The `clarify` tool — ask ONE question, pause, resume with the answer.

A clarification is NOT an authorization: the store refuses to answer a row that
is not a clarification, and the tool returns an explicit `answered: false` when
there is no interactive client instead of inventing an answer.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from harness.clarify_tools import _clarify
from harness.mcp.approvals import ApprovalStore, PENDING
from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext


@pytest.fixture()
def store(tmp_path):
    s = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield s
    s.close()


@pytest.fixture()
def approvals(store):
    return ApprovalStore(store)


class _Emitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def emit(self, event_type: str, data=None) -> None:
        self.events.append((event_type, data or {}))


def _ctx(approvals: ApprovalStore, *, pause: bool = True, emitter=None) -> ToolContext:
    ctx = ToolContext(run_id="run_clarify", log=lambda *_: None)
    ctx.approvals = approvals
    ctx.pause_for_approval = pause
    ctx.approval_timeout_s = 5.0
    ctx.emitter = emitter
    return ctx


def test_request_and_answer_wakes_a_waiting_run(approvals):
    pending = approvals.request_clarification(
        question="Which market?", options=["US", "EU"], run_id="run_clarify",
    )
    assert pending["kind"] == "clarification"

    async def scenario():
        waiter = asyncio.create_task(approvals.wait_for_decision(pending["id"], timeout_s=5))
        await asyncio.sleep(0.05)
        answered = approvals.answer_clarification(pending["id"], answer="EU")
        assert answered is not None and answered["answer"] == "EU"
        return await waiter

    decided = asyncio.run(scenario())
    assert decided is not None
    assert decided["status"] == "approved"
    assert decided["answer"] == "EU"


def test_answer_refuses_a_non_clarification_row(approvals):
    mcp_row = approvals.request(
        server_id="srv", tool="t", eclipse_tool="mcp__srv__t",
        effect="write", args={}, run_id="run_clarify",
    )
    assert approvals.answer_clarification(mcp_row["id"], answer="nope") is None
    # The approval is untouched.
    assert approvals.get(mcp_row["id"])["status"] == PENDING


def test_a_paused_tool_returns_the_operators_answer(approvals):
    emitter = _Emitter()
    ctx = _ctx(approvals, pause=True, emitter=emitter)

    async def scenario():
        call = asyncio.create_task(_clarify(
            {"question": "Which horizon?", "options": ["1y", "5y"], "recommended": "5y"}, ctx,
        ))
        await asyncio.sleep(0.05)
        pending = approvals.list_kind("clarification", PENDING)[-1]
        approvals.answer_clarification(pending["id"], answer="5y")
        return await call

    text, data = asyncio.run(scenario())
    assert json.loads(text)["answered"] is True
    assert json.loads(text)["answer"] == "5y"
    assert data["answered"] is True
    assert [e[0] for e in emitter.events] == [
        "clarification.requested", "clarification.answered",
    ]
    assert emitter.events[0][1]["question"] == "Which horizon?"
    assert emitter.events[0][1]["options"] == ["1y", "5y"]


def test_no_interactive_client_never_blocks_or_invents(approvals):
    ctx = _ctx(approvals, pause=False)
    text, data = asyncio.run(_clarify({"question": "Which one?"}, ctx))
    payload = json.loads(text)
    assert payload["answered"] is False
    assert payload["reason"] == "no_interactive_user"
    assert data["answered"] is False
    # No pending card was created for a client that cannot answer it.
    assert approvals.list_kind("clarification", PENDING) == []


def test_clarify_is_registered_read_only_and_allowlisted():
    from harness.agents import ECLIPSE_AGENT
    from harness.clarify_tools import CLARIFY_TOOLS
    from harness.tools import ToolRegistry

    registry = ToolRegistry()
    from harness.clarify_tools import register_clarify_tools

    register_clarify_tools(registry)
    tool = registry.get("clarify")
    assert tool is not None
    assert tool.permission == "read"
    assert tool.risk == "none"
    assert set(CLARIFY_TOOLS) <= set(ECLIPSE_AGENT.tools)
    # A clarification must never be offered as an effect approval target.
    assert tool.effect is None


def test_empty_answer_means_decide_for_me(approvals):
    ctx = _ctx(approvals, pause=True)

    async def scenario():
        call = asyncio.create_task(_clarify({"question": "Pick one?", "options": ["A"]}, ctx))
        await asyncio.sleep(0.05)
        pending = approvals.list_kind("clarification", PENDING)[-1]
        approvals.answer_clarification(pending["id"], answer="")
        return await call

    text, _data = asyncio.run(scenario())
    payload = json.loads(text)
    assert payload["answered"] is True
    assert payload["answer"] == ""
    assert "guidance" in payload

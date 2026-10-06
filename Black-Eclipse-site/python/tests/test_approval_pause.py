"""Approval cards — the run PAUSES for an operator decision, then resumes.

Pause-and-wait is additive over the existing single-use, digest-bound approval
store: the decision still comes from `consume`/`consume_kind`, so a non-approval
can never authorize. These tests cover the gate, the MCP pause path, and the
deny/timeout refusals.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.mcp.approvals import (
    APPROVED,
    PENDING,
    ApprovalStore,
    make_effect_authorizer,
    notify_decision,
)
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path):
    s = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield s
    s.close()


@pytest.fixture()
def approvals(store):
    return ApprovalStore(store)


class _Ctx:
    def __init__(self, *, pause=True, timeout=5.0):
        self.pause_for_approval = pause
        self.approval_timeout_s = timeout
        self.effect_authorized_digest = None
        self.run_id = "run_x"


class _Tool:
    name = "mcp__srv__write_thing"
    effect = "write"
    effect_metadata = {"serverId": "srv", "tool": "write_thing"}
    effect_action_summary = "Write a record"
    effect_affected_data = None
    effect_risk = "medium"


class _Emitter:
    def __init__(self):
        self.events = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data or {}))


# ── the gate primitive ──────────────────────────────────────────────────────


def test_wait_for_decision_times_out(approvals):
    pending = approvals.request(
        server_id="srv", tool="t", eclipse_tool="mcp__srv__t",
        effect="write", args={}, run_id="run_x",
    )
    assert asyncio.run(approvals.wait_for_decision(pending["id"], timeout_s=1)) is None


def test_decide_wakes_a_waiting_run(approvals):
    pending = approvals.request(
        server_id="srv", tool="t", eclipse_tool="mcp__srv__t",
        effect="write", args={}, run_id="run_x",
    )

    async def scenario():
        waiter = asyncio.create_task(approvals.wait_for_decision(pending["id"], timeout_s=5))
        await asyncio.sleep(0.05)
        approvals.decide(pending["id"], approve=True)
        return await waiter

    decided = asyncio.run(scenario())
    assert decided is not None and decided["status"] == APPROVED


def test_notify_decision_without_waiter_is_a_noop(approvals):
    # Must never raise for an id nobody is waiting on (the decide route calls it
    # on every decision, including the deny-and-retry path).
    notify_decision("mcpappr_does_not_exist")


# ── the MCP authorizer pause path ───────────────────────────────────────────


def _approve_latest(approvals: ApprovalStore):
    pending = approvals.list_kind("mcp_tool", PENDING)[-1]
    approvals.decide(pending["id"], approve=True)
    return pending["id"]


def test_pause_mode_approve_authorizes_the_paused_call(approvals):
    emitter = _Emitter()
    authorize = make_effect_authorizer(approvals, "run_x", emitter)
    ctx = _Ctx(pause=True)
    args = {"a": 1}

    async def scenario():
        call = asyncio.create_task(authorize(_Tool(), args, ctx))
        await asyncio.sleep(0.05)
        _approve_latest(approvals)
        return await call

    assert asyncio.run(scenario()) is True
    assert any(e[0] == "approval.requested" for e in emitter.events)
    assert any(e[0] == "mcp.tool.approved" for e in emitter.events)
    # Single-use: a second identical call needs a fresh decision.
    assert asyncio.run(authorize(_Tool(), args, _Ctx(pause=False))) is False


def test_pause_mode_deny_refuses_the_call(approvals):
    emitter = _Emitter()
    authorize = make_effect_authorizer(approvals, "run_x", emitter)
    ctx = _Ctx(pause=True)
    args = {"a": 1}

    async def scenario():
        call = asyncio.create_task(authorize(_Tool(), args, ctx))
        await asyncio.sleep(0.05)
        pending = approvals.list_kind("mcp_tool", PENDING)[-1]
        approvals.decide(pending["id"], approve=False)
        return await call

    assert asyncio.run(scenario()) is False
    assert any(e[0] == "approval.resolved" and e[1].get("approved") is False for e in emitter.events)


def test_pause_mode_timeout_refuses_the_call(approvals):
    emitter = _Emitter()
    authorize = make_effect_authorizer(approvals, "run_x", emitter)
    ctx = _Ctx(pause=True, timeout=1.0)
    # Never decide: the paused call must fall back to a refusal, never a hang.
    assert asyncio.run(authorize(_Tool(), {"a": 1}, ctx)) is False


def test_default_mode_still_refuses_without_pausing(approvals):
    # The pre-existing deny-and-retry behavior must be unchanged when the run did
    # not opt into pause mode.
    emitter = _Emitter()
    authorize = make_effect_authorizer(approvals, "run_x", emitter)
    ctx = _Ctx(pause=False)
    assert asyncio.run(authorize(_Tool(), {"a": 1}, ctx)) is False
    assert any(e[0] == "approval.requested" for e in emitter.events)


# ── the code-write pause path (regression: it used to refuse without pausing) ──


class _PatchTool:
    name = "workspace_patch_apply"
    effect = "write"


class _Ws:
    id = "ws_x"


def _code_ctx(*, pause=True, timeout=5.0):
    ctx = _Ctx(pause=pause, timeout=timeout)
    ctx.workspace = _Ws()
    ctx.approvals = None  # set below
    return ctx


def test_code_write_pauses_then_approve_admits(approvals):
    from harness.code.tools import make_code_authorizer

    emitter = _Emitter()
    authorize = make_code_authorizer(mcp_authorizer=None)
    ctx = _code_ctx(pause=True)
    ctx.approvals = approvals
    ctx.emitter = emitter
    args = {"operations": [{"op": "create", "path": "a.txt"}]}

    async def scenario():
        call = asyncio.create_task(authorize(_PatchTool(), args, ctx))
        await asyncio.sleep(0.05)
        pending = approvals.list_kind("code_write", PENDING)[-1]
        approvals.decide(pending["id"], approve=True)
        return await call

    assert asyncio.run(scenario()) is True
    # The card event carries the exact paths and a real approval id.
    card = [e for e in emitter.events if e[0] == "approval.requested"]
    assert card and card[0][1].get("approvalId")
    assert card[0][1].get("kind") == "code_write"
    assert card[0][1].get("paths") == ["a.txt"]
    # Single-use: a fresh identical patch needs a fresh decision.
    again = _code_ctx(pause=False)
    again.approvals = approvals
    assert asyncio.run(authorize(_PatchTool(), args, again)) is False


def test_code_write_pauses_then_deny_refuses(approvals):
    from harness.code.tools import make_code_authorizer

    emitter = _Emitter()
    authorize = make_code_authorizer(mcp_authorizer=None)
    ctx = _code_ctx(pause=True)
    ctx.approvals = approvals
    ctx.emitter = emitter
    args = {"operations": [{"op": "create", "path": "a.txt"}]}

    async def scenario():
        call = asyncio.create_task(authorize(_PatchTool(), args, ctx))
        await asyncio.sleep(0.05)
        pending = approvals.list_kind("code_write", PENDING)[-1]
        approvals.decide(pending["id"], approve=False)
        return await call

    assert asyncio.run(scenario()) is False

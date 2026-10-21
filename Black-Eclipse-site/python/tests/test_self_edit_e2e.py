"""End-to-end acceptance: the original failure, fixed and measured.

The first user report was "Eclipse can't create me a portfolio" — the tools were
advertised to `ECLIPSE_AGENT` but refused at call time because no authorizer layer
claimed them. This test drives the WHOLE path with REAL components (a real
`ApprovalStore`, the real composed authorizer, the real portfolio registry):

  * `/eclipsesdk` → the runtime chat code surface binds the write tools;
  * `portfolio_create` is admitted by the chain and requires a single-use operator
    approval of kind `portfolio_write` (a real store: PENDING → APPROVED → consumed);
  * one approval authorizes exactly one call.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from harness.agents import CHAT_CODE_TOOLS, ECLIPSE_AGENT
from harness.code.policy import allowed_tools
from harness.mcp.approvals import APPROVED, PENDING, ApprovalStore
from harness.persistence import AgentMemoryStore
from harness.portfolio.tools import register_portfolio_tools
from harness.tools import ToolRegistry

_EDIT_VERIFY_BIND = [
    "skill_create", "skill_update", "skill_delete",
    "code_edit", "command_run", "write_file", "create_file",
]


@pytest.fixture()
def approvals(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    store_holder = store
    try:
        yield ApprovalStore(store)
    finally:
        store_holder.close()


def _portfolio_tool(name: str):
    reg = ToolRegistry()
    register_portfolio_tools(reg)
    return reg.get(name)


def _ctx(approvals):
    return SimpleNamespace(
        approvals=approvals, run_id="run_e2e", pause_for_approval=False,
        emitter=None, effect_authorized_digest=None,
        workspace=SimpleNamespace(id="ws1"),
    )


def _authorizer(approvals):
    from harness.code.authorizers import build_effect_authorizer

    return build_effect_authorizer(approvals=approvals, run_id="run_e2e", emitter=None, workspace_id="ws1")


@pytest.fixture(autouse=True)
def _no_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    from harness.security import bootstrap as sec

    monkeypatch.setattr(sec, "get_gateway", lambda: None)


def test_eclipsesdk_binds_the_write_tools() -> None:
    # The `edit_verify` chat profile (what `/eclipsesdk` forces) advertises every
    # tool the self-edit path needs.
    bound = set(allowed_tools("edit_verify", tuple(CHAT_CODE_TOOLS)))
    for name in _EDIT_VERIFY_BIND:
        assert name in bound, name


def test_portfolio_create_is_reachable_and_single_use_approved(approvals) -> None:
    auth = _authorizer(approvals)
    tool = _portfolio_tool("portfolio_create")
    args = {"name": "BlackRock Portfolio", "base_currency": "USD", "cost_basis_method": "FIFO"}
    ctx = _ctx(approvals)

    # 1) Not approved yet: refused, and a PENDING approval of the right kind exists.
    ctx.effect_authorized_digest = None
    assert asyncio.run(auth(tool, args, ctx)) is False
    pending = approvals.list_kind("portfolio_write", PENDING)
    assert pending, "a pending portfolio_write approval must be created"
    approval_id = pending[0]["id"]

    # 2) The operator approves it.
    approvals.decide(approval_id, approve=True)
    assert approvals.get(approval_id)["status"] == APPROVED

    # 3) The next call is authorized (the approval is consumed). The registry
    # clears the call-scope digest at the start of each call; mirror that.
    ctx.effect_authorized_digest = None
    assert asyncio.run(auth(tool, args, ctx)) is True

    # 4) Single-use: a fresh call-scope with the same payload is refused.
    ctx.effect_authorized_digest = None
    assert asyncio.run(auth(tool, args, ctx)) is False


def test_a_changed_payload_needs_a_new_approval(approvals) -> None:
    auth = _authorizer(approvals)
    tool = _portfolio_tool("portfolio_create")
    ctx = _ctx(approvals)

    asyncio.run(auth(tool, {"name": "A"}, ctx))
    approvals.decide(approvals.list_kind("portfolio_write", PENDING)[0]["id"], approve=True)
    assert asyncio.run(auth(tool, {"name": "A"}, ctx)) is True
    # A different payload is a different digest → still refused.
    assert asyncio.run(auth(tool, {"name": "B"}, ctx)) is False

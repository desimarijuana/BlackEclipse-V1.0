"""Phase 5 — external actions are single-use, digest-bound, workspace-bound.

Reuses the ONE approval store (McpApproval) and the ONE guarded-claim primitive.
The existing ADR-H92 MCP behaviour must stay unchanged.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.code.actions import (
    CodeActionRequest,
    code_action_digest,
    consume_code_action,
    make_code_action_authorizer,
    request_code_action,
)
from harness.mcp.approvals import ApprovalStore, PENDING, APPROVED, DENIED, CONSUMED
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path):
    s = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield s
    s.close()


@pytest.fixture()
def approvals(store):
    return ApprovalStore(store)


def _commit(workspace="ws_a", message="add report", head="main") -> CodeActionRequest:
    return CodeActionRequest(
        kind="commit", workspaceId=workspace, message=message, headRef=head, runId="run_x",
    )


# ── request / consume ───────────────────────────────────────────────────────


def test_commit_without_approval_is_refused_and_creates_pending(approvals):
    request = _commit()
    assert consume_code_action(approvals, request) is None
    pending = request_code_action(approvals, request)
    assert pending["status"] == PENDING
    assert pending["kind"] == "code_action"
    assert pending["workspaceId"] == "ws_a"


def test_approved_action_consumes_once(approvals):
    request = _commit()
    pending = request_code_action(approvals, request)
    approvals.decide(pending["id"], approve=True)
    first = consume_code_action(approvals, request)
    assert first is not None and first["status"] == CONSUMED
    # Single-use: the second attempt is refused.
    assert consume_code_action(approvals, request) is None


def test_changed_payload_needs_a_new_approval(approvals):
    original = _commit(message="add report")
    pending = request_code_action(approvals, original)
    approvals.decide(pending["id"], approve=True)
    assert consume_code_action(approvals, original) is not None
    # A different message is a different digest → no approval for it.
    changed = _commit(message="fix a bug")
    assert code_action_digest(changed) != code_action_digest(original)
    assert consume_code_action(approvals, changed) is None


def test_changed_workspace_needs_a_new_approval(approvals):
    original = _commit(workspace="ws_a")
    pending = request_code_action(approvals, original)
    approvals.decide(pending["id"], approve=True)
    other = _commit(workspace="ws_b")
    assert code_action_digest(other) != code_action_digest(original)
    assert consume_code_action(approvals, other) is None


def test_denial_is_terminal_for_the_digest(approvals):
    request = _commit()
    pending = request_code_action(approvals, request)
    approvals.decide(pending["id"], approve=False)
    assert consume_code_action(approvals, request) is None
    # Re-requesting returns the SAME terminal denial, never a fresh pending.
    again = request_code_action(approvals, request)
    assert again["status"] == DENIED


# ── the authorizer ──────────────────────────────────────────────────────────


class _Tool:
    def __init__(self, name, action_kind):
        self.name = name
        self.effect = "external_action"
        self.effect_metadata = {"actionKind": action_kind}


class _Emitter:
    def __init__(self):
        self.events = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data or {}))


def test_authorizer_refuses_then_approves_once(approvals):
    emitter = _Emitter()
    authorize = make_code_action_authorizer(approvals, "run_x", "ws_a", emitter)
    tool = _Tool("code_commit", "commit")
    args = {"message": "add report", "baseRef": "", "headRef": "main", "argv": []}

    # No approval → refused + a pending request emitted.
    assert asyncio.run(authorize(tool, args, None)) is False
    assert any(e[0] == "code.action.approval_required" for e in emitter.events)

    # Operator approves the pending request.
    pending = [a for a in approvals.list_kind("code_action", PENDING)]
    assert pending
    approvals.decide(pending[0]["id"], approve=True)

    # Now authorized; a second call is refused (single-use).
    assert asyncio.run(authorize(tool, args, None)) is True
    assert asyncio.run(authorize(tool, args, None)) is False


def test_authorizer_in_wrong_workspace_is_refused(approvals):
    authorize = make_code_action_authorizer(approvals, "run_x", "ws_b")
    tool = _Tool("code_commit", "commit")
    args = {"message": "add report", "headRef": "main", "argv": []}
    # Approve the action for ws_a...
    request = CodeActionRequest(kind="commit", workspaceId="ws_a", message="add report",
                                headRef="main", runId="run_x")
    pending = request_code_action(approvals, request)
    approvals.decide(pending["id"], approve=True)
    # ...the authorizer bound to ws_b cannot claim it.
    assert asyncio.run(authorize(tool, args, None)) is False


# ── the MCP path is unchanged (ADR-H92 regression) ──────────────────────────


def test_mcp_approval_still_single_use(approvals):
    pending = approvals.request(
        server_id="srv", tool="write_thing", eclipse_tool="mcp__srv__write_thing",
        effect="write", args={"a": 1}, run_id="run_x",
    )
    assert pending["kind"] == "mcp_tool"
    approvals.decide(pending["id"], approve=True)
    assert approvals.consume("srv", "write_thing", {"a": 1}) is not None
    assert approvals.consume("srv", "write_thing", {"a": 1}) is None


def test_mcp_rows_default_to_kind_mcp_tool(approvals):
    approvals.request(
        server_id="srv2", tool="t", eclipse_tool="mcp__srv2__t",
        effect="write", args={}, run_id="run_y",
    )
    rows = approvals.list_kind("mcp_tool")
    assert rows and all(r["kind"] == "mcp_tool" for r in rows)
    assert approvals.list_kind("code_action") == []

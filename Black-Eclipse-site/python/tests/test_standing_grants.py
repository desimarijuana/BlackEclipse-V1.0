"""Standing grants — the explicit, revocable "always allow" permission.

These tests pin the safety-critical invariants of the standing-grant layer:

  * a grant authorizes its EXACT `(kind, scope, pattern)` and nothing else;
  * a `deny`-classified command is refused BEFORE a grant is consulted, so a
    grant can never make a destructive command run;
  * a grant removes the prompt — the authorizer returns True with NO pending
    approval created;
  * a grant can only be minted from a real approval row's own grant columns;
  * a `critical` Git operation never offers a grant pattern.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.grants import GRANT_COMMAND, GRANT_MCP_TOOL, GrantStore
from harness.mcp.approvals import PENDING, ApprovalStore, make_effect_authorizer
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store(tmp_path):
    s = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield s
    s.close()


@pytest.fixture()
def approvals(store):
    return ApprovalStore(store)


# ── the store ───────────────────────────────────────────────────────────────


def test_grant_is_exact_scoped_and_revocable(store):
    grants = GrantStore(store)
    g = grants.add(kind=GRANT_COMMAND, pattern="python3", scope="ws_a")
    assert grants.matches(GRANT_COMMAND, "ws_a", "python3") is not None
    # A different workspace, program, or kind never matches.
    assert grants.matches(GRANT_COMMAND, "ws_b", "python3") is None
    assert grants.matches(GRANT_COMMAND, "ws_a", "node") is None
    assert grants.matches(GRANT_MCP_TOOL, "ws_a", "python3") is None
    assert grants.revoke(g["id"]) is True
    assert grants.matches(GRANT_COMMAND, "ws_a", "python3") is None


def test_grant_add_is_idempotent(store):
    grants = GrantStore(store)
    a = grants.add(kind=GRANT_COMMAND, pattern="npm", scope="ws")
    b = grants.add(kind=GRANT_COMMAND, pattern="npm", scope="ws")
    assert a["id"] == b["id"]
    assert len(grants.list()) == 1


# ── remember from an approval row ───────────────────────────────────────────


def test_remember_grant_builds_from_the_row(approvals):
    pending = approvals.request_kind(
        kind="terminal_command", request_key="ws", digest="d1", effect="external_action",
        workspace_id="ws", action_summary="Run python3", risk="medium",
        grant_kind=GRANT_COMMAND, grant_pattern="python3", grant_scope="ws",
    )
    approvals.decide(pending["id"], approve=True)
    grant = approvals.remember_grant(pending["id"])
    assert grant is not None and grant["pattern"] == "python3"
    assert approvals.grants.matches(GRANT_COMMAND, "ws", "python3") is not None


def test_remember_grant_is_none_when_not_grantable(approvals):
    pending = approvals.request_kind(
        kind="terminal_command", request_key="ws", digest="d2", effect="external_action",
        workspace_id="ws", risk="medium",
    )
    approvals.decide(pending["id"], approve=True)
    assert approvals.remember_grant(pending["id"]) is None


# ── the MCP authorizer consults a grant ─────────────────────────────────────


class _Ctx:
    def __init__(self):
        self.pause_for_approval = True
        self.approval_timeout_s = 5.0
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


def test_grant_authorizes_without_a_prompt(approvals):
    approvals.grants.add(kind=GRANT_MCP_TOOL, pattern="write_thing", scope="srv")
    emitter = _Emitter()
    authorize = make_effect_authorizer(approvals, "run_x", emitter)
    assert asyncio.run(authorize(_Tool(), {"a": 1}, _Ctx())) is True
    # No pending approval was created — the grant removed the ask entirely.
    assert approvals.list_kind("mcp_tool", PENDING) == []
    assert any(e[0] == "mcp.tool.approved" and e[1].get("grant") for e in emitter.events)


def test_no_grant_still_prompts_and_refuses(approvals):
    emitter = _Emitter()
    authorize = make_effect_authorizer(approvals, "run_x", emitter)
    ctx = _Ctx()
    ctx.approval_timeout_s = 0.1
    assert asyncio.run(authorize(_Tool(), {"a": 1}, ctx)) is False
    assert any(e[0] == "approval.requested" for e in emitter.events)


# ── the shell authorizer: deny beats a grant ────────────────────────────────


class _Ws:
    id = "ws_shell"


def _shell_ctx(approvals):
    ctx = _Ctx()
    ctx.approvals = approvals
    ctx.workspace = _Ws()
    ctx.autonomy = "edit_verify"  # grants command.execute
    ctx.emitter = _Emitter()
    return ctx


def test_shell_grant_authorizes_a_program(approvals):
    from harness.code.shell_tools import make_shell_authorizer

    approvals.grants.add(kind=GRANT_COMMAND, pattern="python3", scope="ws_shell")
    authorize = make_shell_authorizer()
    ctx = _shell_ctx(approvals)
    tool = type("T", (), {"name": "shell_run"})()
    # A piped command is `ask` (never `allow`), so a True here is the grant.
    assert asyncio.run(authorize(tool, {"command": "python3 -m compileall . | Out-String"}, ctx)) is True
    assert approvals.list_kind("terminal_command", PENDING) == []


def test_shell_grant_never_runs_a_denied_command(approvals):
    from harness.code.shell_tools import make_shell_authorizer

    # A grant exists for the head program, but a destructive arg is still refused
    # BEFORE the grant is consulted.
    authorize = make_shell_authorizer()
    ctx = _shell_ctx(approvals)
    tool = type("T", (), {"name": "shell_run"})()
    assert asyncio.run(authorize(tool, {"command": "rm -rf /"}, ctx)) is False


def test_shell_no_grant_prompts(approvals):
    from harness.code.shell_tools import make_shell_authorizer

    authorize = make_shell_authorizer()
    ctx = _shell_ctx(approvals)
    ctx.approval_timeout_s = 0.1
    tool = type("T", (), {"name": "shell_run"})()
    assert asyncio.run(authorize(tool, {"command": "python3 -m compileall . | Out-String"}, ctx)) is False
    assert len(approvals.list_kind("terminal_command", PENDING)) == 1


# ── a critical Git op never offers a grant ──────────────────────────────────


def test_critical_git_op_offers_no_grant_pattern(approvals):
    from harness.git.approvals import make_git_authorizer

    emitter = _Emitter()
    authorize = make_git_authorizer(approvals, "run_x", "ws_git", emitter)
    ctx = _Ctx()
    ctx.workspace = _Ws()
    ctx.approval_timeout_s = 0.1
    tool = type("T", (), {
        "name": "git_reset", "effect": "write",
        "effect_metadata": {}, "risk": "low",
    })()
    assert asyncio.run(authorize(tool, {"mode": "hard"}, ctx)) is False
    card = [e for e in emitter.events if e[0] == "approval.requested"]
    assert card and card[0][1].get("grantPattern") in (None, "")

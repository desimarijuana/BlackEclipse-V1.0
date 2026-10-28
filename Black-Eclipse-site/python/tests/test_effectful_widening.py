"""Operator-approved effectful widening: token, TTL, caps, revocation."""

from __future__ import annotations

from harness.agents import get_agent
from harness.persistence import AgentMemoryStore
from harness.self_improvement.effectful_widening import (
    EffectfulProposalStore,
    approve,
    check_call,
    granted_tools,
    propose,
    revoke_grant,
)
from harness.surface import effective_allowlist
from harness.tools import ToolDefinition, ToolRegistry


async def _handler(args, ctx):
    return "ok", {}


def _tool(name, *, permission="write", effect="write", risk="medium"):
    return ToolDefinition(
        name=name, description=f"{name} test tool",
        input_schema={"type": "object", "properties": {"notional": {"type": "number"}}},
        handler=_handler, permission=permission, risk=risk, effect=effect,
        timeout_ms=1000,
    )


def test_effectful_grant_requires_token_caps_and_revokes(tmp_path):
    registry = ToolRegistry()
    registry.register(_tool("write_note_test"))
    registry.register(_tool("read_note_test", permission="read", effect="read", risk="low"))
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        bad = propose(
            store, registry, "write_note_test",
            justification="", caps={"maxCallsPerDay": 2, "maxCallsTotal": 2},
        )
        assert bad["ok"] is False and bad["reason"] == "justification_required"

        read_only = propose(
            store, registry, "read_note_test",
            justification="read test", caps={"maxCallsPerDay": 2, "maxCallsTotal": 2},
        )
        assert read_only["ok"] is False

        result = propose(
            store, registry, "write_note_test",
            justification="create a draft note for the operator",
            caps={
                "maxCallsPerDay": 2, "maxCallsTotal": 2,
                "maxNotionalPerCall": 10, "notionalField": "notional",
            },
            ttl_hours=2,
        )
        assert result["ok"] is True
        proposal = result["proposal"]
        token = result["approvalToken"]
        assert token and "tokenHash" not in proposal
        assert proposal["status"] == "pending_approval"

        assert approve(store, proposal["id"], "wrong")["ok"] is False
        approved = approve(store, proposal["id"], token)
        assert approved["ok"] is True
        assert approved["proposal"]["status"] == "active"
        assert "write_note_test" in granted_tools("eclipse-agent")
        assert "write_note_test" in effective_allowlist(get_agent("eclipse-agent"), registry)

        assert check_call(store, "eclipse-agent", "write_note_test", {"notional": 5})["ok"] is True
        blocked = check_call(store, "eclipse-agent", "write_note_test", {"notional": 20})
        assert blocked["ok"] is False and blocked["reason"] == "max_notional_per_call"
        assert check_call(store, "eclipse-agent", "write_note_test", {"notional": 5})["ok"] is True
        exhausted = check_call(store, "eclipse-agent", "write_note_test", {"notional": 1})
        assert exhausted["ok"] is False and exhausted["reason"] == "max_calls_total"

        assert revoke_grant(store, approved["grantId"])["ok"] is True
        assert "write_note_test" not in granted_tools("eclipse-agent")
        assert "write_note_test" not in effective_allowlist(get_agent("eclipse-agent"), registry)
        assert EffectfulProposalStore(store).find(proposal["id"])["status"] == "revoked"
    finally:
        store.close()

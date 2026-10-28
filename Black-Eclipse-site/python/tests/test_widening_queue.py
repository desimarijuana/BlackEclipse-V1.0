"""Staged read-only widening proposals: evidence queue, never a grant."""

from __future__ import annotations

import json

from harness.persistence import AgentMemoryStore
from harness.self_improvement.widening_queue import (
    WideningProposalStore,
    stage_proposals,
)
from harness.tools import ToolDefinition, ToolRegistry


async def _handler(args, ctx):
    return "ok", {}


def _tool(name, *, permission="read", risk="low", effect=None):
    return ToolDefinition(
        name=name, description=f"{name} test tool",
        input_schema={"type": "object", "properties": {}},
        handler=_handler, permission=permission, risk=risk, effect=effect,
        timeout_ms=1000,
    )


def test_stage_eligible_tools_without_granting(tmp_path):
    registry = ToolRegistry()
    for tool in (
        _tool("market_read_test"),
        _tool("write_test", permission="write", effect="write"),
        _tool("place_order"),
    ):
        registry.register(tool)
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        before = registry.names()
        result = stage_proposals(store, registry, granted_tools=())
        assert result["ok"] is True
        assert len(result["staged"]) == 1
        proposal = result["staged"][0]
        assert proposal["toolName"] == "market_read_test"
        assert proposal["status"] == "needs_evidence"
        evidence = json.loads(proposal["evidence"])
        assert evidence["required"] == {
            "historicalReplay": False, "denyPath": False,
            "conclusionStability": False,
        }
        assert registry.names() == before

        again = stage_proposals(store, registry, granted_tools=())
        assert any(item["reason"] == "already_staged" for item in again["skipped"])

        assert WideningProposalStore(store).withdraw(proposal["id"]) is True
        saved = WideningProposalStore(store).find("market_read_test")
        assert saved["status"] == "withdrawn"
    finally:
        store.close()

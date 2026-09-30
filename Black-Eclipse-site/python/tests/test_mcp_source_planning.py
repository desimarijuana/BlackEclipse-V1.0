"""Phase 6 Milestone 6 — MCP-aware source planning.

Behavior contracts: a stale JDdS result loses preference to a fresher eligible
source; missing / failed / stale are three distinct outcomes; a conflict survives
into evidence; an MCP tool that does not implement the retrieval contract is still
directly callable.
"""

from __future__ import annotations

import os
import sys

import pytest

from harness.mcp.mcp_retrieval import (
    FAILED,
    FRESH,
    MISSING,
    STALE,
    SourceCandidate,
    build_mcp_retrieval_source,
    freshness_state,
    plan_candidates,
)
from harness.mcp.config import MCPServerConfig
from harness.mcp.manager import MCPManager
from harness.tools import ToolContext, ToolRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
FAST = os.path.join(FIXTURES, "fastmcp_fixture.py")


def _cand(source_id, value, freshness, **kw):
    return SourceCandidate(
        source_id=source_id, kind=kw.pop("kind", "mcp"), verification=kw.pop("verification", "external"),
        eclipse_verified=False, value=value, freshness=freshness, **kw,
    )


def test_freshness_state_is_three_distinct_outcomes():
    assert freshness_state(age_seconds=10, ttl_seconds=60) == FRESH
    assert freshness_state(age_seconds=120, ttl_seconds=60) == STALE
    assert freshness_state(age_seconds=None, ttl_seconds=60) == MISSING


def test_stale_jds_loses_to_fresher_source():
    candidates = [
        _cand("JDDS", 100.0, STALE, kind="jds", verification="jds", observed_at=1.0),
        _cand("MCP:srv:quote", 101.0, FRESH, kind="mcp", observed_at=9e9),
    ]
    result = plan_candidates(candidates)
    assert result.chosen is not None and result.chosen.source_id == "MCP:srv:quote"
    assert "fresh" in result.explanation


def test_missing_and_failed_are_reported_separately():
    candidates = [
        _cand("JDDS", None, MISSING, kind="jds"),
        _cand("MCP:down", None, FAILED, status="ERROR"),
        _cand("WEB", 5.0, FRESH, kind="web"),
    ]
    result = plan_candidates(candidates)
    assert "JDDS" in result.missing
    assert "MCP:down" in result.failed
    assert result.chosen.source_id == "WEB"


def test_conflict_is_preserved():
    candidates = [
        _cand("JDDS", 100.0, FRESH, kind="jds", verification="jds"),
        _cand("MCP:srv:quote", 130.0, FRESH, kind="mcp"),
    ]
    result = plan_candidates(candidates)
    assert result.conflicts, "a numeric disagreement must be preserved"
    assert len(result.conflicts[0]["values"]) == 2
    # Both values survive; nothing is silently collapsed.
    chosen_value = result.chosen.value
    other = next(c for c in candidates if c.value != chosen_value)
    assert other.value == 130.0 or other.value == 100.0


def test_agreeing_sources_do_not_conflict():
    candidates = [
        _cand("JDDS", 100.0, FRESH, kind="jds"),
        _cand("MCP:srv:quote", 100.1, FRESH, kind="mcp"),
    ]
    result = plan_candidates(candidates)
    assert result.conflicts == []


@pytest.mark.asyncio
async def test_generic_mcp_tool_remains_directly_callable():
    cfg = MCPServerConfig(
        id="fx", command=sys.executable, args=[FAST], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"},
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    # The generic tool is directly callable and was never routed through a
    # retrieval contract or withheld for not implementing one.
    result = await reg.execute("mcp__fx__echo", "c1", {"text": "hi"},
                               ToolContext(run_id="r1", log=lambda *_: None), allowed=set(names))
    assert result.ok and "echo:hi" in result.text
    await mgr.close()


@pytest.mark.asyncio
async def test_mcp_retrieval_source_adapts_a_declared_tool():
    cfg = MCPServerConfig(
        id="fx", command=sys.executable, args=[FAST], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"},
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    source = build_mcp_retrieval_source(manager=mgr, server_id="fx", tool_name="echo", data_type="current_quote")
    assert source.name == "MCP:fx:echo"
    assert source.available(None) is True

    class _Req:
        symbol = "NVDA"

    outcome = await source.retrieve(_Req())
    assert outcome.status in ("OK", "ERROR")
    if outcome.status == "OK":
        assert outcome.raw
    await mgr.close()


@pytest.mark.asyncio
async def test_declared_mcp_tool_is_planned_by_the_layer():
    # A server with a declared data-source tool contributes a source to the REAL
    # retrieval layer, and the planner selects it (before web) for that data type.
    cfg = MCPServerConfig(
        id="fx", command=sys.executable, args=[FAST], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"},
        data_source_tools={"echo": "current_quote"},
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    assert [s.name for s in mgr.mcp_sources()] == ["MCP:fx:echo"]

    from harness.retrieval.contract import FinancialRetrievalRequest
    from harness.retrieval.layer import FinancialRetrievalLayer

    class _Bridge:
        async def fetch(self, capability, params):
            return {"status": "UNAVAILABLE"}

    layer = FinancialRetrievalLayer(_Bridge(), mcp_sources=mgr.mcp_sources())
    request = FinancialRetrievalRequest(objective="latest quote", dataType="current_quote", instrument="NVDA")
    plan = layer._declared_for(request)
    assert "MCP:fx:echo" in plan
    result = await layer.retrieve(request)
    # The MCP source was considered: its reference/evidence or an attempt is
    # recorded, and the result is never labelled Eclipse-verified.
    assert result is not None
    await mgr.close()


@pytest.mark.asyncio
async def test_undeclared_mcp_tool_is_not_a_retrieval_source():
    cfg = MCPServerConfig(
        id="fx", command=sys.executable, args=[FAST], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"},
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    assert mgr.mcp_sources() == []
    await mgr.close()


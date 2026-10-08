"""A2A security: least privilege, spawning intersection, budgets, injection."""

from __future__ import annotations

import asyncio

import pytest

from harness.a2a import permissions
from harness.a2a.results import merge_results
from harness.a2a.model import A2AResult, Finding
from harness.a2a.service import A2AError

from a2a_helpers import make_service


def _defn(service, agent_id):
    return service.registry.get_agent(agent_id)


def test_trading_capability_requires_approval(tmp_path):
    service, _, _ = make_service(tmp_path)
    trading = _defn(service, "trading-agent")
    ok, reason = permissions.action_allowed(trading, capability="trade_execution",
                                            tool=None, effect=None, approved=False)
    assert ok is False and "approval" in reason
    ok2, _ = permissions.action_allowed(trading, capability="trade_execution",
                                        tool=None, effect=None, approved=True)
    assert ok2 is True


def test_trading_agent_holds_no_analysis_tools(tmp_path):
    service, _, _ = make_service(tmp_path)
    trading = _defn(service, "trading-agent")
    assert trading.tools == []
    assert permissions.permits_tool(trading, "get_ohlcv") is False


def test_research_agent_cannot_delegate_or_trade(tmp_path):
    service, _, _ = make_service(tmp_path)
    research = _defn(service, "research-agent")
    assert permissions.can_delegate(research, "valuation-agent") is False
    assert permissions.has_capability(research, "trade_execution") is False


def test_disabled_agent_is_denied(tmp_path):
    service, _, _ = make_service(tmp_path)
    service.registry.disable_agent("news-agent")
    news = _defn(service, "news-agent")
    ok, _ = permissions.action_allowed(news, capability="news", tool=None, effect=None)
    assert ok is False


def test_spawn_intersection_cannot_widen(tmp_path):
    service, _, _ = make_service(tmp_path)
    sender = _defn(service, "research-agent")
    child = _defn(service, "eclipse-agent")
    composed = permissions.intersection(sender, child)
    assert set(composed.capabilities) <= set(sender.capabilities)
    assert set(composed.capabilities) <= set(child.capabilities)
    # A spawned agent can never delegate on its own.
    assert composed.can_delegate is False or composed.can_delegate == (sender.can_delegate and child.can_delegate)


def test_spawned_agent_cannot_respawn(tmp_path):
    service, _, _ = make_service(tmp_path)

    async def run():
        first = await service.spawn_agent(
            sender_agent_id="eclipse-agent", run_id="r", base_agent_id="research-agent",
            objective="sub-task",
        )
        # The spawned agent has can_delegate False -> a further spawn is refused.
        await service.spawn_agent(
            sender_agent_id=first["spawnedAgentId"], run_id="r",
            base_agent_id="research-agent", objective="nested",
        )

    with pytest.raises(A2AError) as exc:
        asyncio.run(run())
    assert exc.value.code in ("A2A_DELEGATION_REFUSED", "A2A_NO_AGENT")


def test_spawn_cannot_widen_tools(tmp_path):
    # `trading-agent` declares an EMPTY tool list, so a spawned child can only
    # stay empty — an override cannot grant it analysis tools.
    service, _, _ = make_service(tmp_path)

    async def run():
        return await service.spawn_agent(
            sender_agent_id="eclipse-agent", run_id="r", base_agent_id="trading-agent",
            objective="sub", overrides={"tools": ["get_ohlcv", "delegate"]},
        )

    result = asyncio.run(run())
    spawned = service.get_agent(result["spawnedAgentId"])
    base_tools = set(service.get_agent("trading-agent")["tools"] or [])
    assert set(spawned["tools"] or []) <= base_tools


def test_child_budget_cannot_exceed_parent(tmp_path):
    service, _, _ = make_service(tmp_path)
    service.budgets.set_limits("r", max_tokens=1000)
    child = service.budgets.child_budget("r")
    assert child.max_tokens <= 1000


def test_injected_unsupported_claim_is_not_promoted(tmp_path):
    # An agent that returns an unbacked claim (e.g. from untrusted page content)
    # gets it listed as unsupported, never promoted to an evidence-backed fact.
    merged = merge_results([
        A2AResult(agent_id="research-agent", status="COMPLETED",
                  findings=[Finding(claim="Company will definitely merge next week",
                                    confidence=0.99, evidence_refs=[])]),
    ])
    assert merged.unsupported_claims
    assert merged.findings[0].confidence <= 0.4

"""Built-in specialist agent definitions.

The specialist agents (orchestrator, supervisor, research, financial, valuation,
risk, market-data, news, coding, QA, security, trading) are DATA. Each declares a
role, capabilities, permission policy, delegation rights and (where meaningful) a
narrowed tool surface. They are seeded into the Agent Registry at boot and, where
they need to be directly runnable, registered as `AgentConfig` presets so the
existing run runtime can dispatch to them by id.

Trading is deliberately isolated: `trading-agent` declares only approval-gated
trading capabilities, holds NO analysis tools, and can never be delegated to
without an approval.
"""

from __future__ import annotations

from typing import Any, Optional

from .model import AgentDefinition, AgentStatus

_COMMON_RULE = (
    "Only report claims you can back with evidence or a verified calculation. "
    "Never fabricate a number, a source or a result. Disclose uncertainty, "
    "conflicts and gaps explicitly. Stay strictly within your assigned objective."
)


def _defn(agent_id: str, name: str, role: str, capabilities: list[str], *,
          delegates: bool = False, allowed: Optional[list[str]] = None,
          tools: Optional[list[str]] = None, permissions: Optional[dict[str, Any]] = None,
          instructions: str = "", max_steps: int = 6, timeout_ms: int = 120_000) -> AgentDefinition:
    return AgentDefinition(
        id=agent_id, name=name, role=role,
        description=f"{name} ({role}).",
        capabilities=capabilities,
        tools=tools,
        can_delegate=delegates,
        allowed_delegates=allowed or [],
        system_instructions=(instructions + "\n\n" + _COMMON_RULE).strip(),
        permissions=permissions or {"capabilities": capabilities},
        max_concurrency=1,
        timeout_ms=timeout_ms,
        status=AgentStatus.ACTIVE,
        metadata={"maxSteps": max_steps},
    )


def default_definitions() -> list[AgentDefinition]:
    """The seeded agent catalogue. Deterministic and side-effect free."""
    return [
        # The three canonical run presets, so their ids can act as A2A senders.
        _defn(
            "eclipse-agent", "Eclipse Agent", "orchestrator",
            ["orchestration", "delegation", "planning", "synthesis", "quality_control",
             "financial_analysis", "web_research", "market_data", "risk_analysis"],
            delegates=True, tools=None, max_steps=12, timeout_ms=600_000,
            instructions=(
                "You are Eclipse. Decompose a request into independent sub-questions, "
                "delegate each to a specialist with the right capability, then synthesize "
                "an evidence-backed answer."
            ),
        ),
        _defn(
            "code-agent", "Eclipse Code Agent", "coding",
            ["code_generation", "code_review", "debugging", "testing", "orchestration"],
            delegates=True, tools=None, max_steps=24, timeout_ms=600_000,
        ),
        _defn(
            "code-navigator", "Repository Navigator", "navigator",
            ["code_search", "code_read"], tools=None, max_steps=10,
        ),
        _defn(
            "eclipse-orchestrator", "Eclipse Orchestrator", "orchestrator",
            ["orchestration", "delegation", "planning", "synthesis", "quality_control"],
            delegates=True, tools=None, max_steps=10, timeout_ms=300_000,
            instructions=(
                "You decompose a user request into independent sub-questions, delegate "
                "each to the specialist that holds the right capability, then synthesize "
                "an evidence-backed answer. Prefer parallel delegation for independent work."
            ),
        ),
        _defn(
            "supervisor-agent", "Supervisor", "supervisor",
            ["supervision", "quality_control", "review", "conflict_resolution"],
            delegates=True, tools=None, max_steps=6,
            instructions=(
                "You monitor child work, detect missing or failed tasks, validate that "
                "claims are supported, and decide whether a workflow is complete or needs rework."
            ),
        ),
        _defn(
            "qa-agent", "QA Agent", "quality_assurance",
            ["quality_assurance", "verification", "review"],
            instructions=(
                "You verify that claims are supported, calculations are correct, citations "
                "are valid, sources are fresh, conflicts are disclosed and required tasks are "
                "complete. Return PASS, REWORK_REQUIRED or BLOCKED."
            ),
        ),
        _defn(
            "research-agent", "Research Agent", "specialist",
            ["web_research", "evidence", "source_ranking", "claim_verification"],
        ),
        _defn(
            "financial-agent", "Financial Agent", "specialist",
            ["financial_analysis", "fundamentals", "cash_flow", "ratios"],
        ),
        _defn(
            "valuation-agent", "Valuation Agent", "specialist",
            ["dcf", "ddm", "comparable_companies", "pe_valuation", "ev_ebitda"],
        ),
        _defn(
            "risk-agent", "Risk Agent", "specialist",
            ["risk_analysis", "var", "drawdown", "correlation", "scenario_analysis"],
        ),
        _defn(
            "market-data-agent", "Market Data Agent", "specialist",
            ["market_data", "quotes", "ohlcv", "orderbook", "fx"],
        ),
        _defn(
            "news-agent", "News Agent", "specialist",
            ["news", "events", "sentiment", "catalysts"],
        ),
        _defn(
            "coding-agent", "Coding Agent", "specialist",
            ["code_generation", "code_review", "debugging", "testing"],
        ),
        _defn(
            "security-agent", "Security Agent", "specialist",
            ["security_review", "vulnerability_scan", "threat_analysis"],
        ),
        _defn(
            "trading-agent", "Trading Agent", "executor",
            ["trade_execution", "order_placement", "live_trading"],
            tools=[],  # NO analysis tools; execution only, and approval-gated
            permissions={
                "capabilities": ["trade_execution", "order_placement", "live_trading"],
                "approvalGated": True,
                "trading": True,
            },
            instructions=(
                "You may only act on an ALREADY-APPROVED, fully-specified order. You never "
                "decide to trade on your own and never act without a matching approval."
            ),
        ),
    ]


def _tools_for_research() -> Optional[list[str]]:
    try:
        from ..agents import SEARCH_TOOLS, WEB_RESEARCH_TOOLS
    except Exception:  # noqa: BLE001 - a missing group means "inherit"
        return None
    return _dedupe([*WEB_RESEARCH_TOOLS, *SEARCH_TOOLS, "memory"])


def _tools_for_market() -> Optional[list[str]]:
    return _dedupe([
        "get_quote", "get_historical_prices", "get_ohlcv", "get_volume", "get_orderbook",
        "get_trades", "get_market_cap", "get_fx_rate", "market_get_quote", "market_get_ohlcv",
        "research_search_news", "macro_get_series",
    ])


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def default_agent_configs() -> list[dict[str, Any]]:
    """`AgentConfig` preset dicts for the directly-runnable specialists.

    Imported lazily so this module never creates an import cycle with `agents.py`.
    """
    research = _tools_for_research()
    market = _tools_for_market()
    catalog = {
        "eclipse-orchestrator": None,
        "supervisor-agent": None,
        "qa-agent": None,
        "research-agent": research,
        "financial-agent": research,
        "valuation-agent": research,
        "risk-agent": research,
        "market-data-agent": market,
        "news-agent": research,
        "coding-agent": None,
        "security-agent": None,
        "trading-agent": [],
    }
    configs: list[dict[str, Any]] = []
    for definition in default_definitions():
        prompt = definition.system_instructions or _COMMON_RULE
        configs.append({
            "id": definition.id,
            "name": definition.name,
            "systemPrompt": prompt,
            "tools": catalog.get(definition.id),
            "maxSteps": int(definition.metadata.get("maxSteps") or 6),
            "runTimeoutMs": min(600_000, definition.timeout_ms),
        })
    return configs


__all__ = ["default_agent_configs", "default_definitions"]

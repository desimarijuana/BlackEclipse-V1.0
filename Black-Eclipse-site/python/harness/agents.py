"""Agent definitions — authored in Python.

Adding an agent is adding an `AgentConfig` here. Agents declare their tool
allowlist; the registry enforces it. The authoritative system prompt content
lives in `prompts.py`; `sys_prompt` below is exposed so the TS front door can
fetch it instead of carrying its own copy.
"""

from __future__ import annotations

from .prompts import ECLIPSE_AGENT_SYSTEM_PROMPT
from .schemas import AgentConfig

# Tool allowlist. The Phase-2 retrieval tools are the provider-agnostic path
# (the agent asks for the *objective*; the retrieval layer picks the source).
# The legacy JDdS-only tools are kept for compatibility.
ECLIPSE_AGENT = AgentConfig(
    id="eclipse-agent",
    name="Eclipse Agent",
    systemPrompt=ECLIPSE_AGENT_SYSTEM_PROMPT,
    tools=[
        # Phase-2 unified retrieval tools
        "market_get_quote",
        "market_get_ohlcv",
        "fundamentals_get_company_profile",
        "fundamentals_get_financials",
        "research_search",
        "research_retrieve_source",
        "research_search_news",
        "macro_get_series",
        # Phase-1 JDdS tools (still available)
        "get_market_snapshot",
        "get_fundamentals",
        "get_news",
        "get_source_health",
        "get_coverage",
        # Eclipse-Memory: persistent memory + progressive skill discovery.
        "memory",
        "skill_list",
        "skill_view",
    ],
    maxSteps=8,
    toolTimeoutMs=20_000,
    runTimeoutMs=120_000,
)

AGENT_PRESETS: dict[str, AgentConfig] = {
    ECLIPSE_AGENT.id: ECLIPSE_AGENT,
}

DEFAULT_AGENT_ID = ECLIPSE_AGENT.id


def get_agent(agent_id: str) -> AgentConfig:
    agent = AGENT_PRESETS.get(agent_id)
    if agent is None:
        known = ", ".join(AGENT_PRESETS.keys())
        raise ValueError(f"Unknown agent {agent_id!r}. Known: {known}")
    return agent


__all__ = ["ECLIPSE_AGENT", "AGENT_PRESETS", "DEFAULT_AGENT_ID", "get_agent"]

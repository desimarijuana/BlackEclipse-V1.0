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
#
# The truthful-capability tools (`get_capability_matrix`, `get_research_health`)
# are read-only diagnostics and MUST be in the allowlist: without them the agent
# was reduced to the coarser `get_coverage` and could not tell whether a market's
# statement route was implemented/configured (verified in the SYS/RELIANCE/Tata
# runs, where `get_capability_matrix` returned TOOL_FORBIDDEN). They stay
# read-only; no write tool is widened here.
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
        # Truthful per-capability diagnostics (read-only). Recognised ≠ working,
        # configured ≠ healthy, and zero attempts ≠ failure.
        "get_capability_matrix",
        "get_research_health",
        # Eclipse-Memory: persistent memory + progressive skill discovery and
        # explicit, permission-checked skill invocation as a controlled sub-run.
        "memory",
        "skill_list",
        "skill_view",
        "skill_invoke",
    ],
    maxSteps=8,
    # Per-tool CEILING (WS2). Each tool's own declared `timeout_ms` is
    # authoritative; this only bounds a tool that declares more. It is a distinct
    # budget from `runTimeoutMs` (the whole model turn). 30s lets the declared
    # `research_search_news` (30s) run in full instead of being clamped to 20s and
    # timing out, while still bounding any runaway call.
    toolTimeoutMs=30_000,
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

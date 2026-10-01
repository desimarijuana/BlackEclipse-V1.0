"""Agent definitions — authored in Python.

Adding an agent is adding an `AgentConfig` here. Agents declare their tool
allowlist; the registry enforces it. The authoritative system prompt content
lives in `prompts.py`; `sys_prompt` below is exposed so the TS front door can
fetch it instead of carrying its own copy.
"""

from __future__ import annotations

from .prompts import (
    CODE_AGENT_SYSTEM_PROMPT,
    CODE_NAVIGATOR_SYSTEM_PROMPT,
    ECLIPSE_AGENT_SYSTEM_PROMPT,
)
from .schemas import AgentConfig

# The repository tools. Phase 1 shipped the five read tools; Phase 2 adds the
# write half (patch/diff/revert), which the run's autonomy profile gates. Kept as
# a named constant so the preset's closed allowlist is asserted in one place.
CODE_NAVIGATOR_TOOLS = [
    "workspace_status",
    "workspace_list",
    "workspace_search",
    "workspace_read",
    "workspace_docs",
    "workspace_patch_apply",
    "workspace_diff",
    "workspace_revert",
    "command_run",
]

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
        # Full-session historical recall: read-only search/open over prior
        # sessions. Historical content is context, never current evidence.
        "session_search",
        "session_open",
        # Memory providers (M8): native-first search plus an explicitly separate
        # external search whose results are labelled unverified context.
        "memory_search_native",
        "memory_search_external",
        "memory_provider_status",
        # Phase 7: bounded fan-out of independent sub-questions (e.g. "review
        # these five companies"). A research capability, not only a code one.
        "delegate",
    ],
    maxSteps=8,
    # Per-tool CEILING (WS2). Each tool's own declared `timeout_ms` is
    # authoritative; this only bounds a tool that declares more. It is a distinct
    # budget from `runTimeoutMs` (the whole model turn). 30s lets the declared
    # `research_search_news` (30s) run in full instead of being clamped to 20s and
    # timing out, while still bounding any runaway call.
    toolTimeoutMs=30_000,
    runTimeoutMs=120_000,
    # MCP is a user-directed extension surface: the default agent may call the
    # MCP tools the operator has enabled and selected. This opt-in expands ONLY
    # to tools currently registered under the `mcp_` namespace (enabled server +
    # explicitly selected + read-only effect); it does not grant a tool that is
    # merely discovered. Custom agents and skills do NOT set this and keep their
    # exact allowlists.
    allowMcpTools=True,
)

# The read-only repository navigator (Phase 1). A SEPARATE preset, not the
# finance agent widened: its allowlist is ONLY the five read tools. It does NOT
# set `allowMcpTools`, so it keeps its exact, closed allowlist and can never
# reach a finance tool, an MCP tool or any other surface.
CODE_NAVIGATOR = AgentConfig(
    id="code-navigator",
    name="Repository Navigator",
    systemPrompt=CODE_NAVIGATOR_SYSTEM_PROMPT,
    tools=list(CODE_NAVIGATOR_TOOLS),
    maxSteps=10,
    toolTimeoutMs=30_000,
    runTimeoutMs=180_000,
)

# The coding agent (Phase 5). A SEPARATE preset that owns the code tools and NO
# finance tool. Its tool allowlist IS the autonomy boundary: `effective_allowlist`
# narrows it through `code.policy.allowed_tools(autonomy, ...)` before the model
# sees any schema, so at `plan_only` the write/execute tools are simply absent.
# It does NOT set `allowMcpTools` — a coding agent must not inherit the operator's
# MCP reach. The tools listed are the REAL names Phases 1-3 registered.
CODE_AGENT_TOOLS = [
    # Read / navigate (Phase 1)
    "workspace_status", "workspace_list", "workspace_search",
    "workspace_read", "workspace_docs",
    # Change (Phase 2) — effectful; removed at plan_only
    "workspace_patch_apply", "workspace_diff", "workspace_revert",
    # Command broker (Phase 3) — effectful; removed at plan_only
    "command_run",
    # Verification (Phase 4) — the final answer is checked against the ledger.
    # Memory/session recall stays available: read-only context, NOT the finance family.
    "memory", "skill_list", "skill_view", "session_search", "session_open",
    # External actions (Phase 5) — approve_external only, each single-use approved.
    "code_commit", "code_push", "code_open_pr", "code_deploy",
    # Bounded fan-out (Phase 7) — independent sub-tasks in parallel.
    "delegate",
]

CODE_AGENT = AgentConfig(
    id="code-agent",
    name="Eclipse Code Agent",
    systemPrompt=CODE_AGENT_SYSTEM_PROMPT,
    tools=list(CODE_AGENT_TOOLS),
    maxSteps=24,               # a code task legitimately needs more turns than a query
    toolTimeoutMs=120_000,     # a unit-test/build run is slower than a data fetch
    # The AgentConfig run ceiling is 600_000; the Phase 4 repair wall-clock budget
    # is enforced separately inside the loop.
    runTimeoutMs=600_000,
    # Deliberately ABSENT: allowMcpTools.
)

AGENT_PRESETS: dict[str, AgentConfig] = {
    ECLIPSE_AGENT.id: ECLIPSE_AGENT,
    CODE_NAVIGATOR.id: CODE_NAVIGATOR,
    CODE_AGENT.id: CODE_AGENT,
}

DEFAULT_AGENT_ID = ECLIPSE_AGENT.id


def get_agent(agent_id: str) -> AgentConfig:
    agent = AGENT_PRESETS.get(agent_id)
    if agent is None:
        known = ", ".join(AGENT_PRESETS.keys())
        raise ValueError(f"Unknown agent {agent_id!r}. Known: {known}")
    return agent


__all__ = [
    "AGENT_PRESETS",
    "CODE_AGENT",
    "CODE_AGENT_TOOLS",
    "CODE_NAVIGATOR",
    "CODE_NAVIGATOR_TOOLS",
    "DEFAULT_AGENT_ID",
    "ECLIPSE_AGENT",
    "get_agent",
]

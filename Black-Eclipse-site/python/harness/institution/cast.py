"""The Institution preset cast — one source of truth for every role.

An "institution" is a fixed investment-committee pipeline:

    analyst -> debate (bull + bear + chair) -> trader -> risk -> PM

The cast is DATA. It is materialised into `AgentConfig` presets (so each role can
run as a real bot), A2A definitions (so the team layer can route to it), and a
`TeamDefinition` (the durable task graph). No role owns an execution loop, a
store or a model adapter — every stage runs through the existing runtime.

The debate is NOT a vote. It produces a structured record of the strongest long
case, the strongest short case, what they agree on, and what remains unresolved.
Numeric disagreement is never averaged; the existing `team.conflicts` layer
flags it and the reviewer discloses it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

PRESET_ID = "institution"
PRESET_VERSION = 1
PRESET_NAME = "Institution"

#: The common evidence rules every role inherits. Deliberately terse: the same
#: "no fabrication / label UNAVAILABLE / cite source and as-of" rule as the rest
#: of the product.
COMMON_RULES = (
    "Use only retrieved data and cite the source and as-of date/time for every "
    "material figure. If a figure is unavailable, write UNAVAILABLE — never "
    "estimate or fabricate. Prefer JDdS first, then configured providers, then "
    "official web sources. Never average or vote away a disagreement: name it, "
    "state the evidence on each side, and mark it unresolved when it cannot be "
    "settled."
)

#: The tool names every downstream stage may use to read a completed prerequisite
#: memo by its run id (rendered into the task context as `output: <runId>`).
BRIEF_TOOL = "read_run_output"


@dataclass(frozen=True)
class InstitutionRole:
    """One seat at the committee table."""

    key: str
    agent_id: str
    name: str
    label: str
    role: str
    stage: str
    capabilities: tuple[str, ...]
    description: str
    instructions: str
    tools: tuple[str, ...] = field(default_factory=tuple)
    max_steps: int = 6
    run_timeout_ms: int = 180_000


_ANALYST_TOOLS: tuple[str, ...] = (
    "market_get_quote",
    "market_get_ohlcv",
    "fundamentals_get_company_profile",
    "fundamentals_get_financials",
    "research_search",
    "research_retrieve_source",
    "research_search_news",
    "macro_get_series",
    "get_quote",
    "get_historical_prices",
    "get_ohlcv",
    "get_market_cap",
    "get_fx_rate",
    "finance_metrics",
    "finance_series",
    "portfolio_list",
    "portfolio_get",
    "portfolio_calculate_exposure",
    "portfolio_calculate_risk",
    BRIEF_TOOL,
)

_DEBATE_TOOLS: tuple[str, ...] = (
    "market_get_quote",
    "market_get_ohlcv",
    "research_search",
    "research_retrieve_source",
    "research_search_news",
    "macro_get_series",
    "finance_metrics",
    "finance_series",
    BRIEF_TOOL,
)

_CHAIR_TOOLS: tuple[str, ...] = (BRIEF_TOOL,)

_TRADER_TOOLS: tuple[str, ...] = (
    "market_get_quote",
    "get_quote",
    "get_orderbook",
    "get_trades",
    "get_historical_prices",
    "portfolio_list",
    "portfolio_get",
    "portfolio_calculate_exposure",
    BRIEF_TOOL,
)

_RISK_TOOLS: tuple[str, ...] = (
    "portfolio_list",
    "portfolio_get",
    "portfolio_calculate_pnl",
    "portfolio_calculate_exposure",
    "portfolio_calculate_allocation",
    "portfolio_calculate_risk",
    "portfolio_risk_contributions",
    "portfolio_stress_test",
    "portfolio_estimate_inputs",
    "market_get_quote",
    "get_quote",
    "get_historical_prices",
    "finance_metrics",
    "finance_series",
    BRIEF_TOOL,
)

_PM_TOOLS: tuple[str, ...] = (BRIEF_TOOL,)


ROLES: tuple[InstitutionRole, ...] = (
    InstitutionRole(
        key="analyst",
        agent_id="institution-analyst",
        name="Institution Analyst",
        label="Analyst",
        role="analyst",
        stage="analysis",
        capabilities=(
            "financial_analysis",
            "fundamentals",
            "market_data",
            "valuation",
            "web_research",
        ),
        description=(
            "Builds the evidence-backed investment case: business, financials, "
            "valuation, catalysts and the key risks."
        ),
        instructions=(
            "You are the research analyst on an investment committee. Build the "
            "evidence base the rest of the committee will rely on.\n\n"
            "Cover: the business and what actually drives its economics; the last "
            "reported financials (revenue, margins, cash flow, leverage); a "
            "valuation view with the multiples or model used; near-term catalysts; "
            "and the three risks that would invalidate the thesis.\n\n"
            "Every material claim must carry its source and as-of date. Where two "
            "sources disagree, present both and label the disagreement unresolved "
            "rather than choosing silently.\n\n"
            "End with a compact 'ANALYST BRIEF' section: Thesis, Evidence, "
            "Valuation, Catalysts, Risks, Open questions. " + COMMON_RULES
        ),
        tools=_ANALYST_TOOLS,
        max_steps=10,
        run_timeout_ms=300_000,
    ),
    InstitutionRole(
        key="bull",
        agent_id="institution-bull",
        name="Institution Bull",
        label="Bull Case",
        role="debate_bull",
        stage="debate",
        capabilities=("debate", "bull_case", "financial_analysis"),
        description=(
            "Argues the strongest evidence-backed long case. Cannot invent data."
        ),
        instructions=(
            "You are the bull on an investment committee. Read the analyst brief "
            "from the completed prerequisite run, then argue the strongest honest "
            "long case.\n\n"
            "Do not cheerlead. Each argument must rest on a cited figure or event "
            "from the brief or your own retrieval, and must state the condition "
            "under which it fails. Explicitly concede the strongest bear point you "
            "cannot rebut.\n\n"
            "End with: BULL CASE, Key evidence, What would prove me wrong. "
            + COMMON_RULES
        ),
        tools=_DEBATE_TOOLS,
        max_steps=6,
    ),
    InstitutionRole(
        key="bear",
        agent_id="institution-bear",
        name="Institution Bear",
        label="Bear Case",
        role="debate_bear",
        stage="debate",
        capabilities=("debate", "bear_case", "financial_analysis"),
        description=(
            "Argues the strongest evidence-backed short/skeptical case. Cannot invent data."
        ),
        instructions=(
            "You are the bear on an investment committee. Read the analyst brief "
            "from the completed prerequisite run, then argue the strongest honest "
            "skeptical case.\n\n"
            "Do not manufacture pessimism. Each argument must rest on a cited figure "
            "or event from the brief or your own retrieval, and must state the "
            "condition under which it fails. Explicitly concede the strongest bull "
            "point you cannot rebut.\n\n"
            "End with: BEAR CASE, Key evidence, What would prove me wrong. "
            + COMMON_RULES
        ),
        tools=_DEBATE_TOOLS,
        max_steps=6,
    ),
    InstitutionRole(
        key="chair",
        agent_id="institution-chair",
        name="Institution Chair",
        label="Debate Chair",
        role="debate_chair",
        stage="debate",
        capabilities=("debate", "synthesis", "conflict_disclosure"),
        description=(
            "Chairs the debate: records agreement, unresolved disagreements and the "
            "evidence on each side. Never votes or averages."
        ),
        instructions=(
            "You chair an investment-committee debate. Read the bull case and the "
            "bear case from the completed prerequisite runs.\n\n"
            "Produce a DEBATE RECORD with four sections:\n"
            "1. Points of agreement (with the shared evidence).\n"
            "2. Unresolved disagreements — for each, state the bull position, the "
            "bear position, the evidence each relies on, and why it is not settled.\n"
            "3. Facts that are missing and would settle a disagreement (write "
            "UNAVAILABLE where the data does not exist).\n"
            "4. A neutral restatement of the decision the committee now faces.\n\n"
            "You must NOT pick a side, score the debate, or average numbers. If one "
            "side is better supported, say so and cite the evidence; otherwise leave "
            "it unresolved. " + COMMON_RULES
        ),
        tools=_CHAIR_TOOLS,
        max_steps=4,
    ),
    InstitutionRole(
        key="trader",
        agent_id="institution-trader",
        name="Institution Trader",
        label="Trader",
        role="trader",
        stage="trader",
        capabilities=("trade_proposal", "position_sizing", "execution_planning"),
        description=(
            "Turns the committee's debate record into a fully specified trade "
            "proposal. Never executes an order."
        ),
        instructions=(
            "You are the trader on an investment committee. Read the debate record "
            "and the analyst brief, then write a PROPOSAL, not an order.\n\n"
            "Specify: instrument and exchange; direction (long/short); position size "
            "in both currency and % of portfolio; entry style (market/limit and "
            "level); horizon; stop/invalidation level; take-profit or exit plan; and "
            "the exact evidence that justifies each choice.\n\n"
            "Size from the portfolio's actual exposure, not from conviction. If a "
            "required input is missing, write UNAVAILABLE and do not guess. You have "
            "NO order-execution tools and must never claim a trade was placed. "
            + COMMON_RULES
        ),
        tools=_TRADER_TOOLS,
        max_steps=6,
    ),
    InstitutionRole(
        key="risk",
        agent_id="institution-risk",
        name="Institution Risk",
        label="Risk Officer",
        role="risk_officer",
        stage="risk",
        capabilities=(
            "risk_analysis",
            "var",
            "drawdown",
            "concentration",
            "scenario_analysis",
        ),
        description=(
            "Independent risk review of the trade proposal. Holds a veto."
        ),
        instructions=(
            "You are the independent risk officer. Review the trade proposal against "
            "the actual portfolio and the committee's evidence.\n\n"
            "Assess: position and sector concentration after the trade; portfolio "
            "volatility/VaR and drawdown impact; correlation with existing holdings; "
            "liquidity; scenario loss under a stated adverse move; and whether the "
            "stop is consistent with the thesis.\n\n"
            "Ends with a RISK VERDICT: APPROVE, APPROVE WITH LIMITS (state the exact "
            "size/stop limits), or VETO (state the specific breach). A veto may only "
            "be overridden by the PM with a written, evidence-backed reason. "
            + COMMON_RULES
        ),
        tools=_RISK_TOOLS,
        max_steps=8,
        run_timeout_ms=300_000,
    ),
    InstitutionRole(
        key="pm",
        agent_id="institution-pm",
        name="Institution PM",
        label="Portfolio Manager",
        role="portfolio_manager",
        stage="pm",
        capabilities=("decision", "portfolio_management", "risk_oversight"),
        description=(
            "Makes the final committee decision and states the conditions attached "
            "to it."
        ),
        instructions=(
            "You are the portfolio manager chairing the final decision. Read the "
            "analyst brief, the debate record, the trade proposal and the risk "
            "verdict.\n\n"
            "Return a DECISION in exactly one of: APPROVE, APPROVE WITH CONDITIONS, "
            "RESIZE, HOLD, or REJECT. Then state:\n"
            "- the decision and the position/exposure it authorises (or none);\n"
            "- the conditions and invalidation triggers;\n"
            "- how each unresolved disagreement was treated (do not claim it was "
            "settled if it was not);\n"
            "- if you override a risk VETO, the specific evidence-based reason.\n\n"
            "Never place, route or claim to have placed an order. This decision is a "
            "proposal for the operator to approve. " + COMMON_RULES
        ),
        tools=_PM_TOOLS,
        max_steps=4,
    ),
)


ROLE_BY_KEY = {role.key: role for role in ROLES}
ROLE_BY_AGENT = {role.agent_id: role for role in ROLES}


def role_for(agent_id: str) -> Optional[InstitutionRole]:
    return ROLE_BY_AGENT.get(agent_id)


def member_instructions(role: InstitutionRole, objective: str) -> str:
    """The standing instructions a team member receives for one run."""
    return (
        f"{role.instructions}\n\n"
        f"Committee objective for this run: {objective}\n\n"
        "Completed prerequisite memos are listed in your task context as "
        f"`output: <runId>`. Read each with `{BRIEF_TOOL}` before deciding."
    )


__all__ = [
    "BRIEF_TOOL",
    "COMMON_RULES",
    "InstitutionRole",
    "PRESET_ID",
    "PRESET_NAME",
    "PRESET_VERSION",
    "ROLES",
    "ROLE_BY_AGENT",
    "ROLE_BY_KEY",
    "member_instructions",
    "role_for",
]

"""Materialise the Institution cast into the runtime's existing contracts.

Everything here is pure data. `build_team` returns the same `TeamDefinition` the
`/team/runs` route already accepts; `agent_configs` returns the same preset dicts
the A2A layer already installs; `bot_specs` is what the Bots workspace turns into
real `AutomationDefinition` rows through `/api/automations`.
"""

from __future__ import annotations

from typing import Any, Optional

from ..team.model import (
    OptionalFailurePolicy,
    Strictness,
    TeamDefinition,
    TeamMember,
    TeamPolicy,
    TeamSubtask,
)
from .cast import (
    COMMON_RULES,
    PRESET_ID,
    PRESET_NAME,
    PRESET_VERSION,
    ROLES,
    InstitutionRole,
    member_instructions,
)

DEFAULT_OBJECTIVE = (
    "Evaluate the investment case and produce an authorised committee decision."
)
DEFAULT_UNIVERSE = "the user's holdings and watchlist"
DEFAULT_HORIZON = "3-12 months"


def _objective(
    objective: str,
    *,
    universe: str = "",
    horizon: str = "",
    constraints: Optional[list[str]] = None,
) -> str:
    parts = [objective.strip() or DEFAULT_OBJECTIVE]
    parts.append(f"Universe: {universe.strip() or DEFAULT_UNIVERSE}.")
    parts.append(f"Horizon: {horizon.strip() or DEFAULT_HORIZON}.")
    if constraints:
        parts.append("Constraints: " + "; ".join(c for c in constraints if c.strip()) + ".")
    return "\n".join(parts)[:4_000]


def agent_configs() -> list[dict[str, Any]]:
    """`AgentConfig` preset dicts, installed through the A2A preset seam."""
    return [
        {
            "id": role.agent_id,
            "name": role.name,
            "systemPrompt": role.instructions,
            "tools": list(role.tools),
            "maxSteps": role.max_steps,
            "runTimeoutMs": role.run_timeout_ms,
        }
        for role in ROLES
    ]


def a2a_definitions() -> list[dict[str, Any]]:
    """The registry view of each role (capabilities + least privilege)."""
    return [
        {
            "id": role.agent_id,
            "name": role.name,
            "description": role.description,
            "role": role.role,
            "capabilities": list(role.capabilities),
            "tools": list(role.tools),
            "canDelegate": False,
            "status": "ACTIVE",
            "systemInstructions": role.instructions,
        }
        for role in ROLES
    ]


def _member(role: InstitutionRole, objective: str) -> TeamMember:
    return TeamMember(
        agent_id=role.agent_id,
        role=role.role,
        capabilities=list(role.capabilities),
        max_concurrency=1,
        tools=list(role.tools),
        instructions=member_instructions(role, objective),
        label=role.label,
    )


def _subtask(
    sid: str,
    role: InstitutionRole,
    objective: str,
    *,
    depends_on: Optional[list[str]] = None,
    expected: Optional[dict[str, Any]] = None,
    review: bool = False,
) -> TeamSubtask:
    return TeamSubtask(
        id=sid,
        objective=objective,
        capability=role.capabilities[0] if role.capabilities else "",
        assigned_agent_id=role.agent_id,
        depends_on=list(depends_on or []),
        required=True,
        expected_output=expected or {"memo": "string"},
        review=review,
    )


def build_team(
    objective: str = "",
    *,
    universe: str = "",
    horizon: str = "",
    constraints: Optional[list[str]] = None,
    name: str = "Investment Committee",
) -> TeamDefinition:
    """The analyst -> debate -> trader -> risk -> PM task graph."""
    resolved = _objective(
        objective or DEFAULT_OBJECTIVE,
        universe=universe,
        horizon=horizon,
        constraints=constraints,
    )
    by_key = {role.key: role for role in ROLES}
    analyst, bull, bear, chair, trader, risk, pm = (
        by_key["analyst"],
        by_key["bull"],
        by_key["bear"],
        by_key["chair"],
        by_key["trader"],
        by_key["risk"],
        by_key["pm"],
    )

    subtasks = [
        _subtask(
            "analysis",
            analyst,
            f"Produce the analyst brief for the committee.\n\n{resolved}",
            expected={"brief": "string", "evidence_refs": "array"},
        ),
        _subtask(
            "bull_case",
            bull,
            "Read the analyst brief and argue the strongest honest long case.",
            depends_on=["analysis"],
            expected={"case": "string", "conceded_bear_point": "string"},
        ),
        _subtask(
            "bear_case",
            bear,
            "Read the analyst brief and argue the strongest honest skeptical case.",
            depends_on=["analysis"],
            expected={"case": "string", "conceded_bull_point": "string"},
        ),
        _subtask(
            "debate",
            chair,
            "Chair the debate and produce a debate record. Do not vote or average.",
            # `analysis` is listed EXPLICITLY so the chair can read the brief
            # directly (the task context only lists DIRECT prerequisites).
            depends_on=["analysis", "bull_case", "bear_case"],
            expected={
                "agreement": "array",
                "unresolved": "array",
                "missing_facts": "array",
            },
            review=True,
        ),
        _subtask(
            "trade_proposal",
            trader,
            "Turn the debate record into a fully specified trade proposal. "
            "Never execute or claim execution.",
            depends_on=["analysis", "debate"],
            expected={
                "instrument": "string",
                "direction": "string",
                "size": "number",
                "entry": "string",
                "stop": "string",
                "horizon": "string",
            },
        ),
        _subtask(
            "risk_review",
            risk,
            "Independently review the trade proposal against the portfolio and "
            "return a risk verdict (APPROVE / APPROVE WITH LIMITS / VETO).",
            depends_on=["analysis", "debate", "trade_proposal"],
            expected={"verdict": "string", "limits": "array", "breaches": "array"},
            review=True,
        ),
        _subtask(
            "decision",
            pm,
            "Make the final committee decision from the brief, debate record, "
            "proposal and risk verdict. Never place an order.",
            depends_on=["analysis", "debate", "trade_proposal", "risk_review"],
            expected={
                "decision": "string",
                "conditions": "array",
                "risk_override_reason": "string",
            },
            review=True,
        ),
    ]

    return TeamDefinition(
        id=f"{PRESET_ID}-committee",
        name=name[:300],
        objective=resolved,
        agent_id="eclipse-orchestrator",
        members=[_member(role, resolved) for role in ROLES],
        subtasks=subtasks,
        policy=TeamPolicy(
            delegation_enabled=True,
            member_fanout=False,
            # The A2A budget counts every delegation against `depth`, not just
            # nesting, so the committee's seven subtasks need a depth of 7+.
            max_depth=8,
            max_children=len(subtasks),
            max_concurrency=4,
            per_agent_concurrency=1,
            max_tasks=len(subtasks) + 3,
            max_cost=25.0,
            max_runtime_ms=900_000,
            require_review=True,
            review_strictness=Strictness.STRICT,
            optional_failure_policy=OptionalFailurePolicy.REQUIRE_ALL,
            require_approval=False,
        ),
        metadata={
            "presetId": PRESET_ID,
            "presetVersion": PRESET_VERSION,
            "stages": ["analysis", "debate", "trader", "risk", "pm"],
        },
    )


def bot_specs() -> list[dict[str, Any]]:
    """Specs the Bots workspace turns into real automations (one per seat)."""
    specs: list[dict[str, Any]] = []
    for role in ROLES:
        objective = (
            f"{role.description}\n\n{role.instructions}\n\n"
            "This bot is one seat on the Institution committee. To run the whole "
            "committee, use the Institution preset rather than asking this bot "
            "alone."
        )
        specs.append({
            "name": role.name,
            "description": role.description,
            "agentId": role.agent_id,
            "role": role.role,
            "stage": role.stage,
            "objective": objective[:4_000],
            "tags": ["bot", PRESET_ID, role.stage],
        })
    return specs


def descriptor() -> dict[str, Any]:
    """The stable wire view of the preset (no objective required)."""
    return {
        "id": PRESET_ID,
        "name": PRESET_NAME,
        "version": PRESET_VERSION,
        "stages": ["analysis", "debate", "trader", "risk", "pm"],
        "roles": [
            {
                "key": role.key,
                "agentId": role.agent_id,
                "name": role.name,
                "label": role.label,
                "role": role.role,
                "stage": role.stage,
                "description": role.description,
                "capabilities": list(role.capabilities),
            }
            for role in ROLES
        ],
        "rules": COMMON_RULES,
    }


class InstitutionPreset:
    """A tiny handle stored on the service so the layer is discoverable."""

    id = PRESET_ID
    version = PRESET_VERSION

    def build_team(self, *args: Any, **kwargs: Any) -> TeamDefinition:
        return build_team(*args, **kwargs)

    def bot_specs(self) -> list[dict[str, Any]]:
        return bot_specs()

    def descriptor(self) -> dict[str, Any]:
        return descriptor()


__all__ = [
    "DEFAULT_HORIZON",
    "DEFAULT_OBJECTIVE",
    "DEFAULT_UNIVERSE",
    "InstitutionPreset",
    "a2a_definitions",
    "agent_configs",
    "bot_specs",
    "build_team",
    "descriptor",
]

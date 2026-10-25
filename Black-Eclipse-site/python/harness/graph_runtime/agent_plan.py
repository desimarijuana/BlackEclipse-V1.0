"""Structured step planning for the `agent.plan` node.

This is one bounded model call that proposes independent steps for an objective.
It does not run the steps, choose tools or persist anything; `agent.delegate`
executes them on the existing agent run plane, and the graph remains the
authority for ordering and effects.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..model_runtime import get_runtime
from ..schemas import ModelSettings

MAX_STEPS = 8

STEP_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string", "maxLength": 800},
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_STEPS,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 120},
                    "objective": {"type": "string", "maxLength": 1_500},
                    "dependsOn": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": MAX_STEPS,
                    },
                },
                "required": ["title", "objective"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["steps"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You plan work for an agent runtime. Return ONLY the strict JSON object the "
    "schema describes. Break the objective into at most eight steps that can each "
    "be handled by ONE bounded agent turn. Steps that are genuinely independent "
    "must not depend on each other; use `dependsOn` with the titles of earlier "
    "steps for real ordering. Do not invent facts, tools or results. Keep each "
    "objective self-contained and answerable by a single agent run."
)


def validate_step_plan(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a proposal, assigning stable ids and checking dependencies."""
    if not isinstance(raw, dict):
        raise ValueError("the plan is not a JSON object")
    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("the plan has no steps")
    if len(raw_steps) > MAX_STEPS:
        raise ValueError(f"the plan exceeds {MAX_STEPS} steps")

    steps: list[dict[str, Any]] = []
    titles: set[str] = set()
    for index, item in enumerate(raw_steps):
        if not isinstance(item, dict):
            raise ValueError(f"step {index + 1} is not an object")
        title = str(item.get("title") or "").strip()[:120]
        objective = str(item.get("objective") or "").strip()
        if not title or not objective:
            raise ValueError(f"step {index + 1} needs a title and an objective")
        if title in titles:
            raise ValueError(f"duplicate step title {title!r}")
        depends = item.get("dependsOn")
        depends_on = [str(value) for value in depends] if isinstance(depends, list) else []
        unknown = [value for value in depends_on if value not in titles]
        if unknown:
            raise ValueError(
                f"step {title!r} depends on an earlier step that does not exist: "
                f"{', '.join(unknown)}"
            )
        titles.add(title)
        steps.append({
            "id": f"step_{index + 1}",
            "title": title,
            "objective": objective[:1_500],
            "dependsOn": depends_on,
        })
    if len({step["id"] for step in steps}) != len(steps):
        raise ValueError("step ids collided")
    return {
        "rationale": str(raw.get("rationale") or "")[:800],
        "steps": steps,
        "stepCount": len(steps),
    }


async def generate_step_plan(
    objective: str,
    *,
    model_settings: Optional[dict[str, Any]],
) -> dict[str, Any]:
    text = str(objective or "").strip()
    if not text:
        raise ValueError("objective is required")
    if len(text) > 4_000:
        raise ValueError("objective exceeds 4 000 characters")
    if not model_settings:
        raise ValueError(
            "model settings are unavailable for this run; start it as an operator "
            "run with a configured model provider"
        )
    try:
        settings = ModelSettings(**model_settings)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid model settings: {exc}") from exc

    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    response = await get_runtime().generate(
        settings=settings,
        messages=[
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=json.dumps({"objective": text})),
        ],
        task="graph_plan_steps",
        response_schema=STEP_PLAN_SCHEMA,
        timeout_s=90.0,
        temperature=0.1,
    )
    structured = (response.decision or {}).get("structured") or {}
    if not structured.get("ok"):
        reason = structured.get("validationError") or "the model returned no valid JSON plan"
        raise ValueError(f"step plan was not a valid proposal: {reason}")
    plan = validate_step_plan(structured.get("value") or {})
    plan["model"] = {"provider": response.provider_id, "model": response.model_id}
    return plan


__all__ = [
    "MAX_STEPS",
    "STEP_PLAN_SCHEMA",
    "generate_step_plan",
    "validate_step_plan",
]

"""Integration seams between the harness graph and the Model Runtime.

Kept outside `graph.py` so the execution graph (already a ratcheted god-file)
does not grow, and so the mapping from a run to a task profile is testable in
isolation.
"""

from __future__ import annotations

from typing import Any


def task_profile_of(request: Any, agent: Any) -> str:
    """The task profile the ModelRouter scores against for this run (spec §14).

    Explicit per-request context wins; otherwise the agent's id selects a
    sensible profile. Unknown agents fall back to `default` — never a guess.
    """
    context = getattr(getattr(request, "input", None), "context", None) or {}
    override = context.get("taskProfile")
    if isinstance(override, str) and override:
        return override
    agent_id = (getattr(agent, "id", "") or "").lower()
    if "research" in agent_id:
        return "financial_research"
    if "code" in agent_id:
        return "coding"
    return "default"


def runtime_requirements(request: Any) -> dict[str, Any]:
    """Routing requirements a run may carry via its input context (additive).

    Empty by default; the task profile supplies the baseline requirements. Kept
    deliberately small so no existing caller changes behaviour.
    """
    context = getattr(getattr(request, "input", None), "context", None) or {}
    requirements: dict[str, Any] = {}
    for key in ("required", "preferred", "min_context", "reasoning"):
        if key in context:
            requirements[key] = context[key]
    return requirements


def runtime_policy_overrides(request: Any) -> dict[str, Any]:
    """User/workflow routing overrides (spec §44), additive and off by default.

    Read from `input.context.modelPolicy`: `local_only`, `prefer_free`,
    `allowed_providers`, `denied_providers`, `max_cost_per_request`. An explicit
    user override outranks the automatic router; absent means normal routing.
    """
    context = getattr(getattr(request, "input", None), "context", None) or {}
    raw = context.get("modelPolicy")
    if not isinstance(raw, dict):
        return {}
    allowed: dict[str, Any] = {}
    for key in (
        "local_only", "prefer_free", "allowed_providers",
        "denied_providers", "max_cost_per_request",
    ):
        if key in raw:
            allowed[key] = raw[key]
    return allowed


__all__ = ["runtime_policy_overrides", "runtime_requirements", "task_profile_of"]

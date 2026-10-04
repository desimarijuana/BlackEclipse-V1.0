"""Bounded replanning on the ONE execution graph (Phase 11).

    plan → act → observe → **replan** → act

A run already IS a reason-act loop: the agent proposes tool calls, the tools
execute, the model observes. When a step *fails* or the agent *stalls* — it
re-issues the same call it already made — repeating until `maxSteps` is not an
approach. This module lets the loop take an explicit, bounded second look.

It owns ONLY the trigger, the bound, and the revision text. It never builds a
second graph, registry or model adapter: `graph.py` calls it from a `replan`
node that sits on the SAME `tools → agent` edge, and a replan is inert prose the
model may ignore. The path is FLAG-GATED and DEFAULT OFF (`HARNESS_REPLAN_ENABLED`),
so a run without the flag behaves exactly as before.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional

DEFAULT_MAX_REPLANS = 2

ReplanReason = Literal["tool_failures", "stall"]


def replan_enabled() -> bool:
    """Whether the bounded replan path is on. Default OFF (like workflows)."""
    return os.environ.get("HARNESS_REPLAN_ENABLED") in ("1", "true", "True")


@dataclass(frozen=True)
class ReplanBudget:
    """The hard bound on replans in one run. Never crossed."""

    max_replans: int = DEFAULT_MAX_REPLANS

    def exceeded(self, replans: int) -> Optional[str]:
        """The reason the budget is spent ("replans"), or None. Checked first."""
        if replans >= max(0, int(self.max_replans)):
            return "replans"
        return None


def should_replan(
    *,
    replans: int,
    budget: Optional[ReplanBudget],
    step_failures: int,
    stalled: bool,
) -> Optional[ReplanReason]:
    """The pure trigger: a reason to replan, or None.

    A stall is a stronger signal than a failure (the agent is not merely wrong,
    it is repeating itself), so it is preferred when both hold. No budget, a
    spent budget, or a healthy step all yield None.
    """
    if budget is None or budget.exceeded(replans) is not None:
        return None
    if stalled:
        return "stall"
    if step_failures > 0:
        return "tool_failures"
    return None


def build_replan_instruction(
    reason: ReplanReason,
    *,
    failures: Optional[list[dict[str, Any]]] = None,
    stalled_calls: Optional[list[str]] = None,
) -> str:
    """A bounded, deterministic revision directive (inert prose, never code)."""
    lines = [
        "## Revised approach",
        "Your previous step did not make progress. Do not repeat the same action; "
        "revise your approach before calling another tool.",
    ]
    if reason == "tool_failures" and failures:
        named = ", ".join(
            f"{f.get('name')} ({f.get('code') or 'error'})" for f in failures[:5]
        )
        lines.append(f"These tool calls failed: {named}.")
        lines.append(
            "Use the error text to correct the arguments, pick a different tool, "
            "or answer with what you already have. Do not re-issue the identical "
            "failing call."
        )
    if reason == "stall" and stalled_calls:
        lines.append(
            "You repeated the same tool call(s): " + ", ".join(stalled_calls[:5]) + "."
        )
        lines.append(
            "A repeated call returns the same result — use the result you already "
            "have or take a genuinely different step."
        )
    return "\n".join(lines)


# An optional, bounded model-authored plan. The seam takes the run's OWN model
# (no second adapter); a failure returns None so the deterministic directive
# always stands. Tool-less by construction: the model only writes text.
ModelPlanFn = Callable[[str], Awaitable[str]]


async def model_replan(
    model: Any,
    reason: ReplanReason,
    *,
    failures: Optional[list[dict[str, Any]]] = None,
    stalled_calls: Optional[list[str]] = None,
    timeout_s: float = 20.0,
) -> Optional[str]:
    """Optionally ask the run's model for a short revised plan (best-effort).

    Additive to `build_replan_instruction`: any failure or empty reply returns
    None, so the caller keeps the deterministic directive. Never raises.
    """
    import asyncio

    from langchain_core.messages import HumanMessage  # noqa: PLC0415

    deterministic = build_replan_instruction(
        reason, failures=failures, stalled_calls=stalled_calls
    )
    prompt = (
        deterministic
        + "\n\nIn at most four short bullet points, state the revised plan."
    )
    try:
        response = await asyncio.wait_for(
            model.ainvoke([HumanMessage(content=prompt)]), timeout=timeout_s
        )
    except Exception:  # noqa: BLE001 - absence/failure is not an error here
        return None
    text = getattr(response, "content", "")
    if not isinstance(text, str) or not text.strip():
        return None
    return text.strip()[:2000]


__all__ = [
    "DEFAULT_MAX_REPLANS",
    "ModelPlanFn",
    "ReplanBudget",
    "ReplanReason",
    "build_replan_instruction",
    "model_replan",
    "replan_enabled",
    "should_replan",
]

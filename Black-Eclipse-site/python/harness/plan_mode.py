"""The composer's "Plan" preference — lay out a plan before acting.

`planMode` is a per-turn PRESENTATION preference, never a capability grant:

  * ``"on"``  — append a short runtime-context block that tells the model to work
                out a concrete plan, present it to the operator, and wait for
                approval before it starts the work. If the durable task/plan
                tools are on this run's surface it records the plan there;
                otherwise it writes the plan in its reply.
  * ``"off"`` — add nothing; the model acts on its best interpretation.
  * ``"auto"``/absent — add nothing; the base guidance already plans when the
                work is complex enough to warrant it.

This is guidance only. It does not hard-block a tool call, does not widen the
surface, and does not authorize an effect — effectful steps already go through
the approval card. The block lives in `runtime_context`, exactly like the
trading/quant/choices directives, so it is per-run and excluded from the prompt
cache key.
"""

from __future__ import annotations

from typing import Any

PLAN_CONTEXT_KEY = "planMode"

PLAN_MODE_BLOCK = """<plan_mode>
The operator turned on "Plan mode". Before you start the work, plan it and wait
for approval.
1. Work out the goal, the constraints, your assumptions and the ordered steps
   that reach the goal.
2. If the durable task/plan tools are on this turn's surface, record the plan
   with `create_plan` and add its steps with `create_task` (or `decompose_task`),
   using dependencies and acceptance criteria where they genuinely matter.
   Otherwise, write the numbered plan directly in your reply.
3. Present the plan: the goal, each step and what it will produce, and any
   assumption or open choice that would change the result. Keep it short and
   concrete.
4. Then STOP and wait. Do not call `run_plan`, do not mark tasks IN_PROGRESS,
   and do not start effectful work until the operator approves the plan or asks
   you to proceed. Read-only inspection needed to make the plan correct is fine.
Never invent facts, tools, steps or results. If the objective is genuinely
unclear, state the assumption your plan rests on instead of guessing silently.
</plan_mode>"""


def plan_mode_block() -> str:
    """The per-run prompt block. A function so callers never mutate the text."""
    return PLAN_MODE_BLOCK


def apply_plan_context(request: Any, allowed: Any, runtime_context: str) -> str:
    """Append the Plan block for a ``planMode: "on"`` turn. Never raises."""
    try:
        context = getattr(request.input, "context", None)
        mode = context.get(PLAN_CONTEXT_KEY) if isinstance(context, dict) else None
        if mode != "on":
            return runtime_context
        return f"{runtime_context}\n\n{PLAN_MODE_BLOCK}"
    except Exception:  # noqa: BLE001 - guidance must never break the run
        return runtime_context


__all__ = [
    "PLAN_CONTEXT_KEY",
    "PLAN_MODE_BLOCK",
    "apply_plan_context",
    "plan_mode_block",
]

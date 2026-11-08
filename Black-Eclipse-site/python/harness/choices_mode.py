"""The composer's "Choices" preference — ask with selectable options up front.

`choicesMode` is a per-turn PRESENTATION preference, never a capability grant:

  * ``"on"``  — append a short runtime-context block that tells the model to use
                the existing ``clarify`` tool BEFORE it starts work whenever the
                request leaves a meaningful choice open (scope, horizon, entity,
                output format, next step). The operator gets a question card with
                2–4 clickable options and the run resumes with the answer.
  * ``"off"`` — add nothing; the model acts on its best interpretation.
  * ``"auto"``/absent — add nothing; the base prompt's act-don't-ask guidance
                already allows a clarification when the ambiguity changes the
                deliverable.

The block is appended ONLY when ``clarify`` is actually on this run's tool
surface, so the model is never told to call a tool it does not have. It is
per-run and excluded from the prompt cache key (it lives in `runtime_context`,
exactly like the trading/quant directives).
"""

from __future__ import annotations

from typing import Any

CHOICES_CONTEXT_KEY = "choicesMode"

CHOICES_MODE_BLOCK = """<choices_mode>
The operator turned on "Choices". Before starting the work, when the request
leaves a meaningful choice open — scope, time horizon, which entity or market,
the output format, or which next step to take — call `clarify` ONCE with 2–4
short, concrete options and mark the one you recommend. Put the reason the
choice matters in `context`. The run pauses on the question card and resumes
with the answer in the same turn, so ask early and keep the question to one
line. Do not ask when the request is already specific, never ask more than one
question per turn, never ask something a tool can resolve, and never use
`clarify` to ask for permission — effectful steps already use the approval card.
</choices_mode>"""


def choices_mode_block() -> str:
    """The per-run prompt block. A function so callers never mutate the text."""
    return CHOICES_MODE_BLOCK


def apply_choices_context(request: Any, allowed: Any, runtime_context: str) -> str:
    """Append the Choices block for a ``choicesMode: "on"`` turn. Never raises."""
    try:
        context = getattr(request.input, "context", None)
        mode = context.get(CHOICES_CONTEXT_KEY) if isinstance(context, dict) else None
        if mode != "on":
            return runtime_context
        if allowed is not None and "clarify" not in set(allowed):
            return runtime_context
        return f"{runtime_context}\n\n{CHOICES_MODE_BLOCK}"
    except Exception:  # noqa: BLE001 - guidance must never break the run
        return runtime_context


__all__ = [
    "CHOICES_CONTEXT_KEY",
    "CHOICES_MODE_BLOCK",
    "apply_choices_context",
    "choices_mode_block",
]

"""The `clarify` tool — ask the operator one question instead of guessing.

Some turns are genuinely ambiguous in a way that changes the deliverable, or
they reach a consequential step whose intent is unclear. The agent can call
`clarify` ONCE with a short question and a small set of concrete options. The
run then pauses on the SAME in-process gate approvals use
(`mcp/approvals.py::wait_for_decision`), the chat shows a question card, and the
operator's answer or free text is returned to the model as the tool result — the
agent continues in the same step with the answer.

This is deliberately NOT an authorization: a clarification is a `read` tool, and
an answer never approves an effect. Effectful steps still require the existing
single-use, digest-bound approval. The store row is a `clarification` kind with
its own `answer` column, so the two flows share the gate but cannot be confused.

Without an interactive client (a bot, a scheduled/background run), the tool does
not block and never fabricates an answer: it returns a structured
`answered: false` result so the model can proceed with a stated assumption.
"""

from __future__ import annotations

import json
from typing import Any

from .tools import ToolContext, ToolDefinition, ToolRegistry

CLARIFY_TOOLS = ["clarify"]

# The longest an interactive run waits for a human answer. The registry's own
# per-tool ceiling is 120s; keep the wait below it so the handler returns its
# structured timeout result instead of being hard-killed.
_MAX_WAIT_S = 110.0
_MAX_OPTIONS = 6
_MAX_QUESTION_CHARS = 1_200
_MAX_CONTEXT_CHARS = 800


def _no_answer(reason: str, *, guidance: str, clarification_id: str = "") -> tuple[str, dict[str, Any]]:
    return (
        json.dumps(
            {"answered": False, "reason": reason, "guidance": guidance},
            ensure_ascii=False,
        ),
        {"clarificationId": clarification_id, "answered": False, "reason": reason},
    )


async def _clarify(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    question = str(args.get("question") or "").strip()[:_MAX_QUESTION_CHARS]
    if not question:
        return "A clarification needs a question.", {"answered": False, "reason": "question_required"}

    options = [
        str(option).strip()[:200]
        for option in (args.get("options") or [])
        if str(option).strip()
    ][:_MAX_OPTIONS]
    context = str(args.get("context") or "").strip()[:_MAX_CONTEXT_CHARS]
    recommended = str(args.get("recommended") or "").strip()[:200]

    store = getattr(ctx, "approvals", None)
    interactive = bool(getattr(ctx, "pause_for_approval", False))
    if store is None or not interactive:
        return _no_answer(
            "no_interactive_user",
            guidance=(
                "No interactive user is available to answer. Proceed with the most "
                "reasonable interpretation, label it as an assumption, and never "
                "invent an answer on the user's behalf."
            ),
        )

    try:
        pending = store.request_clarification(
            question=question,
            options=options,
            context=context,
            run_id=str(getattr(ctx, "run_id", "") or "chat"),
        )
    except Exception as exc:  # noqa: BLE001 - asking must never crash a run
        return _no_answer(
            "clarification_unavailable",
            guidance=(
                "The clarification store was unavailable. Proceed with the most "
                "reasonable interpretation and state the assumption explicitly."
            ),
        )
    clarification_id = str(pending.get("id") or "")

    emitter = getattr(ctx, "emitter", None)
    if emitter is not None:
        try:
            await emitter.emit(
                "clarification.requested",
                {
                    "clarificationId": clarification_id,
                    "question": question,
                    "context": context,
                    "options": options,
                    "recommended": recommended,
                    "allowCustom": bool(args.get("allow_custom", True)),
                },
            )
        except Exception:  # noqa: BLE001 - the card is advisory to the wait
            pass

    wait_s = min(
        _MAX_WAIT_S,
        float(getattr(ctx, "approval_timeout_s", 900.0) or 900.0),
    )
    decided = await store.wait_for_decision(clarification_id, wait_s)

    answered = bool(decided and decided.get("status") == "approved")
    answer = str((decided or {}).get("answer") or "") if answered else ""

    if emitter is not None:
        try:
            await emitter.emit(
                "clarification.answered",
                {"clarificationId": clarification_id, "answered": answered},
            )
        except Exception:  # noqa: BLE001
            pass

    if not answered:
        return _no_answer(
            "timeout",
            guidance=(
                "No answer arrived in time. Proceed with your best interpretation "
                "and state the assumption explicitly; do not ask again this run."
            ),
            clarification_id=clarification_id,
        )

    if not answer:
        return (
            json.dumps(
                {
                    "answered": True,
                    "answer": "",
                    "guidance": (
                        "The user left the decision to you. Proceed with the "
                        "recommended interpretation and state it plainly."
                    ),
                },
                ensure_ascii=False,
            ),
            {"clarificationId": clarification_id, "answered": True, "answer": ""},
        )

    return (
        json.dumps({"answered": True, "answer": answer}, ensure_ascii=False),
        {"clarificationId": clarification_id, "answered": True, "answer": answer},
    )


def register_clarify_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="clarify",
            description=(
                "Ask the user ONE short question when a request is genuinely "
                "ambiguous in a way that changes what you will produce, or before "
                "a consequential step whose intent is unclear. Provide 2-4 concise "
                "options and mark the one you recommend. The run pauses until the "
                "user picks an option or types an answer, then you continue with "
                "it. Do not ask about anything you can resolve with a tool or an "
                "obvious default; never use this to ask for permission."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The one question to ask, in plain language.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional one-sentence reason the choice matters.",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-4 short, concrete choices (optional).",
                    },
                    "recommended": {
                        "type": "string",
                        "description": "Optional label of the option you recommend.",
                    },
                    "allow_custom": {
                        "type": "boolean",
                        "description": "Whether the user may type a free-text answer (default true).",
                    },
                },
                "required": ["question"],
            },
            handler=_clarify,
            interactive=True,
            permission="read",
            risk="none",
            # A human answer is slow and must not be cut off by the agent's
            # ordinary tool ceiling; the handler bounds itself to _MAX_WAIT_S.
            timeout_ms=115_000,
            long_running=True,
            version="1.0.0",
        )
    )


__all__ = ["CLARIFY_TOOLS", "register_clarify_tools"]

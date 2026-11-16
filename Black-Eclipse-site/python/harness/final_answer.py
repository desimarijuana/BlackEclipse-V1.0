"""Final-answer settlement: bounded recovery, C4 settlement and the final state.

Extracted from `graph.py` so the ONE agent loop stays under its size ratchet
without weakening the contract. The graph still owns the loop and the edges;
this module owns the branch that runs when the model returns no tool calls.

Nothing here widens authority: `allowed` is the run's advertised surface, and a
recovery directive names only tools already on it. A refusal after the ladder is
exhausted is accepted.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from langchain_core.messages import HumanMessage

from .answer_guard import (
    MAX_ANSWER_RECOVERIES,
    build_recovery_instruction,
    is_bare_refusal,
    recovery_event,
    recovery_reason,
    render_fallback_block,
)


async def maybe_recover(
    *,
    request: Any,
    emitter: Any,
    state: dict[str, Any],
    final_text: str,
    allowed: Optional[set[str]],
    step: int,
    max_steps: int,
) -> Optional[tuple[str, int]]:
    """The deterministic directive + next attempt count, or None.

    Emits `answer.recovery_started` when a directive is issued and
    `answer.recovery_exhausted` when the bound has been spent on a refusal.
    """
    recoveries = int(state.get("answer_recoveries", 0) or 0)
    tools_used = list(state.get("tools_used") or [])
    unavailable_tools = list(state.get("unavailable_tools") or [])
    reason = recovery_reason(
        query=request.input.query,
        answer=final_text,
        tools_used=tools_used,
        available=allowed,
        recoveries=recoveries,
        step=step,
        max_steps=max_steps,
    )
    if reason:
        instruction = build_recovery_instruction(
            query=request.input.query,
            answer=final_text,
            tools_used=tools_used,
            available=allowed,
            unavailable_tools=unavailable_tools,
            attempt=recoveries + 1,
        )
        if instruction:
            await emitter.emit(
                "answer.recovery_started",
                recovery_event(
                    attempt=recoveries + 1, answer=final_text,
                    tools_used=tools_used, available=allowed,
                ),
            )
            return instruction, recoveries + 1
    if recoveries >= MAX_ANSWER_RECOVERIES and is_bare_refusal(final_text):
        await emitter.emit(
            "answer.recovery_exhausted",
            {"attempts": recoveries, "reason": "blocked_answer"},
        )
    return None


async def note_final_answer(
    emitter: Any, recoveries: int, final_text: str,
) -> None:
    """Record that a recovered run actually produced an accepted answer."""
    if not recoveries:
        return
    await emitter.emit(
        "answer.recovered",
        {"attempts": recoveries, "answerChars": len(final_text)},
    )


def with_fallback_context(
    runtime_context: str, allowed: Optional[set[str]], query: str,
) -> str:
    """Append the per-run fallback ladder (or the source restriction)."""
    block = render_fallback_block(allowed, query)
    if not block:
        return runtime_context
    return f"{runtime_context}\n\n{block}"


async def finish_turn(
    *,
    request: Any,
    emitter: Any,
    state: dict[str, Any],
    response: Any,
    step: int,
    final_text: str,
    usage_state: dict[str, int],
    plan: Any,
    checks: Any,
    max_steps: int,
    max_tool_calls: Optional[int],
    token_budget: Optional[int],
    budget_spent: bool,
    token_budget_spent: bool,
    finalizing: bool,
    allowed: Optional[set[str]],
    plan_step_id: Optional[str],
    emit_step_completed: Callable[..., Any],
    write_checkpoint: Callable[..., Any],
) -> dict[str, Any]:
    """Settle a no-tool-call turn and return the next graph state.

    Covers the empty-final budget failure, bounded answer recovery, the C4
    evidence settlement and the accepted final state — exactly the behavior the
    graph had inline, now in one testable function.
    """
    # A forced final turn that produced no text is not an answer. Report the
    # honest failure rather than a blank "completed".
    if finalizing and not final_text.strip():
        if budget_spent:
            message = f"Reached the {max_tool_calls}-tool-call limit without a final answer."
            code = "TOOL_BUDGET_EXCEEDED"
        elif token_budget_spent:
            message = f"Reached the {token_budget}-token budget without a final answer."
            code = "TOKEN_BUDGET_EXCEEDED"
        else:
            message = f"Reached the maximum of {max_steps} steps without a final answer."
            code = "MAX_STEPS_EXCEEDED"
        try:
            from .event_sequence import append_durable  # noqa: PLC0415

            append_durable(request.runId, "skill.tool_budget_exceeded", {
                "maxToolCalls": max_tool_calls,
                "toolCalls": state.get("tool_calls", 0),
            })
        except Exception:  # noqa: BLE001 - audit must not break the run
            pass
        await emitter.emit("run.failed", {"error": {"code": code, "message": message}})
        await emit_step_completed(
            step, status="failed", error={"code": code, "message": message},
        )
        return {
            **state, **usage_state, "step": step,
            "error": {"code": code, "message": message},
        }

    # Bounded answer recovery: a bare refusal is a routing fact, not a verdict.
    # A FORCED final turn (steps/tool/token budget spent) cannot call a tool, so
    # recovery would only spend another turn saying the same thing.
    recovery = None if finalizing else await maybe_recover(
        request=request, emitter=emitter, state=state, final_text=final_text,
        allowed=allowed, step=step, max_steps=max_steps,
    )
    if recovery is not None:
        instruction, recoveries = recovery
        recovered_state: dict[str, Any] = {
            **state,
            **usage_state,
            "step": step,
            "messages": [
                *state["messages"], response,
                HumanMessage(content=instruction),
            ],
            "answer_recoveries": recoveries,
            "recovery_pending": True,
            "final": None,
        }
        await emit_step_completed(
            step, status="ok",
            tool_calls=int(state.get("tool_calls", 0) or 0),
            tool_errors=int(state.get("tool_errors", 0) or 0),
        )
        return recovered_state

    # C4: record the answer's checkable claims, verify them against this step's
    # evidence, and divert through one bounded replan when a verifier rejects a
    # claim. No plan => exact old behavior.
    replan_needed: Optional[dict[str, Any]] = None
    if plan is not None:
        try:
            replan_needed = plan.finish_answer(
                request.runId, final_text, checks=checks,
            )
        except Exception:  # noqa: BLE001 - plan settlement must not break a run
            pass
    completed: dict[str, Any] = {
        **state,
        **usage_state,
        "step": step,
        "messages": [*state["messages"], response],
        "final": final_text,
        "replan_needed": replan_needed,
        "plan_step_id": plan_step_id,
    }
    await note_final_answer(
        emitter, int(state.get("answer_recoveries", 0) or 0), final_text,
    )
    await write_checkpoint("agent_final", completed)
    await emit_step_completed(
        step, status="ok",
        tool_calls=int(state.get("tool_calls", 0) or 0),
        tool_errors=int(state.get("tool_errors", 0) or 0),
    )
    return completed


__all__ = [
    "finish_turn",
    "maybe_recover",
    "note_final_answer",
    "with_fallback_context",
]

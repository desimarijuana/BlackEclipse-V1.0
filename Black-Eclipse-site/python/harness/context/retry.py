"""One bounded retry when the model rejects a request for context length.

Kept out of `graph.py` (size ratchet) and deliberately narrow: only the history
allowance changes, exactly one retry is attempted, and a step>1 overflow is
recovered only when the effect ledger says no tool outcome is unconfirmed.
"""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage

from ..history import _bounded_history, _dropped_context_block
from ..run_recovery import recover_overflow_state


async def retry_with_tighter_budget(
    request: RunRequest,
    emitter: RunEmitter,
    final_state: dict[str, Any],
    *,
    base_budget: Any,
    overrides: dict[str, Any],
    system_prompt: str,
    profile_block: str,
    skill_manifest: str,
    memory_block: str,
    runtime_context: str,
    memory_service: Optional[Any],
    allowed: Optional[set[str]],
    registry: ToolRegistry,
    invoke: Any,
    anchor: Optional[Any] = None,
    history_chars: int = 0,
    recover_context: Optional[Any] = None,
    budget_fn: Any = None,
) -> tuple[dict[str, Any], Optional[Any]]:
    """Retry ONCE with a materially tighter history allowance.

    Only the history allowance changes: the system prompt, tools, per-run blocks
    and side-effecting tools are NOT re-run differently. An unknown-window budget
    (inert) is unaffected by `tighter`, so overflow on an unknown window fails
    honestly with no pointless second attempt. Returns
    `(final_state, retry_budget_or_None)`.
    """
    if not base_budget.effective:
        return final_state, None
    if budget_fn is None:
        return final_state, None
    # A later step (step>1 means the first call already completed) is recoverable
    # only from a completed-work checkpoint with no unconfirmed effect. The
    # checkpoint carries the messages and counters; the effect ledger and the
    # idempotency ledger ensure no tool is re-executed. One retry, never a loop.
    if int(final_state.get("step") or 1) > 1:
        if recover_context is None:
            return final_state, None
        store, run_id, overflow_emitter, invoke_again = recover_context
        recovered = await recover_overflow_state(
            store, run_id, overflow_emitter, invoke_again, final_state,
            window=getattr(base_budget, "window", None),
            max_chars=getattr(base_budget, "max_history_chars", None),
        )
        if not recovered:
            return final_state, None
        return recovered, base_budget
    tighter_budget = budget_fn(
        request, allowed, registry, system_prompt, profile_block, skill_manifest,
        memory_block, "", runtime_context=runtime_context, overrides=overrides, tighter=True,
        anchor=anchor, history_chars=history_chars,
    )
    kept, _dropped = _bounded_history(request, tighter_budget)
    base_kept_count = len(_bounded_history(request, base_budget)[0])
    # Nothing left to remove: a second attempt would be identical, so do not make
    # one. The honest CONTEXT_OVERFLOW stands.
    if len(kept) >= base_kept_count:
        return final_state, None
    kept_messages = [
        HumanMessage(content=t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in kept
    ]
    # Re-extract the (now larger) dropped window and carry it in the retry so the
    # attempt is materially smaller than the first, not merely a re-ask.
    _msgs, tighter_dropped_block, _dt = await _dropped_context_block(
        request, memory_service, emitter, tighter_budget, emit=False,
    )
    await emitter.emit("context.retry", {
        "reason": "context_overflow",
        "windowKnown": bool(tighter_budget.window_known),
        "keptTurns": len(kept),
        "maxHistoryChars": tighter_budget.max_history_chars,
    })
    retried_state = await invoke(kept_messages, tighter_dropped_block)
    return retried_state, tighter_budget


__all__ = ["retry_with_tighter_budget"]

"""History bounding + the inert dropped-context block, split out of `graph.py`.

`graph.py` is at its file-size ratchet, so the pure history-bounding helpers and
the dropped-context extraction live here. `graph.py` re-exports the names its
callers and tests use, so nothing else changes. This module owns no state.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .events import RunEmitter
from .model_stream import message_text as _text
from .models import build_chat_model
from .model_runtime import get_runtime
from .schemas import RunRequest

MAX_HISTORY_TURNS = 20
MAX_HISTORY_CHARS = 40_000


def _bounded_history(
    request: RunRequest, budget: Optional[Any] = None,
) -> tuple[list[Any], list[Any]]:
    """Return `(kept, dropped)` turns under the history bound.

    `kept` is the oldest-first list actually prompted; `dropped` is the prefix
    the bound removed. A history under the bound drops nothing — `dropped` is
    empty and the caller must behave exactly as before.

    The bound comes from the per-run measured `budget` when it is effective (the
    resolved model's window is known); otherwise it falls back to the module
    constants. The fallback is byte-for-byte today's behaviour, which is the
    safety property for an unknown window.
    """
    history = request.input.history or []
    if budget is not None and getattr(budget, "effective", False):
        max_turns = int(getattr(budget, "max_history_turns", MAX_HISTORY_TURNS))
        max_chars = int(getattr(budget, "max_history_chars", MAX_HISTORY_CHARS))
    else:
        max_turns = MAX_HISTORY_TURNS
        max_chars = MAX_HISTORY_CHARS
    if not history:
        return [], []
    trimmed = list(history[-max_turns:]) if max_turns > 0 else []
    dropped = list(history[: max(0, len(history) - max_turns)]) if max_turns > 0 else list(history)
    # Also cap total characters, dropping oldest turns first.
    total = sum(len(t.content) for t in trimmed)
    while trimmed and total > max_chars:
        total -= len(trimmed[0].content)
        dropped.append(trimmed[0])
        trimmed = trimmed[1:]
    return trimmed, dropped


def _history_messages(request: RunRequest, budget: Optional[Any] = None) -> list[BaseMessage]:
    """Prior conversation turns, oldest first, bounded so a long chat cannot
    blow the context window. Keeps the MOST RECENT turns when trimming."""
    trimmed, _dropped = _bounded_history(request, budget)
    return [
        HumanMessage(content=t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in trimmed
    ]


async def _dropped_context_block(
    request: RunRequest,
    memory_service: Optional[Any],
    emitter: RunEmitter,
    budget: Optional[Any] = None,
    *,
    emit: bool = True,
) -> tuple[list[BaseMessage], str, list[Any]]:
    """The bounded history messages plus an inert dropped-context block ("").

    Returns `(messages, block, dropped_turns)`. When the history is under the
    bound nothing is dropped, so no block is produced and the message list is
    byte-identical to the pre-change behaviour. Extraction is deterministic-first
    and produces INERT candidates only. It is fail-closed: if extraction cannot
    complete, NO block is emitted (never a lossy summary) and an honest event is
    recorded. Extraction never blocks or fails the run.

    `emit=False` suppresses the extraction event, used when `execute_run`
    re-derives the history after measuring the dropped block's own cost (so the
    event is emitted exactly once).
    """
    kept, dropped = _bounded_history(request, budget)
    messages = [
        HumanMessage(content=t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in kept
    ]
    if not dropped:
        return messages, "", dropped
    try:
        from .eclipse_memory.dropped_context import (  # noqa: PLC0415
            MAX_ITEMS,
            DroppedTurn,
            extract_dropped_context,
            render_dropped_context_block,
        )

        settings: dict[str, Any] = {}
        if memory_service is not None:
            try:
                settings = memory_service.policy.get_all()
            except Exception:  # noqa: BLE001 - policy read failure is not fatal
                settings = {}
        result = extract_dropped_context(
            [DroppedTurn(role=t.role, content=t.content) for t in dropped],
            settings=settings, user_id=request.userId,
        )
        model_used = False
        # Optional, policy-gated model-assisted extraction. It is additive to the
        # deterministic pass, inert, bounded, and fail-closed: any failure leaves
        # the deterministic result untouched and emits no lossy summary.
        if settings.get("dropped_context_model_extraction") and memory_service is not None:
            try:
                model_items = await _model_extract_dropped(
                    request, [DroppedTurn(role=t.role, content=t.content) for t in dropped],
                )
                if model_items:
                    merged = list(result.items)
                    seen = {(i.action, i.content) for i in merged}
                    for item in model_items:
                        key = (item.action, item.content)
                        if key not in seen:
                            merged.append(item)
                            seen.add(key)
                    result.items = merged[:MAX_ITEMS]
                    model_used = True
            except Exception:  # noqa: BLE001 - model extraction must never break the run
                model_used = False
        block = render_dropped_context_block(result)
        try:
            if emit:
                await emitter.emit(
                    "memory.dropped_context_extracted",
                    {
                        "droppedTurns": len(dropped),
                        "scanned": result.scanned,
                        "candidates": len(result.items),
                        "emitted": bool(block),
                        "ok": result.ok,
                        "modelAssisted": model_used,
                        "reason": result.reason or None,
                    },
                )
        except Exception:  # noqa: BLE001
            pass
        return messages, block, dropped
    except Exception as exc:  # noqa: BLE001 - extraction must never break a run
        try:
            if emit:
                await emitter.emit("memory.dropped_context_failed", {"error": str(exc), "droppedTurns": len(dropped)})
        except Exception:  # noqa: BLE001
            pass
        # Fail closed: emit no block at all, carry on.
        return messages, "", dropped


async def _model_extract_dropped(
    request: RunRequest, turns: list[Any],
) -> list[Any]:
    """Optionally ask the run's own model for INERT candidates from dropped turns.

    Uses the SAME model/provider the run already resolved (no new dependency, no
    extra client). Bounded by a short timeout and the extractor's own item cap.
    Any failure returns [] — the deterministic extraction is unaffected and the
    caller emits no lossy summary. Never raises to the caller.
    """
    from .eclipse_memory.dropped_context import (  # noqa: PLC0415
        build_extraction_prompt,
        parse_extraction_response,
    )

    prompt = build_extraction_prompt(turns)
    if not prompt:
        return []
    try:
        # Build through the ModelRuntime (task=background_task: a cheap model is
        # appropriate for extraction) while preserving this module's test seam.
        _runtime = get_runtime()
        _resolution = _runtime.resolve_for_run(request.modelSettings, task="background_task")
        model = _runtime.build(
            _resolution.settings, builder=build_chat_model, adapter=_resolution.adapter
        )
        response = await asyncio.wait_for(
            model.ainvoke([HumanMessage(content=prompt)]), timeout=20.0,
        )
    except Exception:  # noqa: BLE001 - absence/failure is not an error here
        return []
    text = _text(response)
    parsed = parse_extraction_response(text)
    return parsed.items if parsed.ok else []


__all__ = [
    "MAX_HISTORY_CHARS",
    "MAX_HISTORY_TURNS",
    "_bounded_history",
    "_dropped_context_block",
    "_history_messages",
    "_model_extract_dropped",
]

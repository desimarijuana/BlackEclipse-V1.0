"""Map harness run events to OpenBB Workspace SSE objects.

OpenBB expects a small, fixed vocabulary (`message_chunk`, `reasoning_step`, …).
The harness emits far more detail. Translating 1→0..n keeps the Workspace
transcript readable: high-frequency progress events are swallowed, text is
delivered as chunks, and tool activity becomes a one-line reasoning step.

Safety: the mapper **whitelists** the fields it forwards. It never serializes a
whole event, so a credential or an attachment payload that happens to be in one
cannot leak into the Workspace transcript.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

MAX_CHUNK_CHARS = 4_000
MAX_STEP_CHARS = 200

#: Harness event types that carry visible assistant text.
TEXT_EVENTS = frozenset({"text_delta", "model.delta", "assistant.delta", "token"})
#: Events that describe an action rather than an answer.
STEP_EVENTS = frozenset({
    "tool_call", "tool.started", "tool_call_started",
    "tool_result", "tool.completed", "tool_call_completed",
    "step.started", "step.completed",
})
#: Events worth surfacing as a status line rather than dropping silently.
STATUS_EVENTS = frozenset({"run.failed", "error", "run.cancelled", "memory.compacted"})


def _clip(text: Any, limit: int) -> str:
    value = str(text or "")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _reasoning_step(content: str) -> dict[str, Any]:
    return {"type": "reasoning_step", "content": _clip(content, MAX_STEP_CHARS)}


def map_event(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Translate one harness event into zero or more OpenBB SSE objects."""
    if not isinstance(event, Mapping):
        return []
    kind = str(event.get("type") or event.get("event") or "")
    data = event.get("data") if isinstance(event.get("data"), Mapping) else event
    if kind in TEXT_EVENTS:
        text = data.get("text") or data.get("delta") or data.get("content") or ""
        if not str(text):
            return []
        return [{"type": "message_chunk", "content": _clip(text, MAX_CHUNK_CHARS)}]
    if kind in STEP_EVENTS:
        name = str(data.get("name") or data.get("tool") or data.get("toolName") or "step")
        status = str(data.get("status") or "")
        verb = "called" if kind.startswith("tool_call") or kind.startswith("tool.started") else "finished"
        suffix = f" ({status})" if status else ""
        return [_reasoning_step(f"{verb} {name}{suffix}")]
    if kind in STATUS_EVENTS:
        message = data.get("message") or data.get("error") or kind
        return [_reasoning_step(f"{kind}: {_clip(message, MAX_STEP_CHARS)}")]
    return []


def map_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for event in events:
        out.extend(map_event(event))
    return out


def sse_lines(objects: Iterable[Mapping[str, Any]]) -> list[str]:
    """Serialize mapped objects as Server-Sent Event `data:` lines."""
    import json

    return [f"data: {json.dumps(obj, ensure_ascii=False)}\n\n" for obj in objects]


__all__ = ["STEP_EVENTS", "STATUS_EVENTS", "TEXT_EVENTS", "map_event", "map_events", "sse_lines"]

"""Checkpoint (de)serialization, extracted from `graph.py` (size ratchet).

A checkpoint payload is a bounded REFERENCE to a run's progress, never a second
copy of the trace. These helpers are pure: they serialize the most recent
messages (truncating each), restore them, and build a minimal terminal payload.
`graph.py` owns WHEN a checkpoint is written; this module owns the encoding.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import (
    BaseMessage,
    messages_from_dict,
    messages_to_dict,
)

# A checkpoint payload is a bounded reference, not a second trace. Serialized
# messages are capped so a pathological run cannot bloat the checkpoint table.
MAX_CHECKPOINT_MESSAGES = 60
MAX_CHECKPOINT_MESSAGE_CHARS = 12_000


def serialize_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """Serialize the conversation tail for a checkpoint (bounded).

    Keeps the most recent messages, truncating each message's text, so a resume
    has enough to continue without duplicating the whole trace.
    """
    tail = messages[-MAX_CHECKPOINT_MESSAGES:]
    out: list[dict[str, Any]] = []
    for msg in tail:
        try:
            dumped = messages_to_dict([msg])[0]
        except Exception:  # noqa: BLE001 - an unserializable message is skipped
            continue
        data = dumped.get("data", {})
        if isinstance(data.get("content"), str) and len(data["content"]) > MAX_CHECKPOINT_MESSAGE_CHARS:
            data["content"] = data["content"][:MAX_CHECKPOINT_MESSAGE_CHARS]
        out.append(dumped)
    return out


def restore_messages(serialized: list[dict[str, Any]]) -> list[BaseMessage]:
    """Rebuild a message list from a checkpoint's serialized tail."""
    if not serialized:
        return []
    try:
        return list(messages_from_dict(serialized))
    except Exception:  # noqa: BLE001 - an unreadable payload yields no seed
        return []


def checkpoint_payload_of(state: dict[str, Any]) -> dict[str, Any]:
    """A minimal terminal checkpoint payload from a final graph state."""
    return {
        "step": state.get("step", 0),
        "toolCalls": state.get("tool_calls", 0),
        "toolErrors": state.get("tool_errors", 0),
        "messages": serialize_messages(state.get("messages", []) or []),
    }


__all__ = [
    "MAX_CHECKPOINT_MESSAGES",
    "MAX_CHECKPOINT_MESSAGE_CHARS",
    "serialize_messages",
    "restore_messages",
    "checkpoint_payload_of",
]

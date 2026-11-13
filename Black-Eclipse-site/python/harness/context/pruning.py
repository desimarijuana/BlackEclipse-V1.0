"""Prune old tool output before summarising (W2).

Tool output is the fastest-growing part of a long run. The first ladder stage
replaces old tool text with a small handle-shaped placeholder. The full text is
already in `ToolOutputStore` when it was truncated; this stage never prunes the
last few results or a result carrying evidence/provenance.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import ToolMessage

# Names whose results carry evidence/provenance and must not be pruned.
_PROTECTED_PREFIXES = (
    "research_", "market_", "finance_", "retrieval_", "quant_", "portfolio_",
    "ledger_", "trade_", "source", "citation", "artifact", "document_",
)
_EVIDENCE_HINTS = re.compile(
    r'"(handles|sourceUrl|citation|artifact|computation|recordId|evidence)"',
    re.IGNORECASE,
)
_MIN_CHARS = 200


def _is_protected(message: Any) -> bool:
    name = str(getattr(message, "name", "") or "")
    if name.startswith(_PROTECTED_PREFIXES):
        return True
    content = str(getattr(message, "content", "") or "")
    return bool(_EVIDENCE_HINTS.search(content[:2_000]))


def prune_tool_messages(
    messages: list[Any],
    *,
    protect_last: int = 4,
    min_chars: int = _MIN_CHARS,
) -> tuple[list[Any], int]:
    """Return `(messages, pruned_count)`; never raises.

    A pruned message keeps its role, tool_call_id and name. The placeholder
    keeps the original character count so the model knows something was removed.
    """
    out = list(messages or [])
    indexes = [i for i, m in enumerate(out) if isinstance(m, ToolMessage)]
    keep = set(indexes[-max(0, int(protect_last)):]) if protect_last > 0 else set()
    pruned = 0
    for index in indexes:
        if index in keep:
            continue
        message = out[index]
        if _is_protected(message):
            continue
        content = str(getattr(message, "content", "") or "")
        if len(content) < max(1, int(min_chars)):
            continue
        name = str(getattr(message, "name", "") or "tool")
        out[index] = ToolMessage(
            content=f"[pruned tool result: {name}, original_chars={len(content)}]",
            tool_call_id=getattr(message, "tool_call_id", ""),
            name=name,
        )
        pruned += 1
    return out, pruned


async def maybe_prune_for_run(messages: list[Any], emitter: Any, step: int) -> tuple[list[Any], int]:
    """Run the W2 prune stage in on/shadow mode, emitting a bounded event."""
    from ..config import flags  # noqa: PLC0415

    mode = flags.get_flag("HARNESS_COMPRESSION_LADDER")
    if mode not in ("on", "shadow"):
        return list(messages or []), 0
    pruned, count = prune_tool_messages(list(messages or []))
    if mode == "on" and count:
        messages = pruned
    try:
        await emitter.emit("context.pruned", {
            "step": int(step or 0), "prunedToolResults": count, "mode": mode,
        })
    except Exception:  # noqa: BLE001
        pass
    return list(messages or []), count


__all__ = ["maybe_prune_for_run", "prune_tool_messages"]

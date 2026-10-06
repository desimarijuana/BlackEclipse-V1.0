"""The single `code.*` event seam (extracted from `code/tools.py`).

A code tool emits through the run's emitter so the event reaches the live SSE
stream and the persisted trace; when no emitter is attached it degrades to
`ctx.log`. Payloads are content-free (counts, paths, names) — never file contents
and never a secret value. An event must NEVER break a tool call.
"""

from __future__ import annotations

from typing import Any

from ..tools import ToolContext


async def emit_code_event(ctx: ToolContext, event_type: str, data: dict[str, Any]) -> None:
    """Emit a `code.*` event on the run's emitter, or degrade to `ctx.log`."""
    emitter = getattr(ctx, "emitter", None)
    if emitter is not None:
        try:
            await emitter.emit(event_type, data)
            return
        except Exception:  # noqa: BLE001 - an event must never break a tool call
            pass
    try:
        if ctx.log is not None:
            ctx.log(event_type, data)
    except Exception:  # noqa: BLE001
        pass


__all__ = ["emit_code_event"]

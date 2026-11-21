"""SSE stream for the OpenBB Workspace route.

Two honesty rules shape this module:

  * **The closing rules are not re-derived.** It consumes
    `run_stream.iter_run_events`, the same loop that ends the harness's own
    stream, so the "answer, then hang" class of bug cannot appear here in a
    second form.
  * **An empty transcript is a bug, not a rendering choice.** The runtime does
    not emit token deltas (its answer is the run's `output`), so a stream built
    only from events would show reasoning steps and no answer. When a run ends
    without having streamed any text, the final answer is read from the run
    record and emitted once as a `message_chunk`. If the run produced no output
    either, a status step says so — nothing is fabricated.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from ..run_stream import iter_run_events
from .event_mapper import MAX_CHUNK_CHARS, map_event

_DONE = "data: [DONE]\n\n"


def _frame(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _clip(text: str) -> str:
    return text if len(text) <= MAX_CHUNK_CHARS else text[: MAX_CHUNK_CHARS - 1] + "…"


async def openbb_frames(
    service: Any,
    run_id: str,
    queue: Any,
    since: int = 0,
) -> AsyncIterator[str]:
    """Yield OpenBB SSE objects for one run, then `[DONE]`."""
    text_streamed = False
    async for event in iter_run_events(service, run_id, queue, since):
        if event is None:
            yield ": keep-alive\n\n"
            continue
        for obj in map_event(event):
            if obj.get("type") == "message_chunk":
                text_streamed = True
            yield _frame(obj)
    if not text_streamed:
        run = service.get_run(run_id) or {}
        answer = str(run.get("output") or "").strip()
        if answer:
            yield _frame({"type": "message_chunk", "content": _clip(answer)})
        else:
            status = str(run.get("status") or "unknown")
            yield _frame({
                "type": "reasoning_step",
                "content": f"run ended with no output (status: {status})",
            })
    yield _DONE


__all__ = ["openbb_frames"]

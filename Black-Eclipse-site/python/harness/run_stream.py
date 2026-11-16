"""SSE frames for one run's live stream (`GET /runs/{id}/stream`).

Kept out of `main.py` (which is size-ratcheted) so the stream's closing rules
live next to the constants they use. The stream MUST always end: a run that
finished while nobody was watching, or a sentinel lost to a slow client, must
never hold the connection open (that shows the answer and then hangs).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from .run_timings import TERMINAL_EVENT_TYPES

_KEEPALIVE_S = 15.0


def _is_terminal(event: dict[str, Any]) -> bool:
    return event.get("type") in TERMINAL_EVENT_TYPES


async def run_event_frames(
    service: Any,
    run_id: str,
    queue: asyncio.Queue[Any],
    since: int = 0,
) -> AsyncIterator[str]:
    """Yield SSE frames, then close the stream honestly.

    Closes on a terminal event, on the bus sentinel, or as soon as the run is no
    longer active. Waiting on the sentinel ALONE was the output-then-hang bug:
    `end_stream()` can fire between the replay and the `is_active()` check while
    the task is still finishing, so a late subscriber never got the sentinel.
    """
    finished = False
    try:
        for event in service.list_events(run_id):
            seq = int(event.get("seq") or 0)
            if seq and seq <= since:
                continue
            if _is_terminal(event):
                finished = True
            yield f"id: {seq}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
        # Only wait for live events while the run can still produce them.
        while not finished and service.is_active(run_id):
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_S)
            except asyncio.TimeoutError:
                # Re-check the durable trace: an event emitted after the replay
                # (the terminal one) must not leave us waiting, and a full queue
                # can drop the sentinel.
                if any(_is_terminal(e) for e in service.list_events(run_id)):
                    finished = True
                    break
                if not service.is_active(run_id):
                    break
                yield ": keep-alive\n\n"
                continue
            if event is None:
                finished = True
                break
            seq = int(event.get("seq") or 0)
            prefix = f"id: {seq}\n" if seq else ""
            yield f"{prefix}event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            if _is_terminal(event):
                finished = True
                break
        yield "event: stream.end\ndata: {}\n\n"
    finally:
        service.bus.close_stream(run_id, queue)


__all__ = ["run_event_frames"]

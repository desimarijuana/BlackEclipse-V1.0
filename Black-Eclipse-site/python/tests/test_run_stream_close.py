"""Regression: a run stream must always end — output-then-hang is a bug.

The SSE endpoint (`GET /runs/{id}/stream`) used to wait for the event-bus
sentinel whenever the run looked active. `run_background`/`run` call
`end_stream()` in a `finally` BEFORE the task is marked done, so a stream
subscribed in that window never received the sentinel and held the connection
open forever — the browser showed the whole answer and then stayed "writing".

These tests pin the closing rules: a terminal event or an inactive run ends the
stream, and the sentinel cannot be dropped by a full queue.
"""

from __future__ import annotations

import asyncio
from typing import Any

from harness.events import EventBus
from harness.main import stream_run

_RUN = "run_stream_close"


class _Queue:
    """A live queue that never yields an event (simulates the lost sentinel)."""

    async def get(self) -> Any:
        raise asyncio.TimeoutError


class _Bus:
    def __init__(self) -> None:
        self.queue = _Queue()
        self.closed = False

    def open_stream(self, _run_id: str) -> _Queue:
        return self.queue

    def close_stream(self, _run_id: str, _queue: Any) -> None:
        self.closed = True


class _Service:
    def __init__(self, *, run_exists: bool, active: bool, terminal_after_replay: bool) -> None:
        self.bus = _Bus()
        self.run_exists = run_exists
        self.active = active
        self.terminal_after_replay = terminal_after_replay
        self._reads = 0

    def list_events(self, _run_id: str) -> list[dict[str, Any]]:
        self._reads += 1
        # First call is the replay; later calls are the timeout re-check.
        if self._reads == 1:
            return []
        if self.terminal_after_replay:
            return [{"type": "run.completed", "seq": 1, "data": {}}]
        return []

    def get_run(self, _run_id: str) -> dict[str, Any] | None:
        return {"runId": _RUN, "status": "completed"} if self.run_exists else None

    def is_active(self, _run_id: str) -> bool:
        return self.active


class _Request:
    headers: dict[str, str] = {}


async def _drain_response(monkeypatch: Any, service: _Service, run_id: str = _RUN) -> str:
    monkeypatch.setattr("harness.main.service", service)
    response = await stream_run(run_id, _Request(), after=0)  # type: ignore[arg-type]
    chunks: list[str] = []
    async for chunk in response.body_iterator:  # type: ignore[union-attr]
        chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
    return "".join(chunks)


async def test_stream_closes_when_run_finished_between_replay_and_check(monkeypatch):
    # The exact race: active at the check, but the terminal event was already
    # persisted and the sentinel will never arrive for this subscriber.
    service = _Service(run_exists=True, active=True, terminal_after_replay=True)
    body = await _drain_response(monkeypatch, service)
    assert "event: stream.end" in body
    assert service.bus.closed is True


async def test_stream_closes_for_unknown_run(monkeypatch):
    service = _Service(run_exists=False, active=False, terminal_after_replay=False)
    body = await _drain_response(monkeypatch, service)
    assert "event: stream.end" in body


async def test_stream_replays_terminal_without_waiting(monkeypatch):
    service = _Service(run_exists=True, active=True, terminal_after_replay=True)
    # First read (the replay) already contains the terminal event.
    original = service.list_events
    service.list_events = lambda run_id: [{"type": "run.failed", "seq": 1, "data": {}}]  # type: ignore[method-assign]
    body = await _drain_response(monkeypatch, service)
    service.list_events = original  # type: ignore[method-assign]
    assert "event: run.failed" in body
    assert "event: stream.end" in body


def test_end_stream_delivers_sentinel_into_a_full_queue():
    bus = EventBus()
    queue = bus.open_stream(_RUN)
    for i in range(queue.maxsize):
        queue.put_nowait({"type": "model.delta", "seq": -i, "data": {"text": "x"}})
    assert queue.full()

    bus.end_stream(_RUN)

    # The sentinel made it in (the oldest live event was dropped to make room).
    assert queue.qsize() == queue.maxsize
    drained = []
    while not queue.empty():
        drained.append(queue.get_nowait())
    assert None in drained

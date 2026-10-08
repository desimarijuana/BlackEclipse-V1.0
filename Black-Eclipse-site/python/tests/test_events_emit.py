"""Tests for the process-wide event emitter (`event_system.emit`)."""

from __future__ import annotations

import asyncio
import threading

from harness.event_system import emit


class FakeSystem:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def publish(self, type, payload=None, *, source="harness", **kwargs):  # noqa: A002
        self.calls.append((type, payload, source))


def _reset() -> None:
    emit.set_event_system(None)
    emit.set_loop(None)


async def test_publish_event_schedules_on_running_loop():
    fake = FakeSystem()
    emit.set_event_system(fake)
    emit.set_loop(asyncio.get_running_loop())
    try:
        emit.publish_event("task.completed", {"taskId": "t1"}, source="test")
        await asyncio.sleep(0)
        assert fake.calls == [("task.completed", {"taskId": "t1"}, "test")]
    finally:
        _reset()


async def test_publish_event_from_background_thread_uses_captured_loop():
    fake = FakeSystem()
    emit.set_event_system(fake)
    emit.set_loop(asyncio.get_running_loop())
    try:
        thread = threading.Thread(
            target=lambda: emit.publish_event("market.price.updated", {"symbol": "X"}, source="test")
        )
        thread.start()
        thread.join()
        await asyncio.sleep(0.05)
        assert fake.calls and fake.calls[0][0] == "market.price.updated"
    finally:
        _reset()


def test_publish_event_is_a_noop_without_a_system():
    _reset()
    emit.publish_event("anything.at.all", {"x": 1})  # must not raise
    assert emit.get_event_system() is None

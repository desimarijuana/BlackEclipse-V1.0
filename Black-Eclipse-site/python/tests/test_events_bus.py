"""Event Bus tests — delivery, filters, idempotency, retry, DLQ, backpressure,
request/reply, legacy bridge and graceful shutdown.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from harness.event_system.bus import EventBus
from harness.event_system.envelope import EclipseEvent
from harness.event_system.filters import EventFilter
from harness.event_system.metrics import EventMetrics
from harness.event_system.registry import RetryPolicy, default_registry
from harness.event_system.store import EventStore
from harness.persistence import AgentMemoryStore


class FakeLegacyBus:
    def __init__(self):
        self.listeners = []
        self.published = []

    def subscribe(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener) if listener in self.listeners else None

    def publish(self, event):
        self.published.append(event)
        for listener in list(self.listeners):
            listener(event)


class Boom(Exception):
    error_class = "PROVIDER_ERROR"


class Permanent(Exception):
    error_class = "PERMISSION_DENIED"


def _build(tmp_workspace, legacy=None):
    memory = AgentMemoryStore(str(Path(tmp_workspace) / "agent-memory.db"))
    store = EventStore(memory)
    metrics = EventMetrics()
    bus = EventBus(store, default_registry(), metrics, legacy_bus=legacy)
    return bus, store, metrics


async def _drain(delay=0.15):
    await asyncio.sleep(delay)


async def test_async_subscribe_persists_and_delivers(tmp_workspace):
    bus, store, _ = _build(tmp_workspace)
    received = []
    bus.subscribe("task.completed", lambda e: received.append(e.id))
    event = await bus.publish("task.completed", {"taskId": "t1"}, source="tasks")
    await _drain()
    assert received == [event.id]
    assert store.get(event.id) is not None
    await bus.shutdown()


async def test_sync_delivery_is_inline(tmp_workspace):
    bus, _, _ = _build(tmp_workspace)
    seen = []
    bus.subscribe("system.started", lambda e: seen.append(e.type), sync=True)
    await bus.publish("system.started", {}, source="harness")
    assert seen == ["system.started"]  # already delivered before publish returned
    await bus.shutdown()


async def test_once_unsubscribes_after_first(tmp_workspace):
    bus, _, _ = _build(tmp_workspace)
    seen = []
    bus.once("task.created", lambda e: seen.append(e.id))
    await bus.publish("task.created", {"taskId": "t1"}, source="tasks")
    await _drain()
    await bus.publish("task.created", {"taskId": "t2"}, source="tasks")
    await _drain()
    assert len(seen) == 1


async def test_namespace_and_predicate_filtering(tmp_workspace):
    bus, _, _ = _build(tmp_workspace)
    sampled = []
    bus.subscribe(
        EventFilter(patterns=("market.**",), predicate="payload.changePercent > 5"),
        lambda e: sampled.append(e.payload["changePercent"]),
    )
    await bus.publish("market.price.updated", {"symbol": "BTCUSDT", "changePercent": 1}, source="market")
    await bus.publish("market.price.updated", {"symbol": "BTCUSDT", "changePercent": 9}, source="market")
    await _drain()
    assert sampled == [9]


async def test_consumer_idempotency_prevents_duplicate_side_effects(tmp_workspace):
    bus, store, _ = _build(tmp_workspace)
    calls = []
    sub = bus.subscribe("task.completed", lambda e: calls.append(e.id), consumer_id="c1")
    event = EclipseEvent.create("task.completed", {"taskId": "t1"}, source="tasks")
    await bus._deliver_with_retry(sub, event)  # first
    await bus._deliver_with_retry(sub, event)  # duplicate delivery
    assert calls == [event.id]
    assert store.has_processed(event.id, "c1") is True


async def test_retry_then_dead_letter(tmp_workspace):
    bus, store, metrics = _build(tmp_workspace)
    attempts = {"n": 0}

    async def flaky(_event):
        attempts["n"] += 1
        raise Boom("transient")

    bus.subscribe(
        "task.completed", flaky,
        retry=RetryPolicy(max_attempts=3, initial_backoff_s=0.001, multiplier=1.0, jitter=False),
    )
    await bus.publish("task.completed", {"taskId": "t1"}, source="tasks")
    await _drain(0.3)
    assert attempts["n"] == 3
    dlq = store.list_dead_letters()
    assert len(dlq) == 1
    assert dlq[0]["errorClass"] == "PROVIDER_ERROR"
    assert metrics.snapshot()["deadLettered"] == 1
    await bus.shutdown()


async def test_non_retryable_goes_straight_to_dead_letter(tmp_workspace):
    bus, store, _ = _build(tmp_workspace)
    attempts = {"n": 0}

    async def permanent(_event):
        attempts["n"] += 1
        raise Permanent("nope")

    bus.subscribe(
        "task.completed", permanent,
        retry=RetryPolicy(max_attempts=5, initial_backoff_s=0.001, multiplier=1.0, jitter=False),
    )
    await bus.publish("task.completed", {"taskId": "t1"}, source="tasks")
    await _drain(0.15)
    assert attempts["n"] == 1  # never retried
    assert len(store.list_dead_letters()) == 1
    await bus.shutdown()


async def test_backpressure_drops_bulk_when_queue_full(tmp_workspace):
    bus, _, metrics = _build(tmp_workspace)
    block = asyncio.Event()

    async def slow(_event):
        await block.wait()

    sub = bus.subscribe("market.price.updated", slow)
    sub.queue = asyncio.Queue(maxsize=1)
    if sub.worker is not None:
        sub.worker.cancel()
        sub.worker = None
    # No worker can drain, so the second enqueue overflows the bound.
    await bus._enqueue(sub, EclipseEvent.create("market.price.updated", {"symbol": "A"}, source="market"))
    await bus._enqueue(sub, EclipseEvent.create("market.price.updated", {"symbol": "B"}, source="market"))
    assert metrics.snapshot()["droppedBackpressure"] == 1
    block.set()
    await bus.shutdown()


async def test_request_reply(tmp_workspace):
    bus, _, _ = _build(tmp_workspace)

    async def responder(event):
        await bus.publish(event.child("reply.pong", {"ok": True}, source="responder"))

    bus.subscribe("rpc.ping", responder)
    request = EclipseEvent.create("rpc.ping", {}, source="test")
    reply = await bus.request(request, reply_pattern="reply.**", timeout=2.0)
    assert reply is not None
    assert reply.type == "reply.pong"
    assert reply.causation_id == request.id
    await bus.shutdown()


async def test_legacy_bridge_ingests_and_echoes(tmp_workspace):
    legacy = FakeLegacyBus()
    bus, store, _ = _build(tmp_workspace, legacy=legacy)
    bus.start()
    legacy.publish({
        "id": "evt_run_1", "runId": "run_1", "type": "run.completed",
        "seq": 1, "at": "2026-10-08T00:00:00.000Z", "data": {"steps": 3},
    })
    await _drain(0.1)
    assert store.get("evt_run_1") is not None
    # A legacy-originated event is not echoed back a second time (no loop).
    assert [e["id"] for e in legacy.published].count("evt_run_1") == 1

    await bus.publish("task.completed", {"taskId": "t1"}, source="tasks")
    await _drain(0.05)
    assert any(e["type"] == "task.completed" for e in legacy.published)
    await bus.shutdown()


async def test_graceful_shutdown_drains_in_flight(tmp_workspace):
    bus, _, _ = _build(tmp_workspace)
    done = []

    async def handler(_event):
        await asyncio.sleep(0.05)
        done.append(True)

    bus.subscribe("task.completed", handler)
    await bus.publish("task.completed", {"taskId": "t1"}, source="tasks")
    await bus.shutdown(timeout=2.0)
    assert done == [True]

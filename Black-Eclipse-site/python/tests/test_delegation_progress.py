"""Live progress bridge for a delegated child run.

The child's events live on its own run id; the bridge folds them into ONE
content-free snapshot on the parent stream. These tests prove the fold, the
honest ceiling (`step`/`maxSteps`, never a computed percent), the real token
count, and that an unknown price stays unknown.
"""

from __future__ import annotations

import asyncio

from harness.delegation_progress import ChildProgressBridge, estimate_cost_usd


class _FakeBus:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.closed = False

    def open_stream(self, _run_id: str) -> asyncio.Queue:
        return self.queue

    def close_stream(self, _run_id: str, _queue: asyncio.Queue) -> None:
        self.closed = True


def _bridge(bus, events: list, **overrides):
    async def emit(event_type, data):
        events.append((event_type, data))

    kwargs = dict(
        bus=bus,
        child_run_id="run_parent_child0_abc123",
        delegation_id="dlg_1",
        child_index=0,
        goal="Review AAPL",
        agent_id="eclipse-agent",
        provider="ollama",
        model="llama3.1",
        emit=emit,
    )
    kwargs.update(overrides)
    return ChildProgressBridge(**kwargs)


def test_an_unknown_price_is_not_zero():
    assert estimate_cost_usd("nope", "no-such-model", 1_000, 500) is None
    # A local/free model is a REAL zero, not an unknown.
    assert estimate_cost_usd("ollama", "llama3.1", 1_000, 500) == 0.0


async def test_the_bridge_emits_a_content_free_terminal_snapshot():
    bus = _FakeBus()
    events: list = []
    bridge = _bridge(bus, events)
    bridge.start()

    bus.queue.put_nowait({"type": "run.started", "data": {"maxSteps": 8, "provider": "ollama"}})
    bus.queue.put_nowait({
        "type": "model.completed",
        "data": {"step": 2, "promptTokens": 100, "completionTokens": 40, "totalTokens": 140},
    })
    bus.queue.put_nowait({
        "type": "tool.requested",
        "data": {"name": "workspace_read", "detail": "Reading AAPL", "step": 2},
    })
    await asyncio.sleep(0.35)
    await bridge.finish("completed", tokens=140)

    snapshots = [data for kind, data in events if kind == "delegation.progress"]
    assert snapshots, "the bridge emitted no progress"
    last = snapshots[-1]
    assert last["delegationId"] == "dlg_1"
    assert last["childIndex"] == 0
    assert last["goal"] == "Review AAPL"
    assert last["activity"] == "Reading AAPL"
    assert last["step"] == 2 and last["maxSteps"] == 8
    assert last["tokens"] >= 140
    assert last["status"] == "completed"
    # Content-free: no summary/prose is ever copied from the child.
    assert "summary" not in last and "output" not in last
    assert bus.closed is True


async def test_a_child_with_no_bus_is_a_silent_no_op():
    events: list = []
    bridge = _bridge(None, events)
    bridge.start()
    await bridge.finish("completed", tokens=0)
    # The bridge may still emit its (honest) terminal snapshot, but it never
    # raises and never opens a stream.
    assert all(isinstance(kind, str) for kind, _ in events)

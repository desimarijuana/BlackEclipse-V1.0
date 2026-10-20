"""EventSystem facade tests — built-in consumers, loop guard, market sampling,
replay and the event→action rule bridge.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from harness.event_system.replay import ReplayError
from harness.event_system.rules import EventRuleBridge, EventRuleError
from harness.event_system.service import MAX_CAUSATION_DEPTH, EventSystem, MarketSampler
from harness.persistence import AgentMemoryStore


class FakeCommandService:
    """The minimal service surface the EventSystem touches at construction."""

    def __init__(self, store, legacy=None):
        self.store = store
        self.bus = legacy


async def _drain(delay=0.15):
    await asyncio.sleep(delay)


def _system(tmp_workspace, legacy=None):
    memory = AgentMemoryStore(str(Path(tmp_workspace) / "agent-memory.db"))
    return EventSystem(FakeCommandService(memory, legacy)), memory


async def test_start_emits_system_started_and_stops(tmp_workspace):
    system, memory = _system(tmp_workspace)
    await system.start()
    await _drain(0.05)
    assert system.store.query(type="system.started")
    assert system.health()["status"] == "ok"
    await system.stop()


async def test_memory_candidate_extractor_emits_bounded_candidate(tmp_workspace):
    system, _ = _system(tmp_workspace)
    await system.start()
    await system.publish(
        "task.completed", {"taskId": "t1", "title": "Answer the question", "result": "x" * 1000},
        source="tasks", correlation_id="c1",
    )
    await _drain(0.2)
    candidates = system.store.query(type="memory.candidate.created")
    assert len(candidates) == 1
    payload = candidates[0].payload
    assert payload["sourceType"] == "task.completed"
    assert payload["sourceEventId"]
    # summary is bounded to primitives; no raw blob is copied
    assert len(payload["summary"].get("result", "")) <= 300
    await system.stop()


async def test_failure_guard_limits_recovery_per_correlation(tmp_workspace):
    system, _ = _system(tmp_workspace)
    await system.start()
    for _ in range(4):
        await system.publish("task.failed", {"taskId": "t1"}, source="tasks", correlation_id="corr-x")
    await _drain(0.25)
    evaluations = system.store.query(type="evaluation.started", correlation_id="corr-x")
    assert 1 <= len(evaluations) <= 2  # capped, never unbounded
    await system.stop()


async def test_evaluation_started_wakes_the_rsl_conductor(tmp_workspace):
    class _Loop:
        def __init__(self) -> None:
            self.wakes = 0

        def wake(self) -> None:
            self.wakes += 1

    memory = AgentMemoryStore(str(Path(tmp_workspace) / "agent-memory-rsl.db"))
    fake = FakeCommandService(memory)
    fake._rsl_loop = _Loop()
    system = EventSystem(fake)
    await system.start()
    await system.publish(
        "evaluation.started", {"reason": "test"}, source="eval", correlation_id="rsl-wake",
    )
    await _drain()
    assert fake._rsl_loop.wakes >= 1
    await system.stop()
    memory.close()


async def test_failure_guard_respects_depth(tmp_workspace):
    system, _ = _system(tmp_workspace)
    await system.start()
    from harness.event_system.envelope import EclipseEvent

    event = EclipseEvent.create("task.failed", {"taskId": "t1"}, source="tasks", depth=MAX_CAUSATION_DEPTH)
    await system.bus.publish(event)  # bypass facade default priority
    await _drain(0.15)
    assert system.store.query(type="evaluation.started") == []
    await system.stop()


async def test_market_sampler_coalesces_price_ticks(tmp_workspace):
    system, _ = _system(tmp_workspace)
    system.bus.start()
    sampler = MarketSampler(system, interval=0.05)
    await sampler.start()
    for price in (100, 101, 102, 103):
        await system.publish("market.price.updated", {"symbol": "BTCUSDT", "price": price}, source="market")
    await asyncio.sleep(0.2)
    await sampler.stop()
    snapshots = system.store.query(type="market.snapshot.updated")
    assert snapshots
    assert snapshots[0].payload["symbol"] == "BTCUSDT"
    assert snapshots[0].payload["ticks"] >= 2
    await system.stop()


async def test_replay_observe_then_full(tmp_workspace):
    system, _ = _system(tmp_workspace)
    system.bus.start()
    delivered = []
    system.subscribe("task.completed", lambda e: delivered.append(e.metadata.get("replayed")), consumer_id="sink")
    await system.publish("task.completed", {"taskId": "t1"}, source="tasks", correlation_id="c1")
    await _drain()
    assert delivered == [None]

    observe = await system.replay(mode="observe", correlation_id="c1")
    assert observe.count == 1 and observe.delivered == 0
    assert len(delivered) == 1  # nothing delivered in observe mode

    sim = await system.replay(mode="simulation", correlation_id="c1")
    assert "sink" in sim.matched_subscribers and sim.delivered == 0

    with pytest.raises(ReplayError):
        await system.replay(mode="full", correlation_id="c1", authorized=False)

    full = await system.replay(mode="full", correlation_id="c1", authorized=True)
    await _drain()
    assert full.delivered >= 1
    assert any(flag is True for flag in delivered)
    await system.stop()


async def test_rule_bridge_refuses_unknown_action():
    class Stub:
        def automation_service(self):
            raise AssertionError("should not be reached")

    bridge = EventRuleBridge(Stub())
    with pytest.raises(EventRuleError):
        bridge.create_rule(name="x", event_type="task.completed", action="explode")


async def test_rule_bridge_refuses_unknown_event():
    class Stub:
        def automation_service(self):
            raise AssertionError("should not be reached")

    bridge = EventRuleBridge(Stub())
    with pytest.raises(EventRuleError):
        bridge.create_rule(name="x", event_type="not.a.real.event", action="run_agent")


async def test_rule_bridge_delegates_to_automation_service():
    captured = {}

    class FakeDefinition:
        def public(self):
            return {"id": "rule_1", "trigger": {"type": "event", "eventType": "task.completed"}}

    class FakeAutomation:
        def create_definition(self, definition, created_by=None):
            captured["definition"] = definition
            return FakeDefinition()

        def list(self, limit=200):
            return []

    class Stub:
        def automation_service(self):
            return FakeAutomation()

    bridge = EventRuleBridge(Stub())
    rule = bridge.create_rule(
        name="notify on completion", event_type="task.completed",
        action="send_notification", notification_template="done", activated=True,
    )
    assert rule["id"] == "rule_1"
    definition = captured["definition"]
    assert definition.trigger.event_type == "task.completed"
    assert definition.action.type == "send_notification"
    assert definition.state == "active"

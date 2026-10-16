"""Native Automation Engine — scheduler/trigger/retry/recovery integration.

Deterministic: an injected clock and a fake dispatcher; tests never sleep (retry
backoff is set to 0).
"""

from __future__ import annotations

import datetime as _dt

import pytest

from harness.automation.engine import AutomationEngine
from harness.automation.facts import StaticFactProvider
from harness.automation.dispatcher import DispatchResult
from harness.automation.model import AutomationDefinition
from harness.automation.store import AutomationStore
from harness.persistence import AgentMemoryStore


class Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now = self.now + _dt.timedelta(**kwargs)


class FakeDispatcher:
    def __init__(self):
        self.calls = 0
        self.sequence: list[str] = []
        self.error_class = None
        self.error = "boom"

    async def check_approval(self, definition):
        return True, None

    async def dispatch(self, definition, *, execution_id, run_id, dry_run=False):
        self.calls += 1
        state = self.sequence.pop(0) if self.sequence else "completed"
        if state == "completed":
            return DispatchResult(state="completed", run_id=run_id, output="ok")
        return DispatchResult(state="failed", run_id=run_id, error=self.error, error_class=self.error_class)


class SlowDispatcher(FakeDispatcher):
    """Each run consumes `work_seconds` of the injected clock (run duration)."""

    def __init__(self, clock, work_seconds=20):
        super().__init__()
        self.clock = clock
        self.work_seconds = work_seconds
        self.fire_times: list = []

    async def dispatch(self, definition, *, execution_id, run_id, dry_run=False):
        self.fire_times.append(self.clock())
        self.clock.advance(seconds=self.work_seconds)
        return DispatchResult(state="completed", run_id=run_id, output="ok")


class FakeService:
    def __init__(self, store):
        self.store = store
        self.bus = None


@pytest.fixture
def env(tmp_workspace):
    from pathlib import Path

    store = AgentMemoryStore(str(Path(tmp_workspace) / "agent-memory.db"))
    auto_store = AutomationStore(store)
    clock = Clock(_dt.datetime(2026, 10, 8, 6, 0, tzinfo=_dt.timezone.utc))
    dispatcher = FakeDispatcher()
    facts = StaticFactProvider({})
    service = FakeService(store)
    engine = AutomationEngine(
        service, auto_store, clock=clock, dispatcher=dispatcher, fact_provider=facts,
        tick_seconds=10_000,
    )
    return type("Env", (), {
        "store": store, "auto_store": auto_store, "clock": clock,
        "dispatcher": dispatcher, "facts": facts, "engine": engine,
    })


def _save(env, **overrides):
    now = env.clock().isoformat()
    base = dict(
        id="auto_test", name="Test", state="active",
        trigger={"type": "interval", "interval_seconds": 3600, "timezone": "UTC"},
        action={"type": "run_agent", "objective": "brief"},
        created_at=now, updated_at=now,
    )
    base.update(overrides)
    definition = AutomationDefinition(**base)
    env.auto_store.save_automation(definition)
    env.engine.refresh_schedule(definition.id)
    return env.auto_store.get_automation(definition.id)


async def test_interval_fires_on_schedule(env):
    _save(env)
    await env.engine._tick()  # not due yet
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 0

    env.clock.advance(minutes=61)
    await env.engine._tick()
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 1

    env.clock.advance(minutes=61)
    await env.engine._tick()
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 2
    executions = env.auto_store.list_executions("auto_test")
    assert all(e["state"] == "completed" for e in executions)


async def test_interval_cadence_is_not_drifted_by_run_duration(env):
    # Regression: the interval grid is anchored to the scheduled slot, never to
    # the run's completion time. A 20s run must NOT turn a 60s interval into 80s.
    slow = SlowDispatcher(env.clock)
    env.engine._dispatcher = slow
    definition = _save(env, trigger={"type": "interval", "interval_seconds": 60, "timezone": "UTC"})
    anchor = _dt.datetime.fromisoformat(definition.created_at)

    slots: list = []
    original = env.auto_store.set_next_run

    def spy(automation_id, next_run_at, *args, **kwargs):
        if next_run_at:
            slots.append(_dt.datetime.fromisoformat(next_run_at))
        return original(automation_id, next_run_at, *args, **kwargs)

    env.auto_store.set_next_run = spy

    for _ in range(20):  # 20 * 30s = 10 minutes of ticks
        env.clock.advance(seconds=30)
        await env.engine._tick()
        await env.engine.wait_idle()

    assert slots, "the interval never fired"
    # Every scheduled slot must land exactly on the 60s grid anchored at creation.
    # Completion-anchoring drifted each slot by the +20s run duration and fails.
    for slot in slots:
        assert (slot - anchor).total_seconds() % 60 == 0, slot.isoformat()


async def test_completed_run_stores_its_output(env):
    # Regression: a completed unattended run must persist WHAT it produced, so
    # the run history and completion notice can show the answer (it used to be
    # dropped, and a bot appeared to run with no output).
    _save(env)
    env.clock.advance(minutes=61)
    await env.engine._tick()
    await env.engine.wait_idle()
    execution = env.auto_store.last_execution("auto_test")
    assert execution["state"] == "completed"
    assert execution["output"] == "ok"


async def test_event_trigger_deduplicates(env):
    _save(env, trigger={"type": "event", "event_type": "filing.created", "timezone": "UTC"})
    event = {"id": "evt-abc", "type": "filing.created", "data": {"ticker": "AAPL"}}
    await env.engine._handle_event(event)
    await env.engine.wait_idle()
    await env.engine._handle_event(event)  # redelivery
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 1
    assert env.auto_store.already_seen_event("auto_test", "evt-abc")


async def test_event_gate_condition(env):
    _save(env, trigger={"type": "event", "event_type": "market.price_changed", "timezone": "UTC"},
          condition={"expression": "ticker == 'BTC'"})
    await env.engine._handle_event({"id": "e1", "type": "market.price_changed", "data": {"ticker": "ETH"}})
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 0
    await env.engine._handle_event({"id": "e2", "type": "market.price_changed", "data": {"ticker": "BTC"}})
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 1


async def test_condition_edge_fires_once(env):
    _save(env, trigger={"type": "condition", "condition": {"expression": "BTC.price < 90000", "edge": True},
                        "timezone": "UTC"})
    env.facts.set("BTC.price", 89900)
    await env.engine._condition_tick()
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 1  # FALSE -> TRUE

    await env.engine._condition_tick()  # still true
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 1

    env.facts.set("BTC.price", 91000)  # TRUE -> FALSE
    await env.engine._condition_tick()
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 1

    env.facts.set("BTC.price", 89000)  # FALSE -> TRUE again
    await env.engine._condition_tick()
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 2


async def test_concurrency_skip_if_running(env):
    definition = _save(env)
    env.auto_store.start_execution(
        definition, trigger_type="schedule", trigger_ref=None,
        scheduled_for=env.clock().isoformat(), snapshot={}, state="running",
    )
    await env.engine._launch(
        definition, trigger_type="schedule", trigger_ref=None, scheduled_for=env.clock().isoformat(),
    )
    assert env.dispatcher.calls == 0
    states = [e["state"] for e in env.auto_store.list_executions("auto_test")]
    assert "skipped" in states


async def test_retry_then_success(env):
    _save(env, retry={"max_attempts": 3, "initial_backoff_s": 0, "jitter": False})
    env.dispatcher.sequence = ["failed", "completed"]
    env.dispatcher.error_class = "PROVIDER_ERROR"
    env.clock.advance(minutes=61)
    await env.engine._tick()
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 2
    execution = env.auto_store.last_execution("auto_test")
    assert execution["state"] == "completed"
    assert execution["attempt"] == 2


async def test_non_retryable_is_not_retried(env):
    _save(env, retry={"max_attempts": 3, "initial_backoff_s": 0, "jitter": False})
    env.dispatcher.sequence = ["failed"]
    env.dispatcher.error_class = "PERMISSION_DENIED"
    env.clock.advance(minutes=61)
    await env.engine._tick()
    await env.engine.wait_idle()
    assert env.dispatcher.calls == 1
    execution = env.auto_store.last_execution("auto_test")
    assert execution["state"] == "failed"
    assert execution["errorClass"] == "PERMISSION_DENIED"


async def test_breaker_opens_and_blocks(env):
    _save(env, retry={"max_attempts": 1})
    env.dispatcher.sequence = ["failed", "failed", "failed", "failed"]
    env.dispatcher.error_class = "PROVIDER_ERROR"
    for _ in range(3):
        env.clock.advance(minutes=61)
        await env.engine._tick()
        await env.engine.wait_idle()
    definition = env.auto_store.get_automation("auto_test")
    assert definition.breaker == "open"
    calls = env.dispatcher.calls
    env.clock.advance(minutes=61)
    await env.engine._tick()
    await env.engine.wait_idle()
    assert env.dispatcher.calls == calls  # blocked, no new dispatch
    assert any(e["state"] == "blocked" for e in env.auto_store.list_executions("auto_test"))


async def test_misfire_skip_and_run_once(env):
    # skip policy records a skipped execution and advances the anchor.
    _save(env, id="auto_skip", execution={"misfire": "skip"},
          trigger={"type": "cron", "cron": "0 8 * * *", "timezone": "UTC"},
          last_run_at="2026-09-01T00:00:00+00:00")
    env.clock.now = _dt.datetime(2026, 10, 8, 6, 0, tzinfo=_dt.timezone.utc)
    await env.engine._recover()
    await env.engine.wait_idle()
    assert any(e["state"] == "skipped" for e in env.auto_store.list_executions("auto_skip"))

    _save(env, id="auto_run", execution={"misfire": "run_once"},
          trigger={"type": "cron", "cron": "0 8 * * *", "timezone": "UTC"},
          last_run_at="2026-09-01T00:00:00+00:00")
    before = env.dispatcher.calls
    await env.engine._recover()
    await env.engine.wait_idle()
    assert env.dispatcher.calls == before + 1


async def test_lease_lock_prevents_double_processing(env):
    assert env.auto_store.acquire_lock("exec:x", "w1", ttl_s=100) is True
    assert env.auto_store.acquire_lock("exec:x", "w2", ttl_s=100) is False
    # An expired lease is reclaimable (crash recovery).
    assert env.auto_store.acquire_lock("exec:y", "w1", ttl_s=0.0001) is True
    import time

    time.sleep(0.01)
    assert env.auto_store.acquire_lock("exec:y", "w2", ttl_s=100) is True


async def test_restart_reconciles_interrupted_execution(env):
    definition = _save(env, retry={"max_attempts": 2})
    env.auto_store.start_execution(
        definition, trigger_type="schedule", trigger_ref=None,
        scheduled_for=env.clock().isoformat(), snapshot={}, state="running",
    )
    await env.engine._recover()
    await env.engine.wait_idle()
    executions = env.auto_store.list_executions("auto_test")
    assert any(e["state"] == "failed" and e["errorClass"] == "INTERRUPTED" for e in executions)
    # retryable and attempts remain -> a fresh run was launched.
    assert env.dispatcher.calls == 1


def test_snapshot_never_contains_credentials(env):
    definition = _save(env)
    snapshot = env.engine._snapshot(definition)
    assert "apiKey" not in str(snapshot)
    assert snapshot["automationVersion"] == definition.version


class ApprovalDispatcher(FakeDispatcher):
    def __init__(self):
        super().__init__()
        self.approved = False

    async def check_approval(self, definition):
        return (self.approved, None if self.approved else "appr_1")


async def test_approval_gate_waits_then_resumes(env):
    ad = ApprovalDispatcher()
    env.engine._dispatcher = ad
    definition = _save(env, permissions={"requires_approval": True, "approval_scope": "trades"})
    execution_id = await env.engine._launch(
        definition, trigger_type="manual", trigger_ref=None, scheduled_for=env.clock().isoformat(),
    )
    await env.engine.wait_idle()
    assert env.auto_store.get_execution(execution_id)["state"] == "waiting"
    assert ad.calls == 0  # no work ran without approval

    # Grant the approval, then resume: the execution keeps its id + context.
    ad.approved = True
    assert await env.engine.resume_execution(execution_id) is True
    await env.engine.wait_idle()
    assert env.auto_store.get_execution(execution_id)["state"] == "completed"
    assert ad.calls == 1

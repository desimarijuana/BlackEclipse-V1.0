"""W4 autonomy: flags, goal contract/gates, judge ordering, continuation, loops."""

from __future__ import annotations

import asyncio
import types

import pytest

from harness.code.sandbox import RawResult
from harness.config import flags
from harness.events import EventBus
from harness.goals import gates as gates_module
from harness.goals import goal_runtime as runtime_module
from harness.goals.gates import GateResult, run_gate
from harness.goals.goal_runtime import GoalRuntime
from harness.goals.judge import JudgeOutcome, judge_goal
from harness.goals.loop_runtime import LoopRuntime
from harness.goals.store import GoalStore
from harness.persistence import AgentMemoryStore
from harness.tasks.manager import TaskManager
from harness.tasks.model import GoalContract, GoalGate
from harness.tasks.store import TaskStore


class FakeService:
    def __init__(self, tmp_path):
        self.store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
        self.tasks = TaskManager(TaskStore(self.store))
        self.bus = EventBus()
        self.code_store = None
        self._active: set[str] = set()

    def is_active(self, run_id: str) -> bool:
        return run_id in self._active

    def cancel(self, run_id: str) -> bool:
        self._active.discard(run_id)
        return True


@pytest.fixture()
def service(tmp_path):
    return FakeService(tmp_path)


def _raw(exit_code=0, output="ok", timed_out=False):
    return RawResult(
        exit_code=exit_code, timed_out=timed_out, killed=False, cancelled=False,
        output=output, truncated=False, total_chars=len(output), duration_ms=12,
        backend="test", launch_error=None,
    )


def test_w4_flags_default_off_and_clamp():
    snap = flags.snapshot(environ={})
    assert snap["HARNESS_GOAL_LOOP"] == "off"
    assert snap["HARNESS_GOAL_MAX_TURNS"] == "20"
    assert flags.get_int(
        "HARNESS_GOAL_MAX_TURNS", environ={"HARNESS_GOAL_MAX_TURNS": "999"},
    ) == 100
    assert flags.get_flag(
        "HARNESS_GOAL_LOOP", environ={"HARNESS_GOAL_LOOP": "maybe"},
    ) == "off"


def test_goal_loop_is_vetoed_by_the_global_kill_switch(monkeypatch):
    from harness.goals.goal_runtime import loop_mode

    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    monkeypatch.setenv("HARNESS_AUTONOMY", "off")
    assert loop_mode() == "off"
    monkeypatch.setenv("HARNESS_AUTONOMY", "on")
    assert loop_mode() == "on"


def test_gates_require_an_execution_profile(service, monkeypatch):
    from harness.goals.goal_runtime import GoalError

    runtime = GoalRuntime(service)
    with pytest.raises(GoalError) as exc:
        runtime.create(
            "ship it", autonomy="plan_only", workspace_id="ws1",
            gates=[{"id": "g", "check": "unit_test"}], start=False,
        )
    assert exc.value.code == "GATES_REQUIRE_EXECUTION"


def test_goal_contract_extension_and_gate_validation():
    contract = GoalContract(
        objective="ship it", verification=["tests"], boundaries=["jdds.db"],
        stop_when=["tests pass"],
    )
    assert contract.verification == ["tests"]
    assert contract.boundaries == ["jdds.db"]
    assert contract.stop_when == ["tests pass"]
    # An old contract (no W4 fields) still validates.
    assert GoalContract(objective="old").verification == []
    with pytest.raises(ValueError):
        GoalGate(id="g", check="rm -rf /")


def test_goal_store_roundtrip_keeps_old_rows_loadable(service):
    store = GoalStore(service.store)
    old = store.create_goal("old goal")
    loaded = store.get_goal(old.id)
    assert loaded.max_turns == 20
    assert loaded.gates == []
    assert loaded.contract is None

    goal = store.create_goal(
        "new goal", contract={"objective": "new goal"},
        gates=[{"id": "g1", "check": "unit_test"}], max_turns=5,
        session_id="s1", workspace_id="ws1",
    )
    store.update_goal_fields(goal.id, {"planId": "plan_x"})
    store.add_goal_turn(goal.id, last_verdict={"verdict": "continue"})
    record = store.record_verdict(
        goal.id, verdict="continue", reason="more", turn=1,
        gate_results=[{"gateId": "g1", "ok": False}],
    )
    store.record_gate_run(
        goal.id, gate_id="g1", check="unit_test", verdict_id=record.id,
        exit_code=1, output_tail="failed",
    )
    reloaded = store.get_goal(goal.id)
    assert reloaded.plan_id == "plan_x"
    assert reloaded.used_turns == 1
    assert reloaded.last_verdict == {"verdict": "continue"}
    assert reloaded.gates[0]["id"] == "g1"
    assert store.list_verdicts(goal.id)[0].verdict == "continue"


def test_gate_failure_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def fake_run(spec):
        calls["n"] += 1
        return _raw(exit_code=1, output="test failed")

    monkeypatch.setattr(gates_module.commands, "resolve_class", lambda name: types.SimpleNamespace(
        name=name, timeout_s=60, output_cap_bytes=1000, network=False,
    ))
    monkeypatch.setattr(gates_module.commands, "build_argv", lambda cls, args: ["fake"])
    monkeypatch.setattr(gates_module.policy, "decide_command", lambda *a: types.SimpleNamespace(
        allowed=True, code="OK", reason="",
    ))
    monkeypatch.setattr(gates_module.sandbox, "run", fake_run)

    binding = types.SimpleNamespace(id="ws1", root=".")
    result = run_gate(
        GoalGate(id="g", check="unit_test", timeout_seconds=60, retries=3), binding,
    )
    assert result.ok is False
    assert result.exit_code == 1
    assert calls["n"] == 1  # a real failing check is definitive


def test_gate_missing_workspace_is_typed():
    result = run_gate(GoalGate(id="g", check="unit_test"), None)
    assert result.ok is False
    assert result.error_code == "WORKSPACE_MISSING"


def test_a_failing_gate_never_calls_the_judge(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create(
        "ship a widget", max_turns=3, start=False, workspace_id="ws1",
        gates=[{"id": "g", "check": "unit_test"}],
    )

    monkeypatch.setattr(runtime_module, "run_gates", lambda gates, binding, **kwargs: [
        GateResult("g", "unit_test", False, exit_code=1, output_tail="red"),
    ])
    called = {"judge": 0}

    async def fake_judge(*args, **kwargs):
        called["judge"] += 1
        return JudgeOutcome("done", "should not be reached")

    monkeypatch.setattr(runtime_module, "judge_goal", fake_judge)
    verdict = asyncio.run(runtime.evaluate(goal.id, "run_1", {"status": "completed"}))
    assert called["judge"] == 0
    assert verdict["verdict"] == "continue"


def test_judge_invalid_json_becomes_blocked(monkeypatch):
    class FakeModel:
        async def ainvoke(self, messages):
            return types.SimpleNamespace(content="not json")

    monkeypatch.setattr("harness.goals.judge.build_chat_model", lambda settings: FakeModel())
    outcome = asyncio.run(judge_goal(
        {"objective": "x"}, [],
        {"status": "completed", "output": "did it"}, [],
        types.SimpleNamespace(provider="ollama", model="x"),
    ))
    assert outcome.verdict == "blocked"
    assert outcome.invalid is True


def test_judge_never_turns_a_red_gate_green(monkeypatch):
    class Boom:
        async def ainvoke(self, messages):  # pragma: no cover - must not be called
            raise AssertionError("judge must not be called with a red gate")

    monkeypatch.setattr("harness.goals.judge.build_chat_model", lambda settings: Boom())
    outcome = asyncio.run(judge_goal(
        {"objective": "x"}, [GateResult("g", "unit_test", False)],
        {"status": "completed"}, [],
        types.SimpleNamespace(provider="ollama", model="x"),
    ))
    assert outcome.verdict == "continue"


def test_continuation_starts_a_second_turn_then_pauses(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create("improve the app", max_turns=2, start=True)
    monkeypatch.setattr(runtime_module, "run_gates", lambda gates, binding, **kwargs: [])

    async def fake_judge(*args, **kwargs):
        return JudgeOutcome("continue", "more work", next_step="do the next thing")

    monkeypatch.setattr(runtime_module, "judge_goal", fake_judge)
    first = asyncio.run(runtime.evaluate(goal.id, "run_1", {"status": "completed"}))
    assert first["verdict"] == "continue"
    after = runtime.get(goal.id)
    assert after.used_turns == 2
    assert after.task_id is not None

    second = asyncio.run(runtime.evaluate(goal.id, "run_2", {"status": "completed"}))
    assert second["verdict"] == "continue"
    final = runtime.get(goal.id)
    assert final.status == "paused"  # turn budget reached


def test_task_event_bridge_evaluates_the_goal(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    from harness.goals.bootstrap import AutonomyService

    runtime = GoalRuntime(service)
    goal = runtime.create("improve the app", max_turns=2, start=True)
    task_id = runtime.get(goal.id).task_id
    assert task_id

    run_id = "run_goal_1"
    service.store.create_run(run_id, "eclipse-agent", {"query": "x"})
    service.store.update_run(run_id, status="completed", output="did the work")
    service.tasks.start_task(task_id, run_id=run_id)

    monkeypatch.setattr(runtime_module, "run_gates", lambda gates, binding, **kwargs: [])

    async def fake_judge(*args, **kwargs):
        return JudgeOutcome("continue", "more work")

    monkeypatch.setattr(runtime_module, "judge_goal", fake_judge)
    layer = AutonomyService(service)
    verdict = asyncio.run(layer.handle_task_event(task_id))
    assert verdict is not None
    assert verdict["verdict"] == "continue"
    assert runtime.get(goal.id).used_turns == 2


def test_wait_goal_wakes_at_its_run_time_and_paused_goal_does_not_continue(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create("keep going", max_turns=3, start=True)
    store = GoalStore(service.store)

    # A paused goal ignores a run event (the operator paused it).
    store.set_goal_status(goal.id, "paused")
    monkeypatch.setattr(runtime_module, "run_gates", lambda gates, binding, **kwargs: [])
    assert asyncio.run(runtime.evaluate(goal.id, "run_x", {"status": "completed"})) is None

    # `wait` parks with a wake time; the heartbeat wakes it into the next turn.
    store.update_goal_fields(goal.id, {"nextRunAt": "2000-01-01T00:00:00+00:00"})
    woken = runtime.wake_due("2026-01-01T00:00:00+00:00")
    assert woken == [goal.id]
    assert runtime.get(goal.id).used_turns == 2


def test_loop_unchanged_reply_pauses(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    monkeypatch.setenv("HARNESS_LOOP_MAX_NO_CHANGE", "2")

    async def fake_run(request):
        return types.SimpleNamespace(output="the same answer", status="completed")

    service.run = fake_run  # type: ignore[attr-defined]
    runtime = LoopRuntime(service)
    loop = runtime.create("s1", kind="loop", prompt="check", interval_seconds=60)

    for tick in range(1, 4):
        current = runtime.get(loop.id)
        asyncio.run(runtime._run(current, tick))
    final = runtime.get(loop.id)
    assert final.status == "paused"
    assert final.no_change_count >= 2


def test_loop_create_clamps_interval_and_tick_defers_when_busy(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = LoopRuntime(service)
    loop = runtime.create("s1", kind="heartbeat", prompt="check", interval_seconds=1)
    assert loop.interval_seconds == flags.get_int("HARNESS_LOOP_MIN_INTERVAL_S")
    assert loop.next_tick_at

    # Force the loop due, and make the session busy.
    store = GoalStore(service.store)
    store.update_loop_fields(loop.id, {"nextTickAt": "2000-01-01T00:00:00+00:00"})
    service._active.add("run_busy")
    service.store.create_run("run_busy", "eclipse-agent", {"query": "x"})
    service.store.update_run("run_busy", sessionId="s1")
    report = asyncio.run(runtime.tick())
    assert report["due"] == 1
    assert report["deferred"] == 1
    assert report["started"] == 0
    reloaded = store.get_loop(loop.id)
    assert reloaded.status == "active"
    assert reloaded.used_ticks == 0

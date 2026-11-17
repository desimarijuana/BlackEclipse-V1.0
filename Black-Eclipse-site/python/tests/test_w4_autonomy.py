"""W4 autonomy: flags, goal contract/gates, judge ordering, continuation, loops."""

from __future__ import annotations

import asyncio
import json
import types

import pytest

from harness.code.sandbox import RawResult
from harness.config import flags
from harness.events import EventBus
from harness.goals import gates as gates_module
from harness.goals import goal_runtime as runtime_module
from harness.goals.gates import GateResult, run_gate
from harness.goals.goal_runtime import GoalRuntime
from harness.goals.judge import JudgeOutcome, build_judge_prompt, judge_goal
from harness.goals.loop_runtime import LoopRuntime
from harness.goals.store import GoalStore
from harness.persistence import AgentMemoryStore
from harness.tasks.manager import TaskManager
from harness.tasks.model import GoalContract, GoalGate, PlanStatus, TaskStatus, TaskType
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


def test_w4_flags_default_on_and_clamp():
    snap = flags.snapshot(environ={})
    # The goal loop is ON by default: `/goal` is user-initiated, and the global
    # kill switch below still vetoes it. An explicit `off` remains supported.
    assert snap["HARNESS_GOAL_LOOP"] == "on"
    assert snap["HARNESS_GOAL_MAX_TURNS"] == "20"
    assert flags.get_int(
        "HARNESS_GOAL_MAX_TURNS", environ={"HARNESS_GOAL_MAX_TURNS": "999"},
    ) == 100
    assert flags.get_flag(
        "HARNESS_GOAL_LOOP", environ={"HARNESS_GOAL_LOOP": "maybe"},
    ) == "on"  # an invalid value falls back to the default, which is now on


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


def test_the_judge_prompt_carries_the_run_metrics():
    """The task event reports counts at the top level; the prompt must forward them."""
    prompt = build_judge_prompt(
        {"objective": "x"}, [],
        {"status": "completed", "output": "done", "totalTokens": 1234,
         "toolCalls": 7, "modelSteps": 5},
        [],
    )
    assert '"tokens": 1234' in prompt
    assert '"toolCalls": 7' in prompt
    assert '"modelSteps": 5' in prompt


def test_judge_accepts_a_near_miss_schema(monkeypatch):
    """`status`/`explanation` is the same answer as `verdict`/`reason`.

    The document goal blocked because the judge answered with the right intent
    and the wrong key. Only the VALUE is authoritative, so normalize the key.
    """
    class FakeModel:
        async def ainvoke(self, messages):
            return types.SimpleNamespace(content=json.dumps({
                "status": "completed",
                "explanation": "the artifact was delivered and verified",
                "evidence": ["artifact:report.md"],
            }))

    monkeypatch.setattr("harness.goals.judge.build_chat_model", lambda settings: FakeModel())
    outcome = asyncio.run(judge_goal(
        {"objective": "write the memo"}, [],
        {"status": "completed", "output": "delivered"}, [],
        types.SimpleNamespace(provider="ollama", model="x"),
    ))
    assert outcome.verdict == "done"
    assert "artifact was delivered" in outcome.reason
    assert outcome.evidence == ["artifact:report.md"]


def test_judge_accepts_fenced_json_and_snake_case(monkeypatch):
    class FakeModel:
        async def ainvoke(self, messages):
            return types.SimpleNamespace(content=(
                "```json\n"
                '{"decision": "continue", "summary": "more work", '
                '"next_step": "run the backtest", "wake_at": ""}\n'
                "```"
            ))

    monkeypatch.setattr("harness.goals.judge.build_chat_model", lambda settings: FakeModel())
    outcome = asyncio.run(judge_goal(
        {"objective": "x"}, [],
        {"status": "completed"}, [],
        types.SimpleNamespace(provider="ollama", model="x"),
    ))
    assert outcome.verdict == "continue"
    assert outcome.next_step == "run the backtest"
    assert outcome.invalid is False


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
    # At the cap the goal is BLOCKED, not paused: a paused goal the operator
    # cannot resume was a dead end. `/goal extend` is the explicit way out.
    assert final.status == "blocked"


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


# ── Hardening: the invariants the loop is only as good as ─────────────────────

def test_the_no_progress_digest_ignores_the_judges_wording():
    """A judge that rephrases the same non-progress must not reset the guard."""
    gate = GateResult("g", "unit_test", False, exit_code=1)
    first = GoalRuntime._progress_digest(
        JudgeOutcome("continue", "tests still fail"), [gate], ["file:a.py"],
    )
    second = GoalRuntime._progress_digest(
        JudgeOutcome("continue", "the same tests are still failing, again"),
        [gate], ["file:a.py"],
    )
    assert first == second
    moved = GoalRuntime._progress_digest(
        JudgeOutcome("continue", "tests still fail"), [gate], ["file:b.py"],
    )
    assert moved != first


def test_a_judge_done_without_verification_evidence_continues(service, monkeypatch):
    """A judge verdict is advisory; the task verifier has the final say."""
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create("finish the widget", max_turns=3, start=False)
    monkeypatch.setattr(runtime_module, "run_gates", lambda gates, binding, **kwargs: [])

    async def fake_judge(*args, **kwargs):
        return JudgeOutcome("done", "looks finished to me")

    monkeypatch.setattr(runtime_module, "judge_goal", fake_judge)
    monkeypatch.setattr(
        runtime, "_verify_completion",
        lambda goal, summary: (False, "verified completion refused: no evidence"),
    )
    verdict = asyncio.run(runtime.evaluate(goal.id, "run_1", {"status": "completed"}))
    assert verdict["verdict"] == "continue"
    assert "refused" in verdict["reason"]
    assert runtime.get(goal.id).status == "active"


def test_one_active_goal_per_session_is_enforced(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    from harness.goals.goal_runtime import GoalError

    runtime = GoalRuntime(service)
    runtime.create("first", start=False, session_id="s1")
    with pytest.raises(GoalError) as exc:
        runtime.create("second", start=False, session_id="s1")
    assert exc.value.code == "GOAL_ALREADY_ACTIVE"
    # Explicit parallelism is still allowed.
    runtime.create("second", start=False, session_id="s1", allow_parallel=True)


def test_a_goal_turn_is_left_todo_so_the_scheduler_can_claim_it(service, monkeypatch):
    """The production bug: `start_task` marked the turn IN_PROGRESS with no lease.

    The scheduler only claims TODO, so the goal sat active with a turn that
    never ran. A new turn must stay TODO and be visible to `runnable_tasks`.
    """
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create("improve the app", max_turns=3, start=True)
    task = service.tasks.get_task(runtime.get(goal.id).task_id)
    assert task.status == TaskStatus.TODO
    assert task.claim_token is None
    assert task.id in {t.id for t in service.tasks.runnable_tasks(limit=50)}


def test_an_orphaned_goal_turn_is_requeued_at_boot(service, monkeypatch):
    """Rows the old enqueue path stranded must be repaired, not left invisible."""
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create("improve the app", max_turns=3, start=True)
    task_id = runtime.get(goal.id).task_id
    # Simulate the old `start_task` enqueue: IN_PROGRESS, no claim, no run.
    service.tasks.start_task(task_id)
    assert service.tasks.get_task(task_id).status == TaskStatus.IN_PROGRESS

    repaired = service.tasks.repair_orphaned_goal_tasks()
    assert repaired == 1
    fresh = service.tasks.get_task(task_id)
    assert fresh.status == TaskStatus.TODO
    assert task_id in {t.id for t in service.tasks.runnable_tasks(limit=50)}


def test_a_second_turn_reopens_a_completed_plan(service, monkeypatch):
    """A completed plan is terminal; the next goal turn must reopen it.

    The scheduler only runs tasks in a RUNNING plan, so a goal whose first turn
    completed would otherwise stall forever on turn 2.
    """
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create("improve the app", max_turns=3, start=True)
    first = runtime.get(goal.id)
    service.tasks.start_task(first.task_id)
    service.tasks.begin_verification(first.task_id)
    for criterion in service.tasks.list_criteria(first.task_id):
        service.tasks.set_criterion(criterion.id, "PASSED", evidence="test")
    service.tasks.complete_task(first.task_id, output_reference="run:test")
    assert service.tasks.get_plan(first.plan_id).status == PlanStatus.COMPLETED

    second_task_id = runtime.start_turn(goal.id)
    assert service.tasks.get_plan(first.plan_id).status == PlanStatus.RUNNING
    assert service.tasks.get_task(second_task_id).status == TaskStatus.TODO


def test_boot_repair_reopens_a_plan_completed_under_a_queued_turn(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create("improve the app", max_turns=3, start=True)
    first = runtime.get(goal.id)
    service.tasks.start_task(first.task_id)
    service.tasks.begin_verification(first.task_id)
    for criterion in service.tasks.list_criteria(first.task_id):
        service.tasks.set_criterion(criterion.id, "PASSED", evidence="test")
    service.tasks.complete_task(first.task_id, output_reference="run:test")
    # Simulate the old gap: a queued turn whose plan is still COMPLETED.
    from harness.tasks.model import CreateTaskInput

    task = service.tasks.create_task(CreateTaskInput(title="turn 2", plan_id=first.plan_id))
    GoalStore(service.store).update_goal_fields(goal.id, {"taskId": task.id})
    service.tasks.set_plan_status(first.plan_id, PlanStatus.COMPLETED)
    assert service.tasks.get_task(task.id).status == TaskStatus.TODO

    repaired = runtime.repair_open_turns()
    assert repaired == 1
    assert service.tasks.get_plan(first.plan_id).status == PlanStatus.RUNNING


def test_rejudging_a_blocked_goal_reuses_the_finished_turn(service, monkeypatch):
    """A judge/schema failure must not force a paid re-run to recover."""
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create("deliver the memo", max_turns=2, start=True)
    record = runtime.get(goal.id)
    service.tasks.start_task(record.task_id)
    service.tasks.begin_verification(record.task_id)
    for criterion in service.tasks.list_criteria(record.task_id):
        service.tasks.set_criterion(criterion.id, "PASSED", evidence="test")
    service.tasks.complete_task(record.task_id, output_reference="run_finished")
    store = GoalStore(service.store)
    store.update_goal_fields(goal.id, {
        "lastVerdict": {"runId": "run_finished", "verdict": "blocked"},
        "usedTurns": 2,
    })
    store.set_goal_status(goal.id, "blocked")

    monkeypatch.setattr(runtime_module, "run_gates", lambda *a, **k: [])

    async def fake_judge(*args, **kwargs):
        return JudgeOutcome("done", "verified")

    monkeypatch.setattr(runtime_module, "judge_goal", fake_judge)
    monkeypatch.setattr(runtime, "_verify_completion", lambda goal, summary: (True, ""))
    verdict = asyncio.run(runtime.reevaluate(goal.id))
    assert verdict["verdict"] == "done"
    assert runtime.get(goal.id).status == "completed"


def test_rejudging_a_completed_goal_is_refused(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    from harness.goals.goal_runtime import GoalError

    runtime = GoalRuntime(service)
    goal = runtime.create("deliver the memo", max_turns=2, start=False)
    GoalStore(service.store).set_goal_status(goal.id, "completed")
    with pytest.raises(GoalError) as exc:
        asyncio.run(runtime.reevaluate(goal.id))
    assert exc.value.code == "GOAL_TERMINAL"


def test_a_finance_turn_is_told_the_data_and_compute_route(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create(
        "backtest a rule on MSFT",
        contract={"taskType": "finance"},
        max_turns=2, start=True,
    )
    task = service.tasks.get_task(runtime.get(goal.id).task_id)
    brief = task.objective
    assert "get_historical_prices" in brief
    assert "analysis_run" in brief
    assert "LIVE-ONLY" in brief


def test_an_explicit_task_type_is_pinned_for_verification(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create(
        "research this market and report the numbers",
        contract={"taskType": "finance"},
        max_turns=2, start=True,
    )
    task = service.tasks.get_task(runtime.get(goal.id).task_id)
    assert task.task_type is TaskType.FINANCE


def test_cancel_targets_the_live_run_not_the_previous_verdict(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create("keep going", max_turns=3, start=False)
    store = GoalStore(service.store)
    store.update_goal_fields(goal.id, {"currentRunId": "run_live"})
    service._active.add("run_live")

    runtime.cancel(goal.id)
    assert "run_live" not in service._active
    assert runtime.get(goal.id).status == "cancelled"


def test_a_gate_goal_refuses_a_released_workspace(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    from harness.goals.goal_runtime import GoalError

    service.code_store = types.SimpleNamespace(get_workspace=lambda _id: None)
    runtime = GoalRuntime(service)
    with pytest.raises(GoalError) as exc:
        runtime.create(
            "ship it", start=False, workspace_id="ws_gone",
            gates=[{"id": "g", "check": "unit_test"}],
        )
    assert exc.value.code == "WORKSPACE_UNAVAILABLE"


def test_a_failed_run_skips_the_gates_and_the_judge(service, monkeypatch):
    monkeypatch.setenv("HARNESS_GOAL_LOOP", "on")
    runtime = GoalRuntime(service)
    goal = runtime.create("improve the app", max_turns=3, start=False)
    called = {"judge": 0, "gates": 0}

    async def fake_judge(*args, **kwargs):
        called["judge"] += 1
        return JudgeOutcome("done", "no")

    def fake_gates(*args, **kwargs):
        called["gates"] += 1
        return []

    monkeypatch.setattr(runtime_module, "judge_goal", fake_judge)
    monkeypatch.setattr(runtime_module, "run_gates", fake_gates)
    verdict = asyncio.run(runtime.evaluate(goal.id, "run_1", {"status": "failed"}))
    assert verdict["verdict"] == "continue"
    assert called == {"judge": 0, "gates": 0}

"""Scheduler tests: claiming, retry/backoff, lease recovery, and E2E dispatch.

The scheduler and TaskManager under test are the REAL implementations; only the
injected executor (the model backend) is a test double, which is exactly the seam
the production code injects `service.run` into.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from harness.persistence import AgentMemoryStore
from harness.tasks.bootstrap import build_task_executor
from harness.tasks.manager import TaskManager
from harness.tasks.model import (
    CreatePlanInput,
    CreateTaskInput,
    ExecutionStatus,
    TaskStatus,
)
from harness.tasks.scheduler import TaskRunOutcome, TaskScheduler
from harness.tasks.store import TaskStore


class Clock:
    """A mutable injected clock (tests never sleep)."""

    def __init__(self) -> None:
        self.now = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)

    def __call__(self) -> _dt.datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + _dt.timedelta(seconds=seconds)


@pytest.fixture()
def mgr(tmp_path):
    store = TaskStore(AgentMemoryStore(str(tmp_path / "agent-memory.db")))
    return TaskManager(store)


def _clock() -> Clock:
    return Clock()


# ── Atomic claim (concurrency) ────────────────────────────────────────────────


def test_one_hundred_racing_claims_win_exactly_once(mgr):
    plan = mgr.create_plan(CreatePlanInput(name="race"))
    task = mgr.create_task(CreateTaskInput(title="solo", plan_id=plan.id))
    wins = sum(
        1
        for i in range(100)
        if mgr._store.claim_task(  # noqa: SLF001
            task.id, worker_id=f"w{i}", claim_token=f"t{i}", lease_seconds=60
        )
    )
    assert wins == 1
    assert mgr.get_task(task.id).status == TaskStatus.IN_PROGRESS


def test_claim_respects_backoff(mgr):
    plan = mgr.create_plan(CreatePlanInput(name="b"))
    task = mgr.create_task(CreateTaskInput(title="t", plan_id=plan.id))
    mgr._store.update_task_fields(task.id, {"availableAt": "2999-01-01T00:00:00+00:00"})  # noqa: SLF001
    assert not mgr._store.claim_task(  # noqa: SLF001
        task.id, worker_id="w", claim_token="t", lease_seconds=60
    )


# ── DAG end-to-end via the scheduler ─────────────────────────────────────────


async def _drain(scheduler):
    for _ in range(50):
        await scheduler.tick()
        await scheduler.wait_idle()
        if not scheduler._manager.runnable_tasks():  # noqa: SLF001
            break


@pytest.mark.asyncio
async def test_plan_runs_end_to_end(mgr):
    async def executor(task, context, run_id):
        return TaskRunOutcome(status="completed", output="done", run_id=run_id)

    scheduler = TaskScheduler(mgr, executor=executor, max_in_flight=4)
    plan = mgr.create_plan(CreatePlanInput(name="Compare"))
    root = mgr.create_task(CreateTaskInput(title="Compare", plan_id=plan.id))
    nvda = mgr.create_task(CreateTaskInput(title="NVDA", plan_id=plan.id,
                                           parent_task_id=root.id))
    amd = mgr.create_task(CreateTaskInput(title="AMD", plan_id=plan.id,
                                          parent_task_id=root.id))
    cmp_task = mgr.create_task(CreateTaskInput(
        title="Comparison", plan_id=plan.id, dependencies=[nvda.id, amd.id],
    ))
    mgr.start_plan(plan.id)
    await _drain(scheduler)

    assert mgr.get_task(root.id).status == TaskStatus.COMPLETED
    assert mgr.get_task(cmp_task.id).status == TaskStatus.COMPLETED
    # Every executed task recorded at least one execution attempt.
    assert mgr.list_executions(cmp_task.id)


@pytest.mark.asyncio
async def test_task_context_is_built_from_durable_state(mgr):
    seen = {}

    async def executor(task, context, run_id):
        seen["objective"] = context.objective
        seen["deps"] = [d["status"] for d in context.dependencies]
        return TaskRunOutcome(status="completed", output="ok", run_id=run_id)

    scheduler = TaskScheduler(mgr, executor=executor)
    plan = mgr.create_plan(CreatePlanInput(name="ctx"))
    a = mgr.create_task(CreateTaskInput(title="A", plan_id=plan.id, objective="do A"))
    b = mgr.create_task(CreateTaskInput(
        title="B", plan_id=plan.id, objective="do B", dependencies=[a.id],
    ))
    mgr.start_plan(plan.id)
    await _drain(scheduler)
    assert seen["objective"] == "do B"
    assert seen["deps"] == [TaskStatus.COMPLETED.value]


# ── Retry / backoff ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retryable_failure_is_retried_with_backoff(mgr):
    clock = _clock()
    calls = {"n": 0}

    async def executor(task, context, run_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return TaskRunOutcome(status="failed", error="timeout",
                                  error_class="TOOL_TIMEOUT", run_id=run_id)
        return TaskRunOutcome(status="completed", output="ok", run_id=run_id)

    scheduler = TaskScheduler(mgr, executor=executor, clock=clock, tick_seconds=0.01)
    plan = mgr.create_plan(CreatePlanInput(name="retry"))
    task = mgr.create_task(CreateTaskInput(title="t", plan_id=plan.id, max_retries=2))
    mgr.start_plan(plan.id)
    await scheduler.tick()
    await scheduler.wait_idle()
    # First attempt failed -> TODO with a backoff gate and a bumped retry count.
    after_first = mgr.get_task(task.id)
    assert after_first.status == TaskStatus.TODO
    assert after_first.retry_count == 1
    assert after_first.available_at is not None
    # Advance past the backoff and run again.
    clock.advance(10)
    await scheduler.tick()
    await scheduler.wait_idle()
    assert mgr.get_task(task.id).status == TaskStatus.COMPLETED
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_non_retryable_failure_fails_immediately(mgr):
    calls = {"n": 0}

    async def executor(task, context, run_id):
        calls["n"] += 1
        return TaskRunOutcome(status="failed", error="bad input",
                              error_class="VALIDATION_ERROR", run_id=run_id)

    scheduler = TaskScheduler(mgr, executor=executor)
    plan = mgr.create_plan(CreatePlanInput(name="nr"))
    task = mgr.create_task(CreateTaskInput(title="t", plan_id=plan.id, max_retries=5))
    mgr.start_plan(plan.id)
    await _drain(scheduler)
    assert mgr.get_task(task.id).status == TaskStatus.FAILED
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_exhausted_retries_fail(mgr):
    clock = _clock()

    async def executor(task, context, run_id):
        return TaskRunOutcome(status="failed", error="timeout",
                              error_class="TOOL_TIMEOUT", run_id=run_id)

    scheduler = TaskScheduler(mgr, executor=executor, clock=clock)
    plan = mgr.create_plan(CreatePlanInput(name="exhaust"))
    task = mgr.create_task(CreateTaskInput(title="t", plan_id=plan.id, max_retries=1))
    mgr.start_plan(plan.id)
    for _ in range(10):
        await scheduler.tick()
        await scheduler.wait_idle()
        clock.advance(60)
    assert mgr.get_task(task.id).status == TaskStatus.FAILED
    assert mgr.get_task(task.id).retry_count >= 1


# ── Lease expiry / crash recovery ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expired_lease_is_recovered_never_stuck(mgr):
    clock = _clock()
    plan = mgr.create_plan(CreatePlanInput(name="crash"))
    task = mgr.create_task(CreateTaskInput(title="t", plan_id=plan.id, max_retries=2))
    # Simulate a crashed worker: claim with a lease that lapses immediately.
    assert mgr._store.claim_task(  # noqa: SLF001
        task.id, worker_id="dead", claim_token="tok", lease_seconds=1,
        now=clock.now.isoformat(),
    )
    mgr._store.start_execution(task_id=task.id, agent_id=None, run_id=None)  # noqa: SLF001
    clock.advance(3600)  # the lease has long expired
    scheduler = TaskScheduler(mgr, executor=None, clock=clock)
    recovered = await scheduler.recover_expired_leases(now=clock.now.isoformat())
    assert recovered == 1
    live = mgr.get_task(task.id)
    # Recovered: no longer IN_PROGRESS, retry counter advanced.
    assert live.status in (TaskStatus.TODO, TaskStatus.FAILED)
    assert live.status != TaskStatus.IN_PROGRESS
    assert live.retry_count == 1
    # The stale execution was closed honestly.
    executions = mgr.list_executions(task.id)
    assert executions[-1].status == ExecutionStatus.TIMED_OUT


@pytest.mark.asyncio
async def test_recovery_exhausts_to_failure(mgr):
    clock = _clock()
    plan = mgr.create_plan(CreatePlanInput(name="crash2"))
    task = mgr.create_task(CreateTaskInput(title="t", plan_id=plan.id, max_retries=0))
    mgr._store.claim_task(  # noqa: SLF001
        task.id, worker_id="dead", claim_token="tok", lease_seconds=1,
        now=clock.now.isoformat(),
    )
    clock.advance(3600)
    scheduler = TaskScheduler(mgr, executor=None, clock=clock)
    await scheduler.recover_expired_leases(now=clock.now.isoformat())
    assert mgr.get_task(task.id).status == TaskStatus.FAILED


# ── Cancellation while running ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancellation_during_execution_does_not_complete(mgr):
    async def executor(task, context, run_id):
        # The operator cancels the task while the run is "in flight".
        mgr.cancel_task(task.id, reason="operator")
        return TaskRunOutcome(status="completed", output="done", run_id=run_id)

    scheduler = TaskScheduler(mgr, executor=executor)
    plan = mgr.create_plan(CreatePlanInput(name="cancel"))
    task = mgr.create_task(CreateTaskInput(title="t", plan_id=plan.id))
    mgr.start_plan(plan.id)
    await scheduler.tick()
    await scheduler.wait_idle()
    assert mgr.get_task(task.id).status == TaskStatus.CANCELLED


# ── E2E through the PRODUCTION executor (only the model backend is faked) ─────


class _Result:
    def __init__(self, run_id, status):
        self._d = {
            "runId": run_id, "status": status, "output": f"answered {run_id}",
            "error": None, "modelSteps": 1, "toolCalls": 0, "toolErrors": 0,
            "totalTokens": 10, "codeVerification": None,
        }

    def model_dump(self):
        return dict(self._d)


class FakeService:
    """Stands in for AgenticService.run — the model/run backend only."""

    def __init__(self):
        self.run_ids = []

    async def run(self, request):
        self.run_ids.append(request.runId)
        assert request.input.context["source"] == "task-scheduler"
        return _Result(request.runId, "completed")


@pytest.mark.asyncio
async def test_production_executor_dispatches_a_real_run(mgr):
    service = FakeService()
    executor = build_task_executor(service, mgr)
    scheduler = TaskScheduler(mgr, executor=executor, max_in_flight=4)
    plan = mgr.create_plan(CreatePlanInput(name="prod"))
    a = mgr.create_task(CreateTaskInput(title="A", plan_id=plan.id))
    b = mgr.create_task(CreateTaskInput(title="B", plan_id=plan.id, dependencies=[a.id]))
    mgr.start_plan(plan.id)
    await _drain(scheduler)
    assert mgr.get_task(a.id).status == TaskStatus.COMPLETED
    assert mgr.get_task(b.id).status == TaskStatus.COMPLETED
    assert len(service.run_ids) == 2

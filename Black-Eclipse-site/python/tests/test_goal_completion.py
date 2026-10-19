"""Round 4 (W8) acceptance: a goal to a VERIFIED result, durably.

The scheduler, manager, store, goal intake, task-type verifier and checkpoint
machinery under test are the REAL implementations. Only the injected executor —
the seam where production injects `service.run` — is a scripted double, exactly
like `test_tasks_scheduler.py` and `team_helpers.py`.

The scenarios are the round's acceptance criteria:

* build a small app → run it → find a deliberate defect → repair → rerun the
  tests → deliver the artifact (completion only after the evidence passes);
* an unverifiable goal ends BLOCKED naming the exact missing evidence;
* an exceeded contract budget ends BLOCKED naming the violated cap;
* a crashed worker's task resumes from its durable checkpoint and delivers
  exactly once.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from harness.persistence import AgentMemoryStore
from harness.tasks.goal import intake_goal
from harness.tasks.manager import TaskManager
from harness.tasks.model import (
    BlockedReason,
    CreatePlanInput,
    CreateTaskInput,
    ExecutionStatus,
    GoalContract,
    TaskStatus,
    TaskType,
)
from harness.tasks.scheduler import TaskRunOutcome, TaskScheduler
from harness.tasks.store import TaskStore


class Clock:
    def __init__(self) -> None:
        self.now = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)

    def __call__(self) -> _dt.datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + _dt.timedelta(seconds=seconds)


@pytest.fixture()
def mgr(tmp_path):
    return TaskManager(TaskStore(AgentMemoryStore(str(tmp_path / "agent-memory.db"))))


async def _drain(scheduler, manager, clock, rounds: int = 20) -> None:
    """Tick until no runnable work remains, advancing the clock past backoffs."""
    for _ in range(rounds):
        await scheduler.tick()
        await scheduler.wait_idle()
        if not manager.runnable_tasks():
            break
        clock.advance(30)


def _goal_task(manager, *, request: str, max_retries: int = 2, budgets=None):
    intake = intake_goal(request)
    contract = intake.contract
    if budgets is not None:
        contract = GoalContract(
            objective=contract.objective, deliverables=contract.deliverables,
            constraints=contract.constraints, acceptance=contract.acceptance,
            budgets=budgets,
        )
    plan = manager.create_plan(CreatePlanInput(name=intake.title, objective=contract.objective))
    task = manager.create_task(CreateTaskInput(
        title=intake.title, plan_id=plan.id, objective=contract.objective,
        task_type=intake.task_type, goal_contract=contract, max_retries=max_retries,
    ))
    manager.start_plan(plan.id)
    return plan, task, intake


def _record(command_class: str, exit_code: int) -> dict:
    return {
        "commandClass": command_class, "exitCode": exit_code,
        "outputDigest": "d" * 16, "argv": ["pytest"], "startedAt": "2026-01-01T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_build_break_repair_deliver(mgr, tmp_path):
    """The headline scenario: a defect is caught by the verifier, repaired with
    the missing evidence named, and only then does the task complete."""
    plan, task, intake = _goal_task(mgr, request="build a small greeting app with tests")
    assert intake.task_type is TaskType.CODE
    workspace = tmp_path / "app"
    workspace.mkdir()
    attempts: list[dict] = []

    async def executor(task_, context, run_id):
        attempts.append({
            "attempt": len(attempts) + 1,
            "previousError": (
                context.previous_attempts[-1]["error"] if context.previous_attempts else None
            ),
        })
        if len(attempts) == 1:
            # Build the app — with a DELIBERATE defect the test run catches.
            (workspace / "greeting.py").write_text("def greet():\n    return 'hi'\n")
            return TaskRunOutcome(
                status="completed", output="wrote greeting.py; tests failed",
                run_id=run_id, metrics={"toolCalls": 2},
                evidence={"codeVerification": {
                    "records": [_record("python_test", 1)], "artifacts": [],
                }},
            )
        # Repair and rerun the tests.
        (workspace / "greeting.py").write_text("def greet():\n    return 'hello'\n")
        return TaskRunOutcome(
            status="completed", output="tests passed",
            run_id=run_id, metrics={"toolCalls": 2},
            artifacts=[{
                "uri": str(workspace / "greeting.py"), "kind": "file",
                "label": "greeting app",
            }],
            evidence={"codeVerification": {
                "records": [_record("python_test", 0)], "artifacts": [],
            }},
        )

    clock = Clock()
    scheduler = TaskScheduler(mgr, executor=executor, clock=clock, lease_seconds=600)
    await _drain(scheduler, mgr, clock)

    assert len(attempts) == 2, "the defect must force exactly one repair attempt"
    # The repair attempt was TOLD what was missing (never a blind retry).
    assert attempts[1]["previousError"]
    assert "no successful tests run was recorded" in attempts[1]["previousError"]

    final = mgr.get_task(task.id)
    assert final.status == TaskStatus.COMPLETED
    assert final.progress == 100
    assert mgr.get_plan(plan.id).status.value == "COMPLETED"

    # The artifact was delivered and attached by reference.
    artifacts = mgr.list_artifacts(task.id)
    assert len(artifacts) == 1 and artifacts[0].label == "greeting app"

    # Completion is EVIDENCE: the durable checkpoint carries the verdict.
    checkpoints = mgr.list_checkpoints(task.id)
    assert checkpoints[-1].label == "run_complete"
    verdict = checkpoints[-1].payload.get("verification")
    assert verdict and verdict["ok"] is True
    assert {c["name"] for c in verdict["checks"]} >= {"run_completed", "tests"}

    # The immutable history recorded the rejection AND the completion.
    types = {e.type for e in mgr._store.list_task_events(task.id)}  # noqa: SLF001
    assert "TASK_COMPLETION_REJECTED" in types
    assert "TASK_COMPLETED" in types
    executions = mgr.list_executions(task.id)
    assert [e.status for e in executions] == [
        ExecutionStatus.FAILED, ExecutionStatus.COMPLETED,
    ]
    assert executions[0].error_class == "VERIFICATION_FAILED"


@pytest.mark.asyncio
async def test_unverifiable_goal_ends_blocked_with_the_missing_evidence(mgr):
    plan, task, _ = _goal_task(
        mgr, request="build a small greeting app with tests", max_retries=1,
    )

    async def never_passes(task_, context, run_id):
        return TaskRunOutcome(
            status="completed", output="wrote files but the tests never ran",
            run_id=run_id, metrics={"toolCalls": 1},
            evidence={"codeVerification": {"records": [], "artifacts": []}},
        )

    clock = Clock()
    scheduler = TaskScheduler(mgr, executor=never_passes, clock=clock, lease_seconds=600)
    await _drain(scheduler, mgr, clock)

    final = mgr.get_task(task.id)
    # NOT failed, NOT completed: a non-terminal, inspectable dead end naming the
    # exact missing evidence and the reason class.
    assert final.status == TaskStatus.BLOCKED
    assert final.blocked_reason is BlockedReason.VERIFICATION
    assert final.error_class == "VERIFICATION_FAILED"
    assert "no successful tests run was recorded" in (final.error or "")
    assert len(mgr.list_executions(task.id)) == 2  # the bounded repair attempt ran

    types = {e.type for e in mgr._store.list_task_events(task.id)}  # noqa: SLF001
    assert "TASK_ESCALATED" in types


@pytest.mark.asyncio
async def test_budget_exceeded_blocks_with_the_violated_cap(mgr):
    from harness.tasks.model import TaskBudget

    plan, task, _ = _goal_task(
        mgr, request="build a small greeting app with tests",
        budgets=TaskBudget(max_tool_calls=1),
    )

    async def over_budget(task_, context, run_id):
        return TaskRunOutcome(
            status="completed", output="done", run_id=run_id,
            artifacts=[{"uri": "/w/greeting.py", "label": "greeting app"}],
            metrics={"toolCalls": 5},
            evidence={"codeVerification": {
                "records": [_record("python_test", 0)], "artifacts": [],
            }},
        )

    clock = Clock()
    scheduler = TaskScheduler(mgr, executor=over_budget, clock=clock, lease_seconds=600)
    await _drain(scheduler, mgr, clock)

    final = mgr.get_task(task.id)
    assert final.status == TaskStatus.BLOCKED
    assert final.blocked_reason is BlockedReason.RESOURCE
    assert final.error_class == "BUDGET_EXCEEDED"
    assert "5 tool calls exceed the contract budget of 1" in (final.error or "")
    # A budget exhaustion is never retried — that would spend more of it.
    assert len(mgr.list_executions(task.id)) == 1
    assert final.retry_count == 0


@pytest.mark.asyncio
async def test_crashed_worker_resumes_from_checkpoint_and_delivers_once(mgr):
    """Kill the worker mid-run; the durable claim/lease/checkpoint lets a new
    worker resume and complete the goal — with exactly one delivery."""
    plan, task, _ = _goal_task(mgr, request="build a small greeting app with tests")

    clock = Clock()
    # A worker claimed the task, opened an attempt and wrote its dispatch
    # checkpoint — then the PROCESS DIED: no settle, no release, no cancel.
    # This is exactly the durable state the scheduler leaves behind.
    assert mgr._store.claim_task(  # noqa: SLF001
        task.id, worker_id="dead-worker", claim_token="dead-token",
        lease_seconds=10, now=clock().isoformat(),
    )
    execution = mgr._store.start_execution(  # noqa: SLF001
        task_id=task.id, agent_id=task.assigned_agent_id, run_id=None,
    )
    mgr.save_checkpoint(
        task.id, label="run_start", execution_id=execution.id,
        payload={"runId": f"taskrun_{task.id}_{execution.attempt}",
                 "attempt": execution.attempt, "progress": 0},
    )
    assert mgr.get_task(task.id).status == TaskStatus.IN_PROGRESS
    assert mgr.list_checkpoints(task.id)[-1].label == "run_start"

    clock.advance(30)  # the dead worker's lease has long expired

    deliveries: list[str] = []

    async def deliver(task_, context, run_id):
        deliveries.append(run_id)
        return TaskRunOutcome(
            status="completed", output="tests passed", run_id=run_id,
            artifacts=[{"uri": "/w/greeting.py", "kind": "file", "label": "greeting app"}],
            metrics={"toolCalls": 2},
            evidence={"codeVerification": {
                "records": [_record("python_test", 0)], "artifacts": [],
            }},
        )

    resumed = TaskScheduler(mgr, executor=deliver, clock=clock, lease_seconds=10)
    await _drain(resumed, mgr, clock)

    executions = mgr.list_executions(task.id)
    assert [e.status for e in executions] == [
        ExecutionStatus.TIMED_OUT,   # the crashed attempt, reconciled honestly
        ExecutionStatus.COMPLETED,   # the resumed attempt
    ]
    assert executions[0].error_class == "LEASE_EXPIRED"
    final = mgr.get_task(task.id)
    assert final.status == TaskStatus.COMPLETED
    assert final.retry_count == 1  # the recovery is auditable, not silent

    # Exactly one delivery: the crash never duplicated the side effect.
    assert len(deliveries) == 1
    assert len(mgr.list_artifacts(task.id)) == 1

    checkpoints = mgr.list_checkpoints(task.id)
    assert [c.label for c in checkpoints] == ["run_start", "run_start", "run_complete"]
    verdict = checkpoints[-1].payload.get("verification")
    assert verdict and verdict["ok"] is True

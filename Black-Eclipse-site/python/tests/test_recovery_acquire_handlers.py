"""Round 4 (W5/W9 remainder): production acquisition handlers.

The lifecycle stops with a typed plan; these tests pin the CALLER half — a
`build` step routes through the real engineering/code-task surface, the original
task parks on a REQUIRES dependency and the existing DAG resumes it when the
capability completes, an install/enable step parks ASKING_USER for the operator,
and the resume callback restores from the durable checkpoint. Nothing
self-installs; nothing self-enables.
"""

from __future__ import annotations

import datetime as _dt
import types

import pytest

from harness.persistence import AgentMemoryStore
from harness.recovery.acquire_handlers import (
    acquire_for_task,
    build_acquisition_handlers,
    proposal_from_dict,
    resume_callback,
)
from harness.tasks.manager import TaskManager
from harness.tasks.model import (
    BlockedReason,
    CreatePlanInput,
    CreateTaskInput,
    ExecutionStatus,
    TaskStatus,
    WaitingReason,
)
from harness.tasks.scheduler import TaskRunOutcome, TaskScheduler
from harness.tasks.store import TaskStore


class Clock:
    def __init__(self) -> None:
        self.now = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)

    def __call__(self) -> _dt.datetime:
        return self.now


@pytest.fixture()
def manager(tmp_path):
    return TaskManager(TaskStore(AgentMemoryStore(str(tmp_path / "agent-memory.db"))))


def _goal_task(manager, *, title="add a world clock widget"):
    plan = manager.create_plan(CreatePlanInput(name="goal", objective=title))
    task = manager.create_task(CreateTaskInput(
        title=title, plan_id=plan.id, objective=title,
        acceptance_criteria=[{"text": "the widget renders"}],
    ))
    manager.start_plan(plan.id)
    return plan, task


def _started_goal_task(manager, *, title="add a world clock widget"):
    """The acquire tests model a task IN_PROGRESS (as a real run is)."""
    plan, task = _goal_task(manager, title=title)
    manager.start_task(task.id)
    return plan, task


def _stop_payload(*, action="build", surface="engineering", requires_approval=True):
    return {
        "stop": True,
        "acquisition": {
            "query": "build a swap-spread widget",
            "resolvedBy": None,
            "steps": [{
                "action": action,
                "description": "build a swap-spread widget",
                "capabilityId": None,
                "requiresApproval": requires_approval,
                "surface": surface,
                "ready": False,
                "reason": "build through ui_start_engineering",
                "missing": ["the build target and its acceptance test are not supplied"],
            }],
            "requiresApproval": requires_approval,
            "gaps": [],
            "retry": {"action": "resume_task", "from": "last_checkpoint", "taskId": None},
        },
    }


def test_proposal_round_trips_from_the_stop_payload():
    proposal = proposal_from_dict(_stop_payload())
    assert proposal.steps[0].action == "build"
    assert proposal.steps[0].surface == "engineering"


def test_build_routes_to_the_engineering_surface(manager):
    plan, task = _started_goal_task(manager)

    calls: list[str] = []

    class _Engineering:
        available = True

        def start(self, text, **kwargs):
            calls.append(text)
            return {"created": True, "taskId": "task_eng", "planId": "plan_eng"}

    service = types.SimpleNamespace(ui=types.SimpleNamespace(engineering=_Engineering()))
    result = acquire_for_task(service, manager, task, stop_payload=_stop_payload(), run_id="run_x")

    assert result["status"] == "executed"
    assert result["result"]["surface"] == "engineering"
    assert result["resume"] == "operator"
    assert calls == ["build a swap-spread widget"]
    # The UI gate creates its own plan (a cross-plan edge is refused by design),
    # so the original task parks WAITING for an explicit resume.
    live = manager.get_task(task.id)
    assert live.status == TaskStatus.WAITING
    assert live.waiting_reason is WaitingReason.AGENT


def test_build_without_ui_creates_a_same_plan_code_task_and_the_dag_resumes(manager):
    plan, task = _started_goal_task(manager)
    service = types.SimpleNamespace(ui=None)

    result = acquire_for_task(service, manager, task, stop_payload=_stop_payload(), run_id="run_y")
    assert result["status"] == "executed"
    assert result["result"]["surface"] == "code_task"
    assert result["resume"] == "dependency"
    capability_task_id = result["capabilityTaskId"]
    capability = manager.get_task(capability_task_id)
    assert capability.assigned_agent_id == "code-agent"
    assert capability.plan_id == task.plan_id  # the resume edge must be same-plan

    # The original task is parked BLOCKED on the capability task, edge included.
    live = manager.get_task(task.id)
    assert live.status == TaskStatus.BLOCKED
    assert live.blocked_reason is BlockedReason.DEPENDENCY
    assert capability_task_id in live.blocked_by
    deps = [d.depends_on_task_id for d in manager.get_dependencies(task.id)]
    assert capability_task_id in deps

    # The capability task completes (its own verification passed) → the DAG
    # unblocks the original task, which the scheduler will re-dispatch.
    manager.start_task(capability_task_id)
    criteria = manager.list_criteria(capability_task_id)
    for criterion in criteria:
        manager.set_criterion(criterion.id, "PASSED", evidence="verified")
    manager.complete_task(capability_task_id)

    resumed = manager.get_task(task.id)
    assert resumed.status == TaskStatus.TODO
    assert resumed.blocked_reason is None


def test_install_step_parks_asking_user_and_the_resume_callback_resumes(manager):
    plan, task = _started_goal_task(manager)
    manager.save_checkpoint(task.id, label="run_start", payload={"progress": 10})
    service = types.SimpleNamespace(ui=None)

    result = acquire_for_task(
        service, manager, task,
        stop_payload=_stop_payload(action="install", surface="operator"),
        run_id="run_z",
    )
    assert result["status"] == "approval_required"
    parked = manager.get_task(task.id)
    assert parked.status == TaskStatus.ASKING_USER
    assert parked.waiting_reason is WaitingReason.APPROVAL
    # Nothing was installed and no capability task was created.
    assert all(t.title != "Build capability: build a swap-spread widget"
               for t in manager.list_tasks(limit=50))

    resumed = resume_callback(manager, task.id)()
    assert resumed["resumed"] is True
    assert resumed["checkpointId"]
    assert manager.get_task(task.id).status == TaskStatus.TODO


def test_install_handlers_never_self_grant(manager):
    plan, task = _started_goal_task(manager)
    handlers = build_acquisition_handlers(types.SimpleNamespace(ui=None), manager, task)
    from harness.recovery.acquisition import AcquisitionStep

    step = AcquisitionStep(
        action="install", description="install the plugin", capability_id="x",
        requires_approval=True, surface="operator", ready=False, reason="r",
        missing=("unknown: no source, credential or dependency was supplied",),
    )
    out = handlers["install"](step)
    assert out["status"] == "approval_required"
    assert "nothing was installed" in out["next"]


def test_no_actionable_step_is_reported_honestly(manager):
    plan, task = _started_goal_task(manager)
    result = acquire_for_task(
        types.SimpleNamespace(ui=None), manager, task,
        stop_payload={"stop": True, "acquisition": {"query": "q", "steps": []}},
    )
    assert result["handled"] is False
    assert result["status"] == "no_actionable_step"
    assert manager.get_task(task.id).status == TaskStatus.IN_PROGRESS  # untouched


@pytest.mark.asyncio
async def test_the_scheduler_records_a_waiting_outcome_without_retry(manager):
    """A parked task must not be failed or retried by the scheduler."""
    plan, task = _goal_task(manager)
    blocker = manager.create_task(CreateTaskInput(title="cap", plan_id=plan.id))

    async def executor(task_, context, run_id):
        # Simulate the acquisition caller: park on a dependency, then report.
        manager.add_dependency(task_.id, blocker.id)
        manager.block_task(task_.id, reason="DEPENDENCY", blocked_by=[blocker.id])
        return TaskRunOutcome(
            status="waiting", run_id=run_id,
            error="capability acquisition routed: task must complete first",
            error_class="ACQUISITION_PENDING",
        )

    scheduler = TaskScheduler(manager, executor=executor, clock=Clock(), lease_seconds=60)
    await scheduler.tick()
    await scheduler.wait_idle()

    live = manager.get_task(task.id)
    assert live.status == TaskStatus.BLOCKED
    assert live.retry_count == 0
    executions = manager.list_executions(task.id)
    assert executions[-1].status == ExecutionStatus.FAILED
    assert executions[-1].error_class == "ACQUISITION_PENDING"


def test_the_operator_routes_execute_and_resume_through_the_real_surfaces(
    manager, tmp_path, monkeypatch,
):
    """The W5/W9 operator surface: execute an approved step (once), park the
    task on the capability, then resume from the durable checkpoint."""
    from harness.eclipse_memory.store import EclipseMemoryStore
    from harness.recovery.discovery import CapabilityIndex
    from harness.recovery.service import RecoveryService
    from harness.routers import recovery as recovery_router

    plan_, task = _started_goal_task(manager)
    engine = RecoveryService(
        EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")),
        capability_index=CapabilityIndex(),  # no match ⇒ the build route is planned
    )
    recorded = engine.record_failure(
        code="UI_CAPABILITY_GAP",
        message="no registered component matches: add a world clock",
        subsystem="ui", task_id=task.id,
    )
    incident_id = recorded["incidentId"]
    monkeypatch.setattr(
        recovery_router, "service",
        types.SimpleNamespace(recovery=engine, tasks=manager, ui=None),
    )

    plan = recovery_router.plan_incident_acquisition(incident_id)
    steps = plan["acquisition"]["steps"]
    build_index = next(i for i, step in enumerate(steps) if step["action"] == "build")

    # Without the operator's approval the mutation step is handed back.
    refused = recovery_router.execute_incident_acquisition(
        incident_id, {"stepIndex": build_index, "approved": False},
    )
    assert refused["outcome"]["status"] == "approval_required"
    assert manager.get_task(task.id).status == TaskStatus.ASKING_USER

    # Approved: the real code-task route runs ONCE and parks the task on it.
    done = recovery_router.execute_incident_acquisition(
        incident_id, {"stepIndex": build_index, "approved": True},
    )
    assert done["success"] is True
    assert done["parked"]["resume"] == "dependency"
    capability_tasks = [
        t for t in manager.list_tasks(plan_id=task.plan_id, limit=50)
        if t.metadata.get("kind") == "acquisition"
    ]
    assert len(capability_tasks) == 1  # never executed twice
    assert manager.get_task(task.id).status == TaskStatus.BLOCKED

    # The resume route restores the task from its durable checkpoint.
    manager.save_checkpoint(task.id, label="operator_resume", payload={"progress": 25})
    resumed = recovery_router.resume_incident_task(incident_id)
    assert resumed["success"] is True
    assert resumed["resume"]["resumed"] is True
    assert manager.get_task(task.id).status == TaskStatus.TODO

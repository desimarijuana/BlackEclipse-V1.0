"""Integration tests for TaskManager over the durable store."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.tasks.manager import TaskError, TaskManager
from harness.tasks.model import (
    CreatePlanInput,
    CreateTaskInput,
    CriterionState,
    DependencyKind,
    PlanStatus,
    TaskPriority,
    TaskStatus,
    WaitingReason,
)
from harness.tasks.store import TaskStore


@pytest.fixture()
def mgr(tmp_path):
    store = TaskStore(AgentMemoryStore(str(tmp_path / "agent-memory.db")))
    return TaskManager(store)


def _plan(mgr):
    return mgr.create_plan(CreatePlanInput(name="Compare NVDA/AMD", objective="compare"))


def test_create_plan_and_task(mgr):
    plan = _plan(mgr)
    assert plan.status == PlanStatus.PLANNING
    task = mgr.create_task(CreateTaskInput(title="Analyze NVDA", plan_id=plan.id))
    assert task.status == TaskStatus.TODO
    assert task.priority == TaskPriority.NORMAL
    # The plan remembers its root.
    assert mgr.get_plan(plan.id).root_task_id == task.id


def test_task_requires_a_home(mgr):
    with pytest.raises(Exception):
        CreateTaskInput(title="orphan")


def test_invalid_plan_and_parent_are_rejected(mgr):
    with pytest.raises(TaskError) as exc:
        mgr.create_task(CreateTaskInput(title="x", plan_id="plan_nope"))
    assert exc.value.code == "INVALID_PLAN"
    with pytest.raises(TaskError) as exc:
        mgr.create_task(CreateTaskInput(title="x", parent_task_id="task_nope"))
    assert exc.value.code == "INVALID_PARENT"


def test_cycle_is_rejected_before_persisting(mgr):
    plan = _plan(mgr)
    a = mgr.create_task(CreateTaskInput(title="A", plan_id=plan.id))
    b = mgr.create_task(CreateTaskInput(title="B", plan_id=plan.id, dependencies=[a.id]))
    with pytest.raises(TaskError) as exc:
        mgr.add_dependency(a.id, b.id)
    assert exc.value.code == "DEPENDENCY_CYCLE"
    # The edge was NOT persisted.
    assert all(d.depends_on_task_id != b.id for d in mgr.get_dependencies(a.id))


def test_self_dependency_is_rejected(mgr):
    plan = _plan(mgr)
    a = mgr.create_task(CreateTaskInput(title="A", plan_id=plan.id))
    with pytest.raises(TaskError) as exc:
        mgr.add_dependency(a.id, a.id)
    assert exc.value.code == "DEPENDENCY_CYCLE"


def test_dependency_blocks_then_unblocks(mgr):
    plan = _plan(mgr)
    a = mgr.create_task(CreateTaskInput(title="A", plan_id=plan.id))
    d = mgr.create_task(CreateTaskInput(title="D", plan_id=plan.id, dependencies=[a.id]))
    assert mgr.get_task(d.id).status == TaskStatus.BLOCKED
    assert mgr.get_task(d.id).blocked_reason.value == "DEPENDENCY"
    mgr.complete_task(a.id)
    assert mgr.get_task(d.id).status == TaskStatus.TODO


def test_diamond_unblocks_only_when_last_prerequisite_completes(mgr):
    plan = _plan(mgr)
    a = mgr.create_task(CreateTaskInput(title="A", plan_id=plan.id))
    b = mgr.create_task(CreateTaskInput(title="B", plan_id=plan.id))
    d = mgr.create_task(CreateTaskInput(title="D", plan_id=plan.id, dependencies=[a.id, b.id]))
    mgr.complete_task(a.id)
    assert mgr.get_task(d.id).status == TaskStatus.BLOCKED
    mgr.complete_task(b.id)
    assert mgr.get_task(d.id).status == TaskStatus.TODO


def test_completion_rejected_until_criteria_pass(mgr):
    plan = _plan(mgr)
    t = mgr.create_task(CreateTaskInput(
        title="Research", plan_id=plan.id,
        acceptance_criteria=[{"text": "10-K obtained"}],
    ))
    with pytest.raises(TaskError) as exc:
        mgr.complete_task(t.id)
    assert exc.value.code == "COMPLETION_REJECTED"
    criteria = mgr.list_criteria(t.id)
    mgr.set_criterion(criteria[0].id, CriterionState.PASSED, evidence="sec.gov")
    done = mgr.complete_task(t.id)
    assert done.status == TaskStatus.COMPLETED
    assert done.progress == 100


def test_completion_force_records_an_override(mgr):
    plan = _plan(mgr)
    t = mgr.create_task(CreateTaskInput(
        title="R", plan_id=plan.id, acceptance_criteria=[{"text": "x"}],
    ))
    done = mgr.complete_task(t.id, force=True)
    assert done.status == TaskStatus.COMPLETED
    events = [e.type for e in mgr._store.list_task_events(t.id)]
    assert "TASK_COMPLETION_OVERRIDDEN" in events


def test_parent_cannot_complete_while_required_child_open(mgr):
    plan = _plan(mgr)
    parent = mgr.create_task(CreateTaskInput(title="Parent", plan_id=plan.id))
    child = mgr.create_task(CreateTaskInput(title="Child", plan_id=plan.id,
                                            parent_task_id=parent.id))
    with pytest.raises(TaskError):
        mgr.complete_task(parent.id)
    mgr.complete_task(child.id)
    # Parent auto-completes via roll-up when its last required child completes.
    assert mgr.get_task(parent.id).status == TaskStatus.COMPLETED


def test_parent_progress_rolls_up_and_clamps(mgr):
    plan = _plan(mgr)
    parent = mgr.create_task(CreateTaskInput(title="P", plan_id=plan.id))
    a = mgr.create_task(CreateTaskInput(title="A", plan_id=plan.id, parent_task_id=parent.id))
    b = mgr.create_task(CreateTaskInput(title="B", plan_id=plan.id, parent_task_id=parent.id))
    assert mgr.get_task(parent.id).progress == 0
    mgr.complete_task(a.id)
    assert mgr.get_task(parent.id).progress == 50
    mgr.complete_task(b.id)
    assert mgr.get_task(parent.id).progress == 100


def test_optional_child_failure_does_not_fail_parent(mgr):
    plan = _plan(mgr)
    parent = mgr.create_task(CreateTaskInput(title="P", plan_id=plan.id))
    optional = mgr.create_task(CreateTaskInput(
        title="opt", plan_id=plan.id, parent_task_id=parent.id, required=False,
    ))
    required = mgr.create_task(CreateTaskInput(
        title="req", plan_id=plan.id, parent_task_id=parent.id,
    ))
    mgr.fail_task(optional.id, error="nope")
    assert mgr.get_task(parent.id).status == TaskStatus.IN_PROGRESS
    mgr.complete_task(required.id)
    assert mgr.get_task(parent.id).status == TaskStatus.COMPLETED


def test_cancel_cascades_to_children(mgr):
    plan = _plan(mgr)
    parent = mgr.create_task(CreateTaskInput(title="P", plan_id=plan.id))
    child = mgr.create_task(CreateTaskInput(title="C", plan_id=plan.id,
                                            parent_task_id=parent.id))
    mgr.start_task(child.id)
    cancelled = mgr.cancel_task(parent.id, reason="operator")
    ids = {t.id for t in cancelled}
    assert parent.id in ids and child.id in ids
    assert mgr.get_task(child.id).status == TaskStatus.CANCELLED
    assert mgr.get_task(parent.id).status == TaskStatus.CANCELLED


def test_wait_and_resume(mgr):
    plan = _plan(mgr)
    t = mgr.create_task(CreateTaskInput(title="T", plan_id=plan.id))
    mgr.wait_task(t.id, reason=WaitingReason.USER_INPUT)
    assert mgr.get_task(t.id).waiting_reason == WaitingReason.USER_INPUT
    mgr.resume_task(t.id)
    assert mgr.get_task(t.id).status == TaskStatus.TODO
    assert mgr.get_task(t.id).waiting_reason is None


def test_invalid_transition_is_refused(mgr):
    plan = _plan(mgr)
    t = mgr.create_task(CreateTaskInput(title="T", plan_id=plan.id))
    mgr.complete_task(t.id)
    with pytest.raises(TaskError) as exc:
        mgr.start_task(t.id)
    assert exc.value.code == "INVALID_TRANSITION"
    # reopen is the explicit path back.
    reopened = mgr.reopen_task(t.id)
    assert reopened.status == TaskStatus.TODO


def test_retry_from_failed(mgr):
    plan = _plan(mgr)
    t = mgr.create_task(CreateTaskInput(title="T", plan_id=plan.id))
    mgr.start_task(t.id)
    mgr.fail_task(t.id, error="timeout", error_class="TIMEOUT")
    retried = mgr.retry_task(t.id)
    assert retried.status == TaskStatus.TODO
    assert retried.retry_count == 1


def test_runnable_excludes_containers_and_claimed(mgr):
    plan = _plan(mgr)
    parent = mgr.create_task(CreateTaskInput(title="P", plan_id=plan.id))
    leaf = mgr.create_task(CreateTaskInput(title="L", plan_id=plan.id,
                                           parent_task_id=parent.id))
    runnable = {t.id for t in mgr.runnable_tasks()}
    assert leaf.id in runnable
    assert parent.id not in runnable  # a container is never dispatched directly


def test_priority_ordering(mgr):
    plan = _plan(mgr)
    low = mgr.create_task(CreateTaskInput(title="low", plan_id=plan.id,
                                          priority=TaskPriority.LOW))
    critical = mgr.create_task(CreateTaskInput(title="crit", plan_id=plan.id,
                                               priority=TaskPriority.CRITICAL))
    order = [t.id for t in mgr.runnable_tasks()]
    assert order.index(critical.id) < order.index(low.id)


def test_events_are_recorded(mgr):
    plan = _plan(mgr)
    t = mgr.create_task(CreateTaskInput(title="T", plan_id=plan.id))
    mgr.start_task(t.id)
    mgr.complete_task(t.id)
    types = [e.type for e in mgr._store.list_task_events(t.id)]
    assert "TASK_CREATED" in types
    assert "TASK_STARTED" in types
    assert "TASK_COMPLETED" in types


def test_artifacts_and_checkpoints(mgr):
    plan = _plan(mgr)
    t = mgr.create_task(CreateTaskInput(title="T", plan_id=plan.id))
    mgr.attach_artifact(t.id, uri="report.md", kind="file", label="report")
    assert len(mgr.list_artifacts(t.id)) == 1
    mgr.save_checkpoint(t.id, label="half-way", payload={"step": 1})
    checkpoints = mgr.list_checkpoints(t.id)
    assert checkpoints and checkpoints[0].label == "half-way"


def test_plan_view_tree_and_stats(mgr):
    plan = _plan(mgr)
    parent = mgr.create_task(CreateTaskInput(title="P", plan_id=plan.id))
    mgr.create_task(CreateTaskInput(title="C1", plan_id=plan.id, parent_task_id=parent.id))
    mgr.create_task(CreateTaskInput(title="C2", plan_id=plan.id, parent_task_id=parent.id))
    view = mgr.plan_view(plan.id)
    assert view["stats"]["total"] == 3
    root = next(t for t in view["tasks"] if t["id"] == parent.id)
    assert len(root["children"]) == 2


def test_add_dependency_applies_block(mgr):
    plan = _plan(mgr)
    a = mgr.create_task(CreateTaskInput(title="A", plan_id=plan.id))
    b = mgr.create_task(CreateTaskInput(title="B", plan_id=plan.id))
    assert mgr.get_task(b.id).status == TaskStatus.TODO
    mgr.add_dependency(b.id, a.id, kind=DependencyKind.BLOCKS)
    assert mgr.get_task(b.id).status == TaskStatus.BLOCKED
    mgr.remove_dependency(b.id, a.id)
    assert mgr.get_task(b.id).status == TaskStatus.TODO

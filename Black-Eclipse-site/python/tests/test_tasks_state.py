"""Unit tests for the task and plan state machines (closed transition tables)."""

from __future__ import annotations

import pytest

from harness.tasks.model import PlanStatus, TaskStatus
from harness.tasks.state import (
    InvalidPlanTransition,
    InvalidTaskTransition,
    TaskOperation,
    can_transition_plan,
    can_transition_task,
    is_task_terminal,
    require_plan_transition,
    require_task_transition,
)


@pytest.mark.parametrize(
    "current,target",
    [
        (TaskStatus.TODO, TaskStatus.IN_PROGRESS),
        (TaskStatus.TODO, TaskStatus.BLOCKED),
        (TaskStatus.TODO, TaskStatus.WAITING),
        (TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED),
        (TaskStatus.IN_PROGRESS, TaskStatus.FAILED),
        (TaskStatus.BLOCKED, TaskStatus.TODO),
        (TaskStatus.WAITING, TaskStatus.IN_PROGRESS),
    ],
)
def test_ordinary_transitions_are_legal(current, target):
    assert can_transition_task(current, target)
    require_task_transition(current, target)  # does not raise


@pytest.mark.parametrize(
    "current,target",
    [
        (TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS),   # terminal by default
        (TaskStatus.FAILED, TaskStatus.IN_PROGRESS),
        (TaskStatus.CANCELLED, TaskStatus.TODO),
        (TaskStatus.TODO, TaskStatus.COMPLETED),          # must pass through running
    ],
)
def test_ordinary_transitions_reject_terminal_edges(current, target):
    assert not can_transition_task(current, target)
    with pytest.raises(InvalidTaskTransition):
        require_task_transition(current, target)


def test_retry_operation_crosses_a_closed_boundary():
    # FAILED -> IN_PROGRESS is only legal as the explicit `retry` operation.
    assert not can_transition_task(TaskStatus.FAILED, TaskStatus.IN_PROGRESS)
    assert can_transition_task(
        TaskStatus.FAILED, TaskStatus.IN_PROGRESS, operation=TaskOperation.RETRY.value
    )
    # ...but retry does NOT let you skip back from COMPLETED.
    assert not can_transition_task(
        TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS, operation=TaskOperation.RETRY.value
    )


def test_reopen_operation_allows_a_terminal_task_to_restart():
    assert can_transition_task(
        TaskStatus.COMPLETED, TaskStatus.TODO, operation=TaskOperation.REOPEN.value
    )
    assert can_transition_task(
        TaskStatus.CANCELLED, TaskStatus.TODO, operation=TaskOperation.REOPEN.value
    )


def test_recover_operation_is_only_running_to_todo():
    assert can_transition_task(
        TaskStatus.IN_PROGRESS, TaskStatus.TODO, operation=TaskOperation.RECOVER.value
    )
    assert not can_transition_task(
        TaskStatus.WAITING, TaskStatus.TODO, operation=TaskOperation.RECOVER.value
    )


def test_terminal_detection():
    assert is_task_terminal(TaskStatus.COMPLETED)
    assert is_task_terminal(TaskStatus.FAILED)
    assert is_task_terminal(TaskStatus.CANCELLED)
    assert not is_task_terminal(TaskStatus.IN_PROGRESS)
    assert not is_task_terminal(TaskStatus.TODO)


def test_plan_transitions():
    assert can_transition_plan(PlanStatus.PLANNING, PlanStatus.READY)
    assert can_transition_plan(PlanStatus.READY, PlanStatus.RUNNING)
    assert can_transition_plan(PlanStatus.RUNNING, PlanStatus.COMPLETED)
    assert not can_transition_plan(PlanStatus.COMPLETED, PlanStatus.RUNNING)
    with pytest.raises(InvalidPlanTransition):
        require_plan_transition(PlanStatus.COMPLETED, PlanStatus.RUNNING)
    # reopen crosses the boundary explicitly.
    assert can_transition_plan(
        PlanStatus.COMPLETED, PlanStatus.READY, operation=TaskOperation.REOPEN.value
    )

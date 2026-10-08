"""The task and plan state machines — one central, closed transition table.

No module mutates a task's status directly. `TaskManager` is the only writer, and
it asks this module whether a transition is legal first. A terminal state has no
ordinary outgoing edge, so `COMPLETED -> IN_PROGRESS` is rejected unless an
explicit, named OPERATION (`retry` / `reopen` / `recover`) is invoked — and even
then only the exact edges listed here are allowed.

Keeping the table closed (no wildcards) is what makes "the agent said done" a
statement about a task, not a mutation of one.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Optional

from .model import PlanStatus, TaskStatus


class TaskOperation(str, Enum):
    """An explicit, auditable way to cross an otherwise-closed boundary."""

    RETRY = "retry"
    REOPEN = "reopen"
    RECOVER = "recover"


# The complete ordinary transition table. Every legal edge is written out.
_TASK_TRANSITIONS: dict[TaskStatus, FrozenSet[TaskStatus]] = {
    # TODO -> FAILED is legal: a task whose input is invalid, whose required
    # resource is unavailable, or whose dependencies failed may be failed before
    # it ever starts (a task is not required to run first to fail).
    TaskStatus.TODO: frozenset(
        {
            TaskStatus.IN_PROGRESS,
            TaskStatus.BLOCKED,
            TaskStatus.WAITING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.IN_PROGRESS: frozenset(
        {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.WAITING,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.BLOCKED: frozenset(
        {
            TaskStatus.TODO,
            TaskStatus.IN_PROGRESS,
            TaskStatus.WAITING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.WAITING: frozenset(
        {
            TaskStatus.TODO,
            TaskStatus.IN_PROGRESS,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }
    ),
    # Terminal states have no ordinary outgoing edges.
    TaskStatus.FAILED: frozenset(),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

# Explicit operations and the ONLY (from, to) edges they may cross.
_TASK_OPERATIONS: dict[str, FrozenSet[tuple[TaskStatus, TaskStatus]]] = {
    TaskOperation.RETRY.value: frozenset(
        {
            (TaskStatus.FAILED, TaskStatus.TODO),
            (TaskStatus.FAILED, TaskStatus.IN_PROGRESS),
            (TaskStatus.BLOCKED, TaskStatus.TODO),
            (TaskStatus.BLOCKED, TaskStatus.IN_PROGRESS),
            (TaskStatus.WAITING, TaskStatus.TODO),
            (TaskStatus.IN_PROGRESS, TaskStatus.TODO),
        }
    ),
    TaskOperation.RECOVER.value: frozenset(
        {(TaskStatus.IN_PROGRESS, TaskStatus.TODO)}
    ),
    TaskOperation.REOPEN.value: frozenset(
        {
            (TaskStatus.COMPLETED, TaskStatus.TODO),
            (TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS),
            (TaskStatus.CANCELLED, TaskStatus.TODO),
            (TaskStatus.CANCELLED, TaskStatus.IN_PROGRESS),
            (TaskStatus.FAILED, TaskStatus.TODO),
            (TaskStatus.FAILED, TaskStatus.IN_PROGRESS),
        }
    ),
}


_PLAN_TRANSITIONS: dict[PlanStatus, FrozenSet[PlanStatus]] = {
    PlanStatus.PLANNING: frozenset(
        {PlanStatus.READY, PlanStatus.CANCELLED, PlanStatus.FAILED}
    ),
    PlanStatus.READY: frozenset(
        {PlanStatus.RUNNING, PlanStatus.CANCELLED, PlanStatus.FAILED, PlanStatus.COMPLETED}
    ),
    PlanStatus.RUNNING: frozenset(
        {
            PlanStatus.COMPLETED,
            PlanStatus.FAILED,
            PlanStatus.BLOCKED,
            PlanStatus.CANCELLED,
        }
    ),
    PlanStatus.BLOCKED: frozenset(
        {PlanStatus.RUNNING, PlanStatus.FAILED, PlanStatus.CANCELLED}
    ),
    PlanStatus.COMPLETED: frozenset(),
    PlanStatus.FAILED: frozenset(),
    PlanStatus.CANCELLED: frozenset(),
}

_PLAN_OPERATIONS: dict[str, FrozenSet[tuple[PlanStatus, PlanStatus]]] = {
    TaskOperation.RETRY.value: frozenset(
        {
            (PlanStatus.FAILED, PlanStatus.READY),
            (PlanStatus.BLOCKED, PlanStatus.READY),
        }
    ),
    TaskOperation.REOPEN.value: frozenset(
        {
            (PlanStatus.COMPLETED, PlanStatus.READY),
            (PlanStatus.CANCELLED, PlanStatus.READY),
            (PlanStatus.FAILED, PlanStatus.READY),
        }
    ),
}


class InvalidTaskTransition(RuntimeError):
    """Raised when a caller attempts an illegal task transition."""

    def __init__(
        self, current: TaskStatus, target: TaskStatus, operation: Optional[str] = None
    ) -> None:
        suffix = f" (operation {operation!r})" if operation else ""
        super().__init__(f"invalid task transition {current.value} -> {target.value}{suffix}")
        self.current = current
        self.target = target
        self.operation = operation


class InvalidPlanTransition(RuntimeError):
    """Raised when a caller attempts an illegal plan transition."""

    def __init__(
        self, current: PlanStatus, target: PlanStatus, operation: Optional[str] = None
    ) -> None:
        suffix = f" (operation {operation!r})" if operation else ""
        super().__init__(f"invalid plan transition {current.value} -> {target.value}{suffix}")
        self.current = current
        self.target = target
        self.operation = operation


def is_task_terminal(status: TaskStatus) -> bool:
    return status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)


def can_transition_task(
    current: TaskStatus, target: TaskStatus, *, operation: Optional[str] = None
) -> bool:
    """Whether `current -> target` is legal (optionally via a named operation)."""
    if operation is not None:
        return (current, target) in _TASK_OPERATIONS.get(operation, frozenset())
    return target in _TASK_TRANSITIONS.get(current, frozenset())


def require_task_transition(
    current: TaskStatus, target: TaskStatus, *, operation: Optional[str] = None
) -> None:
    if not can_transition_task(current, target, operation=operation):
        raise InvalidTaskTransition(current, target, operation)


def can_transition_plan(
    current: PlanStatus, target: PlanStatus, *, operation: Optional[str] = None
) -> bool:
    if operation is not None:
        return (current, target) in _PLAN_OPERATIONS.get(operation, frozenset())
    return target in _PLAN_TRANSITIONS.get(current, frozenset())


def require_plan_transition(
    current: PlanStatus, target: PlanStatus, *, operation: Optional[str] = None
) -> None:
    if not can_transition_plan(current, target, operation=operation):
        raise InvalidPlanTransition(current, target, operation)


__all__ = [
    "InvalidPlanTransition",
    "InvalidTaskTransition",
    "TaskOperation",
    "can_transition_plan",
    "can_transition_task",
    "is_task_terminal",
    "require_plan_transition",
    "require_task_transition",
]

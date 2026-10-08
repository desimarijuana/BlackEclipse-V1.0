"""The strict state machine for task and execution status.

No module in the orchestration layer invents a status string. Every node and
every execution moves through `TaskStatus` / `ExecutionStatus` values, and every
transition is checked against a closed table. A terminal state has no outgoing
edges, so a completed node can never be silently reopened.

The two state machines share the same shape but are kept separate because their
legal transitions differ (a task may be RETRIED back to PENDING; an execution may
not move backwards out of a terminal state).
"""

from __future__ import annotations

from typing import FrozenSet

from .models import (
    TERMINAL_EXECUTION_STATES,
    TERMINAL_TASK_STATES,
    ExecutionStatus,
    TaskStatus,
)

_P = TaskStatus.PENDING
_R = TaskStatus.READY
_N = TaskStatus.RUNNING
_C = TaskStatus.COMPLETED
_F = TaskStatus.FAILED
_X = TaskStatus.CANCELLED
_B = TaskStatus.BLOCKED
_S = TaskStatus.SKIPPED
_T = TaskStatus.TIMED_OUT
_W = TaskStatus.PAUSED

# Every legal task edge, written out. No wildcard. A terminal state maps to the
# empty set.
_TASK_TRANSITIONS: dict[TaskStatus, FrozenSet[TaskStatus]] = {
    _P: frozenset({_R, _X, _B, _S, _W}),
    _R: frozenset({_N, _X, _B, _S, _W}),
    _N: frozenset({_C, _F, _X, _T, _W}),
    _W: frozenset({_R, _N, _X}),  # resumed, or cancelled while paused
    **{state: frozenset() for state in TERMINAL_TASK_STATES},
}
# The RETRY edge. A failed, timed-out, skipped or blocked node may be re-driven by
# the engine's explicit retry path (`retry_node`, the RETRY_FAILED failure policy,
# or crash recovery). It is the ONLY outgoing edge from an otherwise terminal
# state, and it always lands on PENDING so the node re-enters the normal rules.
_TASK_TRANSITIONS[TaskStatus.FAILED] = frozenset({_P})
_TASK_TRANSITIONS[TaskStatus.TIMED_OUT] = frozenset({_P})
_TASK_TRANSITIONS[TaskStatus.SKIPPED] = frozenset({_P})
_TASK_TRANSITIONS[TaskStatus.BLOCKED] = frozenset({_P})

_EP = ExecutionStatus.PENDING
_ER = ExecutionStatus.READY
_EN = ExecutionStatus.RUNNING
_EW = ExecutionStatus.PAUSED

_EXEC_TRANSITIONS: dict[ExecutionStatus, FrozenSet[ExecutionStatus]] = {
    _EP: frozenset({_ER, _EN, ExecutionStatus.CANCELLED}),
    _ER: frozenset({_EN, ExecutionStatus.CANCELLED}),
    _EN: frozenset({
        ExecutionStatus.COMPLETED,
        ExecutionStatus.PARTIAL_SUCCESS,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
        _EW,
    }),
    _EW: frozenset({_EN, ExecutionStatus.CANCELLED}),
    **{state: frozenset() for state in TERMINAL_EXECUTION_STATES},
}


def is_task_terminal(state: TaskStatus) -> bool:
    return state in TERMINAL_TASK_STATES


def is_execution_terminal(state: ExecutionStatus) -> bool:
    return state in TERMINAL_EXECUTION_STATES


def can_transition_task(current: TaskStatus, target: TaskStatus) -> bool:
    return target in _TASK_TRANSITIONS.get(current, frozenset())


def can_transition_execution(current: ExecutionStatus, target: ExecutionStatus) -> bool:
    return target in _EXEC_TRANSITIONS.get(current, frozenset())


class InvalidTransition(RuntimeError):
    """Raised when a caller attempts an illegal state transition."""

    def __init__(self, current: object, target: object, *, kind: str = "task") -> None:
        super().__init__(f"invalid {kind} transition {current} -> {target}")
        self.current = current
        self.target = target
        self.kind = kind


def require_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    if not can_transition_task(current, target):
        raise InvalidTransition(current, target, kind="task")


def require_execution_transition(current: ExecutionStatus, target: ExecutionStatus) -> None:
    if not can_transition_execution(current, target):
        raise InvalidTransition(current, target, kind="execution")


class TaskStateMachine:
    """A tiny holder of one node's status with validated transitions.

    Not thread-safe by design: one node is driven by one scheduler coroutine. The
    scheduler serializes access through its per-execution lock.
    """

    def __init__(self, initial: TaskStatus = TaskStatus.PENDING) -> None:
        self._state = initial
        self.history: list[TaskStatus] = [initial]

    @property
    def state(self) -> TaskStatus:
        return self._state

    @property
    def terminal(self) -> bool:
        return is_task_terminal(self._state)

    def to(self, target: TaskStatus) -> TaskStatus:
        require_task_transition(self._state, target)
        self._state = target
        self.history.append(target)
        return self._state

    def force_terminal(self, target: TaskStatus) -> TaskStatus:
        """Move to a terminal state from anywhere (cleanup safety valve)."""
        if not is_task_terminal(target):
            raise InvalidTransition(self._state, target, kind="task")
        if not is_task_terminal(self._state):
            self._state = target
            self.history.append(target)
        return self._state


__all__ = [
    "InvalidTransition",
    "TaskStateMachine",
    "can_transition_execution",
    "can_transition_task",
    "is_execution_terminal",
    "is_task_terminal",
    "require_execution_transition",
    "require_task_transition",
]

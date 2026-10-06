"""The execution state machine — one central enum, validated transitions.

No module in the execution layer invents a state string. Every execution moves
through `ExecutionState` values and every transition is checked by
`can_transition` / `require_transition`. A terminal state has no outgoing edges,
so a completed execution can never be silently reopened.

The states are grouped exactly as the capability contract describes:

  * initial / active — a run in progress;
  * terminal        — a run that will never change state again. The terminal
                      grouping also distinguishes WHY it stopped (a timeout, a
                      resource limit, a security block, a user-code error, a
                      build error, a test error) so an agent can reason about the
                      failure without parsing free text.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet


class ExecutionState(str, Enum):
    """The lifecycle state of one execution. A `str` enum for easy serialization."""

    # ── initial / active ───────────────────────────────────────────────────────
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    PREPARING = "PREPARING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"

    # ── terminal ────────────────────────────────────────────────────────────────
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    SECURITY_BLOCKED = "SECURITY_BLOCKED"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    BUILD_ERROR = "BUILD_ERROR"
    TEST_ERROR = "TEST_ERROR"


INITIAL_STATES: FrozenSet[ExecutionState] = frozenset(
    {
        ExecutionState.QUEUED,
        ExecutionState.VALIDATING,
        ExecutionState.PREPARING,
        ExecutionState.STARTING,
        ExecutionState.RUNNING,
    }
)

TERMINAL_STATES: FrozenSet[ExecutionState] = frozenset(
    {
        ExecutionState.COMPLETED,
        ExecutionState.FAILED,
        ExecutionState.TIMED_OUT,
        ExecutionState.CANCELLED,
        ExecutionState.RESOURCE_LIMIT,
        ExecutionState.SECURITY_BLOCKED,
        ExecutionState.RUNTIME_ERROR,
        ExecutionState.BUILD_ERROR,
        ExecutionState.TEST_ERROR,
    }
)

# The complete, closed transition table. Every legal edge is written out; there is
# no wildcard. A terminal state maps to the empty set.
_TRANSITIONS: dict[ExecutionState, FrozenSet[ExecutionState]] = {
    ExecutionState.QUEUED: frozenset({ExecutionState.VALIDATING, ExecutionState.CANCELLED, ExecutionState.SECURITY_BLOCKED}),
    ExecutionState.VALIDATING: frozenset({ExecutionState.PREPARING, ExecutionState.SECURITY_BLOCKED, ExecutionState.CANCELLED, ExecutionState.FAILED}),
    ExecutionState.PREPARING: frozenset({ExecutionState.STARTING, ExecutionState.SECURITY_BLOCKED, ExecutionState.CANCELLED, ExecutionState.FAILED, ExecutionState.RUNTIME_ERROR}),
    ExecutionState.STARTING: frozenset({ExecutionState.RUNNING, ExecutionState.CANCELLED, ExecutionState.RUNTIME_ERROR, ExecutionState.FAILED, ExecutionState.SECURITY_BLOCKED}),
    ExecutionState.RUNNING: frozenset(
        {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.TIMED_OUT,
            ExecutionState.CANCELLED,
            ExecutionState.RESOURCE_LIMIT,
            ExecutionState.SECURITY_BLOCKED,
            ExecutionState.RUNTIME_ERROR,
            ExecutionState.BUILD_ERROR,
            ExecutionState.TEST_ERROR,
        }
    ),
    **{state: frozenset() for state in TERMINAL_STATES},
}


def is_terminal(state: ExecutionState) -> bool:
    """Whether `state` is a terminal state."""
    return state in TERMINAL_STATES


def can_transition(current: ExecutionState, target: ExecutionState) -> bool:
    """Whether `current -> target` is a legal edge."""
    return target in _TRANSITIONS.get(current, frozenset())


class InvalidTransition(RuntimeError):
    """Raised when a caller attempts an illegal state transition."""

    def __init__(self, current: ExecutionState, target: ExecutionState) -> None:
        super().__init__(f"invalid execution transition {current.value} -> {target.value}")
        self.current = current
        self.target = target


def require_transition(current: ExecutionState, target: ExecutionState) -> None:
    """Raise `InvalidTransition` unless `current -> target` is legal."""
    if not can_transition(current, target):
        raise InvalidTransition(current, target)


class StateMachine:
    """A tiny, auditable holder of the current state with validated transitions.

    It is intentionally NOT thread-safe: an execution owns one machine, driven by
    one orchestrator thread. The store records the state changes; this object is
    the in-process source of truth.
    """

    def __init__(self, initial: ExecutionState = ExecutionState.QUEUED) -> None:
        self._state = initial
        self.history: list[ExecutionState] = [initial]

    @property
    def state(self) -> ExecutionState:
        return self._state

    @property
    def terminal(self) -> bool:
        return is_terminal(self._state)

    def to(self, target: ExecutionState) -> ExecutionState:
        """Transition to `target`, or raise `InvalidTransition`."""
        require_transition(self._state, target)
        self._state = target
        self.history.append(target)
        return self._state

    def force_terminal(self, target: ExecutionState) -> ExecutionState:
        """Move to a terminal state from anywhere (cleanup / cancel safety valve).

        Only ever moves INTO a terminal state; used by the orchestrator's `finally`
        path so a crash or cancellation always lands on a terminal state even when
        the normal edge was skipped. It refuses a non-terminal target.
        """
        if not is_terminal(target):
            raise InvalidTransition(self._state, target)
        if not is_terminal(self._state):
            self._state = target
            self.history.append(target)
        return self._state


__all__ = [
    "ExecutionState",
    "INITIAL_STATES",
    "InvalidTransition",
    "StateMachine",
    "TERMINAL_STATES",
    "can_transition",
    "is_terminal",
    "require_transition",
]

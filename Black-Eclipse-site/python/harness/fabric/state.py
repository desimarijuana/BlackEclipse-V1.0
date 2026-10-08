"""The strict state machine for a Fabric job.

No module invents a status string. Every job moves through `JobState` values and
every transition is checked against a closed table. A terminal state has no
outgoing edges except the ONE explicit retry/replay edge, so a finished job can
never be silently reopened by an ordinary write.

    CREATED -> QUEUED -> RUNNING -> SUCCEEDED
                                  -> FAILED  -> RETRYING -> QUEUED
                                             -> DEAD_LETTER
                                  -> TIMED_OUT -> RETRYING | DEAD_LETTER
                                  -> CANCEL_REQUESTED -> CANCELLED
    QUEUED  -> PAUSED -> QUEUED
"""

from __future__ import annotations

from typing import FrozenSet

from .models import REPLAYABLE_JOB_STATES, TERMINAL_JOB_STATES, JobState

_C = JobState.CREATED
_Q = JobState.QUEUED
_R = JobState.RUNNING
_P = JobState.PAUSED
_S = JobState.SUCCEEDED
_F = JobState.FAILED
_T = JobState.RETRYING
_X = JobState.CANCEL_REQUESTED
_D = JobState.CANCELLED
_O = JobState.TIMED_OUT
_L = JobState.DEAD_LETTER

# Every legal edge, written out. No wildcard.
_JOB_TRANSITIONS: dict[JobState, FrozenSet[JobState]] = {
    _C: frozenset({_Q, _X, _D, _L}),
    _Q: frozenset({_R, _P, _X, _D, _T, _L}),
    _R: frozenset({_S, _F, _O, _T, _X, _P, _D, _L}),
    _P: frozenset({_Q, _X, _D}),
    # A retrying job is re-queued once its backoff elapses (or cancelled/replayed).
    _T: frozenset({_Q, _X, _D, _L}),
    # A cancel request races completion: the job may still finish or fail before
    # the worker observes the cancellation.
    _X: frozenset({_D, _S, _F, _O, _L}),
    # Terminal states. Reached only deliberately.
    _S: frozenset(),
    _D: frozenset(),
    _L: frozenset({_Q}),  # replay
}
# Retry / replay edges from an otherwise-terminal failure.
for _failed in (_F, _O):
    _JOB_TRANSITIONS[_failed] = frozenset({_T, _L, _Q})


class InvalidJobTransition(RuntimeError):
    """Raised when a caller attempts an illegal job state transition."""

    def __init__(self, current: object, target: object) -> None:
        super().__init__(f"invalid job transition {current} -> {target}")
        self.current = current
        self.target = target


def is_job_terminal(state: JobState) -> bool:
    return state in TERMINAL_JOB_STATES


def is_replayable(state: JobState) -> bool:
    return state in REPLAYABLE_JOB_STATES


def can_transition(current: JobState, target: JobState) -> bool:
    if current == target:
        return True
    return target in _JOB_TRANSITIONS.get(current, frozenset())


def require_transition(current: JobState, target: JobState) -> None:
    if not can_transition(current, target):
        raise InvalidJobTransition(current, target)


class JobStateMachine:
    """A tiny holder of one job's state with validated transitions."""

    def __init__(self, initial: JobState = JobState.CREATED) -> None:
        self._state = initial
        self.history: list[JobState] = [initial]

    @property
    def state(self) -> JobState:
        return self._state

    @property
    def terminal(self) -> bool:
        return is_job_terminal(self._state)

    def to(self, target: JobState) -> JobState:
        require_transition(self._state, target)
        self._state = target
        self.history.append(target)
        return self._state


__all__ = [
    "InvalidJobTransition",
    "JobStateMachine",
    "can_transition",
    "is_job_terminal",
    "is_replayable",
    "require_transition",
]

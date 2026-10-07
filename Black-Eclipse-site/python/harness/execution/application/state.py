"""The application runtime state machine — explicit, validated, never a boolean.

The lifecycle is the spec's sequence:

    DISCOVERING → DISCOVERED → VALIDATING → PREPARING → INSTALLING → BUILDING
      → STARTING → RUNNING → (OBSERVING) → DEGRADED → STOPPING → STOPPED
      → FAILED

A terminal state (`STOPPED`, `FAILED`) has no outgoing edges. Transitions are
validated; an unexpected failure can `force_terminal` from anywhere (cleanup
safety valve). `RUNNING` is not `HEALTHY`: health is a separate report, so the
machine never equates "the process exists" with "the application works".
"""

from __future__ import annotations

from typing import FrozenSet

from .models import ApplicationState, ACTIVE_STATES, TERMINAL_STATES

_TRANSITIONS: dict[ApplicationState, FrozenSet[ApplicationState]] = {
    ApplicationState.DISCOVERING: frozenset({ApplicationState.DISCOVERED, ApplicationState.FAILED}),
    ApplicationState.DISCOVERED: frozenset({ApplicationState.VALIDATING, ApplicationState.FAILED}),
    ApplicationState.VALIDATING: frozenset({ApplicationState.PREPARING, ApplicationState.FAILED}),
    ApplicationState.PREPARING: frozenset({ApplicationState.INSTALLING, ApplicationState.BUILDING, ApplicationState.STARTING, ApplicationState.FAILED}),
    ApplicationState.INSTALLING: frozenset({ApplicationState.BUILDING, ApplicationState.STARTING, ApplicationState.FAILED}),
    ApplicationState.BUILDING: frozenset({ApplicationState.STARTING, ApplicationState.FAILED}),
    ApplicationState.STARTING: frozenset({ApplicationState.RUNNING, ApplicationState.DEGRADED, ApplicationState.FAILED}),
    ApplicationState.RUNNING: frozenset({ApplicationState.OBSERVING, ApplicationState.DEGRADED, ApplicationState.STOPPING, ApplicationState.FAILED}),
    ApplicationState.OBSERVING: frozenset({ApplicationState.RUNNING, ApplicationState.DEGRADED, ApplicationState.STOPPING, ApplicationState.FAILED}),
    ApplicationState.DEGRADED: frozenset({ApplicationState.RUNNING, ApplicationState.OBSERVING, ApplicationState.STOPPING, ApplicationState.FAILED}),
    ApplicationState.STOPPING: frozenset({ApplicationState.STOPPED, ApplicationState.FAILED}),
    ApplicationState.UNKNOWN: frozenset({ApplicationState.DISCOVERING, ApplicationState.DISCOVERED, ApplicationState.VALIDATING, ApplicationState.FAILED, ApplicationState.STOPPED}),
    **{state: frozenset() for state in TERMINAL_STATES},
}


class InvalidTransition(RuntimeError):
    def __init__(self, current: ApplicationState, target: ApplicationState) -> None:
        super().__init__(f"invalid application transition {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: ApplicationState, target: ApplicationState) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def require_transition(current: ApplicationState, target: ApplicationState) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(current, target)


class ApplicationStateMachine:
    """A small, auditable holder of the current application state."""

    def __init__(self, initial: ApplicationState = ApplicationState.UNKNOWN) -> None:
        self._state = initial
        self.history: list[ApplicationState] = [initial]

    @property
    def state(self) -> ApplicationState:
        return self._state

    @property
    def terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    def to(self, target: ApplicationState) -> ApplicationState:
        require_transition(self._state, target)
        self._state = target
        self.history.append(target)
        return self._state

    def force_terminal(self, target: ApplicationState) -> ApplicationState:
        if target not in TERMINAL_STATES:
            raise InvalidTransition(self._state, target)
        if self._state not in TERMINAL_STATES:
            self._state = target
            self.history.append(target)
        return self._state


__all__ = [
    "ACTIVE_STATES",
    "ApplicationStateMachine",
    "InvalidTransition",
    "TERMINAL_STATES",
    "can_transition",
    "require_transition",
]

"""The Computer Use action state machine.

A small, validated state machine mirroring `execution/state.py`. Every important
action progresses UNKNOWN → OBSERVED → TARGET_IDENTIFIED → AUTHORIZED →
ACTION_READY → ACTION_EXECUTED → VERIFYING → CONFIRMED, or terminates in one of
the failure states. An invalid transition is refused, never silently applied —
which is what makes the loop observable and replayable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .errors import ACTION_FAILURE_STATES


class ActionState(str, Enum):
    UNKNOWN = "UNKNOWN"
    OBSERVED = "OBSERVED"
    TARGET_IDENTIFIED = "TARGET_IDENTIFIED"
    AUTHORIZED = "AUTHORIZED"
    ACTION_READY = "ACTION_READY"
    ACTION_EXECUTED = "ACTION_EXECUTED"
    VERIFYING = "VERIFYING"
    CONFIRMED = "CONFIRMED"

    # Failure / terminal states.
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    STALE_ELEMENT = "STALE_ELEMENT"
    ACTION_FAILED = "ACTION_FAILED"
    STATE_CHANGED = "STATE_CHANGED"
    APP_UNRESPONSIVE = "APP_UNRESPONSIVE"
    PERMISSION_REQUIRED = "PERMISSION_REQUIRED"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    UNEXPECTED_DIALOG = "UNEXPECTED_DIALOG"
    TIMEOUT = "TIMEOUT"

    @property
    def terminal(self) -> bool:
        return self is ActionState.CONFIRMED or self.value in ACTION_FAILURE_STATES


_TRANSITIONS: dict[ActionState, set[ActionState]] = {
    ActionState.UNKNOWN: {ActionState.OBSERVED, ActionState.TARGET_NOT_FOUND, ActionState.TIMEOUT, ActionState.APP_UNRESPONSIVE},
    ActionState.OBSERVED: {
        ActionState.TARGET_IDENTIFIED, ActionState.TARGET_NOT_FOUND, ActionState.STALE_ELEMENT,
        ActionState.AMBIGUOUS_TARGET, ActionState.TIMEOUT,
    },
    ActionState.TARGET_IDENTIFIED: {
        ActionState.AUTHORIZED, ActionState.PERMISSION_REQUIRED, ActionState.STALE_ELEMENT,
        ActionState.AMBIGUOUS_TARGET,
    },
    ActionState.AUTHORIZED: {ActionState.ACTION_READY, ActionState.PERMISSION_REQUIRED, ActionState.STALE_ELEMENT},
    ActionState.ACTION_READY: {
        ActionState.ACTION_EXECUTED, ActionState.ACTION_FAILED, ActionState.STALE_ELEMENT,
        ActionState.UNEXPECTED_DIALOG, ActionState.TIMEOUT, ActionState.APP_UNRESPONSIVE,
    },
    ActionState.ACTION_EXECUTED: {ActionState.VERIFYING, ActionState.STATE_CHANGED, ActionState.UNEXPECTED_DIALOG},
    ActionState.VERIFYING: {
        ActionState.CONFIRMED, ActionState.STATE_CHANGED, ActionState.ACTION_FAILED,
        ActionState.UNEXPECTED_DIALOG, ActionState.TIMEOUT,
    },
    ActionState.CONFIRMED: set(),
}
for _failure in ACTION_FAILURE_STATES:
    _TRANSITIONS[ActionState(_failure)] = set()


class InvalidTransition(RuntimeError):
    """An action was asked to move to a state its current state forbids."""


@dataclass
class ActionStateMachine:
    """Tracks one action's state and its (bounded) transition log."""

    state: ActionState = ActionState.UNKNOWN
    log: list[dict[str, Any]] = field(default_factory=list)
    _max_log: int = 64

    def can(self, target: ActionState) -> bool:
        return target in _TRANSITIONS.get(self.state, set())

    def transition(self, target: ActionState, *, note: str = "") -> ActionState:
        """Move to ``target`` or raise if the transition is not allowed."""
        if target == self.state:
            return self.state
        allowed = _TRANSITIONS.get(self.state, set())
        if target not in allowed:
            raise InvalidTransition(f"cannot move from {self.state.value} to {target.value}")
        self.log.append({"from": self.state.value, "to": target.value, "note": note})
        if len(self.log) > self._max_log:
            del self.log[0]
        self.state = target
        return self.state

    def fail(self, target: ActionState, *, note: str = "") -> ActionState:
        """Move to a failure state; an already-failed machine is a no-op."""
        if self.state.terminal:
            return self.state
        if target not in _TRANSITIONS.get(self.state, set()):
            # Record the failure best-effort even if the exact edge is missing, so
            # the loop never loses a failure signal to a strict graph.
            self.log.append({"from": self.state.value, "to": target.value, "note": note, "relaxed": True})
            self.state = target
            return self.state
        return self.transition(target, note=note)

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state.value, "terminal": self.state.terminal, "log": list(self.log)}


__all__ = ["ActionState", "ActionStateMachine", "InvalidTransition"]

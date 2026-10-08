"""Lifecycle + execution state machines (§6).

Two SEPARATE state machines. An automation's lifecycle state (draft → active →
paused → …) is not its execution state (triggered → running → completed → …).
Invalid transitions are REJECTED with a specific error — never silently accepted.

Pure functions, so tests assert exact transitions without a database or clock.
"""

from __future__ import annotations

from .model import ExecutionState, LifecycleState

# ── Lifecycle transitions ────────────────────────────────────────────────────
_LIFECYCLE: dict[str, frozenset[str]] = {
    "draft": frozenset({"validating", "active", "archived"}),
    "validating": frozenset({"draft", "active", "disabled", "archived"}),
    "active": frozenset({"paused", "disabled", "draft", "archived"}),
    "paused": frozenset({"active", "disabled", "archived"}),
    "disabled": frozenset({"active", "draft", "archived"}),
    "archived": frozenset({"draft"}),
}

# ── Execution transitions ────────────────────────────────────────────────────
_EXECUTION: dict[str, frozenset[str]] = {
    "triggered": frozenset({"queued", "blocked", "skipped", "cancelled"}),
    "queued": frozenset({"running", "skipped", "cancelled", "blocked"}),
    "running": frozenset({"waiting", "retrying", "completed", "failed", "cancelled", "timed_out"}),
    "waiting": frozenset({"running", "completed", "failed", "cancelled", "timed_out", "blocked"}),
    "retrying": frozenset({"running", "failed", "cancelled", "timed_out"}),
    "blocked": frozenset({"queued", "running", "cancelled", "skipped"}),
    # Terminal — no outgoing transitions.
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "timed_out": frozenset(),
    "skipped": frozenset(),
}


class TransitionError(ValueError):
    """An invalid lifecycle or execution transition, with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def can_transition_lifecycle(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in _LIFECYCLE.get(current, frozenset())


def assert_lifecycle_transition(current: str, target: str) -> None:
    if not can_transition_lifecycle(current, target):
        raise TransitionError(
            "INVALID_LIFECYCLE_TRANSITION",
            f"an automation cannot go from {current} to {target}",
        )


def can_transition_execution(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in _EXECUTION.get(current, frozenset())


def assert_execution_transition(current: str, target: str) -> None:
    if not can_transition_execution(current, target):
        raise TransitionError(
            "INVALID_EXECUTION_TRANSITION",
            f"an execution cannot go from {current} to {target}",
        )


def lifecycle_actions(state: str) -> list[str]:
    """The lifecycle verbs valid from `state` (drives the UI affordances)."""
    return sorted(_LIFECYCLE.get(state, frozenset()) - {state})


__all__ = [
    "TransitionError",
    "assert_execution_transition",
    "assert_lifecycle_transition",
    "can_transition_execution",
    "can_transition_lifecycle",
    "lifecycle_actions",
]

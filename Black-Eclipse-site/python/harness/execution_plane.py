"""One execution vocabulary for every plane (Round 5 / C2).

Eclipse currently names the same lifecycle in four places:

  * `RunStatus`        -> created | running | completed | failed | cancelled
  * `JobState`         -> CREATED | QUEUED | RUNNING | ... | DEAD_LETTER
  * `TaskStatus`       -> TODO | IN_PROGRESS | VERIFYING | ... | CANCELLED
  * `graph_runtime.RunStatus` -> pending | queued | running | succeeded | ...

That is why a caller cannot ask one question ("is this work still live?") of any
plane. This module is the ONE vocabulary: a transport/UI-facing `ExecutionPhase`
plus pure adapters, and `JobKind` for the unit of work. It changes no existing
enum and owns no scheduler; it is the shared language the planes converge on.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class ExecutionPhase(str, Enum):
    """The canonical lifecycle of any unit of work, whatever plane runs it."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"  # approval, user input, dependency, pause
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


TERMINAL_PHASES: frozenset[ExecutionPhase] = frozenset({
    ExecutionPhase.SUCCEEDED,
    ExecutionPhase.FAILED,
    ExecutionPhase.CANCELLED,
    ExecutionPhase.TIMED_OUT,
})


class JobKind(str, Enum):
    """The unit of work the Execution Fabric owns."""

    AGENT_RUN = "agent_run"
    GRAPH_RUN = "graph_run"
    TASK_RUN = "task_run"
    DELEGATE = "delegate"
    TOOL = "tool"
    RESEARCH = "research"
    AUTOMATION = "automation"


# Every mapping below is total: an unknown value is `None`, never an invented
# phase. Callers must handle `None` (a stale or foreign row), not guess.

_RUN_STATUS = {
    "created": ExecutionPhase.PENDING,
    "running": ExecutionPhase.RUNNING,
    "completed": ExecutionPhase.SUCCEEDED,
    "failed": ExecutionPhase.FAILED,
    "cancelled": ExecutionPhase.CANCELLED,
}

_JOB_STATE = {
    "CREATED": ExecutionPhase.PENDING,
    "QUEUED": ExecutionPhase.QUEUED,
    "RUNNING": ExecutionPhase.RUNNING,
    "PAUSED": ExecutionPhase.WAITING,
    "SUCCEEDED": ExecutionPhase.SUCCEEDED,
    "FAILED": ExecutionPhase.FAILED,
    "RETRYING": ExecutionPhase.QUEUED,
    "CANCEL_REQUESTED": ExecutionPhase.RUNNING,
    "CANCELLED": ExecutionPhase.CANCELLED,
    "TIMED_OUT": ExecutionPhase.TIMED_OUT,
    "DEAD_LETTER": ExecutionPhase.FAILED,
}

_TASK_STATUS = {
    "TODO": ExecutionPhase.PENDING,
    "IN_PROGRESS": ExecutionPhase.RUNNING,
    "VERIFYING": ExecutionPhase.RUNNING,
    "ASKING_USER": ExecutionPhase.WAITING,
    "BLOCKED": ExecutionPhase.WAITING,
    "WAITING": ExecutionPhase.WAITING,
    "FAILED": ExecutionPhase.FAILED,
    "COMPLETED": ExecutionPhase.SUCCEEDED,
    "CANCELLED": ExecutionPhase.CANCELLED,
}

_GRAPH_STATUS = {
    "pending": ExecutionPhase.PENDING,
    "queued": ExecutionPhase.QUEUED,
    "running": ExecutionPhase.RUNNING,
    "succeeded": ExecutionPhase.SUCCEEDED,
    "failed": ExecutionPhase.FAILED,
    "cancelled": ExecutionPhase.CANCELLED,
}


def _lookup(table: dict[str, ExecutionPhase], value: Any) -> Optional[ExecutionPhase]:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    if not isinstance(raw, str):
        return None
    return table.get(raw) or table.get(raw.upper())


def phase_of_run_status(value: Any) -> Optional[ExecutionPhase]:
    return _lookup(_RUN_STATUS, value)


def phase_of_job_state(value: Any) -> Optional[ExecutionPhase]:
    return _lookup(_JOB_STATE, value)


def phase_of_task_status(value: Any) -> Optional[ExecutionPhase]:
    return _lookup(_TASK_STATUS, value)


def phase_of_graph_status(value: Any) -> Optional[ExecutionPhase]:
    return _lookup(_GRAPH_STATUS, value)


def is_terminal_phase(phase: Optional[ExecutionPhase]) -> bool:
    return phase in TERMINAL_PHASES


def is_live_phase(phase: Optional[ExecutionPhase]) -> bool:
    """True when a UI should keep polling/watching this work."""
    return phase in {
        ExecutionPhase.PENDING,
        ExecutionPhase.QUEUED,
        ExecutionPhase.RUNNING,
        ExecutionPhase.WAITING,
    }


__all__ = [
    "ExecutionPhase",
    "JobKind",
    "TERMINAL_PHASES",
    "is_live_phase",
    "is_terminal_phase",
    "phase_of_graph_status",
    "phase_of_job_state",
    "phase_of_run_status",
    "phase_of_task_status",
]

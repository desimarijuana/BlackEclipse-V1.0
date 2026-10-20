"""Resume the original durable task after a capability activation.

The capability loop ends by retrying the work that needed the capability. That
retry is the existing `TaskManager.restore_checkpoint(resume=True)` path — this
module only decides WHEN it is safe: the task must be parked (WAITING or
ASKING_USER), never currently running, and the capability must name it.
"""

from __future__ import annotations

from typing import Any, Optional

PARKED_STATUSES: frozenset[str] = frozenset({"WAITING", "ASKING_USER"})


def _status_of(task: Any) -> str:
    status = getattr(task, "status", "")
    return str(getattr(status, "value", status) or "")


def resume_original_task(manager: Any, task_id: Optional[str]) -> dict[str, Any]:
    """Resume a parked task from its latest checkpoint. Never raises.

    A task that is not parked is left alone: the scheduler owns a TODO task, and
    a running task must never be rewound by an activation. A missing checkpoint
    is reported as `resumed: False`, never hidden.
    """
    if not task_id:
        return {"resumed": False, "reason": "this capability has no original task"}
    if manager is None:
        return {
            "resumed": False, "taskId": str(task_id),
            "reason": "the task runtime is unavailable in this process",
        }
    try:
        task = manager.get_task(str(task_id))
    except Exception as exc:  # noqa: BLE001 - a missing task is reported, not invented
        return {"resumed": False, "taskId": str(task_id), "reason": str(exc)}
    if task is None:
        return {"resumed": False, "taskId": str(task_id), "reason": "task not found"}
    status = _status_of(task)
    if status not in PARKED_STATUSES:
        return {
            "resumed": False, "taskId": str(task_id), "status": status,
            "reason": "the original task is not parked; it was not rewound",
        }
    try:
        result = manager.restore_checkpoint(str(task_id), resume=True)
    except Exception as exc:  # noqa: BLE001 - a failed resume is reported honestly
        return {"resumed": False, "taskId": str(task_id), "reason": str(exc)}
    checkpoint = result.get("checkpoint") or {}
    return {
        "resumed": bool(result.get("resumed")),
        "taskId": str(task_id),
        "status": _status_of(result.get("task")) or status,
        "checkpointId": checkpoint.get("id"),
    }


__all__ = ["PARKED_STATUSES", "resume_original_task"]

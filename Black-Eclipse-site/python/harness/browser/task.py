"""Browser task progress — a persisted, step-level checklist for long runs (Phase 10.1).

`browser_exec` runs a bounded program of steps in ONE call, but a user watching a
long browser task wants to see *where it is*: “open SEC → search → find filing →
download → extract”. This module is that surface. A `BrowserTask` is a small,
bounded record of labelled steps with a per-step status; it is emitted as
`browser.task.*` events AND persisted, so progress survives the call that produced
it (unlike a per-action event, which is gone once streamed).

It is deliberately content-free and bounded: a task names its steps with short
labels, never page text; the step list is capped; and a caller may drive it
directly (the `browser_task` tool) or let `browser_exec` report into it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

# A task is BOUNDED: step labels and the step list cannot grow without limit.
MAX_STEPS = 64
MAX_LABEL = 120
MAX_TASKS_LIST = 200

PENDING = "pending"
ACTIVE = "active"
DONE = "done"
FAILED = "failed"
SKIPPED = "skipped"

_TERMINAL = {"completed", "failed", "cancelled"}


@dataclass
class TaskStep:
    index: int
    label: str
    status: str = PENDING
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "label": self.label, "status": self.status, "note": self.note}


@dataclass
class BrowserTask:
    id: str
    goal: str
    session_id: str = ""
    run_id: str = ""
    steps: list[TaskStep] = field(default_factory=list)
    state: str = "running"          # running | completed | failed | cancelled
    current: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # ── progress ─────────────────────────────────────────────────────────────

    def begin(self, index: int) -> Optional[TaskStep]:
        """Mark a step ACTIVE (and any earlier pending steps as skipped)."""
        if index < 0 or index >= len(self.steps):
            return None
        for step in self.steps[:index]:
            if step.status == PENDING:
                step.status = SKIPPED
        step = self.steps[index]
        step.status = ACTIVE
        self.current = index
        self._touch()
        return step

    def complete(self, index: Optional[int] = None, *, note: Optional[str] = None) -> Optional[TaskStep]:
        """Mark a step (default: the current one) DONE."""
        idx = self.current if index is None else index
        if idx < 0 or idx >= len(self.steps):
            return None
        step = self.steps[idx]
        step.status = DONE
        if note:
            step.note = str(note)[:MAX_LABEL]
        self.current = min(idx + 1, len(self.steps) - 1)
        self._touch()
        return step

    def fail(self, index: Optional[int] = None, *, note: Optional[str] = None) -> Optional[TaskStep]:
        idx = self.current if index is None else index
        if idx < 0 or idx >= len(self.steps):
            return None
        step = self.steps[idx]
        step.status = FAILED
        if note:
            step.note = str(note)[:MAX_LABEL]
        self.state = "failed"
        self._touch()
        return step

    def finish(self, *, state: str = "completed") -> None:
        self.state = state
        for step in self.steps:
            if step.status in (PENDING, ACTIVE):
                step.status = DONE if state == "completed" else SKIPPED
        self._touch()

    def _touch(self) -> None:
        self.updated_at = time.time()

    # ── views ────────────────────────────────────────────────────────────────

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL

    def progress(self) -> dict[str, Any]:
        total = len(self.steps)
        done = sum(1 for s in self.steps if s.status in (DONE, SKIPPED))
        return {
            "taskId": self.id,
            "goal": self.goal,
            "sessionId": self.session_id,
            "runId": self.run_id,
            "state": self.state,
            "current": self.current,
            "stepsTotal": total,
            "stepsDone": done,
            "fraction": round(done / total, 4) if total else 0.0,
            "currentLabel": self.steps[self.current].label if 0 <= self.current < total else None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.progress(), "steps": [s.to_dict() for s in self.steps]}

    def render(self) -> str:
        """A one-line-per-step human view: the checklist a user sees."""
        lines = [f"Task {self.id} — {self.goal} [{self.state}] ({self.progress()['stepsDone']}/{len(self.steps)})"]
        marks = {PENDING: "·", ACTIVE: "→", DONE: "✓", FAILED: "✗", SKIPPED: "-"}
        for step in self.steps:
            mark = marks.get(step.status, "·")
            suffix = f"  ({step.note})" if step.note else ""
            lines.append(f"  {mark} {step.index + 1}. {step.label}{suffix}")
        return "\n".join(lines)


def steps_from_labels(labels: list[Any]) -> list[TaskStep]:
    """Build bounded steps from a list of labels (strings or `{label, note}`)."""
    steps: list[TaskStep] = []
    for index, item in enumerate(labels[:MAX_STEPS]):
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("step") or f"step {index + 1}")
            note = item.get("note")
        else:
            label = str(item)
            note = None
        steps.append(TaskStep(index=index, label=label[:MAX_LABEL], note=(str(note)[:MAX_LABEL] if note else None)))
    return steps


class BrowserTaskRegistry:
    """In-memory live tasks + best-effort persistence and event emission.

    Bounded: at most `MAX_TASKS_LIST` terminal tasks are retained live (in-flight
    tasks are never dropped). Persistence goes through the ONE browser store.
    """

    def __init__(self, *, store: Any = None, emit: Any = None) -> None:
        self._store = store
        self._emit = emit
        self._tasks: dict[str, BrowserTask] = {}
        self._counter = 0

    def create(
        self, *, goal: str, labels: list[Any], session_id: str = "",
        run_id: str = "", task_id: str = "",
    ) -> BrowserTask:
        self._counter += 1
        tid = task_id or f"btask_{int(time.time())}_{self._counter}"
        task = BrowserTask(id=tid, goal=str(goal)[:MAX_LABEL], session_id=session_id, run_id=run_id)
        task.steps = steps_from_labels(labels)
        self._tasks[tid] = task
        self._prune()
        self._publish(task, "browser.task.created")
        return task

    def get(self, task_id: str) -> Optional[BrowserTask]:
        task = self._tasks.get(task_id)
        if task is not None:
            return task
        if self._store is not None:
            row = self._store.get_task(task_id)
            if row:
                return _task_from_row(row)
        return None

    def list(self) -> list[BrowserTask]:
        return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)

    def begin(self, task_id: str, index: int) -> Optional[BrowserTask]:
        task = self._tasks.get(task_id)
        if task is None or task.begin(index) is None:
            return None
        self._publish(task, "browser.task.progress")
        return task

    def complete(self, task_id: str, index: Optional[int] = None, *, note: Optional[str] = None) -> Optional[BrowserTask]:
        task = self._tasks.get(task_id)
        if task is None or task.complete(index, note=note) is None:
            return None
        if task.current >= len(task.steps) - 1 and all(s.status in (DONE, SKIPPED, FAILED) for s in task.steps):
            task.finish()
            self._publish(task, "browser.task.completed")
        else:
            self._publish(task, "browser.task.progress")
        return task

    def fail(self, task_id: str, *, note: Optional[str] = None) -> Optional[BrowserTask]:
        task = self._tasks.get(task_id)
        if task is None or task.fail(note=note) is None:
            return None
        self._publish(task, "browser.task.failed")
        return task

    def finish(self, task_id: str, *, state: str = "completed") -> Optional[BrowserTask]:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        task.finish(state=state)
        self._publish(task, "browser.task.completed" if state == "completed" else "browser.task.failed")
        return task

    def _publish(self, task: BrowserTask, event_type: str) -> None:
        if self._store is not None:
            try:
                self._store.save_task({
                    "id": task.id, "sessionId": task.session_id, "runId": task.run_id,
                    "goal": task.goal, "state": task.state, "current": task.current,
                    "steps": [s.to_dict() for s in task.steps],
                    "createdAt": _iso(task.created_at), "updatedAt": _iso(task.updated_at),
                })
            except Exception:  # noqa: BLE001 - persistence must never break a task
                pass
        if self._emit is not None:
            try:
                self._emit(event_type, {"taskId": task.id, **task.progress()})
            except Exception:  # noqa: BLE001 - observability must never break a task
                pass

    def _prune(self) -> None:
        if len(self._tasks) <= MAX_TASKS_LIST:
            return
        for tid, task in list(self._tasks.items()):
            if len(self._tasks) <= MAX_TASKS_LIST:
                break
            if task.terminal:
                self._tasks.pop(tid, None)


def _task_from_row(row: dict[str, Any]) -> BrowserTask:
    task = BrowserTask(
        id=row.get("id", ""), goal=row.get("goal", ""),
        session_id=row.get("sessionId", "") or "", run_id=row.get("runId", "") or "",
        state=row.get("state", "running"), current=int(row.get("current", 0) or 0),
    )
    task.steps = [TaskStep(index=int(s.get("index", i)), label=str(s.get("label", "")), status=str(s.get("status", PENDING)), note=s.get("note"))
                  for i, s in enumerate(row.get("steps") or [])]
    return task


def _iso(epoch: float) -> str:
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


__all__ = [
    "ACTIVE",
    "BrowserTask",
    "BrowserTaskRegistry",
    "DONE",
    "FAILED",
    "MAX_STEPS",
    "PENDING",
    "SKIPPED",
    "TaskStep",
    "steps_from_labels",
]

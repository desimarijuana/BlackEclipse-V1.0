"""Live state for one in-editor assistant turn.

The assistant stream is a long-lived SSE response, but pause/resume/stop are
separate HTTP calls. This module is the small in-process registry that lets those
calls reach the generator that owns the turn.

Design rules:

* The registry is only the **live** control plane. The transcript and the
  resulting edits remain the editor's own document; nothing here mutates a
  workflow.
* A run is single-owner: `stream_assist` creates it, the router finishes it, and
  every control call is a no-op once it is terminal.
* Pause gates are cooperative. The loop checks them between model rounds and
  between tool calls, so a pause never interrupts a half-written tool result.
* Cancel is sticky. A cancelled run wakes any paused waiter and every later gate
  raises `AssistantRunCancelled`.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

TERMINAL = frozenset({"completed", "failed", "cancelled"})
MAX_RUN_AGE_S = 60 * 60
MAX_LIVE_RUNS = 64


class AssistantRunCancelled(Exception):
    """Raised inside the tool loop when the operator stops the turn."""


class AssistantRun:
    def __init__(self, *, workflow_id: Optional[str] = None) -> None:
        self.id = f"assist_{uuid.uuid4().hex[:16]}"
        self.workflow_id = workflow_id
        self.status = "running"
        self.cancelled = False
        self.paused = False
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.result: Optional[dict[str, Any]] = None
        self._wake = _make_wake()

    # -- state --------------------------------------------------------------

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL

    def snapshot(self) -> dict[str, Any]:
        return {
            "runId": self.id,
            "workflowId": self.workflow_id,
            "status": self.status,
            "paused": self.paused,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    def _touch(self, status: Optional[str] = None) -> None:
        if status is not None and not self.cancelled:
            self.status = status
        self.updated_at = time.time()

    def pause(self) -> dict[str, Any]:
        if not self.terminal and not self.cancelled:
            self.paused = True
            self._touch("paused")
        return self.snapshot()

    def resume(self) -> dict[str, Any]:
        if not self.terminal and not self.cancelled:
            self.paused = False
            self._touch("running")
            self._wake.set()
        return self.snapshot()

    def cancel(self) -> dict[str, Any]:
        if self.terminal:
            return self.snapshot()
        self.paused = False
        self._touch("cancelled")
        self.cancelled = True
        self._wake.set()
        return self.snapshot()

    def finish(self, status: str = "completed") -> dict[str, Any]:
        if not self.cancelled:
            self.status = status
        self.paused = False
        self.updated_at = time.time()
        self._wake.set()
        return self.snapshot()

    # -- gates --------------------------------------------------------------

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise AssistantRunCancelled()

    async def wait_until_resumed(self) -> None:
        """Block while paused. Returns only when running again or cancelled."""
        while self.paused and not self.cancelled:
            self._wake.clear()
            if not self.paused or self.cancelled:
                break
            await self._wake.wait()
        self.raise_if_cancelled()


def _make_wake() -> Any:
    import asyncio  # noqa: PLC0415 - keep import local so the module stays cheap

    return asyncio.Event()


# ── Registry ────────────────────────────────────────────────────────────────

_RUNS: dict[str, AssistantRun] = {}


def _prune() -> None:
    now = time.time()
    stale = [
        run_id
        for run_id, run in _RUNS.items()
        if run.terminal and now - run.updated_at > MAX_RUN_AGE_S
    ]
    for run_id in stale:
        _RUNS.pop(run_id, None)
    if len(_RUNS) <= MAX_LIVE_RUNS:
        return
    ordered = sorted(_RUNS.values(), key=lambda item: item.created_at)
    for run in ordered[: max(0, len(ordered) - MAX_LIVE_RUNS)]:
        if run.terminal:
            _RUNS.pop(run.id, None)


def create_run(*, workflow_id: Optional[str] = None) -> AssistantRun:
    _prune()
    run = AssistantRun(workflow_id=workflow_id)
    _RUNS[run.id] = run
    return run


def get_run(run_id: str) -> Optional[AssistantRun]:
    return _RUNS.get(str(run_id or ""))


def pause_run(run_id: str) -> Optional[dict[str, Any]]:
    run = get_run(run_id)
    return run.pause() if run is not None else None


def resume_run(run_id: str) -> Optional[dict[str, Any]]:
    run = get_run(run_id)
    return run.resume() if run is not None else None


def cancel_run(run_id: str) -> Optional[dict[str, Any]]:
    run = get_run(run_id)
    return run.cancel() if run is not None else None


__all__ = [
    "AssistantRun",
    "AssistantRunCancelled",
    "create_run",
    "get_run",
    "pause_run",
    "resume_run",
    "cancel_run",
]

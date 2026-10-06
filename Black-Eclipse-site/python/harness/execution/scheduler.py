"""The execution scheduler — bounded concurrency, priority, cancellation.

The agent must never be able to start hundreds of processes at once. The
scheduler runs executions on a bounded thread pool, keeps an in-memory registry
keyed by execution id (for cancellation and retrieval), and persists every
result through `ExecutionStore`. Cancellation sets a `threading.Event` the
sandbox honours, so a cancelled execution's whole process tree is killed.

It is the process-wide seam the agent tools and the HTTP surface share, so UI and
agent can never disagree about what is running.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Optional

MAX_CONCURRENT_DEFAULT = 4


def _flag(name: str, default: str = "") -> str:
    import os

    return os.environ.get(name, default)


class ExecutionScheduler:
    """A bounded pool of execution workers with cancellation and history."""

    def __init__(
        self,
        orchestrator: Any,
        store: Optional[Any] = None,
        *,
        max_concurrent: Optional[int] = None,
    ) -> None:
        try:
            configured = int(max_concurrent or _flag("HARNESS_EXEC_MAX_CONCURRENCY", str(MAX_CONCURRENT_DEFAULT)))
        except (TypeError, ValueError):
            configured = MAX_CONCURRENT_DEFAULT
        self.max_concurrent = max(1, min(configured, 32))
        self._orchestrator = orchestrator
        self._store = store
        self._pool = ThreadPoolExecutor(max_workers=self.max_concurrent, thread_name_prefix="exec")
        self._lock = threading.RLock()
        self._cancels: dict[str, threading.Event] = {}
        self._futures: dict[str, Future] = {}
        self._results: dict[str, Any] = {}
        self._queue_ids: list[str] = []

    # ── submit / query ─────────────────────────────────────────────────────────

    def submit(
        self,
        request: Any,
        *,
        actor: Any = None,
        emit: Optional[Any] = None,
        run_id: str = "",
    ) -> str:
        """Queue an execution. Returns its id (the orchestrator's id is authoritative).

        The returned id is a *submission* id used for lookup; the orchestrator
        assigns the real `exec_…` id, which is stored on the result and returned by
        `get`.
        """
        submission_id = "sub_" + uuid.uuid4().hex[:12]
        cancel = threading.Event()
        with self._lock:
            self._cancels[submission_id] = cancel
            self._queue_ids.append(submission_id)

        def _work() -> Any:
            try:
                result = self._orchestrator.run(request, actor=actor, cancel_event=cancel, emit=emit)
            except BaseException as exc:  # noqa: BLE001 - a worker crash must be visible
                from ..execution.models import ErrorClass, ExecutionResult

                result = ExecutionResult(
                    execution_id="exec_error", status="FAILED", exit_code=None,
                    language=getattr(request, "language", ""), runtime="",
                    duration_ms=0, error_class=ErrorClass.INFRASTRUCTURE_ERROR.value,
                    error={"code": "INFRASTRUCTURE_ERROR", "message": f"{type(exc).__name__}: {exc}"},
                )
            with self._lock:
                self._results[submission_id] = result
                self._cancels.pop(submission_id, None)
                if submission_id in self._queue_ids:
                    self._queue_ids.remove(submission_id)
            if self._store is not None:
                try:
                    self._store.save_execution(result, run_id=run_id or getattr(request, "run_id", ""),
                                               agent_id=getattr(request, "agent_id", None))
                except Exception:  # noqa: BLE001 - persistence must not break a run
                    pass
            return result

        with self._lock:
            self._futures[submission_id] = self._pool.submit(_work)
        return submission_id

    def get(self, submission_id: str) -> Optional[Any]:
        with self._lock:
            if submission_id in self._results:
                return self._results[submission_id]
            if submission_id in self._futures:
                return PENDING
        return None

    def wait(self, submission_id: str, timeout: Optional[float] = None) -> Optional[Any]:
        with self._lock:
            future = self._futures.get(submission_id)
        if future is None:
            return self._results.get(submission_id)
        try:
            return future.result(timeout=timeout)
        except Exception:  # noqa: BLE001 - timeout/cancel surface via get()
            return self._results.get(submission_id)

    def cancel(self, submission_id: str) -> bool:
        """Request cancellation. Returns whether an execution is known."""
        with self._lock:
            event = self._cancels.get(submission_id)
            if event is None:
                return False
            event.set()
            future = self._futures.get(submission_id)
            if future is not None and not future.running():
                future.cancel()
            return True

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            pending = list(self._queue_ids)
            done = list(self._results.keys())
        out: list[dict[str, Any]] = []
        for submission_id in pending:
            out.append({"submissionId": submission_id, "status": "QUEUED"})
        for submission_id in done:
            result = self._results.get(submission_id)
            out.append({
                "submissionId": submission_id,
                "executionId": getattr(result, "execution_id", None),
                "status": getattr(result, "status", None),
            })
        return out

    def active_count(self) -> int:
        with self._lock:
            return len(self._queue_ids)

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            for event in self._cancels.values():
                event.set()
        self._pool.shutdown(wait=wait, cancel_futures=True)


class _Pending:
    """Sentinel returned by `get` while an execution is still running."""

    status = "RUNNING"
    execution_id = None


PENDING = _Pending()

__all__ = ["ExecutionScheduler", "MAX_CONCURRENT_DEFAULT", "PENDING"]

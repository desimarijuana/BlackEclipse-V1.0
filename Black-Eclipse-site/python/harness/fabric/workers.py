"""The worker framework and its manager.

A `BaseWorker` declares an identity, the queues it serves, a concurrency and a
`handle(ctx)` coroutine that invokes an EXISTING Eclipse capability. The
`WorkerManager` owns the consumer loops, claiming, leases/heartbeats, timeouts,
hard cancellation, retries/backoff, dead-lettering, graceful draining and crash
recovery.

One manager runs in the process event loop. Multiple worker kinds and multiple
consumer slots per kind give managed concurrency without a second process model.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .config import FabricConfig
from .models import (
    Job,
    WorkerInfo,
    WorkerKind,
    WorkerOutcome,
    WorkerStatus,
    coerce_outcome,
    new_worker_id,
    now,
)
from .store import FabricStore

log = logging.getLogger("harness.fabric.workers")

Listener = Callable[[str, Job, dict[str, Any]], None]
Handler = Callable[["WorkerContext"], Awaitable[Any]]

# Classify an outcome's error as retryable. Reuses the orchestration classifier
# so the two layers cannot disagree about transient-vs-deterministic failures.
try:  # pragma: no cover - import is trivial; guarded for isolation
    from ..orchestration.retry import DEFAULT_NON_RETRYABLE, DEFAULT_RETRYABLE
except Exception:  # noqa: BLE001
    DEFAULT_RETRYABLE = frozenset({"RATE_LIMITED", "NETWORK_ERROR", "TIMEOUT", "PROVIDER_ERROR"})
    DEFAULT_NON_RETRYABLE = frozenset({"INVALID_INPUT", "PERMISSION_DENIED", "CANCELLED"})


def _is_retryable(error_class: Optional[str], explicit: bool) -> bool:
    if explicit:
        return True
    code = (error_class or "").upper()
    if code in DEFAULT_NON_RETRYABLE:
        return False
    if code in DEFAULT_RETRYABLE:
        return True
    return False


@dataclass
class WorkerContext:
    """Everything a worker handler needs for one attempt."""

    job: Job
    worker_id: str
    attempt: int
    store: FabricStore
    service: Any = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    _progress: float = 0.0
    _messages: list[str] = field(default_factory=list)

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def report_progress(self, fraction: float, message: Optional[str] = None) -> None:
        self._progress = max(0.0, min(1.0, float(fraction)))
        if message:
            self._messages.append(str(message)[:500])
        try:
            self.store.update_job(self.job.id, progress=self._progress)
            self.store.append_event(
                self.job.id, "job.progress",
                {"progress": self._progress, "message": message},
            )
        except Exception:  # noqa: BLE001 - progress must never fail the job
            pass

    def log(self, event_type: str, data: Optional[dict[str, Any]] = None) -> None:
        try:
            self.store.append_event(self.job.id, event_type, data or {})
        except Exception:  # noqa: BLE001
            pass


class BaseWorker:
    """Base class for a domain worker. Subclasses implement `handle`."""

    kind: str = WorkerKind.TOOL.value
    queues: tuple[str, ...] = ()
    concurrency: int = 1
    timeout_ms: Optional[int] = None

    def __init__(self, service: Any = None, *, name: Optional[str] = None,
                 concurrency: Optional[int] = None) -> None:
        self.service = service
        self.name = name or self.kind
        if concurrency is not None:
            self.concurrency = concurrency

    async def handle(self, ctx: WorkerContext) -> WorkerOutcome:  # pragma: no cover - abstract
        raise NotImplementedError

    async def health(self) -> dict[str, Any]:
        return {"kind": self.kind, "queues": list(self.queues), "concurrency": self.concurrency}

    async def shutdown(self) -> None:
        """Release worker-owned resources (browser contexts, subprocesses)."""


class FunctionWorker(BaseWorker):
    """A worker backed by an async callable `handler(ctx) -> WorkerOutcome | Any`."""

    def __init__(
        self, kind: str, queues: list[str], handler: Handler, *, service: Any = None,
        concurrency: int = 1, timeout_ms: Optional[int] = None, name: Optional[str] = None,
    ) -> None:
        super().__init__(service, name=name or kind, concurrency=concurrency)
        self.kind = kind
        self.queues = tuple(queues)
        self._handler = handler
        self.timeout_ms = timeout_ms

    async def handle(self, ctx: WorkerContext) -> WorkerOutcome:
        return coerce_outcome(await self._handler(ctx))


class WorkerRegistry:
    def __init__(self) -> None:
        self._workers: dict[str, BaseWorker] = {}

    def register(self, worker: BaseWorker) -> None:
        self._workers[worker.kind] = worker

    def get(self, kind: str) -> Optional[BaseWorker]:
        return self._workers.get(kind)

    def workers(self) -> list[BaseWorker]:
        return list(self._workers.values())

    def for_queue(self, queue: str) -> list[BaseWorker]:
        return [w for w in self._workers.values() if queue in w.queues]


@dataclass
class _WorkerRuntime:
    worker: BaseWorker
    info: WorkerInfo
    loops: list[asyncio.Task] = field(default_factory=list)
    active: int = 0


class WorkerManager:
    """Claims, executes and finalises jobs for the registered workers."""

    def __init__(
        self,
        store: FabricStore,
        config: FabricConfig,
        registry: WorkerRegistry,
        *,
        service: Any = None,
        listener: Optional[Listener] = None,
    ) -> None:
        self._store = store
        self._config = config
        self._registry = registry
        self._service = service
        self._listener = listener
        self._runtimes: dict[str, _WorkerRuntime] = {}
        self._tasks: dict[str, asyncio.Task] = {}       # job_id -> handler task
        self._contexts: dict[str, WorkerContext] = {}   # job_id -> ctx
        self._supervisor: Optional[asyncio.Task] = None
        self._running = False
        self._shutting_down = False
        self._rng = random.Random(0xC0FFEE)

    # ── registry ─────────────────────────────────────────────────────────────
    def register(self, worker: BaseWorker) -> None:
        self._registry.register(worker)

    def workers(self) -> list[BaseWorker]:
        return self._registry.workers()

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._shutting_down = False
        for worker in self._registry.workers():
            await self._start_worker(worker)

    async def _start_worker(self, worker: BaseWorker) -> None:
        concurrency = max(1, int(worker.concurrency))
        info = WorkerInfo(
            id=new_worker_id(), kind=worker.kind, queue=worker.queues[0] if worker.queues else "agent",
            status=WorkerStatus.IDLE.value, concurrency=concurrency, pid=os.getpid(),
        )
        runtime = _WorkerRuntime(worker=worker, info=info)
        self._runtimes[worker.kind] = runtime
        self._store.upsert_worker(info)
        for slot in range(concurrency):
            runtime.loops.append(asyncio.create_task(self._consumer_loop(worker, info, slot)))

    async def stop(self, *, timeout: Optional[float] = None) -> None:
        """Graceful shutdown: drain, cancel in-flight, release every resource."""
        if not self._running and not self._runtimes:
            return
        self._shutting_down = True
        self._running = False
        grace = float(timeout if timeout is not None else self._config.shutdown_timeout_s)
        # Stop accepting work and wait a bounded time for in-flight jobs.
        deadline = time.monotonic() + grace
        while self._tasks and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        # Cancel anything still running, then cancel the consumer loops.
        for job_id in list(self._tasks):
            self._cancel_task(job_id)
        for runtime in self._runtimes.values():
            runtime.info.status = WorkerStatus.DRAINING.value
            for loop in runtime.loops:
                loop.cancel()
        all_loops = [loop for r in self._runtimes.values() for loop in r.loops]
        if all_loops:
            await asyncio.gather(*all_loops, return_exceptions=True)
        for job_id in list(self._tasks):
            await self._await_task(job_id)
        for runtime in self._runtimes.values():
            try:
                await runtime.worker.shutdown()
            except Exception:  # noqa: BLE001 - shutdown must not raise
                log.warning("worker %s shutdown failed", runtime.worker.kind, exc_info=True)
            self._store.remove_worker(runtime.info.id)
        self._runtimes.clear()
        self._tasks.clear()
        self._contexts.clear()
        self._shutting_down = False

    # ── consumer loop ────────────────────────────────────────────────────────
    async def _consumer_loop(self, worker: BaseWorker, info: WorkerInfo, slot: int) -> None:
        try:
            while self._running:
                # The claim and the heartbeat MUST use the same worker id, or
                # the lease is never renewed and recovery requeues live work.
                job = self._store.claim_job(
                    list(worker.queues), worker_id=info.id,
                    worker_kind=worker.kind, lease_seconds=self._config.lease_seconds,
                )
                if job is None:
                    await asyncio.sleep(self._config.poll_seconds)
                    continue
                await self._execute_job(worker, info, job)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a consumer failure must not kill the pool
            log.warning("worker consumer crashed (kind=%s)", worker.kind, exc_info=True)

    async def _execute_job(self, worker: BaseWorker, info: WorkerInfo, job: Job) -> None:
        ctx = WorkerContext(
            job=job, worker_id=info.id, attempt=job.attempts, store=self._store,
            service=self._service,
        )
        self._contexts[job.id] = ctx
        timeout_ms = int(worker.timeout_ms or job.timeout_ms or self._config.job_timeout_ms)
        attempt_id = self._store.start_attempt(job.id, attempt=job.attempts, worker_id=info.id)
        self._emit("job.started", job, {"attempt": job.attempts, "workerId": info.id})
        info.status = WorkerStatus.BUSY.value
        info.active_jobs += 1
        self._store.heartbeat_worker(info.id, status=info.status, active_jobs=info.active_jobs)
        heartbeat = asyncio.create_task(self._heartbeat(info.id, job.id))
        started = time.monotonic()
        handler_task = asyncio.create_task(worker.handle(ctx))
        self._tasks[job.id] = handler_task
        outcome: WorkerOutcome
        try:
            result = await asyncio.wait_for(handler_task, timeout=max(0.1, timeout_ms / 1000.0))
            outcome = coerce_outcome(result)
        except asyncio.TimeoutError:
            handler_task.cancel()
            await self._swallow(handler_task)
            outcome = WorkerOutcome(status="timed_out", error=f"job timed out after {timeout_ms}ms",
                                    error_class="TIMEOUT", retryable=True)
        except asyncio.CancelledError:
            handler_task.cancel()
            await self._swallow(handler_task)
            if self._shutting_down and not ctx.cancelled:
                self._finish_attempt(attempt_id, "cancelled", "shutdown", "CANCELLED", started)
                self._cleanup(info, job.id, heartbeat)
                raise
            outcome = WorkerOutcome(status="cancelled", error="job cancelled", error_class="CANCELLED")
        except Exception as exc:  # noqa: BLE001 - a worker failure is data
            outcome = WorkerOutcome(status="failed", error=str(exc)[:2000], error_class="WORKER_ERROR")
        self._finish_attempt(attempt_id, outcome.status, outcome.error, outcome.error_class, started)
        self._cleanup(info, job.id, heartbeat)
        self._finalize(job, outcome)

    def _cleanup(self, info: WorkerInfo, job_id: str, heartbeat: asyncio.Task) -> None:
        heartbeat.cancel()
        self._tasks.pop(job_id, None)
        self._contexts.pop(job_id, None)
        info.active_jobs = max(0, info.active_jobs - 1)
        info.status = WorkerStatus.IDLE.value if info.active_jobs == 0 else WorkerStatus.BUSY.value
        try:
            self._store.heartbeat_worker(info.id, status=info.status, active_jobs=info.active_jobs)
        except Exception:  # noqa: BLE001
            pass

    def _finish_attempt(self, attempt_id: str, status: str, error: Optional[str],
                        error_class: Optional[str], started: float) -> None:
        try:
            self._store.finish_attempt(
                attempt_id, status=status, error=error, error_class=error_class,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception:  # noqa: BLE001
            pass

    # ── finalisation ─────────────────────────────────────────────────────────
    def _finalize(self, job: Job, outcome: WorkerOutcome) -> None:
        current = self._store.get_job(job.id) or job
        # A cancellation requested mid-flight wins over a completed/failed result.
        if current.state.value in ("CANCEL_REQUESTED", "CANCELLED") and outcome.status != "succeeded":
            self._safe(lambda: self._store.mark_cancelled(job.id))
            self._emit("job.cancelled", current, {"reason": "cancel_requested"})
            self._emit_terminal(self._store.get_job(job.id) or current, outcome)
            return

        if outcome.status == "succeeded":
            updated = self._safe(lambda: self._store.complete_job(
                job.id, output=outcome.output, progress=outcome.progress))
            self._emit("job.succeeded", updated or current, {"durationMs": current.duration_ms()})
            self._emit_terminal(updated or current, outcome)
            return

        if outcome.status == "cancelled":
            updated = self._safe(lambda: self._store.mark_cancelled(job.id))
            self._emit("job.cancelled", updated or current, {})
            self._emit_terminal(updated or current, outcome)
            return

        if outcome.status == "deferred":
            # A durable wait paused the job; requeue at its wake time without
            # counting a retry failure or consuming an attempt.
            delay = max(1.0, float(outcome.metrics.get("wakeAfterSeconds") or 1.0))
            updated = self._safe(lambda: self._store.requeue_for_retry(
                job.id, available_at=now() + delay, error="deferred wait",
                error_class="DEFERRED",
            ))
            self._emit("job.deferred", updated or current,
                       {"wakeAfterSeconds": delay})
            return

        retryable = _is_retryable(outcome.error_class, outcome.retryable)
        exhausted = current.attempts >= max(1, current.max_attempts)
        if retryable and not exhausted:
            delay = self._backoff(current)
            available = now() + delay
            updated = self._safe(lambda: self._store.requeue_for_retry(
                job.id, available_at=available, error=outcome.error or "retryable failure",
                error_class=outcome.error_class))
            self._emit("job.retrying", updated or current,
                       {"attempt": current.attempts, "backoffMs": int(delay * 1000),
                        "errorClass": outcome.error_class})
            return
        # A timed-out job that cannot retry is recorded as TIMED_OUT (a distinct,
        # honest terminal state), never conflated with a generic failure.
        if outcome.status == "timed_out":
            updated = self._safe(lambda: self._store.timed_out_job(
                job.id, error=outcome.error or "timed out"))
            self._emit("job.timed_out", updated or current, {"attempts": current.attempts})
            self._emit_terminal(updated or current, outcome)
            return
        if retryable and current.allow_dlq():
            updated = self._safe(lambda: self._store.to_dead_letter(
                job.id, error=outcome.error or "retries exhausted",
                error_class=outcome.error_class))
            self._emit("job.dead_letter", updated or current, {"attempts": current.attempts})
            self._emit_terminal(updated or current, outcome)
            return
        updated = self._safe(lambda: self._store.fail_job(
            job.id, error=outcome.error or "failed",
            error_class=outcome.error_class or "WORKER_ERROR"))
        self._emit("job.failed", updated or current, {"errorClass": outcome.error_class})
        self._emit_terminal(updated or current, outcome)

    def _backoff(self, job: Job) -> float:
        base = max(0.1, job.metadata.get("backoffMs", 500) / 1000.0)
        multiplier = float(job.metadata.get("backoffMultiplier", 2.0))
        value = min(300.0, base * (multiplier ** max(0, job.attempts - 1)))
        jitter = float(job.metadata.get("jitter", 0.1))
        if jitter > 0:
            value = value * (1 - jitter) + self._rng.random() * value * jitter
        return value

    def _safe(self, fn: Callable[[], Any]) -> Optional[Job]:
        try:
            return fn()
        except Exception:  # noqa: BLE001 - finalisation must never crash the pool
            log.warning("job finalisation failed", exc_info=True)
            return None

    # ── cancellation ─────────────────────────────────────────────────────────
    def cancel(self, job_id: str) -> bool:
        """Request cancellation. Returns whether a running handler was hard-cancelled."""
        ctx = self._contexts.get(job_id)
        if ctx is not None:
            ctx.cancel_event.set()
        return self._cancel_task(job_id)

    def _cancel_task(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def _await_task(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task is not None:
            await self._swallow(task)

    async def _swallow(self, task: asyncio.Task) -> None:
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    # ── heartbeat ────────────────────────────────────────────────────────────
    async def _heartbeat(self, worker_id: str, job_id: str) -> None:
        interval = max(1.0, self._config.lease_seconds / 3.0)
        try:
            while True:
                await asyncio.sleep(interval)
                self._store.renew_lease(
                    job_id, worker_id=worker_id, lease_seconds=self._config.lease_seconds)
                self._store.heartbeat_worker(worker_id, status=WorkerStatus.BUSY.value, active_jobs=1)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            return

    # ── recovery ─────────────────────────────────────────────────────────────
    async def recover(self) -> list[str]:
        """Re-drive jobs whose worker died (expired lease). Never lose durable work."""
        recovered: list[str] = []
        for job in self._store.expired_running_jobs(limit=200):
            max_attempts = max(1, job.max_attempts)
            if job.attempts < max_attempts:
                delay = self._backoff(job)
                self._safe(lambda j=job, d=delay: self._store.requeue_for_retry(
                    j.id, available_at=now() + d, error="worker lease expired",
                    error_class="WORKER_LOST"))
                self._emit("job.recovered", job, {"reason": "lease_expired", "requeued": True})
            else:
                self._safe(lambda j=job: self._store.to_dead_letter(
                    j.id, error="worker lease expired", error_class="WORKER_LOST"))
                self._emit("job.recovered", job, {"reason": "lease_expired", "requeued": False})
            recovered.append(job.id)
        return recovered

    # ── status ───────────────────────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        workers = self._store.list_workers()
        health = []
        for runtime in self._runtimes.values():
            health.append({
                "id": runtime.info.id, "kind": runtime.worker.kind,
                "workerKind": runtime.info.kind, "queue": runtime.info.queue,
                "status": runtime.info.status, "concurrency": runtime.info.concurrency,
                "activeJobs": runtime.info.active_jobs,
                "utilization": round(runtime.info.active_jobs / max(1, runtime.info.concurrency), 3),
                "pid": runtime.info.pid,
            })
        return {
            "running": self._running,
            "draining": self._shutting_down,
            "workers": health,
            "storedWorkers": workers,
            "queues": self._store.queue_stats(),
            "statusCounts": self._store.status_counts(),
        }

    # ── events ───────────────────────────────────────────────────────────────
    def _emit(self, event_type: str, job: Job, data: dict[str, Any]) -> None:
        try:
            self._store.append_event(job.id, event_type, data)
        except Exception:  # noqa: BLE001
            pass
        if self._listener is not None:
            try:
                self._listener(event_type, job, data)
            except Exception:  # noqa: BLE001 - a listener must never break execution
                log.debug("fabric listener failed", exc_info=True)

    def _emit_terminal(self, job: Job, outcome: WorkerOutcome) -> None:
        if self._listener is not None:
            try:
                self._listener("job.terminal", job, {"status": job.state.value, "outcome": outcome.to_dict()})
            except Exception:  # noqa: BLE001
                log.debug("fabric terminal listener failed", exc_info=True)


__all__ = [
    "BaseWorker",
    "FunctionWorker",
    "WorkerContext",
    "WorkerManager",
    "WorkerRegistry",
]

"""ExecutionManager — the ONE routing seam for Eclipse execution.

The agent runtime (and tools, automations, events, JDdS ingestion and plugins)
call `ExecutionManager.submit(...)`; it decides HOW to run:

    DIRECT     -> run a worker handler inline (fast: reads, cheap tools)
    CONCURRENT -> enqueue + await (managed concurrency: child agents, research)
    BACKGROUND -> enqueue, return a job id (outlives the request)
    DURABLE    -> enqueue persisted + idempotent (ingestion, scheduled, retried)

Nothing enqueues trivial work, and nothing bypasses the existing runtime: the
workers themselves call `service.run`, `ToolRegistry.execute`, the plugin
manager, the automation engine, etc. The manager adds routing, durability,
dedup/priority, cancellation, retries and observability around them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Optional

from .config import FabricConfig
from .locks import DistributedLockManager
from .metrics import FabricMetrics
from .models import (
    ExecutionMode,
    Job,
    JobPriority,
    JobState,
    QueueName,
    WorkerOutcome,
    priority_weight,
)
from .policies import PolicyRegistry
from .store import FabricStore
from .workers import BaseWorker, WorkerContext, WorkerManager, WorkerRegistry

log = logging.getLogger("harness.fabric.manager")


def _stable_key(job_type: str, payload: Any) -> str:
    try:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        canonical = str(payload)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"{job_type}:{digest}"


class ExecutionManager:
    def __init__(
        self,
        store: FabricStore,
        *,
        config: Optional[FabricConfig] = None,
        registry: Optional[WorkerRegistry] = None,
        service: Any = None,
    ) -> None:
        self._store = store
        self.config = config or FabricConfig()
        self.policies = PolicyRegistry(self.config)
        self.metrics = FabricMetrics()
        self.locks = DistributedLockManager(store, default_ttl_ms=self.config.lock_ttl_ms)
        self._registry = registry or WorkerRegistry()
        self._service = service
        self._workers = WorkerManager(
            store, self.config, self._registry, service=service, listener=self._on_event,
        )
        self._waiters: dict[str, asyncio.Future] = {}
        self._started = False

    # ── registration / lifecycle ─────────────────────────────────────────────
    def register_worker(self, worker: BaseWorker) -> None:
        self._registry.register(worker)

    def workers(self) -> list[BaseWorker]:
        return self._registry.workers()

    @property
    def worker_manager(self) -> WorkerManager:
        return self._workers

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self._workers.recover()
        await self._workers.start()

    async def stop(self, *, timeout: Optional[float] = None) -> None:
        self._started = False
        await self._workers.stop(timeout=timeout)
        self.locks.purge_expired()
        for future in list(self._waiters.values()):
            if not future.done():
                future.cancel()
        self._waiters.clear()

    async def recover(self) -> list[str]:
        return await self._workers.recover()

    # ── submission ───────────────────────────────────────────────────────────
    async def submit(
        self,
        job_type: str,
        payload: Optional[dict[str, Any]] = None,
        *,
        mode: Optional[Any] = None,
        queue: Optional[Any] = None,
        priority: Optional[Any] = None,
        timeout_ms: Optional[int] = None,
        max_attempts: Optional[int] = None,
        worker_kind: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        parent_job_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        await_result: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Route and (where needed) enqueue a unit of work. See module docstring."""
        policy = self.policies.resolve(
            job_type, mode=mode, queue=queue, priority=priority,
            timeout_ms=timeout_ms, max_attempts=max_attempts, worker_kind=worker_kind,
        )
        input_payload = dict(payload or {})
        exec_mode = policy.mode

        if exec_mode == ExecutionMode.DIRECT:
            return await self._run_direct(job_type, input_payload, policy)

        # Idempotency / coalescing.
        key = idempotency_key
        if key is None and (policy.idempotent or exec_mode == ExecutionMode.DURABLE):
            key = _stable_key(job_type, input_payload)
        if key is not None:
            existing_id = self._store.idempotency_get(key)
            if existing_id:
                existing = self._store.get_job(existing_id)
                if existing is not None and existing.state not in (
                    JobState.FAILED, JobState.CANCELLED, JobState.TIMED_OUT,
                ):
                    self.metrics.incr("deduplicated")
                    return {"jobId": existing.id, "status": existing.status,
                            "mode": exec_mode.value, "deduplicated": True}

        parent = self._store.get_job(parent_job_id) if parent_job_id else None
        root_job_id = (parent.root_job_id or parent.id) if parent is not None else None
        job = Job(
            type=job_type,
            queue=policy.queue,
            status=JobState.QUEUED.value,
            priority=int(policy.priority),
            worker_kind=policy.worker_kind,
            task_id=task_id, parent_job_id=parent_job_id, root_job_id=root_job_id,
            agent_id=agent_id, session_id=session_id, user_id=user_id,
            workspace_id=workspace_id, input=input_payload,
            max_attempts=max(1, int(policy.max_attempts)),
            timeout_ms=int(policy.timeout_ms),
            idempotency_key=key, correlation_id=correlation_id,
            durable=bool(policy.durable or exec_mode == ExecutionMode.DURABLE),
            available_at=None,
            metadata={
                "backoffMs": policy.backoff_ms,
                "backoffMultiplier": policy.multiplier,
                "jitter": policy.jitter,
                "mode": exec_mode.value,
                "idempotent": policy.idempotent,
                **(metadata or {}),
            },
        )
        if not job.trace_id:
            job.trace_id = job.id
        self._store.create_job(job)
        if key is not None:
            self._store.idempotency_put(key, job.id)
        self._store.append_event(job.id, "job.queued", {"mode": exec_mode.value, "queue": job.queue})
        self.metrics.incr("submitted")
        self.metrics.incr("queued")
        self._publish("fabric.job.queued", job, {"mode": exec_mode.value})

        if exec_mode == ExecutionMode.CONCURRENT:
            return await self._await_job(job)
        return {"jobId": job.id, "status": job.status, "mode": exec_mode.value}

    async def _run_direct(self, job_type: str, payload: dict[str, Any],
                          policy: Any) -> dict[str, Any]:
        self.metrics.incr("submitted")
        self.metrics.incr("direct")
        worker = self._registry.get(policy.worker_kind or job_type)
        if worker is None:
            return {"status": "failed", "mode": ExecutionMode.DIRECT.value,
                    "error": f"no worker registered for {policy.worker_kind or job_type!r}",
                    "errorClass": "WORKER_UNAVAILABLE"}
        job = Job(type=job_type, queue=policy.queue, input=payload,
                  priority=int(policy.priority), timeout_ms=int(policy.timeout_ms),
                  worker_kind=policy.worker_kind, status=JobState.RUNNING.value)
        ctx = WorkerContext(job=job, worker_id="direct", attempt=1, store=self._store,
                            service=self._service)
        try:
            result = await asyncio.wait_for(
                worker.handle(ctx), timeout=max(0.1, policy.timeout_ms / 1000.0))
            outcome = result if isinstance(result, WorkerOutcome) else WorkerOutcome(output=result)
        except asyncio.TimeoutError:
            outcome = WorkerOutcome(status="timed_out", error="direct call timed out",
                                    error_class="TIMEOUT")
        except Exception as exc:  # noqa: BLE001
            outcome = WorkerOutcome(status="failed", error=str(exc)[:2000],
                                    error_class="WORKER_ERROR")
        self._emit_metric(outcome)
        return {"status": outcome.status, "mode": ExecutionMode.DIRECT.value,
                "output": outcome.output, "error": outcome.error,
                "errorClass": outcome.error_class}

    async def _await_job(self, job: Job) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._waiters[job.id] = future
        timeout = max(1.0, job.timeout_ms / 1000.0) + 30.0
        try:
            outcome = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            await self.cancel(job.id)
            return {"jobId": job.id, "status": "TIMED_OUT", "mode": ExecutionMode.CONCURRENT.value,
                    "error": "the caller timed out waiting for the job", "errorClass": "AWAIT_TIMEOUT"}
        except asyncio.CancelledError:
            await self.cancel(job.id)
            raise
        finally:
            self._waiters.pop(job.id, None)
        current = self._store.get_job(job.id) or job
        return {
            "jobId": job.id, "status": current.status, "mode": ExecutionMode.CONCURRENT.value,
            "output": current.output, "error": current.error, "errorClass": current.error_class,
            "outcome": outcome.to_dict() if isinstance(outcome, WorkerOutcome) else None,
        }

    # ── DAG delegation ───────────────────────────────────────────────────────
    async def submit_dag(
        self, tasks: list[dict[str, Any]], *, concurrency: int = 0,
        failure_policy: str = "CONTINUE", quorum: int = 0, aggregate: bool = False,
        model_settings: Any = None, callback_base_url: str = "", callback_token: Optional[str] = None,
        user_id: Optional[str] = None, run_id: str = "",
    ) -> dict[str, Any]:
        """Run a DAG on the EXISTING orchestration engine (parallel by construction)."""
        orchestration = getattr(self._service, "orchestration", None)
        if orchestration is None:
            return {"status": "failed", "error": "the orchestration layer is unavailable",
                    "errorClass": "RUNTIME_UNAVAILABLE"}
        from ..orchestration.models import FailurePolicy
        from ..orchestration.primitives import parallel_execute

        try:
            policy = FailurePolicy(str(failure_policy).upper())
        except ValueError:
            policy = FailurePolicy.CONTINUE
        runtime = orchestration.runtime_for(
            model_settings=model_settings, callback_base_url=callback_base_url,
            callback_token=callback_token, user_id=user_id, run_id=run_id,
        )
        engine = orchestration.new_engine(runtime)
        result = await parallel_execute(
            engine, tasks, concurrency=concurrency, failure_policy=policy,
            quorum=quorum, aggregate=aggregate, metadata={"source": "fabric"},
        )
        return {"status": "completed" if result.status.value == "COMPLETED" else result.status.value,
                "result": result.to_dict()}

    # ── queries / admin ──────────────────────────────────────────────────────
    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        job = self._store.get_job(job_id)
        return job.to_dict() if job else None

    def result(self, job_id: str) -> Optional[dict[str, Any]]:
        job = self._store.get_job(job_id)
        if job is None:
            return None
        return {"jobId": job.id, "status": job.status, "output": job.output,
                "error": job.error, "errorClass": job.error_class,
                "progress": job.progress, "attempts": job.attempts}

    def list_jobs(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [j.to_dict() for j in self._store.list_jobs(**kwargs)]

    def children(self, job_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return [j.to_dict() for j in self._store.list_jobs(parent_job_id=job_id, limit=limit)]

    def events(self, job_id: str, limit: int = 500) -> list[dict[str, Any]]:
        return self._store.list_events(job_id, limit=limit)

    def attempts(self, job_id: str) -> list[dict[str, Any]]:
        return self._store.list_attempts(job_id)

    def dlq(self, limit: int = 100) -> list[dict[str, Any]]:
        return [j.to_dict() for j in self._store.dlq_jobs(limit=limit)]

    async def cancel(self, job_id: str) -> dict[str, Any]:
        job = self._store.request_cancel(job_id)
        if job is None:
            return {"cancelled": False, "jobId": job_id, "reason": "unknown job"}
        hard = self._workers.cancel(job_id)
        self.metrics.incr("cancelled")
        self._publish("fabric.job.cancelling", job, {"hardCancelled": hard})
        return {"cancelled": True, "jobId": job_id, "status": job.status, "hardCancelled": hard}

    async def retry(self, job_id: str) -> dict[str, Any]:
        job = self._store.get_job(job_id)
        if job is None:
            return {"retried": False, "reason": "unknown job"}
        from .state import is_replayable
        if not is_replayable(job.state):
            return {"retried": False, "reason": f"job is {job.status}, not replayable"}
        self._store.set_state(job_id, JobState.QUEUED, error=None, error_class=None,
                              available_at=None, leaseExpiresAt=None, completed_at=None)
        self.metrics.incr("replayed")
        self._publish("fabric.job.retried", job, {})
        return {"retried": True, "jobId": job_id, "status": JobState.QUEUED.value}

    def stats(self) -> dict[str, Any]:
        return {
            "queues": self._store.queue_stats(),
            "statusCounts": self._store.status_counts(),
            "totalJobs": self._store.total_jobs(),
            "dlqSize": len(self._store.dlq_jobs(limit=self.config.dlq_limit)),
            "config": self.config.to_dict(),
        }

    def health(self) -> dict[str, Any]:
        return {
            "available": True,
            "started": self._started,
            "workers": self._workers.status(),
            "metrics": self.metrics.snapshot(),
            "counts": self._store.status_counts(),
        }

    # ── the worker listener ──────────────────────────────────────────────────
    def _on_event(self, event_type: str, job: Job, data: dict[str, Any]) -> None:
        if event_type == "job.terminal":
            future = self._waiters.get(job.id)
            if future is not None and not future.done():
                future.set_result(WorkerOutcome(status=_outcome_status(job),
                                                output=job.output, error=job.error,
                                                error_class=job.error_class))
            self._emit_metric_from_job(job)
        self._publish(f"fabric.{event_type}", job, data)

    def _emit_metric(self, outcome: WorkerOutcome) -> None:
        if outcome.ok:
            self.metrics.incr("succeeded")
        elif outcome.status == "cancelled":
            self.metrics.incr("cancelled")
        elif outcome.status == "timed_out":
            self.metrics.incr("timed_out")
        else:
            self.metrics.incr("failed")

    def _emit_metric_from_job(self, job: Job) -> None:
        self.metrics.observe_latency(job.duration_ms())
        if job.state == JobState.SUCCEEDED:
            self.metrics.incr("succeeded")
        elif job.state == JobState.DEAD_LETTER:
            self.metrics.incr("dlq")
        elif job.state == JobState.CANCELLED:
            self.metrics.incr("cancelled")
        elif job.state == JobState.TIMED_OUT:
            self.metrics.incr("timed_out")
        elif job.state == JobState.FAILED:
            self.metrics.incr("failed")
        elif job.state == JobState.RETRYING:
            self.metrics.incr("retried")

    def _publish(self, event_type: str, job: Job, data: dict[str, Any]) -> None:
        if self._service is None:
            return
        payload = {
            "type": event_type, "jobId": job.id, "status": job.status,
            "queue": job.queue, "jobType": job.type, "taskId": job.task_id,
            "correlationId": job.correlation_id, "data": data,
        }
        bus = getattr(self._service, "bus", None)
        if bus is not None:
            try:
                from ..persistence import now_iso
                bus.publish({**payload, "at": now_iso()})
            except Exception:  # noqa: BLE001
                log.debug("fabric bus publish failed", exc_info=True)
        system = getattr(self._service, "_event_system", None)
        if system is not None:
            try:
                system.emit_nowait(event_type.replace(".", "."), payload)
            except Exception:  # noqa: BLE001
                log.debug("fabric event-system publish failed", exc_info=True)


def _outcome_status(job: Job) -> str:
    if job.state == JobState.SUCCEEDED:
        return "succeeded"
    if job.state == JobState.CANCELLED:
        return "cancelled"
    if job.state == JobState.TIMED_OUT:
        return "timed_out"
    return "failed"


__all__ = ["ExecutionManager"]

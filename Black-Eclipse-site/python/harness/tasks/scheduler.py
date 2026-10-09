"""TaskScheduler — claim runnable tasks, run them, retry, and recover.

One lifespan task, started beside the job scheduler from `AgenticService`. One
tick at a time; bounded in-flight work (this is a desktop app, not a server).

Execution goes through the EXISTING runtime: the injected `executor` runs a task
by calling `service.run` (a normal run with its own trace, events, tool
executions and verification). The scheduler owns only:
  * discovery of runnable tasks (via `TaskManager`);
  * ATOMIC claiming with a lease (`TaskStore.claim_task`);
  * lease heartbeats while a run is in flight;
  * retry with exponential backoff for RETRYABLE errors only;
  * recovery of an expired lease (a crashed worker) — never leaving a task stuck
    in IN_PROGRESS.

Time is injected (`clock`) so tests advance a fake clock and assert exact
decisions without sleeping.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .context import build_task_context
from .manager import TaskManager
from .model import (
    DEFAULT_LEASE_SECONDS,
    ExecutionStatus,
    MAX_MAX_RETRIES,
    NON_RETRYABLE_ERRORS,
    PlanStatus,
    RETRYABLE_ERRORS,
    Task,
    TaskStatus,
)

log = logging.getLogger("harness.tasks.scheduler")

TICK_SECONDS = 15.0
DEFAULT_MAX_IN_FLIGHT = 2
DEFAULT_RUN_TIMEOUT_S = 900


def _default_clock() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


@dataclass
class TaskRunOutcome:
    """What an executor reports back about one task run."""

    status: str = "failed"          # completed | failed | timed_out | cancelled | refused
    output: str = ""
    error: str = ""
    error_class: str = ""
    run_id: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    criteria: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "output": self.output, "error": self.error,
            "errorClass": self.error_class, "runId": self.run_id,
            "artifacts": self.artifacts, "criteria": self.criteria,
            "metrics": self.metrics,
        }


class TaskScheduler:
    def __init__(
        self,
        manager: TaskManager,
        *,
        executor: Optional[Callable[[Task, Any, str], Any]] = None,
        clock: Optional[Callable[[], _dt.datetime]] = None,
        max_in_flight: int = DEFAULT_MAX_IN_FLIGHT,
        tick_seconds: float = TICK_SECONDS,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        run_timeout_s: int = DEFAULT_RUN_TIMEOUT_S,
        worker_id: Optional[str] = None,
        auto_verify_criteria: bool = True,
    ) -> None:
        self._manager = manager
        self._executor = executor
        self._clock = clock or _default_clock
        self._max_in_flight = max(1, int(max_in_flight))
        self._tick_seconds = tick_seconds
        self._lease_seconds = max(10, int(lease_seconds))
        self._run_timeout_s = max(30, int(run_timeout_s))
        self._worker_id = worker_id or f"worker:{uuid.uuid4().hex[:8]}"
        self._auto_verify_criteria = auto_verify_criteria
        self._task: Optional[asyncio.Task[Any]] = None
        self._active: dict[str, asyncio.Task[Any]] = {}
        self._claimed: dict[str, str] = {}  # task_id -> claim_token

    # ── Lifecycle ────────────────────────────────────────────────────────────
    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        for running in list(self._active.values()):
            running.cancel()
        self._active.clear()
        for task_id, token in list(self._claimed.items()):
            try:
                self._manager._store.release_claim(task_id, claim_token=token)  # noqa: SLF001
                self._manager._store.update_task_fields(task_id, {"status": "TODO"})  # noqa: SLF001
            except Exception:  # noqa: BLE001
                pass
        self._claimed.clear()

    async def wait_idle(self) -> None:
        while self._active:
            await asyncio.gather(*list(self._active.values()), return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a tick failure must not kill the loop
                log.warning("task tick failed", exc_info=True)
            await asyncio.sleep(self._tick_seconds)

    def _now(self) -> _dt.datetime:
        moment = self._clock()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=_dt.timezone.utc)
        return moment

    # ── Tick ─────────────────────────────────────────────────────────────────
    async def tick(self) -> dict[str, int]:
        """One scheduling pass. Returns a small report for tests/observability."""
        moment_iso = self._now().isoformat()
        recovered = await self.recover_expired_leases(now=moment_iso)
        started = 0
        for task in self._manager.runnable_tasks(limit=500, now=moment_iso):
            if len(self._active) >= self._max_in_flight:
                break
            if self._plan_status(task) not in (PlanStatus.RUNNING, None):
                continue
            if await self._claim_and_launch(task):
                started += 1
        return {"recovered": recovered, "started": started, "inFlight": len(self._active)}

    def _plan_status(self, task: Task) -> Optional[PlanStatus]:
        if not task.plan_id:
            return None
        plan = self._manager._store.get_plan(task.plan_id)  # noqa: SLF001
        return plan.status if plan is not None else None

    async def run_plan_once(self) -> dict[str, int]:
        """Drain a plan synchronously for tests / a manual 'run now'."""
        report = await self.tick()
        await self.wait_idle()
        return report

    # ── Claim + launch ───────────────────────────────────────────────────────
    async def _claim_and_launch(self, task: Task) -> bool:
        token = uuid.uuid4().hex
        claimed = self._manager._store.claim_task(  # noqa: SLF001
            task.id, worker_id=self._worker_id, claim_token=token,
            lease_seconds=self._lease_seconds, now=self._now().isoformat(),
        )
        if not claimed:
            return False
        self._claimed[task.id] = token
        fresh = self._manager.get_task(task.id)
        self._manager._emit(  # noqa: SLF001
            "TASK_ASSIGNED", task=fresh,
            data={"workerId": self._worker_id, "agentId": fresh.assigned_agent_id},
        )
        execution = self._manager._store.start_execution(  # noqa: SLF001
            task_id=fresh.id, agent_id=fresh.assigned_agent_id, run_id=None
        )
        run_id = f"taskrun_{fresh.id}_{execution.attempt}"
        running = asyncio.create_task(self._execute(fresh, token, execution.id, run_id))
        self._active[fresh.id] = running

        def _done(_t: asyncio.Task[Any], task_id: str = fresh.id) -> None:
            self._active.pop(task_id, None)
            self._claimed.pop(task_id, None)

        running.add_done_callback(_done)
        return True

    async def _execute(
        self, task: Task, claim_token: str, execution_id: str, run_id: str
    ) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(task.id, claim_token))
        try:
            outcome = await self._run(task, run_id)
        except asyncio.TimeoutError:
            outcome = TaskRunOutcome(
                status="timed_out", run_id=run_id, error_class="TIMEOUT",
                error="This task took too long and was stopped.",
            )
        except asyncio.CancelledError:
            outcome = TaskRunOutcome(
                status="cancelled", run_id=run_id, error_class="CANCELLED",
                error="This task was stopped.",
            )
        except Exception as exc:  # noqa: BLE001 - a task failure is data
            outcome = TaskRunOutcome(
                status="failed", run_id=run_id, error=str(exc), error_class="RUNTIME_ERROR",
            )
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

        live = self._manager._store.get_task(task.id)  # noqa: SLF001
        if live is None or live.status == TaskStatus.CANCELLED:
            self._manager._store.finish_execution(  # noqa: SLF001
                execution_id, status=ExecutionStatus.CANCELLED, error="cancelled",
                error_class="CANCELLED", run_id=outcome.run_id or run_id,
            )
            return
        if live.status != TaskStatus.IN_PROGRESS:
            self._manager._store.finish_execution(  # noqa: SLF001
                execution_id, status=ExecutionStatus.CANCELLED,
                error="task state changed during execution", error_class="STATE_CHANGED",
                run_id=outcome.run_id or run_id,
            )
            return

        if str(outcome.status) == "completed":
            self._on_success(task, execution_id, outcome)
        else:
            self._on_failure(task, execution_id, outcome)

    async def _run(self, task: Task, run_id: str) -> TaskRunOutcome:
        context = build_task_context(
            self._manager, task, constraints={"leaseSeconds": self._lease_seconds}
        )
        if self._executor is None:
            return TaskRunOutcome(
                status="failed", run_id=run_id, error_class="RUNTIME_UNAVAILABLE",
                error="No task executor is configured.",
            )
        raw = await asyncio.wait_for(
            self._executor(task, context, run_id), timeout=self._run_timeout_s
        )
        return _coerce_outcome(raw, run_id)

    async def _heartbeat(self, task_id: str, claim_token: str) -> None:
        interval = max(5.0, self._lease_seconds / 3.0)
        try:
            while True:
                await asyncio.sleep(interval)
                ok = self._manager._store.heartbeat_task(  # noqa: SLF001
                    task_id, claim_token=claim_token, lease_seconds=self._lease_seconds,
                    now=self._now().isoformat(),
                )
                if not ok:
                    return
        except asyncio.CancelledError:
            raise

    # ── Success / failure ────────────────────────────────────────────────────
    def _on_success(
        self, task: Task, execution_id: str, outcome: TaskRunOutcome
    ) -> None:
        for artifact in outcome.artifacts:
            try:
                self._manager.attach_artifact(
                    task.id, uri=str(artifact.get("uri") or artifact.get("path") or ""),
                    kind=str(artifact.get("kind") or "file"), digest=artifact.get("digest"),
                    size_bytes=artifact.get("sizeBytes"), label=artifact.get("label"),
                    execution_id=execution_id, metadata=artifact.get("metadata") or {},
                )
            except Exception:  # noqa: BLE001 - an artifact must not fail the task
                log.warning("failed to attach task artifact", exc_info=True)
        # Mirror the task's artifacts into the Artifact Center so the produced
        # files are cataloged and discoverable, with task/run provenance.
        try:
            from ..artifacts.producers import register_reference_dicts  # noqa: PLC0415

            register_reference_dicts(
                outcome.artifacts, source_tool="task",
                run_id=outcome.run_id, task_id=task.id,
                agent_id=getattr(task, "assigned_agent_id", None),
            )
        except Exception:  # noqa: BLE001 - never fail the task over registration
            log.warning("failed to register task artifacts in the catalog", exc_info=True)
        self._apply_criteria(task, outcome)
        try:
            self._manager.complete_task(
                task.id, output_reference=outcome.run_id or outcome.output[:2000] or None,
            )
        except Exception as exc:  # noqa: BLE001 - a rejected completion is a failure
            self._manager._store.finish_execution(  # noqa: SLF001
                execution_id, status=ExecutionStatus.FAILED, error=str(exc),
                error_class="COMPLETION_REJECTED", run_id=outcome.run_id or None,
                metrics=outcome.metrics,
            )
            self._fail_or_retry(task, error=str(exc), error_class="COMPLETION_REJECTED")
            return
        self._manager._store.finish_execution(  # noqa: SLF001
            execution_id, status=ExecutionStatus.COMPLETED, run_id=outcome.run_id or None,
            metrics=outcome.metrics,
        )

    def _apply_criteria(self, task: Task, outcome: TaskRunOutcome) -> None:
        criteria = self._manager.list_criteria(task.id)
        if not criteria:
            return
        by_id = {c.id: c for c in criteria}
        by_text = {c.text: c for c in criteria}
        applied = False
        for result in outcome.criteria:
            criterion = by_id.get(result.get("id")) or by_text.get(result.get("text"))
            if criterion is None:
                continue
            try:
                self._manager.set_criterion(
                    criterion.id, str(result.get("state") or "PASSED"),
                    evidence=result.get("evidence"),
                )
                applied = True
            except Exception:  # noqa: BLE001
                pass
        # Default: a run that completed satisfies the criteria the task declared,
        # with the run as evidence. This is not "the agent said so" — the RUN must
        # have completed through the real runtime. Configurable off per task.
        if (self._auto_verify_criteria and not applied
                and not (task.metadata or {}).get("criteriaRequireExplicit")):
            for criterion in criteria:
                if criterion.state.value == "PENDING":
                    self._manager.set_criterion(
                        criterion.id, "PASSED", evidence=f"run:{outcome.run_id}"
                    )

    def _on_failure(
        self, task: Task, execution_id: str, outcome: TaskRunOutcome
    ) -> None:
        status = {
            "timed_out": ExecutionStatus.TIMED_OUT,
            "cancelled": ExecutionStatus.CANCELLED,
            "refused": ExecutionStatus.REFUSED,
        }.get(outcome.status, ExecutionStatus.FAILED)
        self._manager._store.finish_execution(  # noqa: SLF001
            execution_id, status=status, error=outcome.error, error_class=outcome.error_class,
            run_id=outcome.run_id or None, metrics=outcome.metrics,
        )
        self._fail_or_retry(task, error=outcome.error, error_class=outcome.error_class)

    def _fail_or_retry(self, task: Task, *, error: str, error_class: str) -> None:
        """Retry a RETRYABLE failure with backoff; otherwise fail the task."""
        live = self._manager._store.get_task(task.id)  # noqa: SLF001
        if live is None or live.status != TaskStatus.IN_PROGRESS:
            return
        if (self._is_retryable(error_class)
                and live.retry_count < min(live.max_retries, MAX_MAX_RETRIES)):
            self._manager.retry_task(task.id, actor_id=self._worker_id)
            delay = self._backoff_seconds(live.retry_count + 1, live.backoff_ms)
            available_at = (self._now() + _dt.timedelta(seconds=delay)).isoformat()
            self._manager._store.update_task_fields(  # noqa: SLF001
                task.id, {"availableAt": available_at, "error": error[:2000],
                          "errorClass": error_class}
            )
            return
        self._manager.fail_task(task.id, error=error, error_class=error_class,
                                actor_id=self._worker_id)

    def _is_retryable(self, error_class: str) -> bool:
        if not error_class or error_class in NON_RETRYABLE_ERRORS:
            return False
        return error_class in RETRYABLE_ERRORS

    def _backoff_seconds(self, attempt: int, base_ms: int) -> float:
        base = max(0.1, base_ms / 1000.0)
        return min(300.0, base * (2 ** max(0, attempt - 1)))

    # ── Lease recovery ───────────────────────────────────────────────────────
    async def recover_expired_leases(self, *, now: Optional[str] = None) -> int:
        """Detect IN_PROGRESS tasks whose lease lapsed and recover them.

        A crashed worker leaves a task IN_PROGRESS with an expired lease. This is
        never left stuck: the stale execution is closed as TIMED_OUT and, per
        policy, the task is retried (with backoff) or failed.
        """
        moment = now or self._now().isoformat()
        expired = self._manager._store.expired_leases(now=moment)
        recovered = 0
        for task in expired:
            for execution in reversed(self._manager.list_executions(task.id)):
                if execution.status == ExecutionStatus.RUNNING:
                    self._manager._store.finish_execution(  # noqa: SLF001
                        execution.id, status=ExecutionStatus.TIMED_OUT,
                        error="worker lease expired", error_class="LEASE_EXPIRED",
                    )
                    break
            self._manager._store.release_claim(task.id)  # noqa: SLF001
            self._manager._emit(  # noqa: SLF001
                "TASK_RECOVERED", task=task,
                data={"reason": "lease_expired", "retryCount": task.retry_count},
            )
            self._fail_or_retry(task, error="worker lease expired", error_class="LEASE_EXPIRED")
            recovered += 1
        return recovered


def _coerce_outcome(raw: Any, run_id: str) -> TaskRunOutcome:
    if isinstance(raw, TaskRunOutcome):
        if not raw.run_id:
            raw.run_id = run_id
        return raw
    if isinstance(raw, dict):
        return TaskRunOutcome(
            status=str(raw.get("status") or "failed"),
            output=str(raw.get("output") or ""),
            error=str(raw.get("error") or ""),
            error_class=str(raw.get("errorClass") or raw.get("error_class") or ""),
            run_id=str(raw.get("runId") or raw.get("run_id") or run_id),
            artifacts=list(raw.get("artifacts") or []),
            criteria=list(raw.get("criteria") or []),
            metrics=dict(raw.get("metrics") or {}),
        )
    return TaskRunOutcome(
        status="failed", run_id=run_id, error_class="RUNTIME_ERROR",
        error="The task returned no result.",
    )


__all__ = [
    "DEFAULT_MAX_IN_FLIGHT",
    "DEFAULT_RUN_TIMEOUT_S",
    "TICK_SECONDS",
    "TaskRunOutcome",
    "TaskScheduler",
]

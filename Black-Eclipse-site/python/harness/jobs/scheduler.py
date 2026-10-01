"""The single-process durable job scheduler (Phase 6 §6.3).

One lifespan task, started alongside `start_mcp()` from `AgenticService`. One tick
at a time; no overlap.

Durability rule: a job that SHOULD have fired while the process was down is
reconciled ONCE at startup against `HarnessJobRun` — never silently skipped. The
job's `on_missed` policy decides what happens and the decision is always recorded
(`missed=1`), so "it didn't run" is never a mystery.

A job run IS a normal run: `_run_job` calls the existing `service.run` /
`service.run_skill`, so permissions, allowlists and policy apply unchanged. The
breaker reuses `mcp/circuit.py` states and thresholds rather than a second backoff
implementation.

Time is injected (`clock`), so tests never sleep: they advance a fake clock and
assert exact decisions.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
from typing import Any, Callable, Optional

from ..mcp.circuit import CLOSED, COOLDOWN_S, FAILURE_THRESHOLD, HALF_OPEN, OPEN
from ..persistence import now_iso
from ..schemas import ModelSettings, RunInput, RunRequest, RunWorkspace
from .cron import CronError, parse_cron
from .delivery import DeliverySummary, default_adapters, deliver_all
from .model import JobDefinition
from .store import JobStore
from .triggers import FileWatcher, resolve_watch_path

log = logging.getLogger("harness.jobs.scheduler")

TICK_SECONDS = 30.0
# At most N job runs in flight — this is a desktop app, not a server.
DEFAULT_MAX_IN_FLIGHT = 2
# Failure statuses that count toward the breaker. Operator/caller behaviours
# (a manual refusal) do not trip it; a refused RUN is a job-level failure.
_FAILURE_STATUSES = frozenset({"failed", "timed_out", "refused"})


def _default_clock() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _default_model_settings() -> ModelSettings:
    """A conservative default model for scheduled runs.

    The front door normally resolves model settings from the vault; a scheduled
    job has no request to carry them, so an env-configured default is used. A
    provider that is not configured fails the run honestly (the runtime reports
    PROVIDER_NOT_CONFIGURED), never silently.
    """
    return ModelSettings(
        provider=os.environ.get("HARNESS_JOB_PROVIDER", "ollama"),
        model=os.environ.get("HARNESS_JOB_MODEL", "llama3.1"),
        base_url=os.environ.get("HARNESS_JOB_BASE_URL") or None,
        api_key=os.environ.get("HARNESS_JOB_API_KEY") or None,
    )


def _message_for(
    job: JobDefinition, status: str, outcome: Optional[dict[str, Any]]
) -> tuple[Optional[str], dict[str, Any]]:
    """A template KEY + parameters for the job's message (§6.1).

    Never a sentence, never a run id, job id, duration in ms or a delivery code.
    The surface renders the key. A count is only included when the run reported
    one; otherwise it is omitted rather than fabricated.
    """
    params: dict[str, Any] = {"jobName": job.name}
    if status != "ok":
        return "jobs.delivery.message.trouble", params
    count = _change_count(outcome)
    if count is not None:
        params["changeCount"] = count
        return "jobs.delivery.message.doneCount", params
    return "jobs.delivery.message.done", params


def _change_count(outcome: Optional[dict[str, Any]]) -> Optional[int]:
    """A real, reported change count from the run, or None — never invented."""
    data = outcome or {}
    for name in ("changeCount", "changedCount", "changes"):
        value = data.get(name)
        if isinstance(value, int) and value >= 0:
            return value
    output = data.get("output")
    if isinstance(output, dict):
        value = output.get("changeCount")
        if isinstance(value, int) and value >= 0:
            return value
    return None


def _parse_iso(value: Optional[str]) -> Optional[_dt.datetime]:
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


class JobScheduler:
    """Durable, single-process scheduler over the ONE agent-memory store."""

    def __init__(
        self,
        service: Any,
        store: JobStore,
        *,
        clock: Optional[Callable[[], _dt.datetime]] = None,
        model_settings_factory: Optional[Callable[[], ModelSettings]] = None,
        max_in_flight: int = DEFAULT_MAX_IN_FLIGHT,
        tick_seconds: float = TICK_SECONDS,
        artifact_root: Any = None,
    ) -> None:
        self._service = service
        self._store = store
        self._clock = clock or _default_clock
        self._model_settings = model_settings_factory or _default_model_settings
        self._max_in_flight = max(1, int(max_in_flight))
        self._tick_seconds = tick_seconds
        self._adapters = default_adapters(getattr(service, "bus", None), artifact_root)
        self._task: Optional[asyncio.Task[Any]] = None
        self._active: dict[str, asyncio.Task[Any]] = {}
        self._watchers: dict[str, FileWatcher] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Start the tick loop (idempotent) and reconcile missed runs ONCE."""
        if self._task is not None and not self._task.done():
            return
        try:
            await self._reconcile_missed()
        except Exception:  # noqa: BLE001 - reconciliation must never block boot
            log.warning("missed-run reconciliation failed", exc_info=True)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the tick loop and cancel in-flight runs cooperatively."""
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        for run in list(self._active.values()):
            run.cancel()
        self._active.clear()

    async def wait_idle(self) -> None:
        """Await all in-flight job runs (graceful shutdown + deterministic tests)."""
        while self._active:
            await asyncio.gather(*list(self._active.values()), return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a tick failure must not kill the loop
                log.warning("job tick failed", exc_info=True)
            await asyncio.sleep(self._tick_seconds)

    def _now(self) -> _dt.datetime:
        moment = self._clock()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=_dt.timezone.utc)
        return moment

    # ── Breaker (state machine mirrors mcp/circuit.py) ───────────────────────
    def _breaker_state(self, job: JobDefinition) -> str:
        if job.consecutive_failures < FAILURE_THRESHOLD:
            return CLOSED
        opened = _parse_iso(job.breaker_opened_at)
        if opened is None:
            return OPEN
        elapsed = (self._now() - opened).total_seconds()
        return HALF_OPEN if elapsed >= COOLDOWN_S else OPEN

    def _breaker_allows(self, job: JobDefinition) -> tuple[bool, Optional[str]]:
        """Whether the breaker lets this job run now, and a plain reason if not."""
        state = self._breaker_state(job)
        if state == CLOSED:
            return True, None
        if state == OPEN:
            return False, (
                f"This job has failed {job.consecutive_failures} times, so it's paused. "
                "An operator can restart it from the job's page."
            )
        # HALF_OPEN: exactly one probe run is allowed.
        return True, None

    def _apply_breaker(self, job: JobDefinition, status: str) -> JobDefinition:
        """Update failure counters + breaker state on the persisted job."""
        if status == "ok":
            failures = 0
            breaker = CLOSED
            opened_at = None
        elif status in _FAILURE_STATUSES:
            failures = job.consecutive_failures + 1
            if failures >= FAILURE_THRESHOLD:
                breaker = OPEN
                opened_at = job.breaker_opened_at or now_iso()
            else:
                breaker = CLOSED
                opened_at = None
        else:  # skipped / running — no counter change
            return job
        # `ran_at` uses the INJECTED clock so a fake-clock test advances the
        # anchor consistently; `updatedAt` inside the store still uses wall time.
        self._store.record_outcome(
            job.id, status=status, ran_at=self._now().isoformat(),
            consecutive_failures=failures, breaker=breaker, breaker_opened_at=opened_at,
        )
        updated = self._store.get_job(job.id)
        return updated or job

    # ── Due computation (pure given a clock) ─────────────────────────────────
    def _anchor(self, job: JobDefinition) -> _dt.datetime:
        return _parse_iso(job.last_run_at) or _parse_iso(job.created_at) or self._now()

    def _next_fire(self, job: JobDefinition) -> Optional[_dt.datetime]:
        anchor = self._anchor(job)
        if job.kind == "cron" and job.cron:
            try:
                return parse_cron(job.cron).next_fire(after=anchor)
            except CronError:
                return None
        if job.kind == "interval" and job.interval_seconds:
            return anchor + _dt.timedelta(seconds=int(job.interval_seconds))
        return None

    def _is_due(self, job: JobDefinition) -> bool:
        if not job.enabled:
            return False
        if job.kind in ("webhook", "manual"):
            return False
        if job.kind == "file_watch":
            return self._file_watch_changed(job)
        nxt = self._next_fire(job)
        return nxt is not None and nxt <= self._now()

    def _file_watch_changed(self, job: JobDefinition) -> bool:
        watcher = self._watchers.get(job.id)
        path = resolve_watch_path(job)
        if path is None:
            return False
        if watcher is None or watcher.path != path:
            watcher = FileWatcher(path=path)
            self._watchers[job.id] = watcher
        return watcher.poll()

    # ── Tick ─────────────────────────────────────────────────────────────────
    async def _tick(self) -> None:
        jobs = self._store.list_jobs(limit=500)
        for job in jobs:
            if not job.enabled:
                continue
            if not self._is_due(job):
                continue
            if self._store.has_running(job.id):
                run = self._store.start_run(
                    job.id, triggered_by="schedule",
                    scheduled_for=self._now().isoformat(), missed=False,
                )
                self._store.finish_run(
                    run["id"], status="skipped",
                    outcome_reason="This job was still running from before, so this round was skipped.",
                )
                self._store.touch_last_run(job.id, ran_at=self._now().isoformat())
                continue
            if len(self._active) >= self._max_in_flight:
                # Bounded: defer to the next tick rather than exceed the cap.
                continue
            await self._launch(job, triggered_by="schedule", scheduled_for=self._now().isoformat())

    # ── Launch / execute ─────────────────────────────────────────────────────
    async def _launch(
        self, job: JobDefinition, *, triggered_by: str, scheduled_for: str, missed: bool = False,
    ) -> Optional[str]:
        allowed, reason = self._breaker_allows(job)
        if not allowed:
            run = self._store.start_run(
                job.id, triggered_by=triggered_by, scheduled_for=scheduled_for, missed=missed,
            )
            self._store.finish_run(run["id"], status="skipped", outcome_reason=reason)
            self._store.touch_last_run(job.id, ran_at=self._now().isoformat())
            return run["id"]
        run = self._store.start_run(
            job.id, triggered_by=triggered_by, scheduled_for=scheduled_for, missed=missed,
            run_id=self._run_id(job), scope_id=job.scope_id,
        )
        task = asyncio.create_task(self._execute(job, run["id"], run["runId"]))
        self._active[run["id"]] = task

        def _done(_t: asyncio.Task[Any], job_run_id: str = run["id"]) -> None:
            self._active.pop(job_run_id, None)

        task.add_done_callback(_done)
        return run["id"]

    def _run_id(self, job: JobDefinition) -> str:
        return f"jobrun_{job.id}_{int(self._now().timestamp())}"

    async def _execute(self, job: JobDefinition, job_run_id: str, run_id: str) -> None:
        started = self._now()
        status = "failed"
        reason: Optional[str] = None
        outcome: dict[str, Any] | None = None
        try:
            result = await asyncio.wait_for(
                self._run_job(job, run_id or job_run_id), timeout=job.max_runtime_s
            )
            status = "ok" if str(result.get("status")) == "completed" else "failed"
            reason = result.get("error")
            outcome = result
        except asyncio.TimeoutError:
            status = "timed_out"
            reason = "This job took too long and was stopped."
        except asyncio.CancelledError:
            status = "failed"
            reason = "This job was stopped."
        except Exception as exc:  # noqa: BLE001 - a job failure is recorded, never raised
            status = "failed"
            reason = str(exc)

        updated = self._apply_breaker(job, status)
        delivery = await self._deliver(updated, run_id or job_run_id, status, outcome)
        self._store.finish_run(
            job_run_id, status=status, outcome_reason=reason,
            run_id=run_id, delivery=delivery,
        )

    async def _run_job(self, job: JobDefinition, run_id: str) -> dict[str, Any]:
        """Run a job through the EXISTING runtime. Never a second execution path."""
        target = job.target
        settings = self._model_settings()
        if target.kind == "skill":
            from ..skills.runtime import SkillExecutionRequest  # noqa: PLC0415

            request = SkillExecutionRequest(
                skillId=target.skill_id or "",
                version=target.skill_version,
                input={"objective": target.objective or job.name},
                runId=run_id,
                executionMode="scheduled",
                modelSettings=settings,
                callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
            )
            result = await self._service.run_skill(request)
            return {
                "status": getattr(result, "status", "failed"),
                "output": getattr(result, "output", None),
                "runId": getattr(result, "runId", run_id) or run_id,
                "error": (getattr(result, "error", None) or {}).get("message")
                if isinstance(getattr(result, "error", None), dict) else None,
            }
        request = RunRequest(
            runId=run_id,
            input=RunInput(query=(target.objective or job.name)[:4000]),
            agentId=target.agent_id,
            modelSettings=settings,
            autonomy=target.autonomy,
            workspace=RunWorkspace(root=target.workspace_root)
            if target.workspace_root else None,
            callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
        )
        result = await self._service.run(request)
        dumped = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        error = dumped.get("error")
        return {
            "status": dumped.get("status", "failed"),
            "output": dumped.get("output"),
            "runId": dumped.get("runId", run_id),
            "error": error.get("message") if isinstance(error, dict) else None,
        }

    async def _deliver(
        self, job: JobDefinition, run_id: str, status: str, outcome: Optional[dict[str, Any]],
    ) -> Optional[list[dict[str, Any]]]:
        """Deliver to EVERY configured target; return one outcome PER TARGET.

        A delivery failure is recorded on the run row and never fails the run.
        The message body is a KEY + params — never composed here.
        """
        answer = (outcome or {}).get("output") or ""
        word = {"ok": "delivered", "failed": "couldn't finish", "timed_out": "stopped early",
                "skipped": "skipped", "refused": "not allowed"}.get(status, status)
        outcome_line = f"Ran at {self._now().strftime('%H:%M')} · {word}"
        message_key, message_params = _message_for(job, status, outcome)
        summary = DeliverySummary(
            title=(job.delivery.title or job.name)[:200],
            answer=str(answer)[:20_000],
            outcome_line=outcome_line,
            status=status,
            run_id=run_id,
            meta={"receipt": (outcome or {}).get("receipt")},
            message_key=message_key,
            message_params=message_params,
        )
        try:
            outcomes = await deliver_all(job, run_id, summary, self._adapters)
            return outcomes or None
        except Exception as exc:  # noqa: BLE001 - delivery never fails the run
            return [{
                "adapter": job.delivery.adapter, "target": job.delivery.destination,
                "ok": False, "reason": str(exc)[:2000], "reasonCode": "DELIVERY_FAILED",
            }]

    # ── Message template (Phase 11) ───────────────────────────────────────────
    # The runtime sends a KEY + parameters, never a composed sentence. The surface
    # resolves the key through src/lib/i18n/. A body names the finance job (and a
    # real count when the run produced one) — never a run id, job id or duration.

    # ── Missed-run reconciliation ────────────────────────────────────────────
    async def _reconcile_missed(self) -> None:
        """Reconcile a window that passed while the process was down, ONCE.

        For each enabled timed job, if its next fire time is already in the past,
        the `on_missed` policy decides: `skip` records a skipped run (missed=1);
        `run_once` launches exactly one run (missed=1). Either way it is recorded.
        """
        now = self._now()
        for job in self._store.list_jobs(limit=500):
            if not job.enabled or job.kind not in ("cron", "interval"):
                continue
            nxt = self._next_fire(job)
            if nxt is None or nxt > now:
                continue
            scheduled_for = nxt.isoformat()
            if job.on_missed == "run_once":
                await self._launch(
                    job, triggered_by="schedule", scheduled_for=scheduled_for, missed=True
                )
            else:
                run = self._store.start_run(
                    job.id, triggered_by="schedule", scheduled_for=scheduled_for, missed=True,
                )
                self._store.finish_run(
                    run["id"], status="skipped",
                    outcome_reason="Eclipse was closed when this was due, so it was skipped.",
                )
                self._store.touch_last_run(job.id, ran_at=now.isoformat())

    # ── Manual / event firing ────────────────────────────────────────────────
    async def fire(
        self, job_id: str, *, triggered_by: str, missed: bool = False,
    ) -> Optional[str]:
        """Fire a job now (manual/webhook). Returns the job-run id, or None."""
        job = self._store.get_job(job_id)
        if job is None or not job.enabled:
            return None
        return await self._launch(
            job, triggered_by=triggered_by, scheduled_for=self._now().isoformat(), missed=missed,
        )

    def reset_breaker(self, job_id: str, *, reset_by: str = "operator") -> Optional[JobDefinition]:
        return self._store.reset_breaker(job_id, reset_by=reset_by)


__all__ = ["DEFAULT_MAX_IN_FLIGHT", "JobScheduler", "TICK_SECONDS"]

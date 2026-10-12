"""Boot wiring for the Task / Plan runtime.

One function, `install_task_layer(service)`, constructs the durable store, the
manager (with a live-bus publisher) and the scheduler that dispatches through the
EXISTING runtime (`service.run`). It registers the LLM-facing tools on the SAME
registry as every other subsystem, so validation, permission and the effect
authorizer apply unchanged.

The executor here is the ONE production execution seam: a task run IS a normal
`service.run` with its own trace, events, tool executions and verification. The
scheduler never runs a model itself.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..persistence import now_iso
from ..schemas import ModelSettings, RunInput, RunRequest

# The recovery wiring is optional: if the recovery package cannot be imported in a
# degraded environment, the task layer must still work. A guarded import means a
# recovery problem degrades to the pre-recovery single-attempt behavior, never to
# a disabled task layer.
try:  # noqa: SIM105 - explicit fallback is clearer than contextlib here
    from ..recovery.execution import TaskRunFailed, run_with_recovery

    _RECOVERY_AVAILABLE = True
except Exception:  # noqa: BLE001
    TaskRunFailed = None  # type: ignore[assignment]
    run_with_recovery = None  # type: ignore[assignment]
    _RECOVERY_AVAILABLE = False
from .context import TaskContext, render_task_query
from .manager import TaskManager
from .model import Plan, Task
from .scheduler import TaskRunOutcome, TaskScheduler
from .store import TaskStore

log = logging.getLogger("harness.tasks.bootstrap")


def _default_model_settings() -> ModelSettings:
    """A conservative default model for a scheduled task run.

    Mirrors the job scheduler: the front door resolves model settings from the
    vault per chat; a scheduled task has no request, so an env-configured default
    is used. A provider that is not configured fails the run honestly.
    """
    return ModelSettings(
        provider=(os.environ.get("HARNESS_TASK_PROVIDER")
                  or os.environ.get("HARNESS_JOB_PROVIDER", "ollama")),
        model=(os.environ.get("HARNESS_TASK_MODEL")
               or os.environ.get("HARNESS_JOB_MODEL", "llama3.1")),
        base_url=(os.environ.get("HARNESS_TASK_BASE_URL")
                  or os.environ.get("HARNESS_JOB_BASE_URL") or None),
        api_key=(os.environ.get("HARNESS_TASK_API_KEY")
                 or os.environ.get("HARNESS_JOB_API_KEY") or None),
    )


def _task_model_settings(manager: TaskManager, task: Task) -> ModelSettings:
    """Resolve model settings for one task run.

    Precedence: the task's own `metadata.modelSettings`, then its PLAN's
    `metadata.modelSettings` (so a whole plan can pin a provider), then the
    env-configured default. A headless run still needs SOME provider; with none
    configured the run fails honestly rather than fabricating an answer.
    """
    override = (task.metadata or {}).get("modelSettings")
    if not (isinstance(override, dict) and override.get("provider") and override.get("model")):
        plan = manager._store.get_plan(task.plan_id) if task.plan_id else None  # noqa: SLF001
        override = (plan.metadata or {}).get("modelSettings") if plan is not None else None
    if isinstance(override, dict) and override.get("provider") and override.get("model"):
        try:
            return ModelSettings(**override)
        except Exception:  # noqa: BLE001 - a bad override falls back to defaults
            log.warning("invalid modelSettings override", exc_info=True)
    return _default_model_settings()


def _plan_agent(manager: TaskManager, task: Task) -> str:
    if task.plan_id:
        plan = manager._store.get_plan(task.plan_id)  # noqa: SLF001
        if isinstance(plan, Plan):
            return plan.agent_id
    return "eclipse-agent"


def _extract_artifacts(result: dict[str, Any], service: Any = None) -> list[dict[str, Any]]:
    """Real artifacts only — never invented.

    A run's produced files are recorded in the Artifact Center tagged with the
    run id (the analysis/code tools register them as they execute). After the run
    completes this links those catalog entries to the task by reference
    (``artifact://<id>`` + checksum), so the task owns a durable, retrievable
    pointer to what it produced. An explicit ``codeVerification.artifacts`` list,
    when present, is also honoured. Best-effort: a catalog lookup failure yields
    no artifacts, never a fabricated one.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(uri: str, kind: str, digest: Any, size: Any, label: Any) -> None:
        if not uri or uri in seen:
            return
        seen.add(uri)
        out.append({
            "uri": str(uri), "kind": str(kind or "file"), "digest": digest,
            "sizeBytes": size, "label": label,
        })

    verification = result.get("codeVerification")
    if isinstance(verification, dict):
        for item in verification.get("artifacts") or []:
            if isinstance(item, dict):
                _add(str(item.get("path") or item.get("uri") or ""),
                     item.get("kind"), item.get("digest"),
                     item.get("sizeBytes") or item.get("size"), item.get("label"))

    artifacts_service = getattr(service, "artifacts", None)
    run_id = str(result.get("runId") or "")
    if artifacts_service is not None and run_id:
        try:
            from ..artifacts.model import ListArtifactsQuery  # noqa: PLC0415

            page = artifacts_service.list(ListArtifactsQuery(run_id=run_id, limit=200))
            for artifact in getattr(page, "artifacts", []) or []:
                category = getattr(artifact.category, "value", None)
                _add(
                    f"artifact://{artifact.id}",
                    (category or "file").lower(),
                    getattr(artifact, "checksum", None),
                    getattr(artifact, "size_bytes", None),
                    getattr(artifact, "name", None),
                )
        except Exception:  # noqa: BLE001 - a catalog miss is not a task failure
            log.debug("artifact catalog lookup failed for run %s", run_id, exc_info=True)
    return out


def _dump(result: Any) -> dict[str, Any]:
    return result.model_dump() if hasattr(result, "model_dump") else dict(result)


def _outcome_from_dump(
    dumped: dict[str, Any], base_run_id: str, service: Any
) -> TaskRunOutcome:
    """Build the honest task-run outcome from a run result dump."""
    status = str(dumped.get("status") or "failed")
    error = dumped.get("error")
    return TaskRunOutcome(
        status="completed" if status == "completed" else status,
        output=str(dumped.get("output") or ""),
        error=(error.get("message") if isinstance(error, dict) else None) or "",
        error_class=(error.get("code") if isinstance(error, dict) else None) or "",
        run_id=str(dumped.get("runId") or base_run_id),
        artifacts=_extract_artifacts(dumped, service),
        metrics={
            "modelSteps": dumped.get("modelSteps", 0),
            "toolCalls": dumped.get("toolCalls", 0),
            "toolErrors": dumped.get("toolErrors", 0),
            "totalTokens": dumped.get("totalTokens", 0),
        },
    )


def _recovery_metrics(recovery: Any) -> dict[str, Any]:
    """The recovery trail attached to a task-run outcome (observability)."""
    if recovery is None:
        return {}
    out: dict[str, Any] = {
        "recoveryAttempts": getattr(recovery, "attempts", None),
        "recoveryIncidentId": getattr(recovery, "incident_id", None),
    }
    stopped = getattr(recovery, "stopped_reason", None)
    if stopped:
        out["recoveryStoppedReason"] = stopped
    decision = getattr(recovery, "decision", None)
    if isinstance(decision, dict):
        out["recoveryStrategy"] = decision.get("strategy")
    return out


def build_task_executor(service: Any, manager: TaskManager):
    """The production executor: dispatch one task through `service.run`.

    The run is driven THROUGH the bounded recovery executor (`recovery.execution`)
    when the recovery engine is installed, so a transient run failure is
    classified, diagnosed and retried with the controller's backoff before the
    scheduler's own retry policy applies, and every failure carries a durable
    incident id. With the engine absent or disabled, the run is attempted once,
    exactly as before — the pre-recovery behavior is preserved.
    """
    recovery_service = getattr(service, "recovery", None)

    async def executor(task: Task, context: TaskContext, run_id: str) -> TaskRunOutcome:
        settings = _task_model_settings(manager, task)
        agent_id = task.assigned_agent_id or _plan_agent(manager, task)

        def build_request(attempt: int, attempt_run_id: str) -> RunRequest:
            return RunRequest(
                runId=attempt_run_id or run_id,
                input=RunInput(
                    query=render_task_query(context)[:4000],
                    context={
                        "source": "task-scheduler", "taskId": task.id,
                        "planId": task.plan_id, "taskTitle": task.title,
                        "taskAttempt": attempt,
                    },
                ),
                agentId=agent_id,
                modelSettings=settings,
                callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
                callbackToken=os.environ.get("HARNESS_CALLBACK_TOKEN") or None,
            )

        # Pre-recovery behavior: one attempt, the run's own outcome reported as-is.
        if not _RECOVERY_AVAILABLE or recovery_service is None:
            dumped = _dump(await service.run(build_request(1, run_id)))
            return _outcome_from_dump(dumped, run_id, service)

        last: dict[str, Any] = {"dumped": {}, "code": "TASK_RUN_FAILED", "message": ""}

        async def run_once(attempt: int, attempt_run_id: str) -> dict[str, Any]:
            dumped = _dump(await service.run(build_request(attempt, attempt_run_id)))
            status = str(dumped.get("status") or "failed")
            if status != "completed":
                error = dumped.get("error")
                code = (error.get("code") if isinstance(error, dict) else None) or "RUN_FAILED"
                message = (error.get("message") if isinstance(error, dict) else None) or ""
                last.update({"dumped": dumped, "code": str(code), "message": str(message)})
                raise TaskRunFailed(str(code), str(message), result=dumped)
            last["dumped"] = dumped
            return dumped

        try:
            recovery = await run_with_recovery(
                recovery_service,
                run_once,
                base_run_id=run_id,
                task_id=task.id,
                details={"taskId": task.id, "planId": task.plan_id, "agentId": agent_id},
            )
        except TaskRunFailed as exc:
            dumped = exc.result if isinstance(exc.result, dict) else {}
            outcome = _outcome_from_dump(dumped, run_id, service)
            outcome.status = "failed"
            outcome.error = exc.message or outcome.error
            outcome.error_class = exc.code or outcome.error_class
            return outcome

        if not recovery.ok:
            outcome = _outcome_from_dump(last["dumped"], run_id, service)
            outcome.status = "failed"
            if last["code"]:
                outcome.error_class = last["code"]
            if last["message"]:
                outcome.error = last["message"]
            outcome.metrics.update(_recovery_metrics(recovery))
            return outcome

        outcome = _outcome_from_dump(recovery.value, run_id, service)
        outcome.metrics.update(_recovery_metrics(recovery))
        return outcome

    return executor


# The task vocabulary maps onto the canonical Event System names (`task.created`,
# `workflow.completed`, …), so the Event Registry and the event console see one
# coherent model rather than `task.task_created`.
_CANONICAL_TASK_EVENTS: dict[str, str] = {
    "TASK_CREATED": "task.created",
    "TASK_UPDATED": "task.updated",
    "TASK_STARTED": "task.started",
    "TASK_VERIFYING": "task.verifying",
    "TASK_ASKING_USER": "task.asking_user",
    "TASK_WAITING": "task.waiting",
    "TASK_BLOCKED": "task.blocked",
    "TASK_UNBLOCKED": "task.unblocked",
    "TASK_ASSIGNED": "task.assigned",
    "TASK_DELEGATED": "task.delegated",
    "TASK_RETRIED": "task.retried",
    "TASK_FAILED": "task.failed",
    "TASK_COMPLETED": "task.completed",
    "TASK_CANCEL_REQUESTED": "task.cancelling",
    "TASK_CANCELLED": "task.cancelled",
    "TASK_DECOMPOSED": "task.decomposed",
    "TASK_DEPENDENCY_ADDED": "task.dependency.added",
    "TASK_DEPENDENCY_REMOVED": "task.dependency.removed",
    "TASK_DEPENDENCY_COMPLETED": "task.dependency.completed",
    "TASK_CHECKPOINT_CREATED": "task.checkpoint.created",
    "TASK_CRITERION_UPDATED": "task.criterion.updated",
    "TASK_PROGRESS_UPDATED": "task.progress.updated",
    "TASK_RECOVERED": "task.recovered",
    "TASK_ESCALATED": "task.escalated",
    "TASK_ARTIFACT_ADDED": "task.artifact.added",
    "TASK_COMPLETION_REJECTED": "task.completion.rejected",
    "TASK_COMPLETION_OVERRIDDEN": "task.completion.overridden",
    "PLAN_CREATED": "workflow.created",
    "PLAN_STATUS_CHANGED": "workflow.status.changed",
    "PLAN_REVISED": "workflow.revised",
}


def canonical_task_event(event_type: str) -> str:
    """Map a `TaskEventType` value to its canonical Event System name."""
    return _CANONICAL_TASK_EVENTS.get(event_type, f"task.{event_type.lower()}")


def _bus_publisher(service: Any):
    """Publish a task event on the process bus for live subscribers.

    The persisted `HarnessTaskEvent` row is the durable record; this is the live
    fan-out to SSE consumers, exactly like every other subsystem's events. The
    type is normalized to the canonical Event System vocabulary and the ids are
    attached so the Event System can correlate it with the task/plan.
    """
    bus = getattr(service, "bus", None)
    if bus is None:
        return None

    def publish(event_type: str, data: dict[str, Any]) -> None:
        raw = dict(data or {})
        event = raw.get("event") if isinstance(raw.get("event"), dict) else {}
        inner = event.get("data") if isinstance(event.get("data"), dict) else {}
        bus.publish({
            "type": canonical_task_event(event_type),
            "at": now_iso(),
            "data": raw,
            "taskId": event.get("taskId") or inner.get("taskId") or event.get("task_id"),
            "workflowId": event.get("planId") or inner.get("planId") or event.get("plan_id"),
        })

    return publish


def install_task_layer(service: Any) -> bool:
    """Construct + register the task runtime on the service. Best-effort."""
    try:
        store = TaskStore(service.store)
        manager = TaskManager(store, publisher=_bus_publisher(service))
        scheduler = TaskScheduler(
            manager, executor=build_task_executor(service, manager),
            max_in_flight=int(os.environ.get("HARNESS_TASK_MAX_IN_FLIGHT", "2")),
            tick_seconds=float(os.environ.get("HARNESS_TASK_TICK_SECONDS", "15")),
            lease_seconds=int(os.environ.get("HARNESS_TASK_LEASE_SECONDS", "600")),
        )
        service.tasks_store = store
        service.tasks = manager
        service.task_scheduler = scheduler
        from .tools import register_task_tools  # noqa: PLC0415

        register_task_tools(service.registry)
        return True
    except Exception:  # noqa: BLE001 - the task layer must never block boot
        log.warning("task layer unavailable", exc_info=True)
        service.tasks_store = None
        service.tasks = None
        service.task_scheduler = None
        return False


__all__ = ["build_task_executor", "install_task_layer"]

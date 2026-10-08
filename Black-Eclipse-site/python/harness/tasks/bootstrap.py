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


def _task_model_settings(service: Any, task: Task) -> ModelSettings:
    override = (task.metadata or {}).get("modelSettings")
    if isinstance(override, dict) and override.get("provider") and override.get("model"):
        try:
            return ModelSettings(**override)
        except Exception:  # noqa: BLE001 - a bad override falls back to defaults
            log.warning("invalid task modelSettings override", exc_info=True)
    return _default_model_settings()


def _plan_agent(manager: TaskManager, task: Task) -> str:
    if task.plan_id:
        plan = manager._store.get_plan(task.plan_id)  # noqa: SLF001
        if isinstance(plan, Plan):
            return plan.agent_id
    return "eclipse-agent"


def _extract_artifacts(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Real artifacts only — from the run's code verification, never invented."""
    out: list[dict[str, Any]] = []
    verification = result.get("codeVerification")
    if isinstance(verification, dict):
        for item in verification.get("artifacts") or []:
            if not isinstance(item, dict):
                continue
            uri = item.get("path") or item.get("uri")
            if not uri:
                continue
            out.append({
                "uri": str(uri), "kind": str(item.get("kind") or "file"),
                "digest": item.get("digest"),
                "sizeBytes": item.get("sizeBytes") or item.get("size"),
                "label": item.get("label"),
            })
    return out


def build_task_executor(service: Any, manager: TaskManager):
    """The production executor: dispatch one task through `service.run`."""

    async def executor(task: Task, context: TaskContext, run_id: str) -> TaskRunOutcome:
        settings = _task_model_settings(service, task)
        agent_id = task.assigned_agent_id or _plan_agent(manager, task)
        request = RunRequest(
            runId=run_id,
            input=RunInput(
                query=render_task_query(context)[:4000],
                context={
                    "source": "task-scheduler", "taskId": task.id,
                    "planId": task.plan_id, "taskTitle": task.title,
                },
            ),
            agentId=agent_id,
            modelSettings=settings,
            callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1"),
            callbackToken=os.environ.get("HARNESS_CALLBACK_TOKEN") or None,
        )
        result = await service.run(request)
        dumped = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        status = str(dumped.get("status") or "failed")
        error = dumped.get("error")
        return TaskRunOutcome(
            status="completed" if status == "completed" else status,
            output=str(dumped.get("output") or ""),
            error=(error.get("message") if isinstance(error, dict) else None) or "",
            error_class=(error.get("code") if isinstance(error, dict) else None) or "",
            run_id=str(dumped.get("runId") or run_id),
            artifacts=_extract_artifacts(dumped),
            metrics={
                "modelSteps": dumped.get("modelSteps", 0),
                "toolCalls": dumped.get("toolCalls", 0),
                "toolErrors": dumped.get("toolErrors", 0),
                "totalTokens": dumped.get("totalTokens", 0),
            },
        )

    return executor


def _bus_publisher(service: Any):
    """Publish a task event on the process bus for live subscribers.

    The persisted `HarnessTaskEvent` row is the durable record; this is the live
    fan-out to SSE consumers, exactly like every other subsystem's events.
    """
    bus = getattr(service, "bus", None)
    if bus is None:
        return None

    def publish(event_type: str, data: dict[str, Any]) -> None:
        bus.publish({"type": f"task.{event_type.lower()}", "at": now_iso(), "data": data})

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

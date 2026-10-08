"""Legacy `/jobs` adapter — one implementation, two API surfaces (§50).

The earlier `HarnessJob` model maps onto the Automation model losslessly for the
fields it had. This module is the ONLY place that translation lives: the legacy
router and the migration both call it. There is no second scheduler and no
duplicated scheduling logic.

  * legacy ``cron``/``interval``/``manual`` map to the same trigger kinds;
  * legacy ``file_watch`` becomes an event trigger on ``file.changed`` filtered
    by path (the engine polls the path and emits that internal event);
  * legacy ``webhook`` becomes a manual-fire automation whose hashed token is
    kept in ``action.config['webhookTokenHash']`` (a webhook can never widen
    authority — it fires the stored definition or nothing);
  * legacy ``skill`` target → ``execute_task`` (skill-bound); ``objective``
    target → ``run_agent``.
"""

from __future__ import annotations

import json
from typing import Any

from ..jobs.model import JobDelivery, JobTarget
from .model import (
    Action,
    AutomationDefinition,
    ConditionSpec,
    ConcurrencyPolicy,
    DeliveryPolicy,
    DeliveryTarget,
    ExecutionPolicy,
    PermissionPolicy,
    ResourceLimits,
    RetryPolicy,
    Trigger,
)

FILE_CHANGED_EVENT = "file.changed"
WEBHOOK_EVENT = "webhook.received"

_RUN_TO_EXECUTION = {
    "running": "running",
    "ok": "completed",
    "failed": "failed",
    "skipped": "skipped",
    "timed_out": "timed_out",
    "refused": "blocked",
}
_EXECUTION_TO_RUN = {
    "triggered": "running",
    "queued": "running",
    "running": "running",
    "waiting": "running",
    "retrying": "running",
    "completed": "ok",
    "failed": "failed",
    "cancelled": "refused",
    "timed_out": "timed_out",
    "blocked": "refused",
    "skipped": "skipped",
}


def _target_dict(row: Any) -> dict[str, Any]:
    raw = row["targetJson"] if "targetJson" in row.keys() else None
    return json.loads(raw) if raw else {}


def _delivery_dict(row: Any) -> dict[str, Any]:
    raw = row["deliveryJson"] if "deliveryJson" in row.keys() else None
    return json.loads(raw) if raw else {}


def job_to_automation(row: Any) -> AutomationDefinition:
    """Convert a `HarnessJob` sqlite row into an `AutomationDefinition`."""
    target = JobTarget(**_target_dict(row))
    delivery = JobDelivery(**_delivery_dict(row))
    kind = row["kind"]
    timezone = row["timezone"] or "UTC"
    on_missed = row["onMissed"] or "skip"

    if kind == "cron":
        trigger = Trigger(type="cron", cron=row["cron"], timezone=timezone)
    elif kind == "interval":
        trigger = Trigger(type="interval", interval_seconds=row["intervalSeconds"], timezone=timezone)
    elif kind == "file_watch":
        trigger = Trigger(
            type="event", event_type=FILE_CHANGED_EVENT,
            event_filter={"path": row["watchPath"]}, timezone=timezone,
        )
    elif kind == "webhook":
        trigger = Trigger(
            type="event", event_type=WEBHOOK_EVENT,
            event_filter={"automationId": row["id"]}, timezone=timezone,
        )
    else:
        trigger = Trigger(type="manual", timezone=timezone)

    action = _action_for(target, kind, token_hash=row["webhookTokenHash"] if "webhookTokenHash" in row.keys() else None)
    delivery_policy = _delivery_for(delivery)

    state = "active" if bool(row["enabled"]) else "disabled"
    return AutomationDefinition(
        id=row["id"],
        name=row["name"],
        description=None,
        version=1,
        state=state,
        trigger=trigger,
        condition=None,
        action=action,
        execution=ExecutionPolicy(
            max_runtime_s=int(row["maxRuntimeS"] or 900),
            misfire="run_once" if on_missed == "run_once" else "skip",
        ),
        retry=RetryPolicy(max_attempts=1),
        concurrency=ConcurrencyPolicy(max_concurrent_runs=1, on_conflict="skip_if_running"),
        limits=ResourceLimits(),
        permissions=PermissionPolicy(),
        delivery=delivery_policy,
        scope_id=row["scopeId"] if "scopeId" in row.keys() else None,
        created_at=row["createdAt"],
        updated_at=row["updatedAt"],
        last_run_at=row["lastRunAt"] if "lastRunAt" in row.keys() else None,
        consecutive_failures=int(row["consecutiveFailures"] or 0),
        breaker=row["breaker"] or "closed",
        breaker_opened_at=row["breakerOpenedAt"],
        breaker_reset_by=row["breakerResetBy"],
    )


def job_definition_to_automation(job: Any, *, token_hash: Optional[str] = None) -> AutomationDefinition:
    """Convert a `jobs.model.JobDefinition` (the model, not a row) to an automation.

    Used by the legacy router's create path (raw + template instantiation) and by
    the migration, so both go through ONE translation.
    """
    target = job.target
    kind = job.kind
    if kind == "cron":
        trigger = Trigger(type="cron", cron=job.cron, timezone=job.timezone or "UTC")
    elif kind == "interval":
        trigger = Trigger(type="interval", interval_seconds=job.interval_seconds, timezone=job.timezone or "UTC")
    elif kind == "file_watch":
        trigger = Trigger(type="event", event_type=FILE_CHANGED_EVENT,
                          event_filter={"path": job.watch_path}, timezone=job.timezone or "UTC")
    elif kind == "webhook":
        trigger = Trigger(type="event", event_type=WEBHOOK_EVENT,
                          event_filter={"automationId": job.id}, timezone=job.timezone or "UTC")
    else:
        trigger = Trigger(type="manual", timezone=job.timezone or "UTC")

    action = _action_for(target, kind, token_hash=token_hash)
    return AutomationDefinition(
        id=job.id,
        name=job.name,
        description=None,
        version=1,
        state="active" if job.enabled else "disabled",
        trigger=trigger,
        condition=None,
        action=action,
        execution=ExecutionPolicy(
            max_runtime_s=job.max_runtime_s,
            misfire="run_once" if job.on_missed == "run_once" else "skip",
        ),
        retry=RetryPolicy(max_attempts=1),
        concurrency=ConcurrencyPolicy(max_concurrent_runs=1, on_conflict="skip_if_running"),
        limits=ResourceLimits(),
        permissions=PermissionPolicy(),
        delivery=_delivery_for(job.delivery),
        scope_id=job.scope_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        last_run_at=job.last_run_at,
        consecutive_failures=job.consecutive_failures,
        breaker=job.breaker,
        breaker_opened_at=job.breaker_opened_at,
        breaker_reset_by=job.breaker_reset_by,
    )


def _action_for(target: JobTarget, kind: str, *, token_hash: Optional[str]) -> Action:
    if target.kind == "skill":
        action = Action(
            type="execute_task", skill_id=target.skill_id, skill_version=target.skill_version,
            objective=target.objective, agent_id=target.agent_id,
            workspace_root=target.workspace_root, autonomy=target.autonomy,
        )
    else:
        action = Action(
            type="run_agent", objective=target.objective, agent_id=target.agent_id,
            workspace_root=target.workspace_root, autonomy=target.autonomy,
        )
    if kind == "webhook":
        action = action.model_copy(update={"config": {"webhookTokenHash": token_hash}})
    return action


def _delivery_for(delivery: JobDelivery) -> DeliveryPolicy:
    return DeliveryPolicy(
        adapter=delivery.adapter,
        title=delivery.title,
        destination=delivery.destination,
        targets=[
            DeliveryTarget(destination=t.destination, adapter=t.adapter)
            for t in delivery.effective_targets()
        ],
    )


def job_run_to_execution(row: Any, automation_id: str) -> dict[str, Any]:
    """Convert a `HarnessJobRun` sqlite row into an execution dict."""
    status = row["status"] or "failed"
    return {
        "id": row["id"],
        "automationId": automation_id,
        "automationVersion": 1,
        "runId": row["runId"],
        "taskId": None,
        "scopeId": row["scopeId"] if "scopeId" in row.keys() else None,
        "triggerType": row["triggeredBy"] or "manual",
        "triggerRef": None,
        "state": _RUN_TO_EXECUTION.get(status, "failed"),
        "attempt": 1,
        "maxAttempts": 1,
        "scheduledFor": row["scheduledFor"],
        "startedAt": row["startedAt"],
        "finishedAt": row["finishedAt"],
        "outcomeReason": row["outcomeReason"],
        "errorClass": None,
        "cost": None,
        "tokens": None,
        "workerId": None,
        "leaseExpiresAt": None,
        "snapshot": None,
        "dryRun": False,
    }


def _legacy_target(definition: AutomationDefinition) -> dict[str, Any]:
    action = definition.action
    if action.skill_id:
        return {
            "kind": "skill", "skillId": action.skill_id, "skillVersion": action.skill_version,
            "objective": action.objective, "agentId": action.agent_id or "eclipse-agent",
            "workspaceRoot": action.workspace_root, "autonomy": action.autonomy,
        }
    return {
        "kind": "objective", "skillId": None, "skillVersion": None,
        "objective": action.objective, "agentId": action.agent_id or "eclipse-agent",
        "workspaceRoot": action.workspace_root, "autonomy": action.autonomy,
    }


def automation_to_job_view(definition: AutomationDefinition, *, last_run: Any = None) -> dict[str, Any]:
    """The legacy JobDefinitionView shape (camelCase), for the legacy front door."""
    trigger = definition.trigger
    if trigger.type == "cron":
        kind, cron, interval, watch = "cron", trigger.cron, None, None
    elif trigger.type == "interval":
        kind, cron, interval, watch = "interval", None, trigger.interval_seconds, None
    elif trigger.type == "event" and trigger.event_type == FILE_CHANGED_EVENT:
        kind, cron, interval, watch = "file_watch", None, None, trigger.event_filter.get("path")
    elif trigger.type == "event" and trigger.event_type == WEBHOOK_EVENT:
        kind, cron, interval, watch = "webhook", None, None, None
    else:
        kind, cron, interval, watch = "manual", None, None, None

    delivery = definition.delivery
    token_hash = definition.action.config.get("webhookTokenHash")
    view = {
        "id": definition.id,
        "name": definition.name,
        "kind": kind,
        "cron": cron,
        "intervalSeconds": interval,
        "watchPath": watch,
        "timezone": trigger.timezone,
        "onMissed": "run_once" if definition.execution.misfire == "run_once" else "skip",
        "target": _legacy_target(definition),
        "delivery": {
            "adapter": delivery.adapter,
            "title": delivery.title,
            "destination": delivery.destination,
            "targets": [{"destination": t.destination, "adapter": t.adapter} for t in delivery.effective_targets()],
        },
        "scopeId": definition.scope_id,
        "enabled": definition.state == "active",
        "maxRuntimeS": definition.execution.max_runtime_s,
        "createdAt": definition.created_at,
        "updatedAt": definition.updated_at,
        "lastRunAt": definition.last_run_at,
        "consecutiveFailures": definition.consecutive_failures,
        "breaker": definition.breaker,
        "breakerOpenedAt": definition.breaker_opened_at,
        "breakerResetBy": definition.breaker_reset_by,
        "webhook": bool(token_hash),
        "lastRun": last_run,
    }
    return view


def execution_to_job_run(execution: dict[str, Any], *, deliveries: Any = None) -> dict[str, Any]:
    """The legacy JobRunView shape for the legacy front door."""
    return {
        "id": execution["id"],
        "jobId": execution["automationId"],
        "runId": execution["runId"],
        "triggeredBy": execution["triggerType"],
        "scheduledFor": execution["scheduledFor"],
        "startedAt": execution["startedAt"],
        "finishedAt": execution["finishedAt"],
        "status": _EXECUTION_TO_RUN.get(execution["state"], "failed"),
        "outcomeReason": execution["outcomeReason"],
        "delivery": (deliveries[0] if deliveries else None),
        "deliveries": deliveries,
        "scopeId": execution["scopeId"],
        "missed": False,
    }


__all__ = [
    "FILE_CHANGED_EVENT",
    "WEBHOOK_EVENT",
    "automation_to_job_view",
    "execution_to_job_run",
    "job_run_to_execution",
    "job_to_automation",
]

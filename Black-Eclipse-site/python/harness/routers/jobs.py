"""Legacy `/jobs` route group — an ADAPTER over the Native Automation Engine (§50).

The route paths and request/response shapes are UNCHANGED so existing clients
keep working. The implementation is no longer a second scheduler: every handler
translates to the Automation service (`automation.legacy`) and back. There is one
definition model, one scheduler, one execution ledger.

EVERY route carries `require_operator` (reads AND mutations), exactly as before.
The single exception is `POST /jobs/{id}/trigger`, which authenticates on the
job's own hashed webhook token.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..automation.legacy import (
    WEBHOOK_EVENT,
    automation_to_job_view,
    execution_to_job_run,
    job_definition_to_automation,
)
from ..automation.model import (
    AutomationDefinition,
    DeliveryPolicy,
    DeliveryTarget,
    ExecutionPolicy,
    Trigger,
)
from ..automation.validation import ERROR, is_valid
from ..deps import require_operator, service
from ..jobs.model import JobDefinition, JobDelivery, JobTarget, KNOWN_ADAPTERS
from ..jobs.store import new_job_id
from ..jobs.templates import get_template, instantiate, list_templates
from ..jobs.triggers import hash_webhook_token, make_webhook_token, verify_webhook_token
from ..persistence import now_iso

router = APIRouter(tags=["jobs"])


def _automation_service():
    return service.automation_service()


class CreateJobRequest(BaseModel):
    """Create a job from a definition or a library template."""

    name: Optional[str] = Field(None, max_length=120)
    kind: Optional[str] = None
    cron: Optional[str] = None
    intervalSeconds: Optional[int] = None  # noqa: N815
    watchPath: Optional[str] = None  # noqa: N815
    timezone: str = "local"
    onMissed: str = "skip"  # noqa: N815
    target: Optional[dict[str, Any]] = None
    delivery: Optional[dict[str, Any]] = None
    maxRuntimeS: int = 900  # noqa: N815
    scopeId: Optional[str] = Field(None, max_length=200)  # noqa: N815
    templateId: Optional[str] = None  # noqa: N815
    params: dict[str, Any] = Field(default_factory=dict)
    enableWebhook: bool = False  # noqa: N815


class UpdateJobRequest(BaseModel):
    """Update a job. ABSENT means PRESERVE; present means replace."""

    name: Optional[str] = None
    kind: Optional[str] = None
    cron: Optional[str] = None
    intervalSeconds: Optional[int] = None  # noqa: N815
    watchPath: Optional[str] = None  # noqa: N815
    timezone: Optional[str] = None
    onMissed: Optional[str] = None  # noqa: N815
    target: Optional[dict[str, Any]] = None
    delivery: Optional[dict[str, Any]] = None
    maxRuntimeS: Optional[int] = None  # noqa: N815
    scopeId: Optional[str] = Field(None, max_length=200)  # noqa: N815
    enabled: Optional[bool] = None


def _validate_or_400(definition: AutomationDefinition) -> None:
    issues = _automation_service().validate(definition)
    if not is_valid(issues):
        first = next(i for i in issues if i.severity == ERROR)
        raise HTTPException(status_code=400, detail=first.message)


def _legacy_job_from_body(body: CreateJobRequest) -> JobDefinition:
    if not body.target:
        raise HTTPException(status_code=400, detail="A job needs a target or a template")
    now = now_iso()
    try:
        return JobDefinition(
            id=new_job_id(),
            name=body.name or "Untitled job",
            kind=body.kind or "manual",  # type: ignore[arg-type]
            cron=body.cron,
            interval_seconds=body.intervalSeconds,
            watch_path=body.watchPath,
            timezone=body.timezone,
            on_missed=body.onMissed,  # type: ignore[arg-type]
            target=body.target,  # type: ignore[arg-type]
            delivery=body.delivery or {},  # type: ignore[arg-type]
            scope_id=body.scopeId,
            max_runtime_s=body.maxRuntimeS,
            created_at=now,
            updated_at=now,
        )
    except Exception as exc:  # noqa: BLE001 - a malformed body is a 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/templates")
def job_templates(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """The finance job library (data only; every template instantiates disabled)."""
    return {"success": True, "templates": list_templates()}


@router.get("/jobs")
def list_jobs(
    scopeId: Optional[str] = None,  # noqa: N803 - the wire name
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """List jobs. `scopeId` is a caller-supplied FILTER (never authorization)."""
    svc = _automation_service()
    jobs = []
    for definition in svc.list(limit=200, scope_id=scopeId):
        last = svc.status(definition.id)
        jobs.append(automation_to_job_view(definition, last_run=last.get("lastExecution") if last else None))
    return {"success": True, "jobs": jobs}


@router.post("/jobs")
def create_job(body: CreateJobRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    token: Optional[str] = None
    token_hash: Optional[str] = None
    if body.templateId:
        template = get_template(body.templateId)
        if template is None:
            raise HTTPException(status_code=404, detail="Unknown job template")
        try:
            job = instantiate(body.templateId, body.params, name=body.name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if body.delivery:
            job = job.model_copy(update={"delivery": job.delivery.model_copy(update=body.delivery)})
        if body.scopeId is not None:
            job = job.model_copy(update={"scope_id": body.scopeId})
    else:
        job = _legacy_job_from_body(body)

    if body.enableWebhook and job.kind == "webhook":
        token, token_hash = make_webhook_token()

    definition = job_definition_to_automation(job, token_hash=token_hash)
    _validate_or_400(definition)
    saved = _automation_service().create_definition(definition, created_by="operator")
    result = automation_to_job_view(saved)
    if token is not None:
        return {"success": True, "job": result, "webhookToken": token}
    return {"success": True, "job": result}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    definition = _automation_service().get(job_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job": automation_to_job_view(definition)}


def _apply_legacy_patch(definition: AutomationDefinition, body: UpdateJobRequest) -> AutomationDefinition:
    present = body.model_dump(exclude_unset=True)
    patch: dict[str, Any] = {"updated_at": now_iso()}
    for camel in ("name", "scopeId"):
        if camel in present:
            patch["scope_id" if camel == "scopeId" else camel] = present[camel]

    trigger = definition.trigger
    if any(k in present for k in ("kind", "cron", "intervalSeconds", "watchPath", "timezone")):
        kind = present.get("kind", _kind_of(trigger))
        timezone = present.get("timezone", trigger.timezone)
        if kind == "cron":
            trigger = Trigger(type="cron", cron=present.get("cron", trigger.cron), timezone=timezone)
        elif kind == "interval":
            trigger = Trigger(type="interval", interval_seconds=present.get("intervalSeconds", trigger.interval_seconds), timezone=timezone)
        elif kind == "file_watch":
            trigger = Trigger(type="event", event_type="file.changed",
                              event_filter={"path": present.get("watchPath", trigger.event_filter.get("path"))},
                              timezone=timezone)
        elif kind == "webhook":
            trigger = Trigger(type="event", event_type=WEBHOOK_EVENT,
                              event_filter={"automationId": definition.id}, timezone=timezone)
        else:
            trigger = Trigger(type="manual", timezone=timezone)
        patch["trigger"] = trigger

    if "target" in present and body.target:
        action = definition.action
        target = JobTarget(**body.target)
        if target.kind == "skill":
            action = action.model_copy(update={
                "type": "execute_task", "skill_id": target.skill_id, "skill_version": target.skill_version,
                "objective": target.objective, "agent_id": target.agent_id,
                "workspace_root": target.workspace_root, "autonomy": target.autonomy,
            })
        else:
            action = action.model_copy(update={
                "type": "run_agent", "objective": target.objective, "agent_id": target.agent_id,
                "workspace_root": target.workspace_root, "autonomy": target.autonomy,
            })
        patch["action"] = action

    if "delivery" in present and body.delivery:
        delivery = JobDelivery(**body.delivery)
        patch["delivery"] = DeliveryPolicy(
            adapter=delivery.adapter, title=delivery.title, destination=delivery.destination,
            targets=[DeliveryTarget(destination=t.destination, adapter=t.adapter) for t in delivery.effective_targets()],
        )

    execution = definition.execution
    if "maxRuntimeS" in present or "onMissed" in present:
        patch["execution"] = execution.model_copy(update={
            "max_runtime_s": present.get("maxRuntimeS", execution.max_runtime_s),
            "misfire": "run_once" if present.get("onMissed", _misfire_name(execution)) == "run_once" else "skip",
        })

    if "enabled" in present:
        patch["state"] = "active" if present["enabled"] else "disabled"

    return definition.model_copy(update=patch)


def _kind_of(trigger: Trigger) -> str:
    if trigger.type == "cron":
        return "cron"
    if trigger.type == "interval":
        return "interval"
    if trigger.type == "event" and trigger.event_type == "file.changed":
        return "file_watch"
    if trigger.type == "event" and trigger.event_type == WEBHOOK_EVENT:
        return "webhook"
    return "manual"


def _misfire_name(execution: ExecutionPolicy) -> str:
    return "run_once" if execution.misfire == "run_once" else "skip"


@router.patch("/jobs/{job_id}")
def update_job(
    job_id: str, body: UpdateJobRequest, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Update; ABSENT means PRESERVE. A present field replaces (never merges)."""
    svc = _automation_service()
    definition = svc.get(job_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Job not found")
    candidate = _apply_legacy_patch(definition, body)
    _validate_or_400(candidate)
    # Use the automation update path (version bump + schedule refresh) by saving
    # the rebuilt definition directly; legacy PATCH semantics are preserve-based.
    candidate = candidate.model_copy(update={"version": definition.version + 1})
    saved = svc._store.save_automation(candidate, created_by="operator")  # noqa: SLF001
    svc._engine.refresh_schedule(saved.id)  # noqa: SLF001
    return {"success": True, "job": automation_to_job_view(svc.get(job_id) or saved)}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not _automation_service().delete(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "deleted": job_id}


@router.post("/jobs/{job_id}/enable")
def enable_job(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        definition = _automation_service().enable(job_id, actor="operator")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "job": automation_to_job_view(definition)}


@router.post("/jobs/{job_id}/disable")
def disable_job(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        definition = _automation_service().disable(job_id, actor="operator")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "job": automation_to_job_view(definition)}


@router.post("/jobs/{job_id}/run")
async def run_job_now(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Fire a job now (manual). The job must be enabled."""
    svc = _automation_service()
    definition = svc.get(job_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if definition.state != "active":
        raise HTTPException(status_code=409, detail="Enable this job before running it")
    execution_id = await svc.run_now(job_id)
    if execution_id is None:
        raise HTTPException(status_code=409, detail="Enable this job before running it")
    return {"success": True, "jobRunId": execution_id}


@router.post("/jobs/{job_id}/reset-breaker")
def reset_job_breaker(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    definition = _automation_service().reset_breaker(job_id, reset_by="operator")
    if definition is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job": automation_to_job_view(definition)}


@router.get("/jobs/{job_id}/runs")
def job_runs(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _automation_service()
    if svc.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    runs = []
    for execution in svc.history(job_id, limit=100):
        deliveries = svc._store.list_deliveries(execution["id"])  # noqa: SLF001
        runs.append(execution_to_job_run(execution, deliveries=deliveries))
    return {"success": True, "runs": runs}


@router.get("/jobs/{job_id}/runs/{run_id}/artifact")
def job_run_artifact(
    job_id: str, run_id: str,
    scopeId: Optional[str] = None,  # noqa: N803 - the wire name
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Read a saved report artifact. The path is DERIVED from the run id."""
    svc = _automation_service()
    execution = svc.get_execution(run_id)
    if execution is None or execution["automationId"] != job_id:
        raise HTTPException(status_code=404, detail="Run not found")
    if scopeId is not None and execution.get("scopeId") != scopeId:
        raise HTTPException(status_code=404, detail="Run not found")
    from ..jobs.delivery import artifact_dir_for  # noqa: PLC0415

    artifact_run_id = execution.get("runId") or run_id
    try:
        directory = artifact_dir_for(artifact_run_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not directory.is_dir():
        raise HTTPException(status_code=404, detail="No saved report for this run")
    files: dict[str, Any] = {}
    for name in ("report.md", "meta.json", "receipt.json"):
        path = directory / name
        if path.is_file():
            if name.endswith(".json"):
                try:
                    files[name] = json.loads(path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    files[name] = None
            else:
                files[name] = path.read_text(encoding="utf-8")
    return {"success": True, "artifact": files}


@router.post("/jobs/{job_id}/trigger")
async def trigger_job(
    job_id: str,
    x_job_token: Optional[str] = Header(None, alias="X-Job-Token"),
) -> dict[str, Any]:
    """Webhook entry. Authenticates on the job's HASHED token, not operator proof."""
    svc = _automation_service()
    definition = svc.get(job_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if definition.trigger.type != "event" or definition.trigger.event_type != WEBHOOK_EVENT:
        raise HTTPException(status_code=400, detail="This job is not a webhook job")
    stored_hash = definition.action.config.get("webhookTokenHash")
    if not stored_hash or not x_job_token or not verify_webhook_token_hash(stored_hash, x_job_token):
        raise HTTPException(status_code=403, detail="Invalid job token")
    if definition.state != "active":
        raise HTTPException(status_code=409, detail="This job is disabled")
    execution_id = await svc.run_now(job_id, trigger_ref="webhook")
    return {"success": True, "jobRunId": execution_id}


def verify_webhook_token_hash(stored_hash: str, token: str) -> bool:
    """Constant-time compare of a presented token against the stored hash."""
    import hmac  # noqa: PLC0415

    return hmac.compare_digest(hash_webhook_token(token), stored_hash)


__all__ = ["router", "KNOWN_ADAPTERS"]

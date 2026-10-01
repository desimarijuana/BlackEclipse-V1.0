"""Harness-owned jobs route group (Phase 6 §6.6).

Registered by `main.py` via `app.include_router(...)`. Shared state comes from
`deps.py` — this module never imports `main`.

EVERY route carries `require_operator` — reads AND mutations — exactly as the MCP
route group was hardened to do (ADR-H48). A directly reachable runtime must not
expose job control to an unauthenticated caller. The single exception is
`POST /jobs/{id}/trigger`, which authenticates on the job's own hashed webhook
token instead (a webhook cannot carry operator proof).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..jobs.guardrails import JobValidationError, validate_job
from ..jobs.model import JobDefinition, KNOWN_ADAPTERS
from ..jobs.store import JobStore, new_job_id
from ..jobs.templates import get_template, instantiate, list_templates
from ..jobs.triggers import make_webhook_token, verify_webhook_token
from ..persistence import now_iso

router = APIRouter(tags=["jobs"])


def _jobs() -> JobStore:
    return service.jobs_store()


def _scheduler():
    return service.jobs


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
    # When set, a library template builds the job; `params` parameterizes it.
    templateId: Optional[str] = None  # noqa: N815
    params: dict[str, Any] = Field(default_factory=dict)
    enableWebhook: bool = False  # noqa: N815


class UpdateJobRequest(BaseModel):
    """Update a job. ABSENT means PRESERVE; present means replace (config rule)."""

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
    enabled: Optional[bool] = None


def _cron_error(job: JobDefinition) -> None:
    """Validate a cron expression at save time (refuse with a specific error)."""
    if job.kind != "cron":
        return
    from ..jobs.cron import CronError, parse_cron  # noqa: PLC0415

    try:
        parse_cron(job.cron or "")
    except CronError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc


def _validate_or_400(job: JobDefinition, *, allow_external: bool = False) -> JobDefinition:
    _cron_error(job)
    try:
        return validate_job(job, skill_registry=service.skill_registry, allow_external=allow_external)
    except JobValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc


@router.get("/jobs/templates")
def job_templates(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """The finance job library (data only; every template instantiates disabled)."""
    return {"success": True, "templates": list_templates()}


@router.get("/jobs")
def list_jobs(_: bool = Depends(require_operator)) -> dict[str, Any]:
    store = _jobs()
    jobs = []
    for job in store.list_jobs(limit=200):
        item = job.public()
        last = store.last_run(job.id)
        item["lastRun"] = last
        jobs.append(item)
    return {"success": True, "jobs": jobs}


@router.post("/jobs")
def create_job(body: CreateJobRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = _jobs()
    token: Optional[str] = None
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
    else:
        if not body.target:
            raise HTTPException(status_code=400, detail="A job needs a target or a template")
        now = now_iso()
        try:
            job = JobDefinition(
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
                max_runtime_s=body.maxRuntimeS,
                created_at=now,
                updated_at=now,
            )
        except Exception as exc:  # noqa: BLE001 - a malformed body is a 400
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.enableWebhook and job.kind == "webhook":
        token, token_hash = make_webhook_token()
        job = job.model_copy(update={"webhook_token_hash": token_hash})

    job = _validate_or_400(job)
    store.save_job(job)
    result = job.public()
    if token is not None:
        # Shown ONCE at the TOP level; only the hash is stored from here on, and
        # the job view itself never carries the token or its hash.
        return {"success": True, "job": result, "webhookToken": token}
    return {"success": True, "job": result}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    job = _jobs().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job": job.public()}


@router.patch("/jobs/{job_id}")
def update_job(
    job_id: str, body: UpdateJobRequest, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Update; ABSENT means PRESERVE. A present field replaces (never merges)."""
    store = _jobs()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    patch: dict[str, Any] = {"updated_at": now_iso()}
    present = body.model_dump(exclude_unset=True)
    mapping = {
        "name": "name", "kind": "kind", "cron": "cron", "intervalSeconds": "interval_seconds",
        "watchPath": "watch_path", "timezone": "timezone", "onMissed": "on_missed",
        "maxRuntimeS": "max_runtime_s", "enabled": "enabled",
    }
    for camel, field in mapping.items():
        if camel in present:
            patch[field] = present[camel]
    if "target" in present:
        from ..jobs.model import JobTarget  # noqa: PLC0415

        patch["target"] = JobTarget(**body.target) if body.target else job.target
    if "delivery" in present:
        from ..jobs.model import JobDelivery  # noqa: PLC0415

        patch["delivery"] = JobDelivery(**(body.delivery or {}))
    updated = job.model_copy(update=patch)
    updated = _validate_or_400(updated)
    store.save_job(updated)
    return {"success": True, "job": updated.public()}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    removed = _jobs().delete_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "deleted": job_id}


@router.post("/jobs/{job_id}/enable")
def enable_job(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    job = _jobs().set_enabled(job_id, True)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job": job.public()}


@router.post("/jobs/{job_id}/disable")
def disable_job(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    job = _jobs().set_enabled(job_id, False)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job": job.public()}


@router.post("/jobs/{job_id}/run")
async def run_job_now(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Fire a job now (manual). The job must be enabled."""
    scheduler = _scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="The job runner is not available")
    if _jobs().get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job_run_id = await scheduler.fire(job_id, triggered_by="manual")
    if job_run_id is None:
        raise HTTPException(status_code=409, detail="Enable this job before running it")
    return {"success": True, "jobRunId": job_run_id}


@router.post("/jobs/{job_id}/reset-breaker")
def reset_job_breaker(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    scheduler = _scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="The job runner is not available")
    job = scheduler.reset_breaker(job_id, reset_by="operator")
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job": job.public()}


@router.get("/jobs/{job_id}/runs")
def job_runs(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = _jobs()
    if store.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "runs": store.list_runs(job_id, limit=100)}


@router.post("/jobs/{job_id}/trigger")
async def trigger_job(
    job_id: str,
    x_job_token: Optional[str] = Header(None, alias="X-Job-Token"),
) -> dict[str, Any]:
    """Webhook entry. Authenticates on the job's HASHED token, not operator proof.

    The body is ignored entirely: a webhook can never select a skill, raise a
    budget, or widen a permission. It fires the stored definition or nothing.
    """
    job = _jobs().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.kind != "webhook":
        raise HTTPException(status_code=400, detail="This job is not a webhook job")
    if not verify_webhook_token(job, x_job_token):
        raise HTTPException(status_code=403, detail="Invalid job token")
    scheduler = _scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="The job runner is not available")
    if not job.enabled:
        raise HTTPException(status_code=409, detail="This job is disabled")
    job_run_id = await scheduler.fire(job_id, triggered_by="webhook")
    return {"success": True, "jobRunId": job_run_id}


__all__ = ["router", "KNOWN_ADAPTERS"]

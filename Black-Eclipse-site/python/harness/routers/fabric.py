"""Execution Fabric HTTP routes — the operator/UI surface over the fabric.

Every route is `require_operator` (transport/token), exactly like the terminal,
code, execution and orchestration routers. The routes are thin adapters over the
SAME `ExecutionManager` the agent tools use, so the UI and the agent can never
disagree about what is running.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["fabric"])


class SubmitBody(BaseModel):
    type: str = Field(default="tool")
    mode: Optional[str] = None
    queue: Optional[str] = None
    priority: Optional[str] = None
    tool: Optional[str] = None
    args: Optional[dict[str, Any]] = None
    query: Optional[str] = None
    objective: Optional[str] = None
    agentId: Optional[str] = None  # noqa: N815
    automationId: Optional[str] = None  # noqa: N815
    sessionId: Optional[str] = None  # noqa: N815
    taskId: Optional[str] = None  # noqa: N815
    userId: Optional[str] = None  # noqa: N815
    idempotencyKey: Optional[str] = None  # noqa: N815
    parentJobId: Optional[str] = None  # noqa: N815
    input: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None


def _fabric():
    manager = getattr(service, "fabric", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="the execution fabric is unavailable")
    return manager


@router.get("/fabric/status")
def fabric_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_fabric().health()}


@router.get("/fabric/health")
def fabric_health(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_fabric().health()}


@router.get("/fabric/queues")
def fabric_queues(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "queues": _fabric().stats()["queues"]}


@router.get("/fabric/metrics")
def fabric_metrics(_: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _fabric()
    return {"success": True, "metrics": manager.metrics.snapshot(), "stats": manager.stats()}


@router.get("/fabric/workers")
def fabric_workers(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_fabric().worker_manager.status()}


@router.get("/fabric/jobs")
def fabric_jobs(
    queue: Optional[str] = None, status: Optional[str] = None, type: Optional[str] = None,
    parentJobId: Optional[str] = None, limit: int = 100, offset: int = 0,  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    jobs = _fabric().list_jobs(
        queue=queue, status=status, type=type, parent_job_id=parentJobId,
        limit=limit, offset=offset,
    )
    return {"success": True, "jobs": jobs}


@router.post("/fabric/jobs")
async def fabric_submit(body: SubmitBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    payload: dict[str, Any] = dict(body.input or {})
    for key in ("tool", "args", "query", "objective", "agentId", "automationId"):
        value = getattr(body, key)
        if value is not None:
            payload[key] = value
    result = await _fabric().submit(
        body.type, payload, mode=body.mode, queue=body.queue, priority=body.priority,
        agent_id=body.agentId, task_id=body.taskId, session_id=body.sessionId,
        user_id=body.userId, parent_job_id=body.parentJobId,
        idempotency_key=body.idempotencyKey, metadata=body.metadata,
    )
    return {"success": True, **result}


@router.get("/fabric/jobs/{job_id}")
def fabric_job(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _fabric()
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="no such job")
    return {"success": True, "job": job, "events": manager.events(job_id, limit=200),
            "attempts": manager.attempts(job_id)}


@router.get("/fabric/jobs/{job_id}/events")
def fabric_job_events(job_id: str, limit: int = 500,
                      _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _fabric()
    if manager.get(job_id) is None:
        raise HTTPException(status_code=404, detail="no such job")
    return {"success": True, "events": manager.events(job_id, limit=limit)}


@router.get("/fabric/jobs/{job_id}/attempts")
def fabric_job_attempts(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _fabric()
    if manager.get(job_id) is None:
        raise HTTPException(status_code=404, detail="no such job")
    return {"success": True, "attempts": manager.attempts(job_id)}


@router.get("/fabric/jobs/{job_id}/children")
def fabric_job_children(job_id: str, limit: int = 100,
                        _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "jobs": _fabric().children(job_id, limit=limit)}


@router.post("/fabric/jobs/{job_id}/cancel")
async def fabric_cancel(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **await _fabric().cancel(job_id)}


@router.post("/fabric/jobs/{job_id}/retry")
async def fabric_retry(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = await _fabric().retry(job_id)
    if not result.get("retried") and result.get("reason") == "unknown job":
        raise HTTPException(status_code=404, detail="no such job")
    return {"success": True, **result}


@router.get("/fabric/dlq")
def fabric_dlq(limit: int = 100, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "deadLetters": _fabric().dlq(limit=limit)}


@router.post("/fabric/dlq/{job_id}/replay")
async def fabric_dlq_replay(job_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = await _fabric().retry(job_id)
    if not result.get("retried") and result.get("reason") == "unknown job":
        raise HTTPException(status_code=404, detail="no such job")
    return {"success": True, **result}


__all__ = ["router"]

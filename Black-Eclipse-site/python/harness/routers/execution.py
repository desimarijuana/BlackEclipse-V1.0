"""Execution HTTP routes — the UI/debugging surface over the shared service.

Every route is `require_operator` (transport/token), exactly like the terminal and
code routers. Reads are operator-gated too: the execution surface is powerful, so
even enumerating past executions is not anonymous.

The routes are thin adapters over `harness.deps.service.execution` — the SAME
service the agent tools use, so UI and agent can never disagree.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["execution"])


class RunRequest(BaseModel):
    language: str = Field(min_length=1, max_length=32)
    code: Optional[str] = Field(default=None, max_length=200_000)
    entrypoint: Optional[str] = Field(default=None, max_length=1_000)
    args: list[str] = Field(default_factory=list, max_length=64)
    cwd: str = Field(default="", max_length=1_000)
    mode: str = Field(default="RUN", max_length=32)
    timeoutMs: Optional[int] = Field(default=None, ge=100, le=900_000)  # noqa: N815


class ServiceStartRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4_000)
    cwd: str = Field(default="", max_length=1_000)
    port: int = Field(default=0, ge=0, le=65_535)
    protocol: str = Field(default="http", max_length=16)
    healthUrl: str = Field(default="", max_length=2_000)  # noqa: N815
    waitReady: bool = True  # noqa: N815


def _execution():
    layer = getattr(service, "execution", None)
    if layer is None:
        raise HTTPException(status_code=503, detail="the execution layer is unavailable")
    return layer


@router.get("/execution/status")
def execution_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_execution().describe()}


@router.get("/execution/list")
def list_executions(runId: Optional[str] = None, limit: int = 100, _: bool = Depends(require_operator)) -> dict[str, Any]:  # noqa: N803
    return {"success": True, "executions": _execution().list_executions(run_id=runId, limit=limit),
            "active": _execution().list_active()}


@router.post("/execution/run")
async def run_execution(body: RunRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    from ..execution.models import ExecutionMode
    from ..execution.service import build_request, make_actor
    from ..tools import ToolContext

    layer = _execution()
    from ..code.workspace import resolve_workspace

    ctx = ToolContext(run_id="", log=lambda *_: None, autonomy="edit_verify")
    ctx.workspace = resolve_workspace(None)
    if getattr(ctx, "workspace", None) is None:
        raise HTTPException(status_code=503, detail="no workspace root is selected")
    try:
        mode = ExecutionMode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unknown mode {body.mode!r}") from exc
    request = build_request(
        ctx, language=body.language, code=body.code or "", entrypoint=body.entrypoint or "",
        args=body.args, cwd=body.cwd, mode=mode.value, timeout_ms=body.timeoutMs,
    )
    result = layer.run(request, actor=make_actor(ctx))
    return {"success": True, "result": result.to_dict()}


@router.get("/execution/{execution_id}")
def get_execution(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    record = _execution().get_execution(execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no such execution")
    return {"success": True, "execution": record}


@router.get("/execution/{execution_id}/logs")
def get_execution_logs(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _execution().get_execution_logs(execution_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such execution")
    return {"success": True, **data}


@router.get("/execution/{execution_id}/artifacts")
def get_execution_artifacts(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _execution().get_execution_artifacts(execution_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such execution")
    return {"success": True, **data}


@router.post("/execution/{execution_id}/cancel")
def cancel_execution(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not _execution().cancel_execution(execution_id):
        raise HTTPException(status_code=404, detail="no running execution with that id")
    return {"success": True, "executionId": execution_id}


# ── services ────────────────────────────────────────────────────────────────


@router.get("/execution/services/list")
def list_services(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "services": _execution().list_services()}


@router.post("/execution/services")
def start_service(body: ServiceStartRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _execution().start_service(
        command=body.command, cwd=body.cwd, port=body.port, protocol=body.protocol,
        health_url=body.healthUrl, wait_ready=body.waitReady,
    )
    if data.get("status") != "ok":
        raise HTTPException(status_code=400, detail=data)
    return {"success": True, **data}


@router.post("/execution/services/{service_id}/stop")
def stop_service(service_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _execution().stop_service(service_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such service")
    return {"success": True, **data}


@router.post("/execution/services/{service_id}/restart")
def restart_service(service_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _execution().restart_service(service_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such service")
    return {"success": True, **data}


@router.get("/execution/services/{service_id}")
def get_service_status(service_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _execution().get_service_status(service_id)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such service")
    return {"success": True, **data}


@router.get("/execution/services/{service_id}/logs")
def get_service_logs(service_id: str, tail: int = 200, _: bool = Depends(require_operator)) -> dict[str, Any]:
    data = _execution().get_service_logs(service_id, tail=tail)
    if data.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="no such service")
    return {"success": True, **data}


__all__ = ["router"]

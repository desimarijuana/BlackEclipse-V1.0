"""Native Automation Engine route group (§40).

The first-class tool API over the Automation service. EVERY route carries
`require_operator` — reads AND mutations — so a directly reachable runtime never
exposes automation control to an unauthenticated caller.

This is the surface the agent tools, the TS front door and the UI all use. The
legacy `/jobs` routes are a thin adapter over the SAME service (ADR-H114).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from ..automation.service import AutomationError
from ..deps import require_operator, service

router = APIRouter(tags=["automations"])


def _svc():
    return service.automation_service()


def _domain_error(exc: AutomationError) -> HTTPException:
    status = 404 if exc.code == "NOT_FOUND" else 400
    return HTTPException(status_code=status, detail=exc.message)


@router.get("/automations/metrics")
def automation_metrics(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "metrics": _svc().metrics()}


@router.get("/automations")
def list_automations(
    scopeId: Optional[str] = None,  # noqa: N803 - the wire name
    state: Optional[str] = None,
    limit: int = 200,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    definitions = _svc().list(limit=limit, scope_id=scopeId, state=state)
    return {"success": True, "automations": [d.public() for d in definitions]}


@router.post("/automations")
def create_automation(body: dict[str, Any] = Body(...), _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        definition = _svc().create(body, created_by="operator")
    except AutomationError as exc:
        raise _domain_error(exc) from exc
    return {"success": True, "automation": definition.public()}


@router.get("/automations/monitors")
def list_monitors(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """The closed catalogue of proactive portfolio monitors."""
    return {"success": True, "monitors": _svc().list_monitors()}


@router.post("/automations/monitors")
def create_monitor(body: dict[str, Any] = Body(...), _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Arm a monitor from the catalogue; it is saved OFF until the operator enables it."""
    monitor_id = body.get("monitorId") or body.get("monitor")
    try:
        definition = _svc().create_monitor(
            monitor_id, body.get("params") or {}, name=body.get("name"),
            objective=body.get("objective"), created_by="operator",
        )
    except AutomationError as exc:
        raise _domain_error(exc) from exc
    return {"success": True, "automation": definition.public()}


@router.get("/automations/statuses")
def automation_statuses(ids: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Latest run per automation in one response (the Bots sidebar's needs).

    Declared before `/{automation_id}` so it is not read as an id.
    """
    wanted = [part for part in (ids or "").split(",") if part] or None
    return {"success": True, "statuses": _svc().statuses(ids=wanted)}


@router.get("/automations/{automation_id}")
def get_automation(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    definition = _svc().get(automation_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"success": True, "automation": definition.public()}


@router.patch("/automations/{automation_id}")
def update_automation(
    automation_id: str, body: dict[str, Any] = Body(...), _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        definition = _svc().update(automation_id, body, updated_by="operator")
    except AutomationError as exc:
        raise _domain_error(exc) from exc
    return {"success": True, "automation": definition.public()}


@router.delete("/automations/{automation_id}")
def delete_automation(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not _svc().delete(automation_id):
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"success": True, "deleted": automation_id}


@router.post("/automations/{automation_id}/validate")
def validate_automation(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    definition = _svc().get(automation_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    issues = _svc().validate(definition)
    return {"success": True, "valid": not any(i.severity == "error" for i in issues),
            "issues": [i.to_dict() for i in issues]}


@router.post("/automations/{automation_id}/test")
async def test_automation(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = await _svc().test(automation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"success": True, **result}


@router.post("/automations/{automation_id}/dry-run")
async def dry_run_automation(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = await _svc().dry_run(automation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"success": True, "dryRun": result}


@router.post("/automations/{automation_id}/enable")
def enable_automation(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _lifecycle(automation_id, "enable")


@router.post("/automations/{automation_id}/disable")
def disable_automation(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _lifecycle(automation_id, "disable")


@router.post("/automations/{automation_id}/pause")
def pause_automation(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _lifecycle(automation_id, "pause")


@router.post("/automations/{automation_id}/resume")
def resume_automation(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _lifecycle(automation_id, "resume")


@router.post("/automations/{automation_id}/archive")
def archive_automation(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return _lifecycle(automation_id, "archive")


def _lifecycle(automation_id: str, action: str) -> dict[str, Any]:
    svc = _svc()
    try:
        definition = getattr(svc, action)(automation_id, actor="operator")
    except AutomationError as exc:
        raise _domain_error(exc) from exc
    return {"success": True, "automation": definition.public()}


@router.post("/automations/{automation_id}/run")
async def run_automation_now(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    svc = _svc()
    definition = svc.get(automation_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    if definition.state != "active":
        raise HTTPException(status_code=409, detail="Enable this automation before running it")
    execution_id = await svc.run_now(automation_id)
    if execution_id is None:
        raise HTTPException(status_code=409, detail="Enable this automation before running it")
    return {"success": True, "executionId": execution_id}


@router.post("/automations/{automation_id}/reset-breaker")
def reset_automation_breaker(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    definition = _svc().reset_breaker(automation_id, reset_by="operator")
    if definition is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"success": True, "automation": definition.public()}


@router.get("/automations/{automation_id}/status")
def automation_status(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = _svc().status(automation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"success": True, "status": result}


@router.get("/automations/{automation_id}/history")
def automation_history(
    automation_id: str, limit: int = 100, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    if _svc().get(automation_id) is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"success": True, "executions": _svc().history(automation_id, limit=limit)}


@router.get("/automations/{automation_id}/versions")
def automation_versions(automation_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if _svc().get(automation_id) is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"success": True, "versions": _svc().versions(automation_id)}


@router.get("/automations/{automation_id}/versions/{version}")
def automation_version(automation_id: str, version: int, _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = _svc().version(automation_id, version)
    if result is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"success": True, "version": result}


@router.get("/automations/executions/{execution_id}")
def get_execution(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    execution = _svc().get_execution(execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return {"success": True, "execution": execution}


@router.get("/automations/executions/{execution_id}/timeline")
def execution_timeline(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if _svc().get_execution(execution_id) is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return {"success": True, "timeline": _svc().timeline(execution_id)}


@router.post("/automations/executions/{execution_id}/cancel")
def cancel_execution(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not _svc().cancel_execution(execution_id):
        raise HTTPException(status_code=409, detail="This execution is not running")
    return {"success": True, "cancelled": execution_id}


@router.post("/automations/executions/{execution_id}/resume")
async def resume_execution(execution_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    if not await _svc().resume_execution(execution_id):
        raise HTTPException(status_code=409, detail="This execution is not waiting for approval")
    return {"success": True, "resumed": execution_id}


__all__ = ["router"]

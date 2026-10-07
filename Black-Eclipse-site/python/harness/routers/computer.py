"""Computer Use HTTP routes — the operator/UI surface over the shared manager.

Every route is `require_operator` (transport/token), exactly like the terminal,
code, browser and workspace routers. The routes are thin adapters over
`harness.deps.service.computer` — the SAME manager the agent tools use, so the UI
and the agent can never disagree about desktop state.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["computer"])


def _manager():
    manager = getattr(service, "computer", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="the Computer Use capability is unavailable")
    return manager


@router.get("/computer/capabilities")
def computer_capabilities(_: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = getattr(service, "computer", None)
    if manager is None:
        return {"success": True, "available": False}
    return {"success": True, "available": True, **manager.capabilities()}


@router.get("/computer/doctor")
def computer_doctor(_: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = getattr(service, "computer", None)
    if manager is None:
        return {"success": True, "available": False}
    return {"success": True, **manager.doctor()}


@router.get("/computer/status")
def computer_status(_: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = getattr(service, "computer", None)
    if manager is None:
        return {"success": True, "available": False}
    return {"success": True, **manager.health(), "metrics": manager.telemetry.snapshot()}


@router.get("/computer/windows")
def computer_windows(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "windows": [w.to_dict() for w in _manager().driver.list_windows()]}


@router.get("/computer/applications")
def computer_applications(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "applications": [a.to_dict() for a in _manager().driver.list_applications()]}


@router.get("/computer/displays")
def computer_displays(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "displays": [d.to_dict() for d in _manager().driver.list_displays()]}


@router.get("/computer/sessions")
def computer_sessions(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "sessions": _manager().list_sessions()}


class StartSessionRequest(BaseModel):
    risk_mode: Optional[str] = Field(default=None, max_length=32)


@router.post("/computer/sessions")
async def computer_session_start(body: StartSessionRequest, _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _manager()
    from ..computer.errors import ComputerError  # noqa: PLC0415

    try:
        session = await manager.create_session(risk_mode=body.risk_mode)
    except ComputerError as exc:
        raise HTTPException(status_code=503, detail=exc.to_dict()) from exc
    return {"success": True, "session": session.snapshot_summary()}


@router.delete("/computer/sessions/{session_id}")
async def computer_session_close(session_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    result = await _manager().destroy_session(session_id)
    if not result.get("destroyed"):
        raise HTTPException(status_code=404, detail="no such desktop session")
    return {"success": True, **result}


@router.post("/computer/sessions/{session_id}/takeover")
def computer_takeover(session_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_manager().takeover.take_control(session_id)}


@router.post("/computer/sessions/{session_id}/pause")
def computer_pause(session_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_manager().takeover.pause(session_id)}


@router.post("/computer/sessions/{session_id}/resume")
def computer_resume(session_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_manager().takeover.resume(session_id)}


@router.post("/computer/sessions/{session_id}/release")
def computer_release(session_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, **_manager().takeover.release(session_id)}


@router.get("/computer/actions")
def computer_actions(session_id: Optional[str] = None, limit: int = 100, _: bool = Depends(require_operator)) -> dict[str, Any]:
    manager = _manager()
    if manager.store is None:
        return {"success": True, "actions": []}
    return {"success": True, "actions": manager.store.list_actions(session_id, limit)}


__all__ = ["router"]

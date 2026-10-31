"""Operator-authored agent presets (Graph Studio Phase 1).

The store lives on `agent-memory.db` and is owned by the runtime. The front door
is a thin proxy; no preset is executed here.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..agent_presets import get_preset_store
from ..deps import require_operator

router = APIRouter(prefix="/agents", tags=["agents"])


def _store():
    store = get_preset_store()
    if store is None:
        raise HTTPException(status_code=503, detail="the agent preset store is unavailable")
    return store


@router.get("/presets")
def list_presets(
    includeArchived: bool = Query(default=False),  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    return {"presets": _store().list(include_archived=includeArchived)}


@router.post("/presets", status_code=201)
def create_preset(
    body: dict[str, Any], _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        return {"preset": _store().create(body)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/presets/{preset_id}")
def get_preset(
    preset_id: str,
    version: Optional[int] = Query(default=None),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    preset = _store().get(preset_id, version)
    if preset is None:
        raise HTTPException(status_code=404, detail="agent preset not found")
    return {"preset": preset}


@router.patch("/presets/{preset_id}")
def update_preset(
    preset_id: str,
    body: dict[str, Any],
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        preset = _store().update(preset_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if preset is None:
        raise HTTPException(status_code=404, detail="agent preset not found")
    return {"preset": preset}


@router.delete("/presets/{preset_id}")
def archive_preset(
    preset_id: str, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    if not _store().archive(preset_id):
        raise HTTPException(status_code=404, detail="agent preset not found")
    return {"archived": True, "id": preset_id}


@router.get("/presets/{preset_id}/versions")
def list_versions(
    preset_id: str, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    return {"versions": _store().versions(preset_id)}


@router.get("/tools")
def tool_catalog(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"tools": _store().catalog()}


@router.get("/builtins")
def built_in_agents(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Every code/seed-resolved agent the runtime can name (not custom presets)."""
    from ..agents import AGENT_PRESETS  # noqa: PLC0415

    return {
        "agents": [
            {"id": agent.id, "name": agent.name}
            for agent in sorted(AGENT_PRESETS.values(), key=lambda item: item.id)
        ]
    }


__all__ = ["router"]

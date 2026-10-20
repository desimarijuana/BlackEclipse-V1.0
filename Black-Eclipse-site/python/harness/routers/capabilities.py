"""Generated-capability routes for the Capability Studio.

Reads expose the durable records the builder wrote; mutations are the
operator's own activation / deactivation / rollback / retire actions. The agent
never reaches these routes: its activation rule is enforced in
`capabilities/builder.py`, and every mutation here requires the operator
transport token.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..capabilities import builder
from ..capabilities.resume import resume_original_task
from ..capabilities.store import CapabilityStore
from ..deps import require_operator, service

router = APIRouter(tags=["capabilities"])


def _store() -> CapabilityStore:
    return CapabilityStore(getattr(service, "store", None))


def _root() -> Optional[Path]:
    try:
        from ..code.workspace import default_root

        return default_root()
    except Exception:
        return None


def _usage(store: CapabilityStore, capability_id: str, version: str) -> dict[str, Any]:
    entries = store.usage(capability_id, version, limit=50)
    ok = sum(1 for entry in entries if entry.get("status") == "ok")
    failed = sum(1 for entry in entries if entry.get("status") == "failed")
    return {
        "total": len(entries),
        "ok": ok,
        "failed": failed,
        "lastStatus": entries[0].get("status") if entries else None,
        "lastUsedAt": entries[0].get("createdAt") if entries else None,
    }


@router.get("/capabilities")
def list_capabilities(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    store = _store()
    records = store.records(status=status, limit=limit)
    for record in records:
        record["usage"] = _usage(
            store,
            str(record.get("capabilityId") or ""),
            str(record.get("version") or ""),
        )
    return {"capabilities": records, "count": len(records)}


@router.get("/capabilities/builtins")
def list_builtins() -> dict[str, Any]:
    """The read-only recipe catalogue Eclipse ships with.

    Declared BEFORE `/{capability_id}` so "builtins" is never read as an id.
    Dynamic (generated) recipes are returned by `/capabilities`, not here.
    """
    from ..code.recipes import RECIPES

    items = [
        {
            "id": recipe.name,
            "name": recipe.name,
            "title": recipe.name.replace("_", " ").title(),
            "description": recipe.answers,
            "kind": "recipe",
            "source": "builtin",
            "inputs": [
                {
                    "name": item.name,
                    "kind": item.kind,
                    "description": item.description,
                    "required": item.required,
                }
                for item in recipe.inputs
            ],
        }
        for recipe in RECIPES
    ]
    return {"builtins": items, "count": len(items)}


@router.get("/capabilities/{capability_id}")
def get_capability(capability_id: str) -> dict[str, Any]:
    store = _store()
    versions = store.versions(capability_id)
    if not versions:
        raise HTTPException(status_code=404, detail="capability not found")
    for record in versions:
        record["usage"] = _usage(
            store, capability_id, str(record.get("version") or ""),
        )
    return {"capabilityId": capability_id, "versions": versions}


@router.post("/capabilities/{capability_id}/activate")
def activate_capability(
    capability_id: str,
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    result = builder.activate(
        capability_id, payload.get("version"), store=_store(), operator=True, root=_root(),
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="capability not found")
    resume = resume_original_task(
        getattr(service, "tasks", None), (result.get("record") or {}).get("taskId"),
    )
    return {"success": True, "result": {**result, "resume": resume}}


@router.post("/capabilities/{capability_id}/deactivate")
def deactivate_capability(
    capability_id: str,
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    result = builder.deactivate(
        capability_id, payload.get("version"), store=_store(), root=_root(),
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="capability not found")
    return {"success": True, "result": result}


@router.post("/capabilities/{capability_id}/rollback")
def rollback_capability(
    capability_id: str,
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    result = builder.rollback(
        capability_id, payload.get("version"), store=_store(), operator=True, root=_root(),
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="capability not found")
    resume = resume_original_task(
        getattr(service, "tasks", None), (result.get("record") or {}).get("taskId"),
    )
    return {"success": True, "result": {**result, "resume": resume}}


@router.post("/capabilities/{capability_id}/promote")
def promote_capability(
    capability_id: str,
    payload: dict[str, Any],
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    result = builder.promote(
        capability_id, payload.get("version"), store=_store(), root=_root(), operator=True,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="capability not found")
    return {"success": True, "result": result}


@router.post("/capabilities/{capability_id}/remove")
def remove_capability(
    capability_id: str,
    _: Any = Depends(require_operator),
) -> dict[str, Any]:
    result = builder.retire(capability_id, store=_store())
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="capability not found")
    return {"success": True, "result": result}


__all__ = ["router"]

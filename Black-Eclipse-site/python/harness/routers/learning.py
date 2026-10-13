"""Learning-research HTTP routes.

Thin, operator-gated adapters over the SAME LearningStore the agent tools write
through (bound to the ONE eclipse-memory connection). The chat's interactive
learning-map block calls the front-door proxy that reaches these routes, so a
completion toggle the user clicks and a completion the agent records can never
disagree.

Progress reads and writes are operator-gated: the roadmap and its progress are
the learner's own data.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["learning"])


def _store():
    store = getattr(service, "learning_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="the learning-research engine is unavailable")
    return store


class ProgressBody(BaseModel):
    pathId: str = Field(min_length=1, max_length=200)  # noqa: N815
    nodeId: str = Field(min_length=1, max_length=200)  # noqa: N815
    status: str = Field(min_length=1, max_length=40)
    assessment: Optional[str] = Field(default=None, max_length=4000)


class PreferenceBody(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)


@router.get("/learning/paths")
def list_learning_paths(limit: int = 50, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "paths": _store().list_paths(limit=limit)}


@router.get("/learning/paths/{path_id}")
def get_learning_path(path_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = _store()
    path = store.get_path(path_id)
    if path is None:
        raise HTTPException(status_code=404, detail="learning path not found")
    store.touch(path_id)
    return {"success": True, "path": path, "progress": store.list_node_progress(path_id)}


@router.get("/learning/progress")
def get_learning_progress(
    path_id: Optional[str] = None,  # noqa: N803
    goal: Optional[str] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    store = _store()
    resolved = path_id
    if not resolved and goal:
        found = store.find_active_by_goal(goal)
        resolved = found["id"] if found else None
    if not resolved:
        return {"success": True, "pathId": None, "progress": [], "paths": store.list_paths(limit=20)}
    path = store.get_path(resolved)
    if path is None:
        raise HTTPException(status_code=404, detail="learning path not found")
    store.touch(resolved)
    return {"success": True, "pathId": resolved, "path": path, "progress": store.list_node_progress(resolved)}


@router.post("/learning/progress")
def update_learning_progress(body: ProgressBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    store = _store()
    if store.get_path(body.pathId) is None:
        raise HTTPException(status_code=404, detail="learning path not found")
    record = store.set_node_status(body.pathId, body.nodeId, body.status, body.assessment)
    return {"success": True, "record": record}


@router.get("/learning/preferences")
def list_learning_preferences(_: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "preferences": _store().list_preferences()}


@router.post("/learning/preferences")
def set_learning_preference(body: PreferenceBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    return {"success": True, "preference": _store().set_preference(body.key, body.value)}


__all__ = ["router"]

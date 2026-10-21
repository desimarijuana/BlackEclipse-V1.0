"""The Project routes — the named scopes the agent and the UI share.

Thin adapters over the ONE `ProjectStore` on the runtime's own database, so
the UI and the agent can never disagree about what a project holds. Every
route is operator-gated; a project is a record, not an effect on the world.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..projects import ProjectError

router = APIRouter(tags=["projects"])


def _store() -> Any:
    store = getattr(service, "project_store", None)
    if store is None:
        raise HTTPException(status_code=503,
                            detail="the project layer is unavailable in this runtime")
    return store


class CreateProjectBody(BaseModel):
    name: str
    description: str = ""
    symbols: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AttachMemberBody(BaseModel):
    kind: str
    ref: str
    label: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


@router.get("/projects")
async def list_projects(status: Optional[str] = None, limit: int = 50,
                        _: bool = Depends(require_operator)) -> dict:
    store = _store()
    projects = store.list(status=status, limit=limit)
    return {
        "projects": [p.to_dict() for p in projects],
        "count": len(projects),
    }


@router.post("/projects")
async def create_project(body: CreateProjectBody,
                         _: bool = Depends(require_operator)) -> dict:
    store = _store()
    try:
        project = store.create(body.name, description=body.description,
                                symbols=body.symbols, tags=body.tags)
    except ProjectError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"project": project.to_dict()}


@router.get("/projects/{project_id}")
async def get_project(project_id: str,
                      _: bool = Depends(require_operator)) -> dict:
    store = _store()
    detail = store.detail(project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no project {project_id!r}")
    return detail


@router.get("/projects/{project_id}/digest")
async def project_digest_route(project_id: str,
                                _: bool = Depends(require_operator)) -> dict:
    """The curated view of a project: what it is, what matters, what it lacks."""
    store = _store()
    from ..projects.curate import curate_project

    digest = curate_project(store, project_id)
    if digest is None:
        raise HTTPException(status_code=404, detail=f"no project {project_id!r}")
    return {"digest": digest.to_dict(), "markdown": digest.to_markdown()}


@router.get("/projects/{project_id}/proposals")
async def project_proposals_route(project_id: str, firm: str = "topstep",
                                  size: str = "50k",
                                  _: bool = Depends(require_operator)) -> dict:
    """What this project should do next, from its own evidence."""
    store = _store()
    from ..projects.propose import propose_next

    quant_store = getattr(service, "quant_store", None)
    report = propose_next(store, project_id, quant_store=quant_store,
                          firm=firm, firm_size=size)
    if not report.get("available"):
        raise HTTPException(status_code=404,
                            detail=str(report.get("reason") or "no project"))
    return report


@router.post("/projects/{project_id}/members")
async def attach_member(project_id: str, body: AttachMemberBody,
                        _: bool = Depends(require_operator)) -> dict:
    store = _store()
    try:
        member = store.attach(project_id, body.kind, body.ref, label=body.label,
                              meta=body.meta)
    except ProjectError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"member": member.to_dict()}


@router.delete("/projects/{project_id}/members/{member_id}")
async def detach_member(project_id: str, member_id: str,
                        _: bool = Depends(require_operator)) -> dict:
    store = _store()
    if not store.detach(project_id, member_id):
        raise HTTPException(
            status_code=404,
            detail=f"no member {member_id!r} in project {project_id!r}")
    return {"detached": member_id}


__all__ = ["router"]

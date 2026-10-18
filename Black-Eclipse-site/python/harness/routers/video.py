"""Native-video route group (Phase 7) — the HTTP door the front door proxies.

Registered by `main.py` via `app.include_router(...)`. Shared state comes from
`deps.py` — this module never imports `main`.

EVERY route carries `require_operator` (reads AND mutations), exactly as the
canvas, artifacts and fabric route groups do. The routes are a thin shell over
`VideoService`: they never render, resolve or register anything themselves, so
the SAME job policy (queued Execution-Fabric jobs, bounded repair, confined
workspaces, Artifact Center registration) applies to HTTP callers as to the
agent tools. A video exists only when a job SUCCEEDED — the routes add no
success of their own.

The owner label comes from `X-Harness-User` (the front door forwards
`x-eclipse-user`); a `conversationId` on a job request associates produced
artifacts with the conversation they came from (a label, never an authority).
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..video.models import VideoError

router = APIRouter(tags=["video"])

_MAX_SPEC_BYTES_NOTE = "spec is validated by the video layer, not here"


# ── bodies ────────────────────────────────────────────────────────────────────


class CreateProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="title_card", max_length=32)
    spec: Optional[dict[str, Any]] = Field(default=None, description=_MAX_SPEC_BYTES_NOTE)
    context: Optional[dict[str, Any]] = None


class UpdateProjectBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    spec: Optional[dict[str, Any]] = Field(default=None, description=_MAX_SPEC_BYTES_NOTE)


class RenderBody(BaseModel):
    mode: Literal["draft", "final"] = "draft"
    # The conversation this render belongs to (associates the artifact). A
    # label only — bounded, never an authority decision.
    conversationId: Optional[str] = Field(default=None, max_length=200)  # noqa: N815


class PreviewBody(BaseModel):
    count: Optional[int] = Field(default=None, ge=2, le=24)
    columns: Optional[int] = Field(default=None, ge=1, le=8)
    width: Optional[int] = Field(default=None, ge=160, le=960)
    frames: bool = True
    conversationId: Optional[str] = Field(default=None, max_length=200)  # noqa: N815


class RepairBody(BaseModel):
    ofJobId: str = Field(min_length=1, max_length=200)  # noqa: N815
    spec: Optional[dict[str, Any]] = Field(default=None, description=_MAX_SPEC_BYTES_NOTE)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    mode: Literal["draft", "final"] = "draft"
    conversationId: Optional[str] = Field(default=None, max_length=200)  # noqa: N815


class RecapBody(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=5)
    title: Optional[str] = Field(default=None, max_length=80)
    subtitle: Optional[str] = Field(default=None, max_length=120)


# ── accessors ─────────────────────────────────────────────────────────────────


def _video() -> Any:
    layer = getattr(service, "video", None)
    if layer is None:
        raise HTTPException(status_code=503, detail="the video pipeline is unavailable")
    return layer


def _owner(request: Request) -> str:
    return (request.headers.get("x-harness-user") or "local").strip() or "local"


def _context(conversation_id: Optional[str], request: Request) -> Optional[dict[str, Any]]:
    """The execution context to queue a job with (conversation + operator)."""
    context: dict[str, Any] = {}
    if conversation_id:
        context["conversationId"] = conversation_id
    agent = (request.headers.get("x-harness-agent") or "").strip()
    if agent:
        context["agentId"] = agent
    return context or None


def _raise(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        # An accessor's own honest refusal (503 layer-unavailable) passes
        # through untouched — never re-wrapped as a generic 500.
        raise exc
    if isinstance(exc, VideoError):
        code = exc.code
        status = 400
        if code.endswith("NOT_FOUND"):
            status = 404
        elif code == "RUNTIME_UNAVAILABLE" or code == "DATA_UNAVAILABLE":
            status = 503
        elif code in ("REPAIR_LIMIT_REACHED", "REPAIR_REQUIRES_CHANGE", "INVALID_STATE"):
            status = 409
        raise HTTPException(status_code=status, detail={"code": code, "message": exc.message})
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=500, detail=str(exc))


# ── capabilities ──────────────────────────────────────────────────────────────


@router.get("/video/capabilities")
def video_capabilities(request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, **(_video().capabilities())}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover - _raise always raises


@router.post("/video/recaps", status_code=201)
def create_recap(
    body: RecapBody, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    """Create a data-bound market-recap video project (the recurring-video
    entry point: schedules and scripts call this, then the ordinary render)."""
    try:
        from ..video.recaps import create_recap_project  # noqa: PLC0415

        project = create_recap_project(
            _video(), symbols=body.symbols, title=body.title, subtitle=body.subtitle,
        )
        return {"success": True, "project": project}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


# ── projects ──────────────────────────────────────────────────────────────────


@router.get("/video/projects")
def list_projects(request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "projects": _video().list_projects()}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.post("/video/projects", status_code=201)
def create_project(
    body: CreateProjectBody, request: Request, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        project = _video().create_project(name=body.name, kind=body.kind, spec=body.spec)
        return {"success": True, "project": project}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.get("/video/projects/{project_id}")
def get_project(project_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "project": _video().get_project(project_id)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.put("/video/projects/{project_id}")
def update_project(
    project_id: str, body: UpdateProjectBody, request: Request,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        project = _video().update_project(project_id, name=body.name, spec=body.spec)
        return {"success": True, "project": project}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.post("/video/projects/{project_id}/validate")
def validate_project(
    project_id: str, request: Request, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        return {"success": True, **(_video().validate_project(project_id))}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.post("/video/projects/{project_id}/resolve-data")
async def resolve_project_data(
    project_id: str, request: Request, _: bool = Depends(require_operator)
) -> dict[str, Any]:
    try:
        manifest = await _video().resolve_project_data(project_id)
        return {"success": True, "evidence": manifest}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.post("/video/projects/{project_id}/preview", status_code=202)
async def preview_project(
    project_id: str, body: PreviewBody, request: Request,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        handle = await _video().preview_project(
            project_id, owner=_owner(request), count=body.count, columns=body.columns,
            width=body.width, frames=body.frames,
            context=_context(body.conversationId, request),
        )
        return {"success": True, "job": handle}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.post("/video/projects/{project_id}/render", status_code=202)
async def submit_render(
    project_id: str, body: RenderBody, request: Request,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        layer = _video()
        submit = layer.render_final if body.mode == "final" else layer.render_draft
        handle = await submit(
            project_id, owner=_owner(request),
            context=_context(body.conversationId, request),
        )
        return {"success": True, "job": handle}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.post("/video/projects/{project_id}/repair", status_code=202)
async def repair_render(
    project_id: str, body: RepairBody, request: Request,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        handle = await _video().render_repair(
            project_id, of_job_id=body.ofJobId, spec=body.spec, name=body.name,
            mode=body.mode, owner=_owner(request),
            context=_context(body.conversationId, request),
        )
        return {"success": True, "job": handle}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


# ── jobs ──────────────────────────────────────────────────────────────────────


@router.get("/video/jobs")
def list_jobs(
    request: Request, projectId: Optional[str] = None, limit: int = 50,  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        jobs = _video().list_jobs(project_id=projectId, limit=max(1, min(200, limit)))
        return {"success": True, "jobs": jobs}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.get("/video/jobs/{job_id}")
def get_job(job_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        job = _video().get_job(job_id)
        if job is None:
            raise VideoError("JOB_NOT_FOUND", f"video job {job_id!r} was not found")
        return {"success": True, "job": job}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.post("/video/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = await _video().cancel_job(job_id)
        return {"success": True, "cancellation": result}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


@router.post("/video/jobs/{job_id}/inspect", status_code=202)
async def inspect_video(job_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        handle = await _video().inspect_video(job_id=job_id)
        return {"success": True, "job": handle}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
        raise  # pragma: no cover


__all__ = ["router"]

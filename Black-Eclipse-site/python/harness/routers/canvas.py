"""Canvas route group — thin, operator-gated shell over `CanvasService`.

Content is never trusted from the client on an AI-assisted save: the typed
operations are re-applied to the current bytes under the revision guard.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ..canvas.edits import CanvasEditOrchestrator
from ..canvas.model import (
    CanvasConflict,
    CanvasEditRequest,
    CanvasError,
    CanvasKind,
    CanvasProposal,
    CanvasSnapshot,
    CreateCanvasInput,
    RestoreCanvasInput,
    SaveCanvasInput,
)
from ..canvas.service import CanvasService
from ..deps import require_operator, service
from ..schemas import ModelSettings

router = APIRouter(tags=["canvas"])


def _artifacts():
    artifact_service = getattr(service, "artifacts", None)
    if artifact_service is None:
        from ..artifacts.bootstrap import install_artifact_layer  # noqa: PLC0415

        install_artifact_layer(service)
        artifact_service = getattr(service, "artifacts", None)
    if artifact_service is None:
        raise HTTPException(status_code=503, detail="Artifact runtime unavailable")
    return artifact_service


def _service() -> CanvasService:
    return CanvasService(_artifacts())


def _owner(request: Request) -> str:
    return (request.headers.get("x-harness-user") or "local").strip() or "local"


def _raise(exc: Exception) -> None:
    if isinstance(exc, CanvasConflict):
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": exc.message,
                "currentVersion": exc.current_version,
            },
        )
    if isinstance(exc, CanvasError):
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=500, detail=str(exc))


@router.get("/canvas/artifacts")
def list_canvas_artifacts(
    request: Request,
    kind: Optional[CanvasKind] = None,
    q: Optional[str] = None,
    limit: int = 100,
    _: bool = Depends(require_operator),
):
    try:
        return {"artifacts": _service().list(owner_id=_owner(request), kind=kind, query=q, limit=limit)}
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.post("/canvas/artifacts", status_code=201)
def create_canvas_artifact(
    body: CreateCanvasInput,
    request: Request,
    _: bool = Depends(require_operator),
) -> CanvasSnapshot:
    try:
        return _service().create(body, owner_id=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.get("/canvas/artifacts/{artifact_id}")
def get_canvas_artifact(
    artifact_id: str,
    request: Request,
    _: bool = Depends(require_operator),
) -> CanvasSnapshot:
    try:
        return _service().snapshot(artifact_id, owner_id=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.put("/canvas/artifacts/{artifact_id}")
def save_canvas_artifact(
    artifact_id: str,
    body: SaveCanvasInput,
    request: Request,
    _: bool = Depends(require_operator),
) -> CanvasSnapshot:
    try:
        return _service().save(artifact_id, body, owner_id=_owner(request), actor="canvas")
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.post("/canvas/artifacts/{artifact_id}/restore")
def restore_canvas_artifact(
    artifact_id: str,
    body: RestoreCanvasInput,
    request: Request,
    _: bool = Depends(require_operator),
) -> CanvasSnapshot:
    try:
        return _service().restore(artifact_id, body, owner_id=_owner(request), actor="canvas")
    except Exception as exc:  # noqa: BLE001
        _raise(exc)


@router.post("/canvas/artifacts/{artifact_id}/edits")
async def propose_canvas_edit(
    artifact_id: str,
    body: CanvasEditRequest,
    request: Request,
    _: bool = Depends(require_operator),
) -> CanvasProposal:
    try:
        if body.model_settings is not None:
            # Fail closed before the model call if the provider payload is bad.
            body = body.model_copy(
                update={"model_settings": ModelSettings.model_validate(body.model_settings).model_dump(by_alias=True)}
            )
        return await CanvasEditOrchestrator(_service()).propose(
            artifact_id, body, owner_id=_owner(request)
        )
    except Exception as exc:  # noqa: BLE001
        _raise(exc)

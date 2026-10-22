"""The gallery routes - the published catalogue (operator-gated).

Thin adapters over the ONE gallery store, so the UI and the agent can never
disagree about what has been published.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_operator, service

router = APIRouter(tags=["gallery"])


def _store() -> Any:
    store = getattr(service, "gallery_store", None)
    if store is None:
        raise HTTPException(status_code=503,
                            detail="the gallery is unavailable in this runtime")
    return store


class PublishBody(BaseModel):
    strategyId: str
    version: Optional[str] = None
    name: Optional[str] = None
    description: str = ""
    author: str = "local"
    grade: Optional[str] = None
    score: Optional[float] = None
    summary: str = ""
    report: str = ""
    symbols: list[str] = Field(default_factory=list)


class FavouriteBody(BaseModel):
    publishedId: str


class CloneBody(BaseModel):
    publishedId: str


@router.get("/gallery")
async def list_gallery(_: bool = Depends(require_operator)) -> dict[str, Any]:
    """Every published strategy, newest first."""
    store = _store()
    entries = store.list(limit=200)
    return {"entries": [e.to_dict() for e in entries], "count": len(entries)}


@router.get("/gallery/{published_id}")
async def get_published(published_id: str,
                         _: bool = Depends(require_operator)) -> dict[str, Any]:
    """One published record, with its spec and its report."""
    store = _store()
    entry = store.get(published_id)
    if entry is None:
        raise HTTPException(status_code=404,
                            detail=f"no published {published_id!r}")
    return {"published": entry.to_dict(include_spec=True)}


@router.post("/gallery")
async def publish_strategy(body: PublishBody,
                            _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Publish a strategy into the gallery."""
    from ..gallery.tools import publish_strategy as handler

    class _Ctx:
        def __init__(self) -> None:
            self.gallery_store = getattr(service, "gallery_store", None)
            self.quant_store = getattr(service, "quant_store", None)

    text, payload = await handler(body.model_dump(), _Ctx())
    if payload.get("status") == "ERROR":
        raise HTTPException(status_code=422, detail=payload.get("error"))
    return {"status": "OK", "summary": text, **payload}


@router.post("/gallery/{published_id}/favourite")
async def favourite(published_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Favourite a published strategy."""
    store = _store()
    entry = store.favourite(published_id)
    if entry is None:
        raise HTTPException(status_code=404,
                            detail=f"no published {published_id!r}")
    return {"published": entry.to_dict()}


@router.post("/gallery/{published_id}/clone")
async def clone(published_id: str, _: bool = Depends(require_operator)) -> dict[str, Any]:
    """Clone a published strategy into the quant store as a new strategy."""
    from ..gallery.tools import clone_published_strategy as handler

    class _Ctx:
        def __init__(self) -> None:
            self.gallery_store = getattr(service, "gallery_store", None)
            self.quant_store = getattr(service, "quant_store", None)

    text, payload = await handler({"publishedId": published_id}, _Ctx())
    if payload.get("status") == "ERROR":
        raise HTTPException(status_code=422, detail=payload.get("error"))
    return {"status": "OK", "summary": text, **payload}


__all__ = ["router"]

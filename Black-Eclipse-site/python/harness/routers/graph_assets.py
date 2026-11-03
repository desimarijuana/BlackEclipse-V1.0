"""Graph asset routes: upload / inspect / download / delete a local file.

The Graph Studio inspector uploads raw bytes here (no multipart dependency): the
file name and MIME arrive as query parameters and the body is the file itself.
The store is bounded and local; this route never forwards the bytes anywhere.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from ..deps import require_operator
from ..graph_runtime.assets import (
    MAX_ASSET_BYTES,
    AssetError,
    AssetExpired,
    AssetNotFound,
    AssetTooLarge,
    AssetUnsupportedType,
    GraphAssetStore,
)

router = APIRouter(prefix="/graph/assets", tags=["graph-assets"])

MAX_IMAGE_BYTES = 20_000_000


async def _body(request: Request, limit: int) -> bytes:
    """Read a bounded body; a declared or actual oversize is a 413.

    The Next front door already caps uploads; this is defence in depth for a
    direct runtime call.
    """
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > limit:
                raise HTTPException(status_code=413, detail=f"upload exceeds {limit} bytes")
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid Content-Length") from None
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="the request body is empty")
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"upload exceeds {limit} bytes")
    return data


def _store() -> GraphAssetStore:
    from ..graph_runtime.assets import get_asset_store  # noqa: PLC0415

    store = get_asset_store()
    if store is None:
        # The graph layer may not have booted yet (or boot failed).
        from ..deps import service  # noqa: PLC0415

        existing = getattr(service, "graphs_assets", None)
        if isinstance(existing, GraphAssetStore):
            return existing
        from ..graph_runtime.bootstrap import install_graph_layer  # noqa: PLC0415

        install_graph_layer(service)
        store = get_asset_store()
    if store is None:
        raise HTTPException(status_code=503, detail="Graph asset store unavailable")
    return store


def _fail(exc: AssetError) -> HTTPException:
    if isinstance(exc, AssetNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, AssetExpired):
        return HTTPException(status_code=410, detail=str(exc))
    if isinstance(exc, (AssetTooLarge, AssetUnsupportedType)):
        return HTTPException(status_code=413, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _owner(request: Request, requested: str = "") -> str:
    """The verified owner. A caller-supplied owner is used only in local mode."""
    try:
        from ..deps import identity_for  # noqa: PLC0415

        identity = identity_for(request)
        if identity.is_authenticated and identity.user_id:
            return str(identity.user_id)[:120]
        if identity.tenant_id:
            return str(identity.tenant_id)[:120]
    except Exception:  # noqa: BLE001 - never break an upload on identity resolution
        pass
    return (requested or "local").strip()[:120] or "local"


def _rate_limit(request: Request, owner: str, *, cost: float = 1.0) -> None:
    """A per-owner upload budget (defence in depth; the proxy should also limit)."""
    try:
        from ..security.ratelimit import default_limiter  # noqa: PLC0415

        client = getattr(request.client, "host", "") if request.client else ""
        if not default_limiter().allow(f"graph-asset:{owner or client}", cost=cost):
            raise HTTPException(
                status_code=429,
                detail="too many uploads; wait a moment and retry",
                headers={"Retry-After": "5"},
            )
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - never fail closed on a limiter bug
        pass


@router.get("")
def list_assets(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    owner: Optional[str] = Query(default=None, max_length=120),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    store = _store()
    return {"assets": store.list(limit=limit, owner=_owner(request, owner or ""))}


@router.post("")
async def upload_asset(
    request: Request,
    name: str = Query(default="upload.dat", min_length=1, max_length=200),
    mime: str = Query(default="application/octet-stream", max_length=120),
    owner: str = Query(default="local", max_length=120),
    ttlHours: int = Query(default=0, ge=0, le=8_760),  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    resolved_owner = _owner(request, owner)
    _rate_limit(request, resolved_owner)
    data = await _body(request, MAX_ASSET_BYTES)
    store = _store()
    try:
        return store.save(
            name,
            data,
            mime=mime,
            ttl_seconds=ttlHours * 3600,
            owner=resolved_owner,
        )
    except AssetError as exc:
        raise _fail(exc) from exc


def _vision_store() -> Any:
    from ..deps import service  # noqa: PLC0415

    store = getattr(service, "vision_assets", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Vision asset store unavailable")
    return store


def _image_meta(asset: Any, name: str = "") -> dict[str, Any]:
    metadata = getattr(asset, "metadata", None) or {}
    return {
        "assetId": asset.asset_id,
        "name": str(metadata.get("name") or name or asset.source_ref or asset.asset_id),
        "mime": asset.mime_type,
        "width": asset.width,
        "height": asset.height,
        "bytes": asset.byte_size,
        "sha256": asset.sha256,
        "createdAt": asset.created_at,
        "ownerId": getattr(asset, "owner_id", "local"),
    }


@router.post("/images")
async def upload_image(
    request: Request,
    name: str = Query(default="image.png", min_length=1, max_length=200),
    mime: str = Query(default="application/octet-stream", max_length=120),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    from ..vision.errors import VisionError  # noqa: PLC0415
    from ..vision.image import decode_bytes  # noqa: PLC0415

    resolved_owner = _owner(request)
    _rate_limit(request, resolved_owner)
    data = await _body(request, MAX_IMAGE_BYTES)
    try:
        decoded = decode_bytes(data, source=name, expected_mime=mime or None)
    except VisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store = _vision_store()
    asset = store.save(
        decoded, source_kind="upload", source_ref=name,
        metadata={"name": name}, owner=resolved_owner,
    )
    return _image_meta(asset, name)


@router.get("/images/{asset_id}")
def image_meta(
    asset_id: str, request: Request, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    store = _vision_store()
    asset = store.get(asset_id, owner=_owner(request))
    if asset is None:
        raise HTTPException(status_code=404, detail=f"image {asset_id!r} does not exist")
    return _image_meta(asset)


@router.get("/images/{asset_id}/content")
def image_content(
    asset_id: str, request: Request, _: bool = Depends(require_operator),
) -> Response:
    store = _vision_store()
    owner = _owner(request)
    asset = store.get(asset_id, owner=owner)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"image {asset_id!r} does not exist")
    data = store.open_bytes(asset_id, owner=owner)
    if data is None:
        raise HTTPException(status_code=404, detail=f"image {asset_id!r} has no stored bytes")
    return Response(
        content=data,
        media_type=asset.mime_type,
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/images/{asset_id}")
def delete_image(
    asset_id: str, request: Request, _: bool = Depends(require_operator),
) -> dict[str, Any]:
    store = _vision_store()
    removed = store.delete(asset_id, owner=_owner(request))
    if not removed:
        raise HTTPException(status_code=404, detail=f"image {asset_id!r} does not exist")
    return {"deleted": True, "assetId": asset_id}


@router.get("/{asset_id}")
def asset_meta(
    asset_id: str,
    request: Request,
    owner: str = Query(default="local", max_length=120),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    store = _store()
    try:
        return store.get(asset_id, owner=_owner(request, owner))
    except AssetError as exc:
        raise _fail(exc) from exc


@router.get("/{asset_id}/content")
def asset_content(
    asset_id: str,
    request: Request,
    owner: str = Query(default="local", max_length=120),
    _: bool = Depends(require_operator),
) -> Response:
    store = _store()
    try:
        resolved = _owner(request, owner)
        meta = store.get(asset_id, owner=resolved)
        data = store.open_bytes(asset_id, owner=resolved)
    except AssetError as exc:
        raise _fail(exc) from exc
    return Response(
        content=data,
        media_type=str(meta.get("mime") or "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="{meta.get("name") or asset_id}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("/{asset_id}")
def delete_asset(
    asset_id: str,
    request: Request,
    owner: str = Query(default="local", max_length=120),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    store = _store()
    removed = store.delete(asset_id, owner=_owner(request, owner))
    if not removed:
        raise HTTPException(status_code=404, detail=f"file {asset_id!r} does not exist")
    return {"deleted": True, "assetId": asset_id}

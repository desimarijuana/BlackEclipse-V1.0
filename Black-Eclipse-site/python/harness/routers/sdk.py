"""Eclipse SDK route group (`/sdk/*`).

Every route is operator-gated (loopback or the runtime token), matching the UI
and Portfolio groups. A locked resource is refused with HTTP 423 until the
caller presents a valid `X-Eclipse-Unlock` token (the middleware in `main.py`
places the header in the SDK contextvar). The front door forwards that header.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..deps import require_operator, service
from ..sdk.locks import LockError
from ..sdk.model import (
    SdkActiveDashboardInput,
    SdkAddStockInput,
    SdkAssertLockInput,
    SdkAuditInput,
    SdkCreateFundInput,
    SdkCreateLockInput,
    SdkCreatePageInput,
    SdkDashboardAddWidgetInput,
    SdkDashboardMoveWidgetInput,
    SdkDashboardResizeWidgetInput,
    SdkDashboardRestoreInput,
    SdkDashboardSetColumnsInput,
    SdkDashboardSetLayoutInput,
    SdkDashboardSetZonesInput,
    SdkDashboardWidgetRefInput,
    SdkUnlockInput,
    SdkWidgetInput,
)
from ..sdk.service import SdkError
from ..ui.service import UiError

router = APIRouter(tags=["sdk"])


def _sdk():
    sdk = getattr(service, "sdk", None)
    if sdk is None:
        from ..sdk.bootstrap import install_sdk_layer  # noqa: PLC0415

        install_sdk_layer(service)
        sdk = getattr(service, "sdk", None)
    if sdk is None:
        raise HTTPException(status_code=503, detail="Eclipse SDK runtime unavailable")
    return sdk


def _owner(request: Request) -> str:
    return (request.headers.get("x-harness-user") or "local").strip() or "local"


def _raise(exc: Exception) -> None:
    if isinstance(exc, LockError):
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
                "lockId": exc.lock_id,
                "resourceType": exc.resource_type,
                "resourceId": exc.resource_id,
                "hint": exc.hint,
            },
        )
    if isinstance(exc, SdkError):
        status = 423 if "LOCK" in exc.code else exc.status_code
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})
    if isinstance(exc, UiError):
        status = 404 if exc.code.endswith("NOT_FOUND") else 409 if exc.code == "UI_CONFLICT" else 423 if "LOCK" in exc.code else 400
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message, "issues": exc.issues})
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=500, detail=str(exc))


def _wrap(exc: Exception) -> None:
    _raise(exc)


# ── capabilities ──────────────────────────────────────────────────────────────


@router.get("/sdk/capabilities")
def sdk_capabilities(request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, **(_sdk().capabilities())}
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)


# ── audit ─────────────────────────────────────────────────────────────────────


@router.get("/sdk/audit")
def sdk_list_audit(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    action: Optional[str] = None,
    resourceType: Optional[str] = None,  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        result = _sdk().list_audit(limit=limit, action=action, resource_type=resourceType)
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.post("/sdk/audit")
def sdk_record_audit(
    request: Request,
    body: SdkAuditInput,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        entry = _sdk().record_audit(body, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, "entry": entry}


# ── declarative widgets ───────────────────────────────────────────────────────


@router.get("/sdk/widgets")
def sdk_list_widgets(request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        return {"success": True, "widgets": _sdk().list_widgets()}
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)


@router.post("/sdk/widgets")
def sdk_create_widget(request: Request, body: SdkWidgetInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        widget = _sdk().create_widget(body, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, "widget": widget}


@router.delete("/sdk/widgets/{component_id}")
def sdk_delete_widget(component_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        removed = _sdk().delete_widget(component_id, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, "removed": removed}


# ── Command Center dashboards ─────────────────────────────────────────────────


@router.get("/sdk/dashboards")
def sdk_list_dashboards(request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.list()
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.get("/sdk/dashboards/active")
def sdk_active_dashboard(request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.active()
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.put("/sdk/dashboards/active")
def sdk_set_active_dashboard(request: Request, body: SdkActiveDashboardInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.set_active(body.dashboard_id)
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.get("/sdk/dashboards/{dashboard_id}")
def sdk_get_dashboard(dashboard_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.get(dashboard_id)
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.put("/sdk/dashboards/{dashboard_id}/layout")
def sdk_set_dashboard_layout(dashboard_id: str, request: Request, body: SdkDashboardSetLayoutInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.set_layout(dashboard_id, body, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.post("/sdk/dashboards/{dashboard_id}/widgets")
def sdk_add_dashboard_widget(dashboard_id: str, request: Request, body: SdkDashboardAddWidgetInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.add_widget(dashboard_id, body, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.delete("/sdk/dashboards/{dashboard_id}/widgets/{instance_id}")
def sdk_remove_dashboard_widget(
    dashboard_id: str,
    instance_id: str,
    request: Request,
    expectedRevision: Optional[int] = Query(None, ge=1),  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.remove_widget(
            dashboard_id,
            SdkDashboardWidgetRefInput(instance_id=instance_id, expected_revision=expectedRevision),
            actor=_owner(request),
        )
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.post("/sdk/dashboards/{dashboard_id}/widgets/{instance_id}/move")
def sdk_move_dashboard_widget(dashboard_id: str, instance_id: str, request: Request, body: SdkDashboardMoveWidgetInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        if body.instance_id != instance_id:
            body = body.model_copy(update={"instance_id": instance_id})
        result = _sdk().dashboards.move_widget(dashboard_id, body, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.post("/sdk/dashboards/{dashboard_id}/widgets/{instance_id}/resize")
def sdk_resize_dashboard_widget(dashboard_id: str, instance_id: str, request: Request, body: SdkDashboardResizeWidgetInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        if body.instance_id != instance_id:
            body = body.model_copy(update={"instance_id": instance_id})
        result = _sdk().dashboards.resize_widget(dashboard_id, body, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.put("/sdk/dashboards/{dashboard_id}/columns")
def sdk_set_dashboard_columns(dashboard_id: str, request: Request, body: SdkDashboardSetColumnsInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.set_columns(dashboard_id, body, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.put("/sdk/dashboards/{dashboard_id}/zones")
def sdk_set_dashboard_zones(dashboard_id: str, request: Request, body: SdkDashboardSetZonesInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.set_zones(dashboard_id, body, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.get("/sdk/dashboards/{dashboard_id}/history")
def sdk_dashboard_history(dashboard_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.history(dashboard_id)
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.post("/sdk/dashboards/{dashboard_id}/restore")
def sdk_restore_dashboard(dashboard_id: str, request: Request, body: SdkDashboardRestoreInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().dashboards.restore(dashboard_id, body.revision, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


# ── pages ─────────────────────────────────────────────────────────────────────


@router.get("/sdk/pages")
def sdk_list_pages(
    request: Request,
    ownerId: Optional[str] = None,  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        # No implicit owner filter: the SDK surface lists every saved page in
        # single-user local mode. An explicit `ownerId` still narrows it.
        result = _sdk().list_pages(owner_id=ownerId)
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.post("/sdk/pages")
def sdk_create_page(request: Request, body: SdkCreatePageInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().create_page(body, owner_id=_owner(request), actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.patch("/sdk/pages/{blueprint_id}")
def sdk_update_page(blueprint_id: str, request: Request, body: dict[str, Any], _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().update_page(blueprint_id, body, owner_id=_owner(request), actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, **result}


@router.delete("/sdk/pages/{blueprint_id}")
def sdk_delete_page(blueprint_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        removed = _sdk().delete_page(blueprint_id, owner_id=_owner(request), actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, "removed": removed}


# ── portfolios / funds ────────────────────────────────────────────────────────


@router.get("/sdk/portfolios")
def sdk_list_portfolios(request: Request, ownerId: Optional[str] = None, _: bool = Depends(require_operator)) -> dict[str, Any]:  # noqa: N803
    try:
        portfolios = _sdk().list_portfolios(owner_id=ownerId)
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, "portfolios": portfolios}


@router.post("/sdk/funds")
def sdk_create_fund(request: Request, body: SdkCreateFundInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        fund = _sdk().create_fund(body, owner_id=_owner(request), actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, "fund": fund}


@router.post("/sdk/portfolios/{portfolio_id}/stocks")
def sdk_add_stock(portfolio_id: str, request: Request, body: SdkAddStockInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().add_stock(portfolio_id, body, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return result


# ── locks ─────────────────────────────────────────────────────────────────────


@router.get("/sdk/locks")
def sdk_list_locks(
    request: Request,
    resourceType: Optional[str] = None,  # noqa: N803
    resourceId: Optional[str] = None,  # noqa: N803
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        locks = _sdk().list_locks(resource_type=resourceType, resource_id=resourceId)
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, "locks": [lock.model_dump(by_alias=True) for lock in locks]}


@router.post("/sdk/locks")
def sdk_create_lock(request: Request, body: SdkCreateLockInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        lock = _sdk().create_lock(body, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, "lock": lock.model_dump(by_alias=True)}


@router.post("/sdk/locks/assert")
def sdk_assert_lock(request: Request, body: SdkAssertLockInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        lock = _sdk().locks.assert_allowed(body.resource_type, body.resource_id, body.action)
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, "locked": lock is not None}


@router.post("/sdk/locks/{lock_id}/unlock")
def sdk_unlock(lock_id: str, request: Request, body: SdkUnlockInput, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _sdk().unlock(lock_id, body.passphrase, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return result


@router.delete("/sdk/locks/{lock_id}")
def sdk_remove_lock(
    lock_id: str,
    request: Request,
    passphrase: Optional[str] = Query(None),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        removed = _sdk().remove_lock(lock_id, passphrase=passphrase, actor=_owner(request))
    except Exception as exc:  # noqa: BLE001
        _wrap(exc)
    return {"success": True, "removed": removed}


__all__ = ["router"]

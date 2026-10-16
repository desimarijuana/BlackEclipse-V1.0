"""UI Engineering route group.

Registered by `main.py` via `app.include_router(...)`. Shared state comes from
`deps.py`; this module never imports `main`.

EVERY route carries `require_operator` — reads AND mutations — exactly as the
task/artifact/MCP route groups are hardened. A directly reachable runtime must
not expose the UI blueprint store (which holds the user's saved layouts) to an
unauthenticated caller.

Routes are a thin shell over `UiService`; they never mutate state directly, so
the validation/audit contract applies to HTTP callers exactly as to the tools.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..deps import require_operator, service
from ..ui.model import (
    Availability,
    BlueprintKind,
    BlueprintScope,
    CatalogQuery,
    ListBlueprintsQuery,
    OwnershipKind,
    RegisterComponentInput,
    UiComponentSpec,
    WorkspaceLayout,
)
from ..ui.service import UiError, UiService

router = APIRouter(tags=["ui"])


def _service() -> UiService:
    ui_service = getattr(service, "ui", None)
    if ui_service is None:
        from ..ui.bootstrap import install_ui_layer  # noqa: PLC0415

        install_ui_layer(service)
        ui_service = getattr(service, "ui", None)
    if ui_service is None:
        raise HTTPException(status_code=503, detail="UI runtime unavailable")
    return ui_service


def _owner(request: Request) -> str:
    return (request.headers.get("x-harness-user") or "local").strip() or "local"


def _raise(exc: Exception) -> None:
    if isinstance(exc, UiError):
        if exc.code.endswith("NOT_FOUND"):
            code = 404
        elif exc.code.endswith("OWNER_MISMATCH"):
            code = 403
        elif exc.code == "UI_CONFLICT":
            code = 409
        else:
            code = 400
        detail: Any = {"code": exc.code, "message": exc.message}
        if exc.issues:
            detail["issues"] = exc.issues
        raise HTTPException(status_code=code, detail=detail)
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=500, detail=str(exc))


class CreatePageBody(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    kind: BlueprintKind = BlueprintKind.PAGE
    scope: BlueprintScope = BlueprintScope.PERSONAL
    path: Optional[str] = None
    icon: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    idempotencyKey: Optional[str] = None  # noqa: N815


class UpdatePageBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    path: Optional[str] = None
    icon: Optional[str] = None
    tags: Optional[list[str]] = None


class DuplicateBody(BaseModel):
    title: Optional[str] = None


class TargetBody(BaseModel):
    sectionId: str  # noqa: N815
    columnId: Optional[str] = None  # noqa: N815
    index: int = 0
    columnIndex: Optional[int] = None  # noqa: N815


class AddWidgetBody(BaseModel):
    componentId: str  # noqa: N815
    instanceId: Optional[str] = None  # noqa: N815
    target: Optional[TargetBody] = None
    config: dict[str, Any] = Field(default_factory=dict)
    zone: Optional[str] = None
    height: Optional[float] = None
    expectedRevision: Optional[int] = None  # noqa: N815


class MoveWidgetBody(BaseModel):
    target: TargetBody
    expectedRevision: Optional[int] = None  # noqa: N815


class ResizeWidgetBody(BaseModel):
    height: Optional[float] = None
    expectedRevision: Optional[int] = None  # noqa: N815


class ReorderWidgetBody(BaseModel):
    toIndex: int = Field(0, ge=0)  # noqa: N815
    expectedRevision: Optional[int] = None  # noqa: N815


class ConfigBody(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict)
    expectedRevision: Optional[int] = None  # noqa: N815


class SaveLayoutBody(BaseModel):
    layout: WorkspaceLayout
    expectedRevision: Optional[int] = None  # noqa: N815


class RestoreBody(BaseModel):
    revision: int = Field(..., ge=1)


class ImportBody(BaseModel):
    blueprint: dict[str, Any] = Field(default_factory=dict)


class PreviewBody(BaseModel):
    ops: list[dict[str, Any]] = Field(default_factory=list)


class RegisterComponentBody(RegisterComponentInput):
    pass


class ClassifyBody(BaseModel):
    text: str = Field(..., min_length=1)
    blueprintId: Optional[str] = None  # noqa: N815


class EngineeringBody(BaseModel):
    text: str = Field(..., min_length=1)
    blueprintId: Optional[str] = None  # noqa: N815
    title: Optional[str] = None
    autonomy: Optional[str] = None


class RegisterEngineeredBody(BaseModel):
    spec: UiComponentSpec


class EngineeringArtifactBody(BaseModel):
    uri: str = Field(..., min_length=1)
    kind: str = "file"
    label: Optional[str] = None


# ── introspection ─────────────────────────────────────────────────────────────


@router.post("/ui/classify")
def classify_request(request: Request, body: ClassifyBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().classify_request(body.text, blueprint_id=body.blueprintId)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.get("/ui/application-map")
def application_map(request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().get_application_map()
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.get("/ui/capabilities")
def capabilities(request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().get_capabilities()
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.get("/ui/current-page")
def resolve_current_page(
    request: Request,
    blueprintId: Optional[str] = None,  # noqa: N803
    path: Optional[str] = None,
    title: Optional[str] = None,
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    """Resolve the current page with no path segment required.

    Exists because ``GET /ui/blueprints/current`` would be swallowed by the
    ``/ui/blueprints/{blueprint_id}`` route. Identify by ``blueprintId``,
    ``path`` or ``title``; with none, the owner's most recently updated page is
    chosen and the response names it (``resolution`` + ``candidates``).
    """
    try:
        result = _service().get_current_page(blueprint_id=blueprintId, path=path, title=title)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.get("/ui/components")
def list_components(
    request: Request,
    text: Optional[str] = None,
    category: Optional[str] = None,
    dataSource: Optional[str] = None,  # noqa: N803
    owner: Optional[OwnershipKind] = None,
    availability: Optional[Availability] = None,
    limit: int = Query(50, ge=1, le=200),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        specs = _service().list_components(CatalogQuery(text=text, category=category, data_source=dataSource, owner=owner, availability=availability, limit=limit))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "components": [s.model_dump(by_alias=True) for s in specs]}


@router.post("/ui/components")
def register_component(request: Request, body: RegisterComponentBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        spec = _service().register_component(body.spec)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "component": spec.model_dump(by_alias=True)}


@router.get("/ui/components/{component_id}")
def inspect_component(component_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        spec = _service().inspect_component(component_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "component": spec.model_dump(by_alias=True)}


# ── blueprints ────────────────────────────────────────────────────────────────


@router.get("/ui/blueprints")
def list_blueprints(
    request: Request,
    scope: Optional[BlueprintScope] = None,
    kind: Optional[BlueprintKind] = None,
    ownerId: Optional[str] = None,  # noqa: N803
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: bool = Depends(require_operator),
) -> dict[str, Any]:
    try:
        result = _service().list_blueprints(ListBlueprintsQuery(scope=scope, kind=kind, owner_id=ownerId, q=q, limit=limit, offset=offset))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.post("/ui/blueprints")
def create_page(request: Request, body: CreatePageBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        from ..ui.model import CreatePageInput  # noqa: PLC0415

        blueprint = _service().create_page(
            CreatePageInput(
                title=body.title, description=body.description, kind=body.kind, scope=body.scope,
                path=body.path, icon=body.icon, tags=body.tags, idempotency_key=body.idempotencyKey,
            ),
            owner_id=_owner(request),
        )
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.get("/ui/blueprints/{blueprint_id}")
def get_blueprint(blueprint_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        blueprint = _service().get_blueprint(blueprint_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.patch("/ui/blueprints/{blueprint_id}")
def update_page(blueprint_id: str, request: Request, body: UpdatePageBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        from ..ui.model import UpdatePageInput  # noqa: PLC0415

        blueprint = _service().update_page(
            blueprint_id,
            UpdatePageInput(title=body.title, description=body.description, path=body.path, icon=body.icon, tags=body.tags),
        )
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.delete("/ui/blueprints/{blueprint_id}")
def delete_blueprint(blueprint_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        removed = service.ui_store.delete_blueprint(blueprint_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "removed": removed}


@router.post("/ui/blueprints/{blueprint_id}/duplicate")
def duplicate_page(blueprint_id: str, request: Request, body: DuplicateBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        blueprint = _service().duplicate_page(blueprint_id, title=body.title)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.get("/ui/blueprints/{blueprint_id}/current")
def current_page(blueprint_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().get_current_page(blueprint_id=blueprint_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.get("/ui/blueprints/{blueprint_id}/verify")
def verify_page(blueprint_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().verify_page(blueprint_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.get("/ui/blueprints/{blueprint_id}/layout")
def get_layout(blueprint_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().get_layout(blueprint_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.put("/ui/blueprints/{blueprint_id}/layout")
def save_layout(blueprint_id: str, request: Request, body: SaveLayoutBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        from ..ui.model import SaveLayoutInput  # noqa: PLC0415

        blueprint = _service().save_layout(SaveLayoutInput(
            blueprint_id=blueprint_id, layout=body.layout, expected_revision=body.expectedRevision,
        ))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.get("/ui/blueprints/{blueprint_id}/history")
def history(blueprint_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().history(blueprint_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.get("/ui/blueprints/{blueprint_id}/export")
def export_blueprint(blueprint_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().export_blueprint(blueprint_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.post("/ui/blueprints/import")
def import_blueprint(request: Request, body: ImportBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        blueprint = _service().import_blueprint(body.model_dump())
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.post("/ui/blueprints/{blueprint_id}/restore")
def restore_revision(blueprint_id: str, request: Request, body: RestoreBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        from ..ui.model import RestoreRevisionInput  # noqa: PLC0415

        blueprint = _service().restore_revision(RestoreRevisionInput(blueprint_id=blueprint_id, revision=body.revision))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.post("/ui/blueprints/{blueprint_id}/preview")
def preview_change(blueprint_id: str, request: Request, body: PreviewBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().preview(blueprint_id, body.ops)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


# ── widget operations ─────────────────────────────────────────────────────────


@router.post("/ui/blueprints/{blueprint_id}/widgets")
def add_widget(blueprint_id: str, request: Request, body: AddWidgetBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        from ..ui.model import AddWidgetInput, DropTarget  # noqa: PLC0415

        blueprint = _service().add_widget(AddWidgetInput(
            blueprint_id=blueprint_id, component_id=body.componentId, instance_id=body.instanceId,
            target=DropTarget(**body.target.model_dump()) if body.target else None,
            config=body.config, zone=body.zone, height=body.height, expected_revision=body.expectedRevision,
        ))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.delete("/ui/blueprints/{blueprint_id}/widgets/{instance_id}")
def remove_widget(blueprint_id: str, instance_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        from ..ui.model import WidgetRefInput  # noqa: PLC0415

        blueprint = _service().remove_widget(WidgetRefInput(blueprint_id=blueprint_id, instance_id=instance_id))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.post("/ui/blueprints/{blueprint_id}/widgets/{instance_id}/move")
def move_widget(blueprint_id: str, instance_id: str, request: Request, body: MoveWidgetBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        from ..ui.model import DropTarget, MoveWidgetInput  # noqa: PLC0415

        blueprint = _service().move_widget(MoveWidgetInput(
            blueprint_id=blueprint_id, instance_id=instance_id,
            target=DropTarget(**body.target.model_dump()), expected_revision=body.expectedRevision,
        ))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.post("/ui/blueprints/{blueprint_id}/widgets/{instance_id}/resize")
def resize_widget(blueprint_id: str, instance_id: str, request: Request, body: ResizeWidgetBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        from ..ui.model import ResizeWidgetInput  # noqa: PLC0415

        blueprint = _service().resize_widget(ResizeWidgetInput(
            blueprint_id=blueprint_id, instance_id=instance_id, height=body.height, expected_revision=body.expectedRevision,
        ))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.post("/ui/blueprints/{blueprint_id}/widgets/{instance_id}/reorder")
def reorder_widget(blueprint_id: str, instance_id: str, request: Request, body: ReorderWidgetBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        from ..ui.model import ReorderWidgetInput  # noqa: PLC0415

        blueprint = _service().reorder_widget(ReorderWidgetInput(
            blueprint_id=blueprint_id, instance_id=instance_id, to_index=body.toIndex, expected_revision=body.expectedRevision,
        ))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


@router.post("/ui/blueprints/{blueprint_id}/widgets/{instance_id}/config")
def update_widget_config(blueprint_id: str, instance_id: str, request: Request, body: ConfigBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        from ..ui.model import UpdateConfigInput  # noqa: PLC0415

        blueprint = _service().update_widget_config(UpdateConfigInput(
            blueprint_id=blueprint_id, instance_id=instance_id, patch=body.patch, expected_revision=body.expectedRevision,
        ))
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "blueprint": blueprint.model_dump(by_alias=True)}


# ── operations ────────────────────────────────────────────────────────────────


@router.get("/ui/operations/{operation_id}")
def get_operation(operation_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        operation = _service().get_operation_status(operation_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "operation": operation.model_dump(by_alias=True)}


# ── engineering (Phase 7) ─────────────────────────────────────────────────────


@router.post("/ui/engineering")
def start_engineering(request: Request, body: EngineeringBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().engineering.start(
            body.text, blueprint_id=body.blueprintId, title=body.title, autonomy=body.autonomy or "edit_verify",
        )
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.get("/ui/engineering/{plan_id}")
def engineering_status(plan_id: str, request: Request, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().engineering.status(plan_id)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, "plan": result}


@router.post("/ui/engineering/{task_id}/components")
def register_engineered_component(task_id: str, request: Request, body: RegisterEngineeredBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().engineering.register_component(task_id, body.spec)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}


@router.post("/ui/engineering/{task_id}/artifacts")
def link_engineering_artifact(task_id: str, request: Request, body: EngineeringArtifactBody, _: bool = Depends(require_operator)) -> dict[str, Any]:
    try:
        result = _service().engineering.link_artifact(task_id, uri=body.uri, kind=body.kind, label=body.label)
    except Exception as exc:  # noqa: BLE001
        _raise(exc)
    return {"success": True, **result}

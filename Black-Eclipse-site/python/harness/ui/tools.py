"""Agent-facing UI tools — registered on the ONE shared registry.

These let an agent inspect the live UI and modify the user's saved UI
blueprints through natural language. They resolve the process-wide `UiService`
from the run's `ToolContext`; when it is absent they report `UI_UNAVAILABLE`
rather than inventing a result.

Mutation tools change only Eclipse's OWN saved UI configuration (a blueprint
scoped to an owner) — they grant no filesystem, network, shell, database or
secret access, so they carry the `read` permission exactly as the artifact
catalog tools do. A genuinely new capability (a component/plugin that requires
source code) is NOT reachable here; that is the Engineer path, a separate
privileged surface.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .model import (
    AddWidgetInput,
    CatalogQuery,
    CreatePageInput,
    ListBlueprintsQuery,
    MoveWidgetInput,
    ReorderWidgetInput,
    RestoreRevisionInput,
    ResizeWidgetInput,
    SaveLayoutInput,
    SectionRefInput,
    SetColumnCountInput,
    SetColumnWeightInput,
    UpdateConfigInput,
    UpdatePageInput,
    UiComponentSpec,
    WidgetRefInput,
    WorkspaceLayout,
)
from .service import UiError, UiService


def _ok(text: str, data: Optional[dict[str, Any]] = None) -> tuple[str, Any]:
    return text, data or {}


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, UiError):
        payload: dict[str, Any] = {"error": exc.code}
        if exc.issues:
            payload["issues"] = exc.issues
        return f"{exc.code}: {exc.message}", payload
    return f"UI_ERROR: {exc}", {"error": "UI_ERROR"}


def _service(ctx: ToolContext) -> UiService:
    service = getattr(ctx, "ui_service", None)
    if service is None:
        from .bootstrap import get_ui_service  # noqa: PLC0415

        service = get_ui_service()
    if service is None:
        raise UiError("UI_UNAVAILABLE", "the UI service is not available")
    return service


def _owner(ctx: ToolContext) -> str:
    return str(getattr(ctx, "workspace_id", None) or getattr(ctx, "user_id", None) or "operator")


def _bp(payload: dict[str, Any]) -> dict[str, Any]:
    return {"blueprint": payload}


# ── introspection ─────────────────────────────────────────────────────────────


async def _get_application_map(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).get_application_map(owner_id=None)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    # Name each page by id + title: a bare count left the agent unable to target
    # a page (it needs the id for ui_add_widget / ui_update_page / …).
    lines = [f'{p["id"]}  {p["title"]}' for p in result["pages"]]
    suffix = ("\n" + "\n".join(lines)) if lines else ""
    return _ok(
        f"{result['pageCount']} page(s); {result['capabilities']['componentCount']} component(s) available.{suffix}",
        result,
    )


async def _get_current_page(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).get_current_page(
            blueprint_id=args.get("blueprintId"), path=args.get("path"), owner_id=None,
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    title = result["blueprint"]["title"]
    return _ok(f"Page {title!r} (revision {result['revision']}) has {len(result['instances'])} widget instance(s).", result)


async def _get_component_catalog(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        query = CatalogQuery(
            text=args.get("text"), category=args.get("category"),
            data_source=args.get("dataSource"), limit=int(args.get("limit") or 50),
        )
        specs = _service(ctx).list_components(query)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    lines = [f"{s.id} [{s.category}] {s.display_name}" for s in specs]
    return _ok(f"{len(specs)} component(s)." + (("\n" + "\n".join(lines)) if lines else ""),
               {"components": [s.model_dump(by_alias=True) for s in specs]})


async def _inspect_component(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        spec = _service(ctx).inspect_component(str(args.get("componentId") or ""))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    fields = ", ".join(f.key for f in spec.config_schema) or "none"
    return _ok(f"{spec.id}: {spec.display_name}. Config: {fields}. Sources: {', '.join(spec.data_sources) or 'none'}.",
               {"component": spec.model_dump(by_alias=True)})


async def _get_layout(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).get_layout(str(args.get("blueprintId") or ""), owner_id=None)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Layout at revision {result['revision']}.", result)


async def _get_capabilities(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).get_capabilities()
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"{result['componentCount']} component(s) across {len(result['categories'])} categories.", result)


async def _get_blueprint(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).get_blueprint(str(args.get("blueprintId") or ""), owner_id=None)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Blueprint {blueprint.title!r} at revision {blueprint.revision}.", _bp(blueprint.model_dump(by_alias=True)))


async def _get_operation_status(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        operation = _service(ctx).get_operation_status(str(args.get("operationId") or ""))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"{operation.operation}: {operation.status}.", {"operation": operation.model_dump(by_alias=True)})


async def _list_blueprints(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).list_blueprints(ListBlueprintsQuery(limit=int(args.get("limit") or 50)), owner_id=None)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    # The id is in the structured payload; put it in the text too so the agent can
    # NAME the page it was asked to edit instead of only seeing a count.
    lines = [f'{b["id"]}  {b["title"]}' for b in result["blueprints"]]
    suffix = ("\n" + "\n".join(lines)) if lines else ""
    return _ok(f"{result['total']} blueprint(s).{suffix}", result)


async def _classify_request(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).classify_request(str(args.get("text") or ""), blueprint_id=args.get("blueprintId"))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    mode = result["mode"]
    hint = "" if mode == "compose" else " This needs the Engineer (code) path."
    return _ok(f"Mode: {mode}. {result['reasons'][0] if result['reasons'] else ''}{hint}", result)


async def _start_engineering(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        # Pin the invoking run's model on the engineering plan so the dispatched
        # task uses the operator's configured provider, not an env default.
        raw_settings = getattr(ctx, "model_settings", None)
        model_settings: Optional[dict[str, Any]] = None
        if raw_settings is not None:
            dump = raw_settings.model_dump(by_alias=True) if hasattr(raw_settings, "model_dump") else dict(raw_settings)
            if isinstance(dump, dict) and dump.get("provider") and dump.get("model"):
                model_settings = {
                    "provider": dump.get("provider"),
                    "model": dump.get("model"),
                    **({"baseUrl": dump["baseUrl"]} if dump.get("baseUrl") else {}),
                    **({"apiKey": dump["apiKey"]} if dump.get("apiKey") else {}),
                }
        result = _service(ctx).engineering.start(
            str(args.get("text") or ""), blueprint_id=args.get("blueprintId"),
            title=args.get("title"), autonomy=str(args.get("autonomy") or "edit_verify"),
            model_settings=model_settings,
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    if not result.get("created"):
        return _ok(f"Compose mode — {result.get('message', '')}", result)
    return _ok(
        f"Created engineering task {result['taskId']} (plan {result['planId']}, mode {result['mode']}) "
        f"with {len(result['acceptance'])} acceptance criteria.",
        result,
    )


async def _engineering_status(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).engineering.status(str(args.get("planId") or ""))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Plan {result.get('id')} — {result.get('status')}.", result)


async def _register_engineered_component(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        spec = UiComponentSpec.model_validate(args.get("spec") or {})
        result = _service(ctx).engineering.register_component(str(args.get("taskId") or ""), spec)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Registered component {result['componentId']} in the catalog; satisfied {len(result['satisfiedCriteria'])} criterion.", result)


async def _link_engineering_artifact(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).engineering.link_artifact(
            str(args.get("taskId") or ""), uri=str(args.get("uri") or ""),
            kind=str(args.get("kind") or "file"), label=args.get("label"),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Attached engineering evidence {result['uri']}.", result)


# ── mutation ──────────────────────────────────────────────────────────────────


async def _create_page(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).create_page(
            CreatePageInput(
                title=str(args.get("title") or ""),
                description=args.get("description"),
                kind=args.get("kind") or "page",
                scope=args.get("scope") or "personal",
                path=args.get("path"),
                tags=list(args.get("tags") or []),
                idempotency_key=args.get("idempotencyKey"),
            ),
            owner_id=_owner(ctx),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Created page {blueprint.title!r} ({blueprint.id}). Add widgets with ui_add_widget.", _bp(blueprint.model_dump(by_alias=True)))


async def _update_page(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).update_page(
            str(args.get("blueprintId") or ""),
            UpdatePageInput(title=args.get("title"), description=args.get("description"), path=args.get("path"), tags=args.get("tags")),
            owner_id=_owner(ctx),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Updated page {blueprint.title!r} (revision {blueprint.revision}).", _bp(blueprint.model_dump(by_alias=True)))


async def _duplicate_page(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).duplicate_page(str(args.get("blueprintId") or ""), owner_id=_owner(ctx), title=args.get("title"))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Duplicated to {blueprint.title!r} ({blueprint.id}).", _bp(blueprint.model_dump(by_alias=True)))


async def _add_widget(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).add_widget(
            AddWidgetInput(
                blueprint_id=str(args.get("blueprintId") or ""),
                component_id=str(args.get("componentId") or ""),
                instance_id=args.get("instanceId"),
                target=args.get("target"),
                config=dict(args.get("config") or {}),
                zone=args.get("zone"),
                height=args.get("height"),
                expected_revision=args.get("expectedRevision"),
            ),
            owner_id=_owner(ctx),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Added {args.get('componentId')} to {blueprint.title!r} (revision {blueprint.revision}).", _bp(blueprint.model_dump(by_alias=True)))


async def _remove_widget(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).remove_widget(WidgetRefInput(
            blueprint_id=str(args.get("blueprintId") or ""), instance_id=str(args.get("instanceId") or ""),
            expected_revision=args.get("expectedRevision"),
        ), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Removed {args.get('instanceId')} from {blueprint.title!r}.", _bp(blueprint.model_dump(by_alias=True)))


async def _move_widget(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).move_widget(MoveWidgetInput(
            blueprint_id=str(args.get("blueprintId") or ""), instance_id=str(args.get("instanceId") or ""),
            target=args.get("target"), expected_revision=args.get("expectedRevision"),
        ), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Moved {args.get('instanceId')} in {blueprint.title!r}.", _bp(blueprint.model_dump(by_alias=True)))


async def _reorder_widget(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).reorder_widget(ReorderWidgetInput(
            blueprint_id=str(args.get("blueprintId") or ""), instance_id=str(args.get("instanceId") or ""),
            to_index=int(args.get("toIndex") or 0), expected_revision=args.get("expectedRevision"),
        ), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Reordered {args.get('instanceId')} in {blueprint.title!r}.", _bp(blueprint.model_dump(by_alias=True)))


async def _resize_widget(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).resize_widget(ResizeWidgetInput(
            blueprint_id=str(args.get("blueprintId") or ""), instance_id=str(args.get("instanceId") or ""),
            height=args.get("height"), expected_revision=args.get("expectedRevision"),
        ), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Resized {args.get('instanceId')}.", _bp(blueprint.model_dump(by_alias=True)))


async def _update_widget_config(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).update_widget_config(UpdateConfigInput(
            blueprint_id=str(args.get("blueprintId") or ""), instance_id=str(args.get("instanceId") or ""),
            patch=dict(args.get("patch") or {}), expected_revision=args.get("expectedRevision"),
        ), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Reconfigured {args.get('instanceId')}.", _bp(blueprint.model_dump(by_alias=True)))


async def _set_column_count(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).set_column_count(SetColumnCountInput(
            blueprint_id=str(args.get("blueprintId") or ""), section_id=str(args.get("sectionId") or ""),
            count=int(args.get("count") or 1), expected_revision=args.get("expectedRevision"),
        ), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Set column count in {blueprint.title!r}.", _bp(blueprint.model_dump(by_alias=True)))


async def _set_column_weight(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).set_column_weight(SetColumnWeightInput(
            blueprint_id=str(args.get("blueprintId") or ""), column_id=str(args.get("columnId") or ""),
            weight=float(args.get("weight") or 1), expected_revision=args.get("expectedRevision"),
        ), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Set column weight in {blueprint.title!r}.", _bp(blueprint.model_dump(by_alias=True)))


async def _remove_section(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).remove_section(SectionRefInput(
            blueprint_id=str(args.get("blueprintId") or ""), section_id=str(args.get("sectionId") or ""),
            expected_revision=args.get("expectedRevision"),
        ), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Removed section from {blueprint.title!r}.", _bp(blueprint.model_dump(by_alias=True)))


async def _save_layout(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).save_layout(SaveLayoutInput(
            blueprint_id=str(args.get("blueprintId") or ""),
            layout=WorkspaceLayout.model_validate(args.get("layout") or {}),
            expected_revision=args.get("expectedRevision"),
        ), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Saved layout for {blueprint.title!r} (revision {blueprint.revision}).", _bp(blueprint.model_dump(by_alias=True)))


async def _restore_revision(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        blueprint = _service(ctx).restore_revision(RestoreRevisionInput(
            blueprint_id=str(args.get("blueprintId") or ""), revision=int(args.get("revision") or 1),
        ), owner_id=_owner(ctx))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Restored {blueprint.title!r} to a prior revision (now revision {blueprint.revision}).", _bp(blueprint.model_dump(by_alias=True)))


async def _preview_change(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).preview(
            str(args.get("blueprintId") or ""), list(args.get("ops") or []), owner_id=_owner(ctx),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Preview: {len(result['changes'])} change(s); would move r{result['currentRevision']} to r{result['nextRevision']}.", result)


_DEFS: list[tuple[str, str, dict[str, Any]]] = [
    ("ui_get_application_map", "Get the current UI map: the saved pages/workspaces and the component catalog summary.", {"type": "object", "properties": {}}),
    ("ui_get_current_page", "Get the page the user is viewing (by blueprintId or path) with its widget instances.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "path": {"type": "string"}}}),
    ("ui_get_component_catalog", "List/search the components available to compose. Filter by text, category or data source.", {"type": "object", "properties": {"text": {"type": "string"}, "category": {"type": "string"}, "dataSource": {"type": "string"}, "limit": {"type": "integer"}}}),
    ("ui_inspect_component", "Inspect one component's full schema: its configuration fields, data sources and actions.", {"type": "object", "properties": {"componentId": {"type": "string"}}, "required": ["componentId"]}),
    ("ui_get_layout", "Get the workspace layout tree of a blueprint by id.", {"type": "object", "properties": {"blueprintId": {"type": "string"}}, "required": ["blueprintId"]}),
    ("ui_get_capabilities", "Summarize the UI capabilities: component count, categories and data sources.", {"type": "object", "properties": {}}),
    ("ui_get_blueprint", "Get a full page/workspace blueprint by id.", {"type": "object", "properties": {"blueprintId": {"type": "string"}}, "required": ["blueprintId"]}),
    ("ui_get_operation_status", "Inspect the status of a previously executed UI operation by id.", {"type": "object", "properties": {"operationId": {"type": "string"}}, "required": ["operationId"]}),
    ("ui_list_blueprints", "List the saved pages and workspaces.", {"type": "object", "properties": {"limit": {"type": "integer"}}}),
    ("ui_classify_request", "Decide whether a UI request can be Composed from registered components or needs the Engineer (source-code) path. Call this FIRST for any UI change request.", {"type": "object", "properties": {"text": {"type": "string"}, "blueprintId": {"type": "string"}}, "required": ["text"]}),
    ("ui_start_engineering", "Create a durable engineering task (Task/Plan runtime) for a UI request that needs NEW functionality. Returns the task/plan ids. For Compose-mode requests it creates nothing and says so.", {"type": "object", "properties": {"text": {"type": "string"}, "blueprintId": {"type": "string"}, "title": {"type": "string"}, "autonomy": {"type": "string"}}, "required": ["text"]}),
    ("ui_engineering_status", "Get the status of a UI engineering plan (tasks, criteria, progress).", {"type": "object", "properties": {"planId": {"type": "string"}}, "required": ["planId"]}),
    ("ui_register_engineered_component", "After engineering a new component, register it in the UI catalog so Compose can use it, and satisfy the task's catalog criterion (engineer→compose closure).", {"type": "object", "properties": {"taskId": {"type": "string"}, "spec": {"type": "object"}}, "required": ["taskId", "spec"]}),
    ("ui_link_engineering_artifact", "Attach an engineering artifact (diff, screenshot, report) as evidence on an engineering task.", {"type": "object", "properties": {"taskId": {"type": "string"}, "uri": {"type": "string"}, "kind": {"type": "string"}, "label": {"type": "string"}}, "required": ["taskId", "uri"]}),
    ("ui_create_page", "Create a new page or workspace blueprint. Then add widgets to it.", {"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "kind": {"type": "string", "enum": ["page", "workspace"]}, "scope": {"type": "string", "enum": ["personal", "shared"]}, "path": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "idempotencyKey": {"type": "string"}}, "required": ["title"]}),
    ("ui_update_page", "Update a page's title, description, path or tags.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}, "path": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["blueprintId"]}),
    ("ui_duplicate_page", "Duplicate an existing page/workspace.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "title": {"type": "string"}}, "required": ["blueprintId"]}),
    ("ui_add_widget", "Add a registered component to a blueprint. Discovers ids via ui_get_component_catalog; validates config against the component schema.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "componentId": {"type": "string"}, "instanceId": {"type": "string"}, "target": {"type": "object"}, "config": {"type": "object"}, "zone": {"type": "string", "enum": ["left", "main", "right"]}, "height": {"type": "number"}, "expectedRevision": {"type": "integer"}}, "required": ["blueprintId", "componentId"]}),
    ("ui_remove_widget", "Remove a widget instance from a blueprint.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "instanceId": {"type": "string"}, "expectedRevision": {"type": "integer"}}, "required": ["blueprintId", "instanceId"]}),
    ("ui_move_widget", "Move a widget instance to a target section/column/index.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "instanceId": {"type": "string"}, "target": {"type": "object"}, "expectedRevision": {"type": "integer"}}, "required": ["blueprintId", "instanceId", "target"]}),
    ("ui_reorder_widget", "Reorder a widget within its column.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "instanceId": {"type": "string"}, "toIndex": {"type": "integer"}, "expectedRevision": {"type": "integer"}}, "required": ["blueprintId", "instanceId", "toIndex"]}),
    ("ui_resize_widget", "Set a widget instance's pinned height (null = content height).", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "instanceId": {"type": "string"}, "height": {"type": ["number", "null"]}, "expectedRevision": {"type": "integer"}}, "required": ["blueprintId", "instanceId"]}),
    ("ui_update_widget_config", "Merge configuration into a widget instance (validated against its schema).", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "instanceId": {"type": "string"}, "patch": {"type": "object"}, "expectedRevision": {"type": "integer"}}, "required": ["blueprintId", "instanceId", "patch"]}),
    ("ui_set_column_count", "Set a section's column count (1..4).", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "sectionId": {"type": "string"}, "count": {"type": "integer"}, "expectedRevision": {"type": "integer"}}, "required": ["blueprintId", "sectionId", "count"]}),
    ("ui_set_column_weight", "Set a column's relative width weight.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "columnId": {"type": "string"}, "weight": {"type": "number"}, "expectedRevision": {"type": "integer"}}, "required": ["blueprintId", "columnId", "weight"]}),
    ("ui_remove_section", "Remove a section from a blueprint.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "sectionId": {"type": "string"}, "expectedRevision": {"type": "integer"}}, "required": ["blueprintId", "sectionId"]}),
    ("ui_save_layout", "Replace a blueprint's whole layout (validated atomically).", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "layout": {"type": "object"}, "expectedRevision": {"type": "integer"}}, "required": ["blueprintId", "layout"]}),
    ("ui_restore_revision", "Restore a blueprint to an earlier retained revision (recorded as a new revision).", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "revision": {"type": "integer"}}, "required": ["blueprintId", "revision"]}),
    ("ui_preview_change", "Compute the result of a batch of operations WITHOUT saving it (dry run + diff).", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "ops": {"type": "array", "items": {"type": "object"}}}, "required": ["blueprintId", "ops"]}),
]

_HANDLERS = {
    "ui_get_application_map": _get_application_map,
    "ui_get_current_page": _get_current_page,
    "ui_get_component_catalog": _get_component_catalog,
    "ui_inspect_component": _inspect_component,
    "ui_get_layout": _get_layout,
    "ui_get_capabilities": _get_capabilities,
    "ui_get_blueprint": _get_blueprint,
    "ui_get_operation_status": _get_operation_status,
    "ui_list_blueprints": _list_blueprints,
    "ui_classify_request": _classify_request,
    "ui_start_engineering": _start_engineering,
    "ui_engineering_status": _engineering_status,
    "ui_register_engineered_component": _register_engineered_component,
    "ui_link_engineering_artifact": _link_engineering_artifact,
    "ui_create_page": _create_page,
    "ui_update_page": _update_page,
    "ui_duplicate_page": _duplicate_page,
    "ui_add_widget": _add_widget,
    "ui_remove_widget": _remove_widget,
    "ui_move_widget": _move_widget,
    "ui_reorder_widget": _reorder_widget,
    "ui_resize_widget": _resize_widget,
    "ui_update_widget_config": _update_widget_config,
    "ui_set_column_count": _set_column_count,
    "ui_set_column_weight": _set_column_weight,
    "ui_remove_section": _remove_section,
    "ui_save_layout": _save_layout,
    "ui_restore_revision": _restore_revision,
    "ui_preview_change": _preview_change,
}

READ_TOOLS = frozenset({
    "ui_get_application_map", "ui_get_current_page", "ui_get_component_catalog",
    "ui_inspect_component", "ui_get_layout", "ui_get_capabilities", "ui_get_blueprint",
    "ui_get_operation_status", "ui_list_blueprints", "ui_preview_change",
    "ui_classify_request", "ui_start_engineering", "ui_engineering_status",
    "ui_register_engineered_component", "ui_link_engineering_artifact",
})
MUTATION_TOOLS = frozenset(name for name, _, _ in _DEFS if name not in READ_TOOLS)
UI_TOOLS = tuple(name for name, _, _ in _DEFS)


def register_ui_tools(registry: ToolRegistry) -> list[str]:
    """Register the UI tools on the shared registry. Returns the names."""
    registered: list[str] = []
    for name, description, schema in _DEFS:
        if registry.get(name) is not None:
            continue
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema,
            handler=_HANDLERS[name], permission="read",  # agent-local UI config state
            risk="low", timeout_ms=20_000,
        ))
        registered.append(name)
    return registered


__all__ = ["MUTATION_TOOLS", "READ_TOOLS", "UI_TOOLS", "register_ui_tools"]

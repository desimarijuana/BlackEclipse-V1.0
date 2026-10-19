"""Agent-facing Eclipse SDK tools.

They expose the typed control plane to chat: create user widgets, inspect and
mutate the Command Center layout, and manage passphrase locks. The handlers
delegate to `EclipseSdk`; they own no state and execute no user code.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .locks import LockError
from .model import (
    SdkCreateLockInput,
    SdkDashboardAddWidgetInput,
    SdkDashboardMoveWidgetInput,
    SdkDashboardResizeWidgetInput,
    SdkDashboardSetColumnsInput,
    SdkDashboardSetZonesInput,
    SdkWidgetInput,
)
from .service import EclipseSdk, SdkError
from ..ui.service import UiError


def _ok(text: str, data: Optional[dict[str, Any]] = None) -> tuple[str, Any]:
    return text, data or {}


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, LockError):
        return f"{exc.code}: {exc.message}", {"error": exc.code, "lockId": exc.lock_id, "hint": exc.hint}
    if isinstance(exc, SdkError):
        return f"{exc.code}: {exc.message}", {"error": exc.code}
    if isinstance(exc, UiError):
        payload: dict[str, Any] = {"error": exc.code}
        if exc.issues:
            payload["issues"] = exc.issues
        return f"{exc.code}: {exc.message}", payload
    return f"SDK_ERROR: {exc}", {"error": "SDK_ERROR"}


def _service(ctx: ToolContext) -> EclipseSdk:
    service = getattr(ctx, "sdk_service", None)
    if service is None:
        from .bootstrap import get_sdk_service  # noqa: PLC0415

        service = get_sdk_service()
    if service is None:
        raise SdkError("SDK_UNAVAILABLE", "the Eclipse SDK runtime is unavailable", status_code=503)
    return service


def _dashboard_arg(args: dict[str, Any]) -> Optional[str]:
    value = args.get("dashboardId")
    return str(value).strip() if value else None


async def _capabilities(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).capabilities()
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    dashboards = result.get("dashboards") or {}
    return _ok(
        f"Eclipse SDK {result['sdkVersion']}: {result['widgets']['count']} user widget(s), "
        f"{dashboards.get('count', 0)} dashboard(s).",
        result,
    )


async def _widget_list(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        widgets = _service(ctx).list_widgets()
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"{len(widgets)} user widget(s).", {"widgets": widgets})


async def _widget_create(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        payload = {k: v for k, v in args.items() if v is not None}
        record = _service(ctx).create_widget(SdkWidgetInput(**payload), actor="chat")
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Created {record['componentId']} ({record['primitive']}).", {"widget": record})


async def _widget_delete(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        removed = _service(ctx).delete_widget(str(args.get("componentId") or ""), actor="chat")
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok("Removed the user widget." if removed else "No such user widget.", {"removed": removed})


async def _dashboard_list(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).dashboards.list()
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    lines = [
        f"{d['dashboardId']}  {d['title']}  r{d['revision']}  {d['widgetCount']} widget(s)"
        for d in result["dashboards"]
    ]
    return _ok("\n".join(lines) or "No Command Center layout has been published yet.", result)


async def _dashboard_active(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).dashboards.active()
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    dashboard = result["dashboard"]
    return _ok(f"Active dashboard: {dashboard['title']} ({dashboard['dashboardId']}, r{dashboard['revision']}).", result)


async def _dashboard_get(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).dashboards.get(_dashboard_arg(args))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    dashboard = result["dashboard"]
    return _ok(f"{dashboard['title']} ({dashboard['dashboardId']}, r{dashboard['revision']}).", result)


async def _dashboard_set_active(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).dashboards.set_active(str(args.get("dashboardId") or ""))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Active dashboard is now {result['activeDashboardId']}.", result)


async def _dashboard_add_widget(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        payload = {
            key: value for key, value in args.items()
            if key not in {"dashboardId"} and value is not None
        }
        result = _service(ctx).dashboards.add_widget(
            _dashboard_arg(args), SdkDashboardAddWidgetInput(**payload), actor="chat",
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    dashboard = result["dashboard"]
    return _ok(
        f"Added {args.get('componentId')} to {dashboard['title']} (revision {dashboard['revision']}).",
        result,
    )


async def _dashboard_remove_widget(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        from .model import SdkDashboardWidgetRefInput  # noqa: PLC0415

        result = _service(ctx).dashboards.remove_widget(
            _dashboard_arg(args),
            SdkDashboardWidgetRefInput(
                instance_id=str(args.get("instanceId") or ""),
                expected_revision=args.get("expectedRevision"),
            ),
            actor="chat",
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Removed {args.get('instanceId')} from the dashboard.", result)


async def _dashboard_move_widget(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        payload = {k: v for k, v in args.items() if k != "dashboardId" and v is not None}
        result = _service(ctx).dashboards.move_widget(
            _dashboard_arg(args), SdkDashboardMoveWidgetInput(**payload), actor="chat",
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Moved {args.get('instanceId')} in the dashboard.", result)


async def _dashboard_resize_widget(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        payload = {k: v for k, v in args.items() if k != "dashboardId" and v is not None}
        result = _service(ctx).dashboards.resize_widget(
            _dashboard_arg(args), SdkDashboardResizeWidgetInput(**payload), actor="chat",
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Resized {args.get('instanceId')}.", result)


async def _dashboard_set_columns(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        payload = {k: v for k, v in args.items() if k != "dashboardId" and v is not None}
        result = _service(ctx).dashboards.set_columns(
            _dashboard_arg(args), SdkDashboardSetColumnsInput(**payload), actor="chat",
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Set {args.get('count')} column(s) in the dashboard.", result)


async def _dashboard_set_zones(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        payload = {k: v for k, v in args.items() if k != "dashboardId" and v is not None}
        result = _service(ctx).dashboards.set_zones(
            _dashboard_arg(args), SdkDashboardSetZonesInput(**payload), actor="chat",
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok("Updated the dashboard zones.", result)


async def _dashboard_restore(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).dashboards.restore(
            _dashboard_arg(args), int(args.get("revision") or 1), actor="chat",
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Restored the dashboard to revision {args.get('revision')}.", result)


async def _dashboard_history(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).dashboards.history(_dashboard_arg(args))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"{len(result.get('revisions') or [])} retained revision(s).", result)


async def _lock_create(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        payload = {k: v for k, v in args.items() if v is not None}
        lock = _service(ctx).create_lock(SdkCreateLockInput(**payload), actor="chat")
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"Locked {lock.resource_type}:{lock.resource_id}.", {"lock": lock.model_dump(by_alias=True)})


async def _lock_list(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        locks = _service(ctx).list_locks(
            resource_type=args.get("resourceType"), resource_id=args.get("resourceId"),
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok(f"{len(locks)} lock(s).", {"locks": [lock.model_dump(by_alias=True) for lock in locks]})


async def _lock_unlock(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).unlock(str(args.get("lockId") or ""), str(args.get("passphrase") or ""))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok("Unlocked.", result)


async def _lock_remove(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        removed = _service(ctx).remove_lock(
            str(args.get("lockId") or ""), passphrase=args.get("passphrase"), actor="chat",
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok("Removed the lock." if removed else "No such lock.", {"removed": removed})


_DEFS: list[tuple[str, str, dict[str, Any]]] = [
    ("sdk_capabilities", "Summarize the Eclipse SDK control plane: user widgets, dashboards, pages, portfolio and locks.", {"type": "object", "properties": {}}),
    ("sdk_widget_list", "List the user's declarative widgets.", {"type": "object", "properties": {}}),
    ("sdk_widget_create", "Create a declarative user widget from a closed primitive (data-table, metric-card, charts, list, markdown, status-indicator, empty-state, error-state, clock).", {"type": "object", "properties": {"slug": {"type": "string"}, "label": {"type": "string"}, "description": {"type": "string"}, "icon": {"type": "string"}, "category": {"type": "string"}, "primitive": {"type": "string"}, "source": {"type": "string"}, "surface": {"type": "string", "enum": ["dashboard", "page", "both"]}, "config": {"type": "object"}, "sizes": {"type": "array", "items": {"type": "string"}}}, "required": ["slug", "label"]}),
    ("sdk_widget_delete", "Delete a user widget definition by component id (e.g. sdk.my-clock).", {"type": "object", "properties": {"componentId": {"type": "string"}}, "required": ["componentId"]}),
    ("sdk_dashboard_list", "List the durable Command Center dashboards (mirror blueprints) with revision and widget count.", {"type": "object", "properties": {}}),
    ("sdk_dashboard_active", "Read the active Command Center dashboard and its live layout.", {"type": "object", "properties": {}}),
    ("sdk_dashboard_get", "Read one Command Center dashboard by dashboard id, blueprint id or title. Omit dashboardId for the active board.", {"type": "object", "properties": {"dashboardId": {"type": "string"}}}),
    ("sdk_dashboard_set_active", "Mark a dashboard as the active Command Center board.", {"type": "object", "properties": {"dashboardId": {"type": "string"}}, "required": ["dashboardId"]}),
    ("sdk_dashboard_add_widget", "Add a registered component to a Command Center dashboard. Use componentId 'clock' to add a live clock. Defaults to the active board and packs into the shortest main column.", {"type": "object", "properties": {"dashboardId": {"type": "string"}, "componentId": {"type": "string"}, "instanceId": {"type": "string"}, "config": {"type": "object"}, "target": {"type": "object"}, "zone": {"type": "string", "enum": ["left", "main", "right"]}, "height": {"type": "number"}, "expectedRevision": {"type": "integer"}}, "required": ["componentId"]}),
    ("sdk_dashboard_remove_widget", "Remove a widget instance from a Command Center dashboard.", {"type": "object", "properties": {"dashboardId": {"type": "string"}, "instanceId": {"type": "string"}, "expectedRevision": {"type": "integer"}}, "required": ["instanceId"]}),
    ("sdk_dashboard_move_widget", "Move a widget instance to a target section/column/index in a Command Center dashboard.", {"type": "object", "properties": {"dashboardId": {"type": "string"}, "instanceId": {"type": "string"}, "target": {"type": "object"}, "expectedRevision": {"type": "integer"}}, "required": ["instanceId", "target"]}),
    ("sdk_dashboard_resize_widget", "Set a Command Center widget instance's pinned height (null = content height).", {"type": "object", "properties": {"dashboardId": {"type": "string"}, "instanceId": {"type": "string"}, "height": {"type": ["number", "null"]}, "expectedRevision": {"type": "integer"}}, "required": ["instanceId"]}),
    ("sdk_dashboard_set_columns", "Set a section's column count (1..4) on a Command Center dashboard.", {"type": "object", "properties": {"dashboardId": {"type": "string"}, "sectionId": {"type": "string"}, "count": {"type": "integer"}, "expectedRevision": {"type": "integer"}}, "required": ["sectionId", "count"]}),
    ("sdk_dashboard_set_zones", "Show/hide side zones or set zone widths on a Command Center dashboard.", {"type": "object", "properties": {"dashboardId": {"type": "string"}, "hiddenZones": {"type": "array", "items": {"type": "string"}}, "zoneWidths": {"type": "object"}, "expectedRevision": {"type": "integer"}}}),
    ("sdk_dashboard_history", "List the retained revisions of a Command Center dashboard.", {"type": "object", "properties": {"dashboardId": {"type": "string"}}}),
    ("sdk_dashboard_restore", "Restore a Command Center dashboard to an earlier retained revision (recorded as a new revision, so it is undoable).", {"type": "object", "properties": {"dashboardId": {"type": "string"}, "revision": {"type": "integer"}}, "required": ["revision"]}),
    ("sdk_lock_list", "List passphrase locks (optionally by resourceType/resourceId).", {"type": "object", "properties": {"resourceType": {"type": "string"}, "resourceId": {"type": "string"}}}),
    ("sdk_lock_create", "Lock a page, widget, portfolio, design, dashboard or theme. Subsequent mutations without a valid unlock token are refused.", {"type": "object", "properties": {"resourceType": {"type": "string", "enum": ["page", "widget", "portfolio", "design", "dashboard", "theme"]}, "resourceId": {"type": "string"}, "passphrase": {"type": "string"}, "label": {"type": "string"}, "hint": {"type": "string"}}, "required": ["resourceType", "resourceId", "passphrase"]}),
    ("sdk_lock_unlock", "Unlock a locked resource with its passphrase.", {"type": "object", "properties": {"lockId": {"type": "string"}, "passphrase": {"type": "string"}}, "required": ["lockId", "passphrase"]}),
    ("sdk_lock_remove", "Remove a lock. Requires the unlock token or the passphrase.", {"type": "object", "properties": {"lockId": {"type": "string"}, "passphrase": {"type": "string"}}, "required": ["lockId"]}),
]

_HANDLERS = {
    "sdk_capabilities": _capabilities,
    "sdk_widget_list": _widget_list,
    "sdk_widget_create": _widget_create,
    "sdk_widget_delete": _widget_delete,
    "sdk_dashboard_list": _dashboard_list,
    "sdk_dashboard_active": _dashboard_active,
    "sdk_dashboard_get": _dashboard_get,
    "sdk_dashboard_set_active": _dashboard_set_active,
    "sdk_dashboard_add_widget": _dashboard_add_widget,
    "sdk_dashboard_remove_widget": _dashboard_remove_widget,
    "sdk_dashboard_move_widget": _dashboard_move_widget,
    "sdk_dashboard_resize_widget": _dashboard_resize_widget,
    "sdk_dashboard_set_columns": _dashboard_set_columns,
    "sdk_dashboard_set_zones": _dashboard_set_zones,
    "sdk_dashboard_history": _dashboard_history,
    "sdk_dashboard_restore": _dashboard_restore,
    "sdk_lock_list": _lock_list,
    "sdk_lock_create": _lock_create,
    "sdk_lock_unlock": _lock_unlock,
    "sdk_lock_remove": _lock_remove,
}

READ_TOOLS = frozenset({
    "sdk_capabilities", "sdk_widget_list", "sdk_dashboard_list", "sdk_dashboard_active",
    "sdk_dashboard_get", "sdk_dashboard_history", "sdk_lock_list",
})
SDK_TOOLS = tuple(name for name, _, _ in _DEFS)


def register_sdk_tools(registry: ToolRegistry) -> list[str]:
    registered: list[str] = []
    for name, description, schema in _DEFS:
        if registry.get(name) is not None:
            continue
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema,
            handler=_HANDLERS[name], permission="read",
            risk="low", timeout_ms=20_000,
        ))
        registered.append(name)
    return registered


__all__ = ["READ_TOOLS", "SDK_TOOLS", "register_sdk_tools"]

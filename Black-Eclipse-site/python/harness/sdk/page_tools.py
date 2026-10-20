"""Agent tools for saved pages through the Eclipse SDK."""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext
from .model import SdkCreatePageInput, SdkPageWidget
from .service import EclipseSdk, SdkError


def _service(ctx: ToolContext) -> EclipseSdk:
    service = getattr(ctx, "sdk_service", None)
    if service is None:
        from .bootstrap import get_sdk_service  # noqa: PLC0415

        service = get_sdk_service()
    if service is None:
        raise SdkError("SDK_UNAVAILABLE", "the Eclipse SDK runtime is unavailable", status_code=503)
    return service


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, SdkError):
        return f"{exc.code}: {exc.message}", {"error": exc.code}
    return f"SDK_ERROR: {exc}", {"error": "SDK_ERROR"}


async def _page_list(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        result = _service(ctx).list_pages()
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    pages = result.get("blueprints") or []
    lines = [f'{p["id"]}  {p["title"]}  {p.get("path") or ""}' for p in pages]
    return _ok("\n".join(lines) or "No saved pages yet.", result)


async def _page_create(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        payload = {k: v for k, v in args.items() if v is not None}
        result = _service(ctx).create_page(SdkCreatePageInput(**payload), actor="chat")
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    blueprint = result.get("blueprint") or {}
    path = blueprint.get("path") or ""
    suffix = f" at {path}" if path else ""
    return _ok(f'Created the page "{blueprint.get("title")}"{suffix}.', result)


async def _page_add_widget(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        widget = SdkPageWidget(
            component_id=str(args.get("componentId") or ""),
            config=dict(args.get("config") or {}),
            height=args.get("height"),
        )
        result = _service(ctx).add_page_widget(
            str(args.get("blueprintId") or ""), widget, owner_id=None, actor="chat",
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    blueprint = result.get("blueprint") or {}
    return _ok(f'Added {widget.component_id} to "{blueprint.get("title")}".', result)


async def _page_update(args: dict[str, Any], ctx: ToolContext) -> Any:
    blueprint_id = str(args.get("blueprintId") or "").strip()
    if not blueprint_id:
        return ("A blueprintId is required. Use sdk_page_list to discover page ids.", {"error": "PAGE_ID_REQUIRED"})
    patch = {
        key: args[key] for key in ("title", "description", "path", "icon", "tags")
        if key in args and args[key] is not None
    }
    if not patch:
        return ("Nothing to change: provide title, description, path, icon or tags.", {"error": "PAGE_PATCH_EMPTY"})
    try:
        result = _service(ctx).update_page(blueprint_id, patch, actor="chat")
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    blueprint = result.get("blueprint") or {}
    return _ok(f'Updated the page "{blueprint.get("title") or blueprint_id}".', result)


async def _page_delete(args: dict[str, Any], ctx: ToolContext) -> Any:
    blueprint_id = str(args.get("blueprintId") or "").strip()
    if not blueprint_id:
        return ("A blueprintId is required. Use sdk_page_list to discover page ids.", {"error": "PAGE_ID_REQUIRED"})
    try:
        removed = _service(ctx).delete_page(blueprint_id, actor="chat")
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    return _ok("Deleted the page." if removed else "No such page.", {"removed": removed})


def _ok(text: str, data: Optional[dict[str, Any]] = None) -> tuple[str, Any]:
    return text, data or {}


PAGE_DEFS: list[tuple[str, str, dict[str, Any]]] = [
    ("sdk_page_list", "List the user's saved pages and workspaces.", {"type": "object", "properties": {}}),
    ("sdk_page_create", "Create a saved page/workspace from registered components. Use this for 'create a page called Rates Desk and put it in the nav'; saved pages appear in the main sidebar automatically.", {"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "path": {"type": "string"}, "icon": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "widgets": {"type": "array", "items": {"type": "object", "properties": {"componentId": {"type": "string"}, "config": {"type": "object"}, "height": {"type": "number"}}, "required": ["componentId"]}}, "idempotencyKey": {"type": "string"}}, "required": ["title"]}),
    ("sdk_page_add_widget", "Add a registered component to an existing saved page. Use sdk_page_list to discover page ids and sdk_widget_list / ui_* for component ids.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "componentId": {"type": "string"}, "config": {"type": "object"}, "height": {"type": "number"}}, "required": ["blueprintId", "componentId"]}),
    ("sdk_page_update", "Update a saved page's title, description, path, icon or tags. Use sdk_page_list to discover page ids.", {"type": "object", "properties": {"blueprintId": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}, "path": {"type": "string"}, "icon": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["blueprintId"]}),
    ("sdk_page_delete", "Delete a saved page by blueprint id. Use sdk_page_list to discover page ids.", {"type": "object", "properties": {"blueprintId": {"type": "string"}}, "required": ["blueprintId"]}),
]

PAGE_HANDLERS = {
    "sdk_page_list": _page_list,
    "sdk_page_create": _page_create,
    "sdk_page_add_widget": _page_add_widget,
    "sdk_page_update": _page_update,
    "sdk_page_delete": _page_delete,
}

PAGE_READ_TOOLS = frozenset({"sdk_page_list"})
PAGE_TOOLS = tuple(name for name, _, _ in PAGE_DEFS)


__all__ = ["PAGE_DEFS", "PAGE_HANDLERS", "PAGE_READ_TOOLS", "PAGE_TOOLS"]

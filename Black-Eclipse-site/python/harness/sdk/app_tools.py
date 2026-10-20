"""Agent tools for the Eclipse app shell (nav order/visibility + open a tab).

The app-wide nav config lives in the Next.js front door (JDDS `SystemConfig`),
not in the Python runtime. These tools call `/api/sdk/app*` over the authenticated
loopback callback, exactly like `sdk_theme_*`.
"""

from __future__ import annotations

from typing import Any, Optional

from ..tools import ToolContext
from .callback import callback_base, callback_headers


def _ok(text: str, data: Optional[dict[str, Any]] = None) -> tuple[str, Any]:
    return text, data or {}


async def _app_request(
    method: str, path: str, *, body: Optional[dict[str, Any]] = None,
) -> tuple[int, dict[str, Any]]:
    try:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method,
                f"{callback_base()}/api/sdk/app{path}",
                headers=callback_headers(),
                json=body,
            )
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            payload = {}
        return response.status_code, payload if isinstance(payload, dict) else {}
    except Exception as exc:  # noqa: BLE001 - an unreachable app is reported honestly
        return 0, {"error": str(exc)}


def _failed(status: int, payload: dict[str, Any]) -> Optional[tuple[str, Any]]:
    if status == 0:
        return (
            "The app shell service is unavailable (the app did not answer the loopback callback).",
            {"error": "APP_UNAVAILABLE"},
        )
    if status >= 400:
        message = payload.get("error") or payload.get("detail") or f"app request failed (HTTP {status})"
        return (f"Could not change the app shell: {message}.", {"error": "APP_REQUEST_FAILED", "status": status})
    return None


def _nav_summary(payload: dict[str, Any]) -> str:
    nav = payload.get("nav") if isinstance(payload.get("nav"), dict) else {}
    sections = nav.get("sections") if isinstance(nav.get("sections"), list) else []
    visible = [
        str(section.get("id")) for section in sections
        if isinstance(section, dict) and section.get("enabled") is not False
    ]
    hidden = [
        str(section.get("id")) for section in sections
        if isinstance(section, dict) and section.get("enabled") is False
    ]
    mode = nav.get("mode") or "terminal"
    text = f"Nav mode: {mode}. Visible: {', '.join(visible) or 'none'}."
    if hidden:
        text += f" Hidden: {', '.join(hidden)}."
    return text


async def _get(args: dict[str, Any], ctx: ToolContext) -> Any:
    status, payload = await _app_request("GET", "")
    failed = _failed(status, payload)
    if failed:
        return failed
    return (f"Eclipse app shell. {_nav_summary(payload)}", payload)


async def _nav_update(args: dict[str, Any], ctx: ToolContext) -> Any:
    sections = args.get("sections")
    mode = args.get("mode")
    if sections is None and mode is None:
        return ("Nothing to change: provide sections and/or mode.", {"error": "APP_NAV_EMPTY"})
    nav: dict[str, Any] = {}
    if sections is not None:
        nav["sections"] = sections
    if mode is not None:
        nav["mode"] = mode
    status, payload = await _app_request("PUT", "", body={"nav": nav})
    failed = _failed(status, payload)
    if failed:
        return failed
    return (f"Updated the app navigation. {_nav_summary(payload)}", payload)


async def _nav_reset(args: dict[str, Any], ctx: ToolContext) -> Any:
    status, payload = await _app_request("DELETE", "")
    failed = _failed(status, payload)
    if failed:
        return failed
    return ("Reset the app navigation to the shipped order.", payload)


async def _open(args: dict[str, Any], ctx: ToolContext) -> Any:
    tab = str(args.get("tab") or "").strip()
    if not tab:
        return ("A tab is required.", {"error": "APP_TAB_REQUIRED"})
    target = {key: value for key, value in args.items() if value is not None}
    target["tab"] = tab
    status, payload = await _app_request("POST", "/navigate", body={"target": target})
    failed = _failed(status, payload)
    if failed:
        return failed
    return (f"Asked the open app to open {tab}.", payload)


APP_DEFS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "sdk_app_get",
        "Read the app-wide sidebar navigation (visible/hidden sections, order, nav mode).",
        {"type": "object", "properties": {}},
    ),
    (
        "sdk_app_nav_update",
        "Reorder, hide or show sidebar sections and/or set the nav mode app-wide. "
        "Pass the full desired order in `sections`; missing sections are appended.",
        {
            "type": "object",
            "properties": {
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "enabled": {"type": "boolean"},
                        },
                        "required": ["id"],
                    },
                },
                "mode": {"type": "string", "enum": ["terminal", "agentic", "bots", "graph"]},
            },
        },
    ),
    (
        "sdk_app_nav_reset",
        "Reset the sidebar navigation to the shipped order and show every section.",
        {"type": "object", "properties": {}},
    ),
    (
        "sdk_app_open",
        "Open an Eclipse surface in the running app. Use tab 'dashboard' for the Command Center, "
        "'pages' with `page` for a saved page, or any other AppTab id. Optional `dashboardId` "
        "selects a Command Center board.",
        {
            "type": "object",
            "properties": {
                "tab": {"type": "string"},
                "page": {"type": "string"},
                "dashboardId": {"type": "string"},
                "subroute": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["tab"],
        },
    ),
]

APP_HANDLERS = {
    "sdk_app_get": _get,
    "sdk_app_nav_update": _nav_update,
    "sdk_app_nav_reset": _nav_reset,
    "sdk_app_open": _open,
}

APP_READ_TOOLS = frozenset({"sdk_app_get"})
APP_TOOLS = tuple(name for name, _, _ in APP_DEFS)


__all__ = ["APP_DEFS", "APP_HANDLERS", "APP_READ_TOOLS", "APP_TOOLS"]

"""Agent tools for the app-wide Eclipse theme.

The theme is front-door-owned (JDDS `SystemConfig`, served at `/api/theme` and
`/api/sdk/theme`). These tools call the SDK theme routes over the loopback
callback with the operator token, exactly like the Journal write path. The
server builds, validates and persists the ThemeSpec; no CSS or arbitrary code
crosses the boundary.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

from ..tools import ToolContext
from .callback import callback_base, callback_headers

THEME_SPEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "description": "Optional preset name."},
        "basePreset": {"type": "string", "description": "Shipped preset id, e.g. eclipse, midnight, white."},
        "brand": {"type": "string", "description": "Brand hex color; drives primary and bullish."},
        "scheme": {"type": "string", "enum": ["dark", "light"]},
        "density": {"type": "string", "enum": ["compact", "comfortable", "spacious"]},
        "radius": {"type": "number", "minimum": 0, "maximum": 1.6},
        "shadow": {"type": "string", "enum": ["none", "soft", "medium", "dramatic"]},
        "background": {"type": "string", "enum": ["solid", "gradient", "grid"]},
        "glass": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "enabled": {"type": "boolean"},
                "blur": {"type": "number", "minimum": 0, "maximum": 60},
                "opacity": {"type": "number", "minimum": 0, "maximum": 1},
                "tint": {"type": "string", "description": "Hex color."},
            },
        },
        "sidebar": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "tint": {"type": "string", "description": "Hex color."},
                "opacity": {"type": "number", "minimum": 0, "maximum": 1},
                "blur": {"type": "number", "minimum": 0, "maximum": 60},
            },
        },
        "fontUi": {"type": "string"},
        "fontHeading": {"type": "string"},
        "fontMono": {"type": "string"},
        "appName": {"type": "string"},
        "logoText": {"type": "string"},
        "logoUrl": {"type": "string", "description": "http(s) or data:image URL, max 200 kB."},
    },
}


async def _theme_request(
    method: str, path: str, *, body: Optional[dict[str, Any]] = None,
) -> tuple[int, dict[str, Any]]:
    try:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method, f"{callback_base()}/api/sdk/theme{path}", headers=callback_headers(), json=body,
            )
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            payload = {}
        return response.status_code, payload if isinstance(payload, dict) else {}
    except Exception as exc:  # noqa: BLE001 - an unreachable app is reported honestly
        return 0, {"error": str(exc)}


def _failed(status: int, payload: dict[str, Any]) -> tuple[str, Any] | None:
    if status == 0:
        return (
            "The theme service is unavailable (the app did not answer the loopback callback).",
            {"error": "THEME_UNAVAILABLE"},
        )
    if status >= 400:
        issues = payload.get("issues")
        message = payload.get("error") or f"theme request failed (HTTP {status})"
        data: dict[str, Any] = {"error": "THEME_REQUEST_FAILED", "status": status}
        if issues:
            data["issues"] = issues
        return (f"Could not change the theme: {message}.", data)
    return None


async def _get(args: dict[str, Any], ctx: ToolContext) -> Any:
    status, payload = await _theme_request("GET", "")
    failed = _failed(status, payload)
    if failed:
        return failed
    theme = payload.get("theme") or {}
    saved = payload.get("savedPresets") or []
    return (
        f'Theme: {theme.get("appName") or "Eclipse"} ({theme.get("scheme") or "dark"}); '
        f'{len(saved)} saved preset(s).',
        payload,
    )


async def _create(args: dict[str, Any], ctx: ToolContext) -> Any:
    status, payload = await _theme_request("POST", "", body={"spec": args.get("spec") or {}})
    failed = _failed(status, payload)
    if failed:
        return failed
    theme = payload.get("theme") or {}
    return (
        f'Applied the theme "{theme.get("appName") or "Custom"}" app-wide.',
        payload,
    )


async def _apply(args: dict[str, Any], ctx: ToolContext) -> Any:
    status, payload = await _theme_request("PUT", "", body={"patch": args.get("patch") or {}})
    failed = _failed(status, payload)
    if failed:
        return failed
    return ("Applied the theme patch app-wide.", payload)


async def _apply_preset(args: dict[str, Any], ctx: ToolContext) -> Any:
    preset = str(args.get("preset") or args.get("name") or "").strip()
    status, payload = await _theme_request("POST", "/presets/apply", body={"preset": preset})
    failed = _failed(status, payload)
    if failed:
        return failed
    theme = payload.get("theme") or {}
    return (f'Applied the theme preset "{preset}" ({theme.get("scheme") or "dark"}).', payload)


async def _list_presets(args: dict[str, Any], ctx: ToolContext) -> Any:
    status, payload = await _theme_request("GET", "/presets")
    failed = _failed(status, payload)
    if failed:
        return failed
    presets = payload.get("presets") or []
    names = [str(p.get("name")) for p in presets if isinstance(p, dict) and p.get("name")]
    return (
        f"{len(names)} saved theme preset(s): {', '.join(names)}" if names else "No saved theme presets.",
        payload,
    )


async def _save_preset(args: dict[str, Any], ctx: ToolContext) -> Any:
    status, payload = await _theme_request(
        "POST", "/presets",
        body={"name": args.get("name"), "spec": args.get("spec") or {}},
    )
    failed = _failed(status, payload)
    if failed:
        return failed
    preset = payload.get("preset") or {}
    return (f'Saved the theme preset "{preset.get("name") or args.get("name")}".', payload)


async def _delete_preset(args: dict[str, Any], ctx: ToolContext) -> Any:
    name = str(args.get("name") or "").strip()
    status, payload = await _theme_request("DELETE", f"/presets/{quote(name, safe='')}")
    failed = _failed(status, payload)
    if failed:
        return failed
    return (f'Deleted the theme preset "{name}".', payload)


async def _reset(args: dict[str, Any], ctx: ToolContext) -> Any:
    status, payload = await _theme_request("DELETE", "")
    failed = _failed(status, payload)
    if failed:
        return failed
    return ("Reset the app-wide theme to the shipped Eclipse default.", payload)


THEME_DEFS: list[tuple[str, str, dict[str, Any]]] = [
    ("sdk_theme_get", "Read the app-wide theme and its saved presets.", {"type": "object", "properties": {}}),
    ("sdk_theme_create", "Create, validate and apply a theme app-wide from a closed ThemeSpec. Use for requests like 'cyberpunk neon magenta dark, tight radius'. No CSS or code is accepted.", {"type": "object", "properties": {"spec": THEME_SPEC_SCHEMA}, "required": ["spec"]}),
    ("sdk_theme_apply", "Patch the app-wide theme with existing ThemePatch fields (colors, glass, sidebar, density, radius, fonts, appName, logoUrl).", {"type": "object", "properties": {"patch": {"type": "object"}}, "required": ["patch"]}),
    ("sdk_theme_apply_preset", "Apply a shipped preset id (eclipse, midnight, white, ...) or a saved theme preset by name.", {"type": "object", "properties": {"preset": {"type": "string"}}, "required": ["preset"]}),
    ("sdk_theme_list_presets", "List the app-wide saved theme presets.", {"type": "object", "properties": {}}),
    ("sdk_theme_save_preset", "Save a ThemeSpec as a named app-wide theme preset (or overwrite an existing name).", {"type": "object", "properties": {"name": {"type": "string"}, "spec": THEME_SPEC_SCHEMA}, "required": ["name", "spec"]}),
    ("sdk_theme_delete_preset", "Delete a saved app-wide theme preset by name. Shipped presets cannot be deleted.", {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}),
    ("sdk_theme_reset", "Reset the app-wide theme to the shipped Eclipse default.", {"type": "object", "properties": {}}),
]

THEME_HANDLERS = {
    "sdk_theme_get": _get,
    "sdk_theme_create": _create,
    "sdk_theme_apply": _apply,
    "sdk_theme_apply_preset": _apply_preset,
    "sdk_theme_list_presets": _list_presets,
    "sdk_theme_save_preset": _save_preset,
    "sdk_theme_delete_preset": _delete_preset,
    "sdk_theme_reset": _reset,
}

THEME_READ_TOOLS = frozenset({"sdk_theme_get", "sdk_theme_list_presets"})
THEME_TOOLS = tuple(name for name, _, _ in THEME_DEFS)


__all__ = [
    "THEME_DEFS",
    "THEME_HANDLERS",
    "THEME_READ_TOOLS",
    "THEME_SPEC_SCHEMA",
    "THEME_TOOLS",
]

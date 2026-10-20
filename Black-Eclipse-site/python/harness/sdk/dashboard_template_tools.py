"""Agent tools for Command Center persona templates and reset.

The templates are TypeScript data (`src/lib/dashboard/templates.ts`), so these
tools call the front door's `/api/sdk/dashboards/*/template` routes over the
loopback callback. The route builds the layout and writes it through the
revision-guarded Python layout API; no template copy lives in Python.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

from ..tools import ToolContext
from .callback import callback_base, callback_headers
from .service import SdkError


def _ok(text: str, data: Optional[dict[str, Any]] = None) -> tuple[str, Any]:
    return text, data or {}


async def _dashboard_request(
    method: str, path: str, *, body: Optional[dict[str, Any]] = None,
) -> tuple[int, dict[str, Any]]:
    try:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                f"{callback_base()}/api/sdk/dashboards{path}",
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
            "The dashboard template service is unavailable (the app did not answer the loopback callback).",
            {"error": "DASHBOARD_TEMPLATE_UNAVAILABLE"},
        )
    if status >= 400:
        message = payload.get("error") or payload.get("detail") or f"template request failed (HTTP {status})"
        return (f"Could not change the dashboard: {message}.", {"error": "DASHBOARD_TEMPLATE_FAILED", "status": status})
    return None


def _service(ctx: Optional[ToolContext]) -> Any:
    service = getattr(ctx, "sdk_service", None) if ctx is not None else None
    if service is None:
        from .bootstrap import get_sdk_service  # noqa: PLC0415

        service = get_sdk_service()
    return service


def _dashboard_id(args: dict[str, Any], ctx: Optional[ToolContext]) -> str:
    raw = str(args.get("dashboardId") or "").strip()
    if raw:
        return raw
    service = _service(ctx)
    if service is None:
        raise SdkError("SDK_UNAVAILABLE", "the Eclipse SDK runtime is unavailable", status_code=503)
    result = service.dashboards.active()
    dashboard = result.get("dashboard") or {}
    raw = str(dashboard.get("dashboardId") or "").strip()
    if not raw:
        raise SdkError("SDK_DASHBOARD_NOT_FOUND", "no active Command Center dashboard", status_code=404)
    return raw


def _options(args: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    market = str(args.get("market") or "").strip()
    if market:
        options["market"] = market
    revision = args.get("expectedRevision")
    if isinstance(revision, int) and revision > 0:
        options["expectedRevision"] = revision
    return options


async def _templates(args: dict[str, Any], ctx: ToolContext) -> Any:
    status, payload = await _dashboard_request("GET", "/templates")
    failed = _failed(status, payload)
    if failed:
        return failed
    templates = payload.get("templates") or []
    lines = [f'{t.get("id")}  {t.get("name")}' for t in templates if isinstance(t, dict)]
    return (_ok("\n".join(lines) or "No dashboard templates.", payload))


async def _apply_template(args: dict[str, Any], ctx: ToolContext) -> Any:
    template_id = str(args.get("templateId") or "").strip()
    if not template_id:
        return ("A templateId is required. Use sdk_dashboard_templates to list them.", {"error": "TEMPLATE_REQUIRED"})
    try:
        dashboard_id = _dashboard_id(args, ctx)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    status, payload = await _dashboard_request(
        "POST",
        f"/{quote(dashboard_id, safe='')}/template",
        body={"templateId": template_id, **_options(args)},
    )
    failed = _failed(status, payload)
    if failed:
        return failed
    dashboard = payload.get("dashboard") or {}
    return (
        f'Applied the "{template_id}" template to {dashboard.get("title") or dashboard_id} '
        f'(revision {dashboard.get("revision")}).',
        payload,
    )


async def _reset(args: dict[str, Any], ctx: ToolContext) -> Any:
    try:
        dashboard_id = _dashboard_id(args, ctx)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    status, payload = await _dashboard_request(
        "POST",
        f"/{quote(dashboard_id, safe='')}/reset",
        body=_options(args),
    )
    failed = _failed(status, payload)
    if failed:
        return failed
    dashboard = payload.get("dashboard") or {}
    return (
        f'Reset {dashboard.get("title") or dashboard_id} to the default board '
        f'(revision {dashboard.get("revision")}).',
        payload,
    )


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, SdkError):
        return (f"{exc.code}: {exc.message}", {"error": exc.code})
    return (f"DASHBOARD_TEMPLATE_ERROR: {exc}", {"error": "DASHBOARD_TEMPLATE_ERROR"})


DASHBOARD_TEMPLATE_DEFS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "sdk_dashboard_templates",
        "List the Command Center persona templates (tape-reader, rates-desk, allocator, ...).",
        {"type": "object", "properties": {}},
    ),
    (
        "sdk_dashboard_apply_template",
        "Replace a Command Center board with a persona template (centre bands + side rails). "
        "Defaults to the active dashboard. Use for 'reset my command center to the rates template'. "
        "If the user wants to see it, follow with sdk_app_open {tab: 'dashboard'}.",
        {
            "type": "object",
            "properties": {
                "templateId": {"type": "string"},
                "dashboardId": {"type": "string"},
                "market": {"type": "string", "description": "US, FOREX, COMMODITIES or CRYPTO; drives the right rail."},
                "expectedRevision": {"type": "integer"},
            },
            "required": ["templateId"],
        },
    ),
    (
        "sdk_dashboard_reset",
        "Reset a Command Center board to the shipped default board/template. Defaults to the active dashboard. "
        "If the user wants to see it, follow with sdk_app_open {tab: 'dashboard'}.",
        {
            "type": "object",
            "properties": {
                "dashboardId": {"type": "string"},
                "market": {"type": "string"},
                "expectedRevision": {"type": "integer"},
            },
        },
    ),
]

DASHBOARD_TEMPLATE_HANDLERS = {
    "sdk_dashboard_templates": _templates,
    "sdk_dashboard_apply_template": _apply_template,
    "sdk_dashboard_reset": _reset,
}

DASHBOARD_TEMPLATE_READ_TOOLS = frozenset({"sdk_dashboard_templates"})
DASHBOARD_TEMPLATE_TOOLS = tuple(name for name, _, _ in DASHBOARD_TEMPLATE_DEFS)


__all__ = [
    "DASHBOARD_TEMPLATE_DEFS",
    "DASHBOARD_TEMPLATE_HANDLERS",
    "DASHBOARD_TEMPLATE_READ_TOOLS",
    "DASHBOARD_TEMPLATE_TOOLS",
]

"""Browser admin handlers — sessions, profiles, vault and device emulation.

These are the tools that manage the browser runtime itself rather than drive a
page, so they live in their own module. Each returns `(text, data)` and uses the
shared helpers in `tool_support.py`; registration is composed in `tools.py`.
"""

from __future__ import annotations

from typing import Any

from ..tools import ToolContext
from .errors import BrowserError, BrowserUnavailable
from .tool_support import emit, manager, ok, refusal, session_of, unavailable


async def _launch_or_create(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    # Imported lazily to avoid a cycle (tools.py imports this module's table).
    from . import tools as tools_mod  # noqa: PLC0415

    return await tools_mod._launch(args, ctx)


async def close(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    from . import tools as tools_mod  # noqa: PLC0415

    return await tools_mod._close(args, ctx)


async def session_create(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _launch_or_create(args, ctx)


async def session_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    mgr = manager()
    if mgr is None:
        return unavailable()
    sessions = mgr.list_sessions()
    text = "\n".join(f"{s['sessionId']} {s['state']} {s['url']}" for s in sessions) or "No browser sessions."
    return ok("session_list", text, {"sessions": sessions, "count": len(sessions)})


async def session_pause(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args, ctx)
    if error:
        return error
    result = await manager().pause_session(session.id)
    return ok("session_pause", f"Session {session.id} paused.", result)


async def session_resume(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args, ctx)
    if error:
        return error
    result = manager().resume_session(session.id)
    return ok("session_resume", f"Session {session.id} resumed.", result)


async def session_destroy(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await close(args, ctx)


# ── Profiles ─────────────────────────────────────────────────────────────────


async def profile_create(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    mgr = manager()
    if mgr is None:
        return unavailable()
    from .profiles import ProfileError  # noqa: PLC0415

    try:
        info = mgr.profiles.create(str(args["name"]))
    except ProfileError as exc:
        return refusal(BrowserError(exc.reason, code=exc.code, action="profile_create"), "browser_profile_create")
    if mgr.store is not None:
        try:
            mgr.store.save_profile({"id": info.id, "name": info.id, "path": info.path, "persistent": True})
        except Exception:  # noqa: BLE001
            pass
    return ok("profile_create", f"Profile {info.id} created.", info.to_dict())


async def profile_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    mgr = manager()
    if mgr is None:
        return unavailable()
    profiles = mgr.profiles.list_profiles()
    text = "\n".join(p["id"] for p in profiles) or "No saved profiles."
    return ok("profile_list", text, {"profiles": profiles})


async def profile_use(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    mgr = manager()
    if mgr is None:
        return unavailable()
    name = str(args["name"])
    try:
        session = await mgr.create_session(profile_id=name, persistent=True, url=args.get("url"))
    except BrowserError as exc:
        return refusal(exc, "browser_profile_use")
    return ok("profile_use", f"Opened session {session.id} with profile {name}.", {"sessionId": session.id})


async def profile_delete(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    mgr = manager()
    if mgr is None:
        return unavailable()
    from .profiles import ProfileError  # noqa: PLC0415

    try:
        removed = mgr.profiles.delete(str(args["name"]))
    except ProfileError as exc:
        return refusal(BrowserError(exc.reason, code=exc.code, action="profile_delete"), "browser_profile_delete")
    if mgr.store is not None:
        try:
            mgr.store.delete_profile(str(args["name"]))
        except Exception:  # noqa: BLE001
            pass
    return ok("profile_delete", f"Deleted profile {args['name']}.", {"deleted": removed})


# ── Vault ────────────────────────────────────────────────────────────────────


async def vault_list(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    mgr = manager()
    if mgr is None:
        return unavailable()
    entries = mgr.vault.list_entries(args.get("profile"))
    text = "\n".join(f"{e['reference']} ({e['kind']}, {e['origin']})" for e in entries) or "No saved credentials."
    return ok("vault_list", text, {"entries": entries})


async def vault_unlock(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    mgr = manager()
    if mgr is None:
        return unavailable()
    reference = str(args["reference"])
    value = await mgr.vault.resolve(reference)
    # Never return the value: only whether it resolved.
    return ok("vault_unlock", f"{reference}: {'resolvable' if value else 'not available'}.", {"reference": reference, "resolvable": value is not None})


async def vault_fill(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    from .tool_support import require_permission  # noqa: PLC0415

    session, error = session_of(args, ctx)
    if error:
        return error
    allowed, gate = await require_permission(ctx, session, "credentials", detail=str(args["reference"]), tool="browser_vault_fill")
    if not allowed:
        return gate  # type: ignore[return-value]
    value = await manager().vault.resolve(str(args["reference"]))
    if value is None:
        return refusal(BrowserError("Eclipse couldn't unlock that saved credential.", code="BROWSER_AUTHENTICATION_FAILED", action="vault_fill"), "browser_vault_fill")
    try:
        result = await session.type_text(args.get("target"), value, submit=bool(args.get("submit")))
    except BrowserError as exc:
        return refusal(exc, "browser_vault_fill")
    await emit(ctx, "browser.vault.filled", {"sessionId": session.id})
    return ok("vault_fill", "Filled the field from the vault (value never shown).", {"chars": result["chars"]})


async def vault_enter_code(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await vault_fill(args, ctx)


async def vault_save_login(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    mgr = manager()
    if mgr is None:
        return unavailable()
    from .vault import parse_reference  # noqa: PLC0415

    reference = str(args["reference"])
    if parse_reference(reference) is None:
        return refusal(BrowserError("A credential reference must look like vault://scope/name.", action="vault_save_login", code="BROWSER_INVALID_INPUT"), "browser_vault_save_login")
    entry = mgr.vault.save_entry(
        reference=reference, kind=str(args.get("kind") or "password"),
        username=str(args.get("username") or ""), profile_id=str(args.get("profile") or ""),
        origin=str(args.get("origin") or ""),
    )
    await emit(ctx, "browser.vault.saved", {"reference": reference, "origin": args.get("origin")})
    return ok("vault_save_login", f"Saved a reference for {reference} (no secret stored).", entry)


# ── Human-in-the-loop / device emulation ─────────────────────────────────────


async def request_human(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args, ctx)
    if error:
        return error
    result = session.request_human(str(args["reason"]))
    await emit(ctx, "browser.human.requested", {"sessionId": session.id, "reason": args["reason"]})
    from .telemetry import get_telemetry  # noqa: PLC0415

    get_telemetry().record_human_intervention(session.id)
    text = (
        f"Paused session {session.id} for a person: {args['reason']}. "
        "Eclipse does not bypass CAPTCHA, MFA or security checks. "
        "Resume with browser_resume once the person has finished."
    )
    return ok("request_human", text, result)


async def pause(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args, ctx)
    if error:
        return error
    result = session.pause()
    return ok("pause", f"Session {session.id} paused.", result)


async def resume(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args, ctx)
    if error:
        return error
    result = session.resume()
    await emit(ctx, "browser.resumed", {"sessionId": session.id})
    return ok("resume", f"Session {session.id} resumed.", result)


async def emulate_device(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args, ctx)
    if error:
        return error
    try:
        result = await session.emulate_device(str(args["device"]))
    except BrowserError as exc:
        return refusal(exc, "browser_emulate_device")
    return ok("emulate_device", f"Emulating {result['device']}.", result)


async def set_viewport(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args, ctx)
    if error:
        return error
    try:
        result = await session.set_viewport(int(args["width"]), int(args["height"]))
    except BrowserError as exc:
        return refusal(exc, "browser_set_viewport")
    return ok("set_viewport", f"Viewport set to {result['width']}×{result['height']}.", result)


def make_set_context(kind: str, tool: str):
    async def handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
        session, error = session_of(args, ctx)
        if error:
            return error
        try:
            if kind == "user_agent":
                value = str(args["user_agent"])
                await session.ps_context.set_extra_http_headers({"User-Agent": value})
                session.user_agent_override = value
                return ok(tool, "Applied.", {"kind": kind, "userAgent": value})
            if kind == "locale":
                value = str(args["locale"])
                await session.ps_context.set_extra_http_headers({"Accept-Language": value})
                session.locale_override = value
                return ok(tool, "Applied.", {"kind": kind, "locale": value})
            if kind == "timezone":
                value = str(args["timezone"])
                session.timezone_override = value
                return ok(tool, "Applied.", {"kind": kind, "timezone": value})
            if kind == "geolocation":
                latitude = float(args["latitude"])
                longitude = float(args["longitude"])
                await session.ps_context.grant_permissions(["geolocation"])
                session.permissions_granted = sorted(set(session.permissions_granted) | {"geolocation"})
                await session.ps_context.set_geolocation({"latitude": latitude, "longitude": longitude})
                session.geolocation = {"latitude": latitude, "longitude": longitude}
                return ok(tool, "Applied.", {"kind": kind, "geolocation": session.geolocation})
        except Exception as exc:  # noqa: BLE001
            return refusal(BrowserError("Eclipse couldn't apply that setting.", code="BROWSER_SESSION_ERROR", action=tool, metadata={"error": str(exc)[:200]}), tool)
        return ok(tool, "Applied.", {"kind": kind})
    return handler


ADMIN_HANDLERS: dict[str, Any] = {
    "browser_session_create": session_create,
    "browser_session_list": session_list,
    "browser_session_pause": session_pause,
    "browser_session_resume": session_resume,
    "browser_session_destroy": session_destroy,
    "browser_profile_create": profile_create,
    "browser_profile_list": profile_list,
    "browser_profile_use": profile_use,
    "browser_profile_delete": profile_delete,
    "browser_vault_list": vault_list,
    "browser_vault_unlock": vault_unlock,
    "browser_vault_fill": vault_fill,
    "browser_vault_enter_code": vault_enter_code,
    "browser_vault_save_login": vault_save_login,
    "browser_request_human": request_human,
    "browser_pause": pause,
    "browser_resume": resume,
    "browser_emulate_device": emulate_device,
    "browser_set_viewport": set_viewport,
    "browser_set_user_agent": make_set_context("user_agent", "browser_set_user_agent"),
    "browser_set_locale": make_set_context("locale", "browser_set_locale"),
    "browser_set_timezone": make_set_context("timezone", "browser_set_timezone"),
    "browser_set_geolocation": make_set_context("geolocation", "browser_set_geolocation"),
}

__all__ = ["ADMIN_HANDLERS"]

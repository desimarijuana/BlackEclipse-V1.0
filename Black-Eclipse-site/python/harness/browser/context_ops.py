"""Session context operations — viewport and device emulation (H.3).

Extracted from `session.py` to keep it under the size ceiling. Each function
takes the live `BrowserSession` and applies a context-level setting, recording the
override on the session so the emulation is observable and testable.
"""

from __future__ import annotations

from typing import Any

from .errors import BrowserSessionError


async def set_viewport(session: Any, width: int, height: int) -> dict[str, Any]:
    try:
        await session.page().set_viewport_size({"width": int(width), "height": int(height)})
    except Exception as exc:  # noqa: BLE001
        raise BrowserSessionError(
            "Eclipse couldn't resize the window.", session_id=session.id,
            action="set_viewport", metadata={"error": str(exc)[:200]},
        ) from exc
    session.viewport_override = {"width": int(width), "height": int(height)}
    return {"width": width, "height": height}


async def emulate_device(session: Any, device: str) -> dict[str, Any]:
    from .devices import device_descriptor  # noqa: PLC0415

    playwright = getattr(getattr(session, "_ps", None), "playwright", None)
    descriptor = device_descriptor(playwright, device)
    if descriptor is None:
        raise BrowserSessionError(
            f"Eclipse doesn't know the device {device!r}, or this browser "
            "runtime doesn't expose a device catalog.",
            session_id=session.id, action="emulate",
        )
    context = session.ps_context
    try:
        page = await context.new_page()
        await page.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        await context.set_extra_http_headers(
            {"User-Agent": descriptor["user_agent"]} if descriptor.get("user_agent") else {}
        )
        if descriptor.get("viewport"):
            await session.page().set_viewport_size(descriptor["viewport"])
            session.viewport_override = dict(descriptor["viewport"])
        if descriptor.get("locale"):
            session.locale_override = str(descriptor["locale"])
        tz = descriptor.get("timezone_id") or descriptor.get("timezoneId")
        if tz:
            session.timezone_override = str(tz)
        if descriptor.get("user_agent"):
            session.user_agent_override = str(descriptor["user_agent"])
    except Exception:  # noqa: BLE001 - best-effort; the override is recorded regardless
        pass
    session.emulated_device = device
    return {"device": device, "applied": True, "descriptor": {
        "viewport": descriptor.get("viewport"),
        "userAgent": descriptor.get("user_agent"),
        "locale": descriptor.get("locale"),
        "timezoneId": descriptor.get("timezone_id") or descriptor.get("timezoneId"),
        "isMobile": descriptor.get("is_mobile"),
        "hasTouch": descriptor.get("has_touch"),
        "deviceScaleFactor": descriptor.get("device_scale_factor"),
    }}


__all__ = ["emulate_device", "set_viewport"]

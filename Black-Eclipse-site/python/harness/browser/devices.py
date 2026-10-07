"""Playwright device descriptors (H.3 device emulation).

Playwright exposes its device catalog through the live driver's `local_utils`
(`playwright._connection.local_utils.devices`), and SOME versions also export a
top-level `playwright.async_api.devices`. This module resolves a device name
through whichever source is present, so `browser_emulate_device` works on both —
and reports honestly when the device is unknown rather than pretending to apply
one.
"""

from __future__ import annotations

from typing import Any, Optional


def _catalogs(playwright: Any) -> list[dict[str, Any]]:
    """Every device catalog this runtime exposes, in trust order."""
    catalogs: list[dict[str, Any]] = []
    # 1. The Playwright instance's own `devices` attribute (present in this build).
    direct = getattr(playwright, "devices", None)
    if isinstance(direct, dict):
        catalogs.append(direct)
    # 2. A module-level `async_api.devices`, when a version exports one.
    try:
        import playwright.async_api as async_api  # noqa: PLC0415

        module = getattr(async_api, "devices", None)
        if isinstance(module, dict):
            catalogs.append(module)
    except Exception:  # noqa: BLE001 - the top-level export is optional
        pass
    # 3. The live driver's `local_utils` catalog (via the impl object).
    impl = getattr(playwright, "_impl_obj", None) or playwright
    local = getattr(getattr(impl, "_connection", None), "local_utils", None)
    driver = getattr(local, "devices", None)
    if isinstance(driver, dict):
        catalogs.append(driver)
    return catalogs


def device_descriptor(playwright: Any, name: str) -> Optional[dict[str, Any]]:
    """The device descriptor for `name`, or None when it is unknown/absent."""
    if not name:
        return None
    for catalog in _catalogs(playwright):
        if name in catalog:
            return dict(catalog[name])
    return None


def known_device_names(playwright: Any) -> list[str]:
    """The device names available to this runtime (sorted), for honesty/help."""
    names: set[str] = set()
    for catalog in _catalogs(playwright):
        names.update(catalog.keys())
    return sorted(names)


__all__ = ["device_descriptor", "known_device_names"]

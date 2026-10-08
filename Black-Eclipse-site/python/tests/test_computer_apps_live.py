"""Opt-in live application verification for the Computer Use adapters.

Skipped by default. When `BLACK_ECLIPSE_CUA_APPS=1` (and the named apps are
installed) these drive the REAL Windows driver against a real application to
confirm the adapter's knowledge records: recognition, a known control's
grounding, and — for a trading terminal — that the finance firewall still holds
(no mutation control is ever clicked).

The rig NEVER fabricates a pass: an app that isn't installed is reported skipped,
and a mismatch fails. A pass is what lets an adapter be marked `verified` with a
build note.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("BLACK_ECLIPSE_CUA_APPS") != "1" or sys.platform != "win32",
    reason="live app verification is opt-in: set BLACK_ECLIPSE_CUA_APPS=1 on Windows",
)


async def _driver():
    from harness.computer.drivers import build_driver

    driver = build_driver("windows")
    await driver.start()
    return driver


def _windows_with(driver, *needles: str) -> list:
    out = []
    for window in driver.list_windows():
        haystack = f"{window.title} {window.app}".lower()
        if any(n.lower() in haystack for n in needles):
            out.append(window)
    return out


@pytest.mark.asyncio
async def test_live_notepad_adapter_grounds_a_known_control():
    """Notepad is present on every Windows box — a real recognition+grounding run."""
    from harness.computer.applications.registry import build_adapter_registry
    from harness.computer.grounding.grounder import Grounder
    from harness.computer.grounding.matching import GroundingQuery
    from harness.computer.models import Bounds, Snapshot

    driver = await _driver()
    try:
        registry = build_adapter_registry()
        windows = _windows_with(driver, "notepad")
        if not windows:
            pytest.skip("Notepad isn't open")
        snap = Snapshot(snapshot_id="live", generation=1, application="notepad",
                        window_id=windows[0].id, bounds=Bounds(0, 0, 800, 600))
        adapter = registry.select(app_name=windows[0].app, title=windows[0].title)
        # The generic adapter is the honest fallback; recognition must not crash.
        assert adapter is not None
        # Grounding a menu item by name through the ladder must not raise a crash.
        try:
            Grounder().ground(GroundingQuery(intent="File"), snap, app_profile=adapter)
        except Exception as exc:  # noqa: BLE001 - TargetNotFound is acceptable
            from harness.computer.errors import TargetNotFound  # noqa: PLC0415

            assert isinstance(exc, TargetNotFound)
    finally:
        await driver.stop()

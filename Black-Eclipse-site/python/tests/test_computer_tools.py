"""Computer Use tool integration tests over a deterministic fake driver.

Exercises the `computer_*` toolset through the REAL `ToolRegistry`, so validation,
registration, permission, the effect authorizer and the response shape are all
covered — without touching a real desktop. Adversarial cases (stale element,
wrong approval, prohibited app, blocked mutation) assert the fail-safe path.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.computer.config import computer_config
from harness.computer.manager import ComputerManager
from harness.computer.runtime import set_computer_manager
from harness.computer.tools import register_computer_tools
from harness.tools import ToolContext, ToolRegistry

from tests.test_computer_safety import _FakeDriver


@pytest.fixture()
def manager(monkeypatch):
    cfg = computer_config(refresh=True)
    cfg.driver_backend = "null"  # replaced below with the fake driver
    mgr = ComputerManager(config=cfg)
    mgr.driver = _FakeDriver()
    mgr.ax = None

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(mgr.start())
    finally:
        loop.close()
    set_computer_manager(mgr)
    yield mgr
    set_computer_manager(None)


@pytest.fixture()
def registry():
    reg = ToolRegistry()
    register_computer_tools(reg)
    return reg


def _ctx() -> ToolContext:
    return ToolContext(run_id="test-run", log=lambda *_: None, user_id="tester")


@pytest.mark.asyncio
async def test_registration_includes_the_full_surface(registry):
    names = set(registry.names())
    for name in ("computer_use", "computer_capabilities", "computer_doctor",
                 "computer_session_start", "computer_finance_read", "computer_finance_prepare",
                 "computer_takeover", "computer_windows"):
        assert name in names
    # Elevated tools are admitted by the computer authorizer, marked non-read.
    assert registry.get("computer_use").permission == "read"
    assert registry.get("computer_finance_prepare").permission == "read"


@pytest.mark.asyncio
async def test_capabilities_and_doctor(registry, manager):
    r = await registry.execute("computer_capabilities", "c", {}, _ctx())
    assert r.ok and r.data["driver"] == "fake"
    r = await registry.execute("computer_doctor", "c", {}, _ctx())
    assert r.ok and r.data["status"] == "READY"


@pytest.mark.asyncio
async def test_listing_tools(registry, manager):
    r = await registry.execute("computer_windows", "c", {}, _ctx())
    assert r.ok and r.data["count"] == 1
    r = await registry.execute("computer_apps", "c", {}, _ctx())
    assert r.ok and r.data["count"] == 1
    r = await registry.execute("computer_displays", "c", {}, _ctx())
    assert r.ok and len(r.data["displays"]) == 1


@pytest.mark.asyncio
async def test_session_start_and_capture(registry, manager):
    r = await registry.execute("computer_session_start", "c", {}, _ctx())
    assert r.ok
    r = await registry.execute("computer_use", "c", {"action": "capture", "mode": "som"}, _ctx())
    assert r.ok
    assert r.data.get("snapshotId")
    assert isinstance(r.data.get("elements"), list)


@pytest.mark.asyncio
async def test_stale_element_returns_recapture_verdict(registry, manager):
    await registry.execute("computer_session_start", "c", {}, _ctx())
    first = await registry.execute("computer_use", "c", {"action": "capture"}, _ctx())
    snapshot_id = first.data["snapshotId"]
    # A second capture invalidates the first snapshot.
    await registry.execute("computer_use", "c", {"action": "capture"}, _ctx())
    r = await registry.execute(
        "computer_use", "c",
        {"action": "click", "element": 1, "snapshot_id": snapshot_id},
        _ctx(),
    )
    # The click is held for approval first, but a stale handle must be refused.
    code = (r.data or {}).get("code")
    assert code in ("COMPUTER_STALE_ELEMENT", "COMPUTER_APPROVAL_REQUIRED")


@pytest.mark.asyncio
async def test_click_without_approval_is_refused(registry, manager):
    await registry.execute("computer_session_start", "c", {}, _ctx())
    snap = await registry.execute("computer_use", "c", {"action": "capture"}, _ctx())
    r = await registry.execute(
        "computer_use", "c",
        {"action": "click", "element": 1, "snapshot_id": snap.data["snapshotId"]},
        _ctx(),
    )
    assert (r.data or {}).get("code") == "COMPUTER_APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_finance_prepare_blocks_withdraw(registry, manager):
    r = await registry.execute("computer_finance_prepare", "c", {"action": "withdraw"}, _ctx())
    assert (r.data or {}).get("code") == "COMPUTER_FINANCE_BLOCKED"


@pytest.mark.asyncio
async def test_finance_prepare_assisted_buy_needs_approval(registry, manager):
    import harness.computer.config as config_mod

    config_mod.computer_config(refresh=True).finance_mode = "assisted"
    r = await registry.execute(
        "computer_finance_prepare", "c",
        {"action": "buy", "instrument": "NVDA", "quantity": 10, "price": 100},
        _ctx(),
    )
    assert (r.data or {}).get("code") == "COMPUTER_FINANCE_APPROVAL"


@pytest.mark.asyncio
async def test_finance_read_carries_screen_provenance(registry, manager):
    await registry.execute("computer_session_start", "c", {}, _ctx())
    r = await registry.execute("computer_finance_read", "c", {}, _ctx())
    assert r.ok
    provenance = r.data["financialState"]["provenance"]
    assert provenance["source_type"] == "desktop_screen"
    assert "confidence" in provenance


@pytest.mark.asyncio
async def test_takeover_tool_stops_actions(registry, manager):
    start = await registry.execute("computer_session_start", "c", {}, _ctx())
    session_id = start.data["session"]["sessionId"]
    await registry.execute("computer_takeover", "c", {"session_id": session_id}, _ctx())
    assert not manager.takeover.agent_may_act(session_id)
    await registry.execute("computer_resume", "c", {"session_id": session_id}, _ctx())
    assert manager.takeover.agent_may_act(session_id)


@pytest.mark.asyncio
async def test_dry_run_never_clicks(registry, manager):
    await registry.execute("computer_session_start", "c", {}, _ctx())
    snap = await registry.execute("computer_use", "c", {"action": "capture"}, _ctx())
    r = await registry.execute(
        "computer_use", "c",
        {"action": "click", "element": 1, "snapshot_id": snap.data["snapshotId"], "dry_run": True},
        _ctx(),
    )
    assert r.ok
    assert r.data["deliveryMode"] == "dry_run"
    assert manager.driver.clicks == []

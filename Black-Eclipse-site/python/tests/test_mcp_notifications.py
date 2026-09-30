"""Continuation Milestone 4 — inbound `tools/list_changed` triggers rediscovery.

A server may add/remove/rename tools mid-session. The client surfaces the
notification; the manager re-runs discovery for THAT server only, through the
existing path, and the existing digest+confirmation gate re-engages. Deterministic
and offline (local fixture subprocess).
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from harness.mcp.config import MCPServerConfig
from harness.mcp.manager import MCPManager
from harness.tools import ToolContext, ToolRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
RAW = os.path.join(FIXTURES, "raw_fixture.py")


def _cfg(mode: str, **overrides) -> MCPServerConfig:
    data = dict(
        id="raw",
        command=sys.executable,
        args=[RAW, mode],
        enabled=True,
        selected_tools=["echo"],
        tool_effects={"echo": "read"},
        startup_timeout_ms=8_000,
        catalog_timeout_ms=8_000,
        call_timeout_ms=8_000,
    )
    data.update(overrides)
    return MCPServerConfig(**data)


class RecordingSink:
    def __init__(self):
        self.events = []

    async def __call__(self, event_type, data=None):
        self.events.append((event_type, data or {}))


async def _wait_for(predicate, *, timeout=8.0):
    """Poll until predicate() is truthy (notification handling is async)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.mark.asyncio
async def test_list_changed_reruns_discovery_and_deregisters_the_removed_tool():
    manager = MCPManager([_cfg("list_changed")])
    registry = ToolRegistry()
    sink = RecordingSink()
    manager.set_event_sink(sink)
    await manager.start()
    try:
        [name] = manager.register_selected_tools(registry)
        assert name == "mcp__raw__echo"
        rt = manager._runtimes["raw"]
        # The fixture announces the change on the first call; make that call.
        ctx = ToolContext(run_id="r-notify", log=lambda *_: None)
        await registry.execute(name, "c1", {"text": "hi"}, ctx, allowed={name})
        # First catalog included the transient tool (before the change).
        # Wait for the notification-driven rediscovery (the refresh drops it).
        ok = await _wait_for(lambda: "transient" not in rt.descriptors)
        assert ok, f"rediscovery did not happen; descriptors={list(rt.descriptors)}"
        # The changed catalog re-engaged the confirmation gate: a read tool whose
        # effect came from the (untrusted) server hint is inert again until the
        # operator re-confirms the new digest.
        assert rt.catalog_digest != rt.config.confirmed_catalog_digest
        # `echo` was declared read (operator), so it stays activatable; the event
        # fired exactly once with counts + identity only.
        changed = [e for e in sink.events if e[0] == "mcp.catalog.changed"]
        assert len(changed) == 1, sink.events
        payload = changed[0][1]
        assert payload["serverId"] == "raw"
        assert "catalogDigest" in payload and "discovered" in payload
        assert "removed" in payload
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_a_disappeared_tool_is_deregistered_from_the_registry():
    manager = MCPManager([_cfg("list_changed", selected_tools=["echo", "transient"],
                               tool_effects={"echo": "read", "transient": "read"})])
    registry = ToolRegistry()
    await manager.start()
    try:
        names = set(manager.register_selected_tools(registry))
        assert "mcp__raw__transient" in names
        assert registry.get("mcp__raw__transient") is not None
        rt = manager._runtimes["raw"]
        # Trigger the change via a call on an existing tool.
        ctx = ToolContext(run_id="r-notify2", log=lambda *_: None)
        await registry.execute("mcp__raw__echo", "c1", {"text": "hi"}, ctx, allowed=names)
        ok = await _wait_for(lambda: "transient" not in rt.descriptors)
        assert ok
        # The removed tool is gone from the registry too.
        assert registry.get("mcp__raw__transient") is None
        assert "mcp__raw__transient" not in rt.registered_tools
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_resource_and_prompt_list_changes_refresh_the_listings():
    # The connection snapshots resources/prompts at connect; a list_changed
    # notification must refresh them rather than serve the stale snapshot.
    manager = MCPManager([
        _cfg("list_changed_all", selected_tools=["echo"], tool_effects={"echo": "read"},
             tools={"resources": True, "prompts": True})
    ])
    registry = ToolRegistry()
    sink = RecordingSink()
    manager.set_event_sink(sink)
    await manager.start()
    try:
        names = manager.register_selected_tools(registry)
        name = "mcp__raw__echo"
        assert name in names
        rt = manager._runtimes["raw"]
        # At connect the resource/prompt lists include the soon-to-be-dropped ones.
        assert {r["uri"] for r in rt.connection.resources} == {"note://kept", "note://dropped"}
        assert {p["name"] for p in rt.connection.prompts} == {"kept_prompt", "dropped_prompt"}
        # Trigger the change via a tool call.
        ctx = ToolContext(run_id="r-res", log=lambda *_: None)
        await registry.execute(name, "c1", {"text": "hi"}, ctx, allowed={name})
        # Wait for the resource listing to be refreshed (dropped disappears).
        ok = await _wait_for(
            lambda: {r["uri"] for r in rt.connection.resources} == {"note://kept"}
        )
        assert ok, f"resources not refreshed: {rt.connection.resources}"
        ok = await _wait_for(
            lambda: {p["name"] for p in rt.connection.prompts} == {"kept_prompt"}
        )
        assert ok, f"prompts not refreshed: {rt.connection.prompts}"
        # One content-free event per kind.
        kinds = {e[1].get("kind") for e in sink.events if e[0] == "mcp.catalog.changed"}
        assert {"tools", "resources", "prompts"} <= kinds, sink.events
        for _, payload in [e for e in sink.events if e[0] == "mcp.catalog.changed"]:
            assert payload["serverId"] == "raw"
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_notification_for_a_dead_server_is_ignored_safely():
    # A notification arriving after the server is closed must not raise.
    # `normal` mode sends no notifications, so the only change count is from the
    # explicit call below once the server is dead.
    manager = MCPManager([_cfg("normal")])
    registry = ToolRegistry()
    await manager.start()
    rt = manager._runtimes["raw"]
    manager.register_selected_tools(registry)
    await manager._close_runtime(rt)
    assert rt.connection is None
    # Directly invoke the handler; it must be a no-op, not an exception.
    await manager._on_catalog_changed(rt, "tools")
    assert rt.catalog_changes == 0
    await manager.close()


@pytest.mark.asyncio
async def test_unknown_server_catalog_change_is_a_non_event():
    manager = MCPManager([])
    # No runtimes: nothing to do, and it must not raise.
    await manager.close()

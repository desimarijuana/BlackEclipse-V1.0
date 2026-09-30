"""Phase 6 Milestone 4 — resources and prompts (capability-aware utility tools).

Behavior contracts: utility tools register only when the live session advertises
the capability AND the operator toggled it on; a resource read returns bounded
labelled content; a prompt is returned as INERT data and cannot change tools or
instructions; a server advertising no resources registers none.
"""

from __future__ import annotations

import os
import sys

import pytest

from harness.mcp.config import MCPServerConfig
from harness.mcp.manager import MCPManager
from harness.tools import ToolContext, ToolRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
FAST = os.path.join(FIXTURES, "fastmcp_fixture.py")


def fast_config(**overrides) -> MCPServerConfig:
    data = dict(
        id="fx", command=sys.executable, args=[FAST], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"},
    )
    data.update(overrides)
    return MCPServerConfig(**data)


def ctx() -> ToolContext:
    return ToolContext(run_id="r1", log=lambda *_: None)


@pytest.mark.asyncio
async def test_capabilities_are_discovered():
    from harness.mcp.client import MCPConnection

    conn = MCPConnection(fast_config())
    try:
        await conn.start()
        caps = conn.capabilities
        assert caps.get("tools") is True
        assert caps.get("resources") is True
        assert caps.get("prompts") is True
        assert any(r["uri"].startswith("note://") for r in conn.resources)
        assert any(p["name"] == "explain_metric" for p in conn.prompts)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_resource_and_prompt_tools_off_by_default():
    mgr = MCPManager([fast_config()])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    assert names == ["mcp__fx__echo"]  # no utility tools until toggled
    await mgr.close()


@pytest.mark.asyncio
async def test_resource_tools_register_when_enabled_and_advertised():
    cfg = fast_config(tools={"resources": True})
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    assert "mcp__fx____list_resources" in names
    assert "mcp__fx____read_resource" in names
    # Read a resource: bounded, labelled, inert.
    result = await reg.execute("mcp__fx____read_resource", "c1", {"uri": "note://thesis"}, ctx(),
                               allowed=set(names))
    assert result.ok
    assert "NOT Eclipse-verified" in result.text
    assert result.data["provenance"]["eclipseVerified"] is False
    await mgr.close()


@pytest.mark.asyncio
async def test_prompt_is_inert_data_and_cannot_change_tools():
    cfg = fast_config(tools={"prompts": True})
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    before = set(reg.names())
    result = await reg.execute("mcp__fx____get_prompt", "c1",
                               {"name": "explain_metric", "arguments": {"metric": "revenue"}},
                               ctx(), allowed=set(names))
    assert result.ok
    # The prompt text is returned as data; nothing about the tool set changed.
    assert set(reg.names()) == before
    # And the registry still refuses an unselected write tool.
    assert reg.get("mcp__fx__write_thing") is None
    await mgr.close()


@pytest.mark.asyncio
async def test_resource_uri_scheme_is_authorized():
    cfg = fast_config(tools={"resources": True})
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    result = await reg.execute("mcp__fx____read_resource", "c1", {"uri": "javascript:alert(1)"},
                      ctx(), allowed=set(names))
    assert not result.ok
    assert "not allowed" in result.text
    await mgr.close()


@pytest.mark.asyncio
async def test_server_without_resources_registers_no_resource_tools():
    # The raw fixture advertises only tools, no resources/prompts.
    raw = os.path.join(FIXTURES, "raw_fixture.py")
    cfg = MCPServerConfig(
        id="raw", command=sys.executable, args=[raw, "normal"], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"},
        tools={"resources": True, "prompts": True},
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    assert names == ["mcp__raw__echo"]
    await mgr.close()

"""Phase 3 (MCP integrity) — effect classification must not trust a name.

`API-move-page` is a write with no write-looking token; `API-post-search` is a
read with a write-looking token. The name and the server's own `readOnlyHint` are
BOTH untrusted. Rather than infer an effect from a name (which would
auto-activate a tool on a guess), a `read` tool with a write-shaped name is
refused until the operator explicitly acknowledges the mismatch.

Deterministic and offline: the raw fixture's `notion_naming` mode models the real
Notion names.
"""

from __future__ import annotations

import os
import sys

import pytest

from harness.mcp.config import MCPServerConfig
from harness.mcp.manager import MCPManager
from harness.mcp.naming import writes_like_name

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
RAW = os.path.join(FIXTURES, "raw_fixture.py")


def test_writes_like_name_recognises_write_tokens():
    assert writes_like_name("API-move-page") is True
    assert writes_like_name("API-patch-page") is True
    assert writes_like_name("create_file") is True
    assert writes_like_name("delete_everything") is True
    # A read with a write-ish token is flagged (the operator must look).
    assert writes_like_name("API-post-search") is True
    # A plain read name is not flagged.
    assert writes_like_name("API-get-self") is False
    assert writes_like_name("read_file") is False


def _cfg(mode: str, **overrides) -> MCPServerConfig:
    data = dict(
        id="raw",
        command=sys.executable,
        args=[RAW, mode],
        enabled=True,
        selected_tools=["API-post-search", "API-move-page", "API-patch-page"],
        startup_timeout_ms=8_000,
        catalog_timeout_ms=8_000,
        call_timeout_ms=8_000,
    )
    data.update(overrides)
    return MCPServerConfig(**data)


@pytest.mark.asyncio
async def test_write_named_read_tool_is_not_activatable_without_acknowledgement():
    # `API-post-search` is declared read (a legitimate Notion read). Because its
    # name is write-shaped, it stays inert until acknowledged.
    cfg = _cfg("notion_naming", tool_effects={"API-post-search": "read"})
    from harness.tools import ToolRegistry

    mgr = MCPManager([cfg])
    await mgr.start()
    try:
        names = mgr.register_selected_tools(ToolRegistry())
        assert names == []
        rt = mgr._runtimes["raw"]
        descriptor = rt.descriptors["API-post-search"]
        assert descriptor.activatable is False
        assert "acknowledge" in (descriptor.diagnostic or "")
    finally:
        await mgr.close()


@pytest.mark.asyncio
async def test_write_named_read_tool_activates_after_explicit_acknowledgement():
    cfg = _cfg(
        "notion_naming",
        tool_effects={"API-post-search": "read"},
        acknowledged_effect_mismatches=["API-post-search"],
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    try:
        from harness.tools import ToolRegistry

        [name] = mgr.register_selected_tools(ToolRegistry())
        assert name == "mcp__raw__API_post_search"
        assert mgr._runtimes["raw"].descriptors["API-post-search"].activatable is True
    finally:
        await mgr.close()


@pytest.mark.asyncio
async def test_real_write_named_tool_declared_write_requires_approval():
    # `API-move-page` declared write is activatable only when the effect is
    # enabled, and its permission is `write` so a call needs a per-call approval.
    cfg = _cfg(
        "notion_naming",
        tool_effects={"API-move-page": "write", "API-post-search": "read"},
        acknowledged_effect_mismatches=["API-post-search"],
        enabled_effects=["read", "write"],
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    try:
        from harness.tools import ToolContext, ToolRegistry

        registry = ToolRegistry()
        names = set(mgr.register_selected_tools(registry))
        assert "mcp__raw__API_move_page" in names
        definition = registry.get("mcp__raw__API_move_page")
        assert definition is not None and definition.permission == "write"
        # No authorizer on the context => the registry refuses the write.
        ctx = ToolContext(run_id="r1", log=lambda *_: None)
        result = await registry.execute("mcp__raw__API_move_page", "c1", {}, ctx, allowed=names)
        assert not result.ok
    finally:
        await mgr.close()


@pytest.mark.asyncio
async def test_unknown_effect_tool_is_never_activatable():
    # A tool with no declaration and only the server's untrusted readOnlyHint
    # (and no catalog confirmation) is not activatable.
    cfg = _cfg("notion_naming", selected_tools=["API-patch-page"], tool_effects={})
    mgr = MCPManager([cfg])
    await mgr.start()
    try:
        from harness.tools import ToolRegistry

        names = mgr.register_selected_tools(ToolRegistry())
        assert names == []
        assert mgr._runtimes["raw"].descriptors["API-patch-page"].activatable is False
    finally:
        await mgr.close()

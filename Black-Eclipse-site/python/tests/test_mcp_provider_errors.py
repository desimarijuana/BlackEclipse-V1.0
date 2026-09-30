"""Phase 1 (MCP integrity) — provider errors, the empty-result label, Verify.

The defects: Eclipse reported "connected" when all it knew was that a child
process launched, and treated a provider's error payload as data. These tests are
deterministic and offline; the provider-error body is produced by the raw fixture
with `isError=False`, exactly like Notion's 401.

The pure classifier is exercised directly (no server), plus the manager render
path, the empty-result label, and the operator-gated Verify route.
"""

from __future__ import annotations

import os
import sys

import pytest

from harness.mcp.client import looks_like_provider_error
from harness.mcp.manager import MCPManager, _provider_error_line
from harness.mcp.config import MCPServerConfig

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
RAW = os.path.join(FIXTURES, "raw_fixture.py")


# ── the pure classifier, both directions ────────────────────────────────────


def test_real_notion_401_body_is_an_error():
    body = (
        '{"status":401,"object":"error","code":"unauthorized",'
        '"message":"API token is invalid.","request_id":"abc"}'
    )
    assert looks_like_provider_error(body) == {"code": "unauthorized", "status": 401}


def test_legitimate_payload_with_a_code_field_is_not_an_error():
    # A plain result that happens to carry a `code` (a ticker, a currency, etc.)
    # must never be misread as a provider error.
    assert looks_like_provider_error('{"code":"AAPL","price":123.4}') is None
    assert looks_like_provider_error('{"symbol":"AAPL","code":"NASDAQ"}') is None


def test_status_in_success_range_is_not_an_error():
    assert looks_like_provider_error('{"status":200,"code":"ok"}') is None


def test_error_key_is_an_error():
    assert looks_like_provider_error('{"error":"boom"}') == {"code": "provider_error"}


def test_null_error_key_is_not_an_error():
    assert looks_like_provider_error('{"error":null,"value":1}') is None


def test_error_code_vocabulary_needs_status_or_message():
    assert looks_like_provider_error('{"code":"not_found","message":"missing"}') == {"code": "not_found"}
    # A bare recognized-looking code with nothing else is still too weak.
    assert looks_like_provider_error('{"code":"conflict"}') is None


def test_non_object_and_prose_are_not_errors():
    assert looks_like_provider_error("[1,2,3]") is None
    assert looks_like_provider_error('here is the answer: {"status":401}') is None
    assert looks_like_provider_error("") is None
    assert looks_like_provider_error("plain text") is None


def test_5xx_status_string_is_an_error():
    assert looks_like_provider_error('{"status":"503","message":"down"}') == {"status": 503}


def test_provider_error_line_names_status_and_code():
    line = _provider_error_line({"code": "unauthorized", "status": 401}, "raw body")
    assert "provider error" in line
    assert "status 401" in line
    assert "code 'unauthorized'" in line
    assert "raw body" in line


# ── the manager render path treats it as a failure ──────────────────────────


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


class RecordingEmitter:
    def __init__(self):
        self.events = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data or {}))
        return {"type": event_type, "data": data or {}}


@pytest.mark.asyncio
async def test_provider_error_body_renders_a_failure_and_emits_failed_event():
    from harness.tools import ToolContext, ToolRegistry

    manager = MCPManager([_cfg("provider_error")])
    registry = ToolRegistry()
    await manager.start()
    try:
        [tool_name] = manager.register_selected_tools(registry)
        emitter = RecordingEmitter()
        ctx = ToolContext(run_id="r1", log=lambda *_: None, emitter=emitter)
        result = await registry.execute(tool_name, "c1", {"text": "hi"}, ctx, allowed={tool_name})
        assert "provider error" in result.text
        # The provider's own words are preserved verbatim.
        assert "API token is invalid." in result.text
        failed = [e for e in emitter.events if e[0] == "mcp.tool.failed"]
        assert failed, emitter.events
        assert failed[-1][1].get("code") == "mcp_tool_provider_error"
        assert not [e for e in emitter.events if e[0] == "mcp.tool.completed"]
    finally:
        await manager.close()
        manager._registry = None


@pytest.mark.asyncio
async def test_empty_body_is_labelled_not_a_silent_empty_success():
    from harness.tools import ToolContext, ToolRegistry

    manager = MCPManager([_cfg("empty_result")])
    registry = ToolRegistry()
    await manager.start()
    try:
        [tool_name] = manager.register_selected_tools(registry)
        ctx = ToolContext(run_id="r1", log=lambda *_: None)
        result = await registry.execute(tool_name, "c1", {"text": "hi"}, ctx, allowed={tool_name})
        assert "no text content" in result.text
    finally:
        await manager.close()
        manager._registry = None

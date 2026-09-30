"""Phase 4 (MCP integrity) — capability and hygiene gaps.

The per-run MCP call budget, visible `maxTools` truncation, and the stale-cache
signal. Deterministic and offline.
"""

from __future__ import annotations

import os
import sys

import pytest

from harness.mcp.client import MCPClosedError
from harness.mcp.config import MCPServerConfig, DEFAULT_MCP_CALLS_PER_RUN
from harness.mcp.manager import MCPManager
from harness.mcp.runtime import _ServerRuntime
from harness.tools import ToolContext, ToolRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
RAW = os.path.join(FIXTURES, "raw_fixture.py")


class RecordingEmitter:
    def __init__(self):
        self.events = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data or {}))
        return {"type": event_type, "data": data or {}}


def _cfg(mode: str = "normal", **overrides) -> MCPServerConfig:
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


@pytest.mark.asyncio
async def test_per_run_call_budget_refuses_honestly_with_a_named_cap():
    manager = MCPManager([_cfg(max_calls_per_run=2)])
    registry = ToolRegistry()
    await manager.start()
    try:
        [name] = manager.register_selected_tools(registry)
        ctx = ToolContext(run_id="run-budget", log=lambda *_: None)
        emitter = RecordingEmitter()
        ctx.emitter = emitter
        # Two calls fit the cap.
        for _ in range(2):
            result = await registry.execute(name, "c", {"text": "x"}, ctx, allowed={name})
            assert result.ok
        # The third is refused with an honest, named-cap message.
        result = await registry.execute(name, "c", {"text": "x"}, ctx, allowed={name})
        assert not result.ok
        assert "maxCallsPerRun" in result.text or "budget" in result.text
        assert "2" in result.text
        failed = [e for e in emitter.events if e[0] == "mcp.tool.failed"]
        assert any(e[1].get("code") == "mcp_run_budget_exceeded" for e in failed)
        # A DIFFERENT run has its own budget.
        ctx2 = ToolContext(run_id="other-run", log=lambda *_: None)
        ok = await registry.execute(name, "c", {"text": "x"}, ctx2, allowed={name})
        assert ok.ok
    finally:
        await manager.close()


def test_per_run_cap_default_is_documented():
    assert DEFAULT_MCP_CALLS_PER_RUN >= 1
    cfg = MCPServerConfig(id="x", command="npx", args=["-y", "pkg"])
    assert cfg.max_calls_per_run is None  # falls back to the default


@pytest.mark.asyncio
async def test_max_tools_truncation_is_recorded_and_surfaced():
    # Advertise 3 tools but keep only 2 -> a visible truncation record.
    manager = MCPManager([_cfg("notion_naming", max_tools=2,
                               selected_tools=[], tool_effects={})])
    await manager.start()
    try:
        rt = manager._runtimes["raw"]
        assert rt.tools_discovered == 3
        assert rt.tools_kept == 2
        status = manager._lifecycle_status(rt)
        assert status["toolsTruncated"] is True
        assert status["toolsDiscovered"] == 3
        assert status["toolsKept"] == 2
        # And the diagnostics surface reports it.
        diag = manager.diagnostics().get("servers", [])
        checks = {c["code"] for s in diag for c in s["checks"]}
        assert "tools_truncated" in checks
    finally:
        await manager.close()


def test_runtime_defaults_for_truncation_are_unknown_not_zero():
    rt = _ServerRuntime(MCPServerConfig(id="x", command="npx", args=["-y", "pkg"]))
    assert rt.tools_discovered is None
    assert rt.tools_kept is None
    assert rt.cache_stale is False


def test_schema_cache_stale_detection(tmp_path, monkeypatch):
    from harness.mcp import schema_cache

    monkeypatch.setenv("HARNESS_MCP_CACHE", str(tmp_path / "cache.json"))
    cfg = MCPServerConfig(id="s", command="npx", args=["-y", "pkg"])
    fp = schema_cache.config_fingerprint(cfg)
    # No entry yet: not stale (just missing).
    assert schema_cache.is_stale("s", fp) is False
    schema_cache.write_entry("s", fp, [{"name": "t"}])
    assert schema_cache.get_entry("s", fp) is not None
    assert schema_cache.is_stale("s", fp) is False
    # A changed config => stale, and get_entry refuses to serve it.
    assert schema_cache.is_stale("s", "different-fingerprint") is True
    assert schema_cache.get_entry("s", "different-fingerprint") is None

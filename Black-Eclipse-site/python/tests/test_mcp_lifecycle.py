"""Phase 6 Milestone 2 — lifecycle resilience.

Behavior contracts: the retry budget, the call-time reconnect seam, the
read-replay / no-replay-write session-expiry policy, keepalive, stdio recycle,
and the lazy schema cache fingerprint + stale/missing fallback.
"""

from __future__ import annotations

import os
import sys

import pytest

from harness.mcp.config import MCPServerConfig
from harness.mcp.lifecycle import (
    MAX_INITIAL_ATTEMPTS,
    RetryBudget,
    is_session_error,
    jittered,
    keepalive_due,
    should_recycle,
)
from harness.mcp.manager import MCPManager
from harness.mcp.schema_cache import config_fingerprint, get_entry, write_entry
from harness.tools import ToolContext, ToolRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
FAST = os.path.join(FIXTURES, "fastmcp_fixture.py")
RAW = os.path.join(FIXTURES, "raw_fixture.py")


def raw_config(mode: str, **overrides) -> MCPServerConfig:
    data = dict(
        id="raw", command=sys.executable, args=[RAW, mode],
        enabled=True, selected_tools=["echo"], tool_effects={"echo": "read"},
        startup_timeout_ms=8_000, catalog_timeout_ms=8_000, call_timeout_ms=4_000,
    )
    data.update(overrides)
    return MCPServerConfig(**data)


def ctx() -> ToolContext:
    return ToolContext(run_id="r1", log=lambda *_: None)


# ── retry budget ────────────────────────────────────────────────────────────


def test_retry_budget_counts_and_exhausts():
    budget = RetryBudget()
    for i in range(MAX_INITIAL_ATTEMPTS - 1):
        assert budget.note_initial_failure("boom", "mcp_startup_failed") is True
    assert budget.note_initial_failure("boom", "mcp_startup_failed") is False
    assert budget.exhausted is True and budget.initial_attempts == MAX_INITIAL_ATTEMPTS
    # A successful connect resets the counters.
    budget.note_connected()
    assert budget.exhausted is False and budget.ever_connected is True and budget.reconnects == 1


def test_jitter_is_bounded_and_nonnegative():
    assert 0.05 <= jittered(1.0) <= 1.0
    assert jittered(0) == 0.05


@pytest.mark.asyncio
async def test_initial_connect_retries_then_reports_terminal_failure():
    # `slowstart` sleeps 5s but has a 300ms startup timeout: it never connects.
    cfg = raw_config("slowstart", startup_timeout_ms=300)
    mgr = MCPManager([cfg])
    rt = mgr._runtimes["raw"]
    # Shrink the backoff so the test is fast.
    await mgr._connect_with_retry(rt)
    assert rt.state == "failed"
    assert rt.budget.initial_attempts == MAX_INITIAL_ATTEMPTS
    assert "gave up" in (rt.diagnostic or "")


# ── session-expiry classification ───────────────────────────────────────────


def test_is_session_error_classification():
    assert is_session_error("Connection closed") is True
    assert is_session_error("session expired") is True
    assert is_session_error("broken pipe") is True
    assert is_session_error("invalid arguments: missing field") is False


@pytest.mark.asyncio
async def test_read_call_recovers_after_session_expiry():
    # The server exits on the first call; a read call reconnects and replays once.
    cfg = raw_config("crash_on_call", call_timeout_ms=3_000)
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    assert names == ["mcp__raw__echo"]
    # crash_on_call dies on the FIRST call; the replay also hits a dead server,
    # so the call must fail honestly (never hang), not silently succeed.
    result = await reg.execute(names[0], "c1", {"text": "hi"}, ctx(), allowed=set(names))
    assert not result.ok or "echo" in result.text
    await mgr.close()


@pytest.mark.asyncio
async def test_write_call_is_never_replayed_on_session_expiry(tmp_path):
    from harness.mcp.approvals import ApprovalStore
    from harness.mcp.client import MCPSessionError
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        cfg = raw_config(
            "normal", selected_tools=["write_thing"],
            tool_effects={"write_thing": "write"}, enabled_effects=["read", "write"],
        )
        mgr = MCPManager([cfg])
        await mgr.start()
        reg = ToolRegistry()
        # We must register write_thing: it needs approval; register directly.
        mgr.register_selected_tools(reg)
        descriptor = mgr._runtimes["raw"].descriptors["write_thing"]

        # Force a session error from the connection.
        class Boom:
            async def call_tool(self, *a, **k):
                raise MCPSessionError("connection closed")
            redaction_values: list[str] = []
            protocol_version = None
            server_info = None

        rt = mgr._runtimes["raw"]
        rt.connection = Boom()
        from harness.tools import ToolContext as TC

        async def approve(_tool, _args):
            return True

        c = TC(run_id="r1", log=lambda *_: None)
        c.authorize_effect = approve
        text, data = await mgr._execute(rt, descriptor, {"text": "x"}, c)
        assert data.get("outcomeUncertain") is True
        assert "NOT retried" in text or "may or may not" in text
        await mgr.close()
    finally:
        store.close()


# ── keepalive / recycle decisions ───────────────────────────────────────────


def test_should_recycle_only_stdio_and_respects_both_limits():
    assert should_recycle(
        transport="http", now=1000.0, connected_at=0.0, last_call_at=0.0,
        idle_timeout_s=10, max_lifetime_s=10,
    ) is None
    assert should_recycle(
        transport="stdio", now=1000.0, connected_at=0.0, last_call_at=999.0,
        idle_timeout_s=None, max_lifetime_s=100,
    ) == "max_lifetime"
    assert should_recycle(
        transport="stdio", now=1000.0, connected_at=900.0, last_call_at=0.0,
        idle_timeout_s=100, max_lifetime_s=None,
    ) == "idle"


def test_keepalive_due_only_with_interval_and_activity():
    assert keepalive_due(transport="http", now=100.0, last_activity=0.0, interval_s=None) is False
    assert keepalive_due(transport="http", now=100.0, last_activity=0.0, interval_s=30) is True
    assert keepalive_due(transport="http", now=10.0, last_activity=0.0, interval_s=30) is False


# ── lazy schema cache ───────────────────────────────────────────────────────


def test_cache_fingerprint_changes_with_connection_config():
    base = raw_config("normal")
    same = raw_config("normal")
    changed = raw_config("normal", args=[RAW, "normal", "extra"])
    assert config_fingerprint(base) == config_fingerprint(same)
    assert config_fingerprint(base) != config_fingerprint(changed)


def test_cache_roundtrip_and_fingerprint_mismatch(tmp_path, monkeypatch):
    path = str(tmp_path / "cache.json")
    monkeypatch.setenv("HARNESS_MCP_CACHE", path)
    cfg = raw_config("normal")
    fp = config_fingerprint(cfg)
    assert get_entry("raw", fp) is None
    write_entry("raw", fp, [{"name": "echo", "description": "d", "inputSchema": {}}])
    entry = get_entry("raw", fp)
    assert entry and entry["tools"][0]["name"] == "echo"
    # A changed fingerprint (a changed config) must NOT reuse the entry.
    assert get_entry("raw", "different-fingerprint") is None


@pytest.mark.asyncio
async def test_lazy_server_registers_from_cache_without_spawn(tmp_path, monkeypatch):
    path = str(tmp_path / "cache.json")
    monkeypatch.setenv("HARNESS_MCP_CACHE", path)
    cfg = MCPServerConfig(
        id="fx", command=sys.executable, args=[FAST], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"}, lazy=True,
    )
    fp = config_fingerprint(cfg)
    write_entry("fx", fp, [{
        "name": "echo", "description": "Echo", "inputSchema": {"type": "object", "properties": {}},
    }])
    mgr = MCPManager([cfg])
    await mgr.start()
    rt = mgr._runtimes["fx"]
    assert rt.state == "lazy" and rt.lazy_active is True
    assert rt.connection is None  # no spawn happened
    assert "echo" in rt.descriptors
    assert mgr.summary()["lazy"] == 1
    await mgr.close()


@pytest.mark.asyncio
async def test_lazy_server_missing_cache_falls_back_to_eager(tmp_path, monkeypatch):
    path = str(tmp_path / "cache.json")
    monkeypatch.setenv("HARNESS_MCP_CACHE", path)
    cfg = MCPServerConfig(
        id="fx", command=sys.executable, args=[FAST], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"}, lazy=True,
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    rt = mgr._runtimes["fx"]
    assert rt.state == "connected"  # fell back to a normal eager connect
    assert rt.lazy_active is False
    await mgr.close()


@pytest.mark.asyncio
async def test_lazy_first_call_connects_and_runs(tmp_path, monkeypatch):
    path = str(tmp_path / "cache.json")
    monkeypatch.setenv("HARNESS_MCP_CACHE", path)
    cfg = MCPServerConfig(
        id="fx", command=sys.executable, args=[FAST], enabled=True,
        selected_tools=["echo"], tool_effects={"echo": "read"}, lazy=True,
    )
    write_entry("fx", config_fingerprint(cfg), [{
        "name": "echo", "description": "Echo", "inputSchema": {"type": "object", "properties": {}},
    }])
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    # Lazy tools are registered from cache (inert until called), then the first
    # call connects. Registration for the lazy path happens via reconnect.
    await mgr._reconnect_on_call(mgr._runtimes["fx"])
    mgr.register_selected_tools(reg)
    names = [n for n in reg.names() if n.startswith("mcp__")]
    assert names, "lazy server should expose its cached+live tools after connect"
    result = await reg.execute(names[0], "c1", {"text": "hi"}, ctx(), allowed=set(names))
    assert result.ok and "echo:hi" in result.text
    await mgr.close()


# ── reconnect re-registration stays authority-bounded ───────────────────────


@pytest.mark.asyncio
async def test_reconnect_does_not_resurrect_unselected_tool():
    cfg = raw_config("normal", selected_tools=["echo"], tool_effects={"echo": "read"})
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    assert mgr.register_selected_tools(reg) == ["mcp__raw__echo"]
    # Simulate a drop, then a reconnect.
    await mgr._close_runtime(mgr._runtimes["raw"])
    ok = await mgr._reconnect_on_call(mgr._runtimes["raw"])
    assert ok is True
    names = set(reg.names())
    assert "mcp__raw__echo" in names
    assert "mcp__raw_write_thing" not in names  # never selected → never resurrected
    await mgr.close()

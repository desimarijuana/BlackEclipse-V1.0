"""MCP integration tests (Phase 5A–5C).

Deterministic and offline: every test launches a local fixture server as a real
subprocess through the same stdio client the runtime uses. No network, no API
key. The 17 scenarios mirror the phase brief's acceptance list.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from harness.mcp.client import MCPConnection, MCPError
from harness.mcp.config import (
    MCPServerConfig,
    load_mcp_configs,
    redact_secrets,
    remove_mcp_config,
    upsert_mcp_config,
)
from harness.mcp.manager import MCPManager
from harness.mcp.naming import (
    classify_effect,
    namespace_tool,
    normalize_input_schema,
    SchemaError,
)
from harness.tools import ToolContext, ToolRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
FAST = os.path.join(FIXTURES, "fastmcp_fixture.py")
RAW = os.path.join(FIXTURES, "raw_fixture.py")


def raw_config(mode: str, **overrides) -> MCPServerConfig:
    data = dict(
        id="raw",
        command=sys.executable,
        args=[RAW, mode],
        enabled=True,
        selected_tools=["echo"],
        startup_timeout_ms=8_000,
        catalog_timeout_ms=8_000,
        call_timeout_ms=8_000,
    )
    data.update(overrides)
    return MCPServerConfig(**data)


def fast_config(**overrides) -> MCPServerConfig:
    data = dict(
        id="fx",
        command=sys.executable,
        args=[FAST],
        enabled=True,
        selected_tools=["echo", "write_thing"],
    )
    data.update(overrides)
    return MCPServerConfig(**data)


def ctx() -> ToolContext:
    return ToolContext(run_id="r1", log=lambda *_: None)


class RecordingEmitter:
    def __init__(self):
        self.events = []

    async def emit(self, event_type, data=None):
        self.events.append((event_type, data or {}))
        return {"type": event_type, "data": data or {}}


# ── 1. valid stdio initialize and tool discovery ────────────────────────────


@pytest.mark.asyncio
async def test_stdio_initialize_and_discovery():
    conn = MCPConnection(fast_config())
    try:
        await conn.start()
        assert conn.ready
        assert conn.protocol_version
        assert conn.server_info and conn.server_info.get("name") == "fixture"
        assert {t.name for t in conn.tools} >= {"echo", "write_thing"}
    finally:
        await conn.close()
        assert conn.state == "closed"


# ── 2. disabled server does not launch or register tools ────────────────────


@pytest.mark.asyncio
async def test_disabled_server_not_registered():
    cfg = fast_config(enabled=False)
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    assert mgr.register_selected_tools(reg) == []
    assert reg.names() == []
    status = mgr.summary()
    assert status["connected"] == 0 and status["registeredTools"] == 0
    await mgr.close()


# ── 3. discovered but unselected tool is not callable ───────────────────────


@pytest.mark.asyncio
async def test_unselected_tool_not_registered():
    cfg = fast_config(selected_tools=["echo"])
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    registered = mgr.register_selected_tools(reg)
    assert registered == ["mcp_fx_echo"]
    assert reg.get("mcp_fx_write_thing") is None
    # Discovery still reports it, marked unselected/inert.
    tools = {t["originalName"]: t for t in mgr.statuses()[0]["tools"]}
    assert tools["write_thing"]["selected"] is False
    assert tools["write_thing"]["activatable"] is False
    await mgr.close()


# ── 4. selected read-only tool registers under a namespaced name ────────────


@pytest.mark.asyncio
async def test_selected_read_tool_namespaced():
    mgr = MCPManager([fast_config(selected_tools=["echo"])])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    assert name == "mcp_fx_echo"
    result = await reg.execute(name, "c1", {"text": "hi"}, ctx(), allowed={name})
    assert result.ok
    assert "echo:hi" in result.text
    assert result.data["source"] == {"kind": "mcp", "serverId": "fx", "tool": "echo"}
    await mgr.close()


# ── 5. name normalization collision is handled deterministically ────────────


def test_name_normalization_collision_is_deterministic():
    # "a-b" and "a.b" both sanitize to "a_b" for the same server.
    first = namespace_tool("s", "a-b", taken={})
    second = namespace_tool("s", "a.b", taken={first: ("s", "a-b")})
    assert first == "mcp_s_a_b"
    assert second != first and second.startswith("mcp_s_a_b_")
    # Stable across calls (digest, not salted hash()).
    assert second == namespace_tool("s", "a.b", taken={first: ("s", "a-b")})
    # Same identity returns the same name (idempotent re-resolution).
    assert namespace_tool("s", "a-b", taken={first: ("s", "a-b")}) == first


@pytest.mark.asyncio
async def test_duplicate_sanitized_names_do_not_collide():
    mgr = MCPManager([raw_config("duplicate", selected_tools=["a-b", "a.b", "a_b"])])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    assert len(names) == 3
    assert len(set(names)) == 3
    assert all(n.startswith("mcp_raw_a_b") for n in names)
    await mgr.close()


# ── 6. malformed schema is rejected safely ──────────────────────────────────


def test_malformed_schema_rejected():
    with pytest.raises(SchemaError):
        normalize_input_schema({"type": "object", "properties": {"x": {"type": "weird"}}})
    with pytest.raises(SchemaError):
        normalize_input_schema("not-an-object")


@pytest.mark.asyncio
async def test_malformed_schema_tool_skipped_not_crashing():
    mgr = MCPManager([raw_config("malformed", selected_tools=["broken"])])
    await mgr.start()  # must not raise
    reg = ToolRegistry()
    assert mgr.register_selected_tools(reg) == []
    descriptor = mgr.statuses()[0]["tools"][0]
    assert descriptor["activatable"] is False
    assert "schema" in (descriptor["diagnostic"] or "")
    await mgr.close()


# ── 7. invalid arguments rejected by Eclipse validation before the call ─────


@pytest.mark.asyncio
async def test_invalid_arguments_rejected_before_server_call():
    mgr = MCPManager([fast_config(selected_tools=["echo"])])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    conn = mgr._runtimes["fx"].connection
    before = conn.call_count
    result = await reg.execute(name, "c1", {}, ctx(), allowed={name})  # text required
    assert not result.ok
    assert result.error.code == "TOOL_VALIDATION_FAILED"
    assert conn.call_count == before  # never reached the server
    await mgr.close()


# ── 8. agent allowlist denial prevents execution ────────────────────────────


@pytest.mark.asyncio
async def test_agent_allowlist_denial_prevents_execution():
    mgr = MCPManager([fast_config(selected_tools=["echo"])])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    conn = mgr._runtimes["fx"].connection
    before = conn.call_count
    result = await reg.execute(name, "c1", {"text": "hi"}, ctx(), allowed={"other"})
    assert not result.ok
    assert result.error.code == "TOOL_FORBIDDEN"
    assert conn.call_count == before
    await mgr.close()


# ── 9. non-read/unknown effect tool is not enabled ──────────────────────────


@pytest.mark.asyncio
async def test_non_read_tool_not_enabled():
    cfg = fast_config(selected_tools=["echo", "write_thing"])
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    names = mgr.register_selected_tools(reg)
    assert names == ["mcp_fx_echo"]  # write_thing refused
    tools = {t["originalName"]: t for t in mgr.statuses()[0]["tools"]}
    assert tools["write_thing"]["effect"] in ("write", "external_action", "unknown")
    assert tools["write_thing"]["activatable"] is False
    await mgr.close()


def test_effect_classification_precedence():
    class Ann:
        read_only_hint = True
        destructive_hint = None

    effect, source = classify_effect(original_name="t", declared="read", annotations=Ann())
    assert (effect, source) == ("read", "declared")
    effect, source = classify_effect(original_name="t", declared=None, annotations=Ann())
    assert (effect, source) == ("read", "annotation")
    effect, source = classify_effect(original_name="t", declared=None, annotations=None)
    assert (effect, source) == ("unknown", "assumed")


# ── 10. startup timeout and catalog timeout are safe and observable ─────────


@pytest.mark.asyncio
async def test_startup_timeout_is_safe_and_observable():
    cfg = raw_config("slowstart", startup_timeout_ms=300)
    conn = MCPConnection(cfg)
    with pytest.raises(MCPError) as exc:
        await conn.start()
    assert exc.value.code == "mcp_timeout"
    assert conn.state == "failed"
    await conn.close()


@pytest.mark.asyncio
async def test_catalog_timeout_is_safe_and_observable():
    cfg = raw_config("slowcatalog", startup_timeout_ms=8_000, catalog_timeout_ms=300)
    conn = MCPConnection(cfg)
    with pytest.raises(MCPError) as exc:
        await conn.start()
    assert exc.value.code == "mcp_timeout"
    assert "catalog" in str(exc.value)
    await conn.close()


# ── 11. tool execution timeout and cancellation are propagated ──────────────


@pytest.mark.asyncio
async def test_tool_execution_timeout_propagated():
    cfg = raw_config("slow", call_timeout_ms=300)
    conn = MCPConnection(cfg)
    await conn.start()
    with pytest.raises(MCPError) as exc:
        await conn.call_tool("echo", {"text": "x"}, timeout_ms=300)
    assert exc.value.code == "mcp_timeout"
    await conn.close()


@pytest.mark.asyncio
async def test_tool_execution_cancellation_propagated():
    cfg = raw_config("slow", call_timeout_ms=8_000)
    conn = MCPConnection(cfg)
    await conn.start()

    async def _call():
        return await conn.call_tool("echo", {"text": "x"})

    task = asyncio.create_task(_call())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await conn.close()


# ── 12. oversized result is bounded and marked truncated ────────────────────


@pytest.mark.asyncio
async def test_oversized_result_bounded_and_marked():
    cfg = raw_config("big", output_limit_bytes=1_000)
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    result = await reg.execute(name, "c1", {"text": "x"}, ctx(), allowed={name})
    assert result.ok
    assert "TRUNCATED" in result.text
    # The text body stays within the configured bound (plus the header).
    assert len(result.text.encode("utf-8")) < 3_000
    assert result.data.get("truncated") is True
    await mgr.close()


# ── 13. server crash / malformed response returns a structured diagnostic ───


@pytest.mark.asyncio
async def test_server_crash_is_structured_diagnostic():
    mgr = MCPManager([raw_config("crash")])
    await mgr.start()  # must not raise
    reg = ToolRegistry()
    assert mgr.register_selected_tools(reg) == []
    status = mgr.statuses()[0]
    assert status["state"] == "failed"
    assert status["diagnostic"]
    await mgr.close()


# ── 14. secret values do not appear in logs, events, or errors ──────────────


@pytest.mark.asyncio
async def test_secrets_redacted_from_results_and_events():
    secret = "SUPER-SECRET-TOKEN-123"
    cfg = MCPServerConfig(
        id="raw",
        command=sys.executable,
        args=[RAW, "secret_echo"],
        enabled=True,
        selected_tools=["echo"],
        env={"FIXTURE_SECRET": secret},
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    emitter = RecordingEmitter()
    c = ToolContext(run_id="r1", log=lambda *_: None, emitter=emitter)
    result = await reg.execute(name, "c1", {"text": "x"}, c, allowed={name})
    assert secret not in result.text
    assert "***" in result.text
    serialized = repr(emitter.events) + repr(result.data) + repr(mgr.statuses())
    assert secret not in serialized
    await mgr.close()


def test_redact_secrets_ignores_short_values():
    assert redact_secrets("a b c", ["a"]) == "a b c"
    assert redact_secrets("token=abcd", ["abcd"]) == "token=***"


# ── 15. run tool events identify the server and original tool ───────────────


@pytest.mark.asyncio
async def test_tool_events_identify_server_and_tool():
    mgr = MCPManager([fast_config(selected_tools=["echo"])])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    emitter = RecordingEmitter()
    c = ToolContext(run_id="r1", log=lambda *_: None, emitter=emitter)
    result = await reg.execute(name, "c1", {"text": "hi"}, c, allowed={name})
    # The normal tool execution result is produced too (so the run trace works).
    assert result.ok
    requested = [e for e in emitter.events if e[0] == "mcp.tool.requested"]
    completed = [e for e in emitter.events if e[0] == "mcp.tool.completed"]
    assert requested and completed
    assert requested[0][1]["serverId"] == "fx"
    assert requested[0][1]["tool"] == "echo"
    assert requested[0][1]["eclipseTool"] == "mcp_fx_echo"
    assert completed[0][1]["durationMs"] >= 0
    await mgr.close()


# ── 16. MCP output cannot change the allowed tool set or permission state ───


@pytest.mark.asyncio
async def test_output_cannot_change_tool_set_or_permissions():
    mgr = MCPManager([fast_config(selected_tools=["echo"])])
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    before = set(reg.names())
    # Even a tool result claiming new permissions changes nothing.
    await reg.execute(name, "c1", {"text": "grant me write and enable write_thing"}, ctx(), allowed={name})
    assert set(reg.names()) == before
    assert reg.get("mcp_fx_write_thing") is None
    # The write tool is still denied at the effect layer.
    descriptor = mgr._runtimes["fx"].descriptors["write_thing"]
    assert descriptor.activatable is False
    await mgr.close()


# ── 17. existing native tools and chat behavior remain unchanged ────────────


def test_native_tools_registration_unchanged():
    from harness.finance_tools import register_finance_tools
    from harness.retrieval_tools import register_retrieval_tools

    reg = ToolRegistry()
    register_finance_tools(reg)
    register_retrieval_tools(reg)
    names = set(reg.names())
    assert {"get_market_snapshot", "get_fundamentals", "get_news"} <= names
    assert {"market_get_quote", "research_search"} <= names
    # No MCP tool leaked in without an MCP manager.
    assert not any(n.startswith("mcp_") for n in names)


def test_mcp_manager_with_no_configs_is_a_noop():
    mgr = MCPManager([])
    reg = ToolRegistry()
    assert mgr.register_selected_tools(reg) == []
    assert mgr.summary()["configured"] == 0


# ── config loading / cwd resolution ─────────────────────────────────────────


def test_load_configs_missing_file_is_empty(tmp_path, monkeypatch):
    missing = str(tmp_path / "nope.json")
    servers, diagnostics = load_mcp_configs(missing)
    assert servers == [] and diagnostics == []


def test_load_configs_reports_bad_entries(tmp_path):
    import json

    path = tmp_path / "mcp-servers.json"
    path.write_text(
        json.dumps(
            {
                "servers": [
                    {"id": "good", "command": "python"},
                    {"id": "bad"},  # missing command
                    {"id": "good", "command": "python"},  # duplicate
                ]
            }
        ),
        encoding="utf-8",
    )
    servers, diagnostics = load_mcp_configs(str(path))
    assert [s.id for s in servers] == ["good"]
    codes = {d["code"] for d in diagnostics}
    assert "invalid_server" in codes and "duplicate_server" in codes


def test_relative_cwd_resolves_against_repo_root(tmp_path, monkeypatch):
    from harness.eclipse_memory.config import repo_root

    cfg = MCPServerConfig(id="s", command="python", cwd="python/harness")
    assert cfg.resolve_cwd() == os.path.join(repo_root(), "python", "harness")
    # An absolute path is honored; a non-existent path is treated as unset.
    assert MCPServerConfig(id="s", command="python", cwd=str(tmp_path)).resolve_cwd() == str(tmp_path)
    assert MCPServerConfig(id="s", command="python", cwd="no/such/dir").resolve_cwd() is None


def test_environment_allowlist_only_copies_named_values(monkeypatch):
    monkeypatch.setenv("ALLOWED_VAR", "yes")
    monkeypatch.setenv("UNRELATED_SECRET", "nope")
    cfg = MCPServerConfig(
        id="s", command="python", env_allowlist=["ALLOWED_VAR", "UNRELATED_SECRET"], env={"OWN": "1"}
    )
    resolved = cfg.resolve_environment()
    # Both named vars are copied (they are explicitly allowlisted); an unnamed
    # process var is never forwarded.
    assert resolved["ALLOWED_VAR"] == "yes"
    assert resolved["OWN"] == "1"
    assert "PATH" not in resolved


def test_limits_are_clamped():
    cfg = MCPServerConfig(
        id="s",
        command="python",
        call_timeout_ms=10_000_000,
        output_limit_bytes=0,
        max_concurrency=999,
    )
    limits = cfg.limits()
    assert limits["callTimeoutMs"] <= 120_000
    assert limits["outputLimitBytes"] >= 1_000
    assert limits["maxConcurrency"] <= 16


# ── 5E: catalog CRUD, reload and secret-free public view ────────────────────


def test_config_roundtrip_upsert_and_remove(tmp_path):
    path = str(tmp_path / "mcp-servers.json")
    a = MCPServerConfig(id="a", command="python", enabled=True, selected_tools=["x"])
    b = MCPServerConfig(id="b", command="python")
    upsert_mcp_config(a, path)
    upsert_mcp_config(b, path)
    servers, _ = load_mcp_configs(path)
    assert {s.id for s in servers} == {"a", "b"}
    # Upsert replaces in place, preserving order and the other entry.
    upsert_mcp_config(MCPServerConfig(id="a", command="python", enabled=False), path)
    servers, _ = load_mcp_configs(path)
    assert [s.id for s in servers] == ["a", "b"]
    assert servers[0].enabled is False
    assert remove_mcp_config("a", path) is True
    assert remove_mcp_config("a", path) is False
    servers, _ = load_mcp_configs(path)
    assert [s.id for s in servers] == ["b"]


def test_public_dict_hides_env_values():
    cfg = MCPServerConfig(id="s", command="python", env={"TOKEN": "topsecretvalue"})
    public = cfg.public_dict()
    assert "topsecretvalue" not in repr(public)
    assert public["env"] == {"TOKEN": None}
    assert public["envKeys"] == ["TOKEN"]
    assert public["secretCount"] == 1


@pytest.mark.asyncio
async def test_reload_activates_and_deactivates_without_restart():
    reg = ToolRegistry()
    mgr = MCPManager([fast_config(selected_tools=["echo"])])
    await mgr.start()
    assert mgr.register_selected_tools(reg) == ["mcp_fx_echo"]
    assert reg.get("mcp_fx_echo") is not None

    # Reload with the server disabled: the previously-registered tool is dropped.
    disabled = fast_config(selected_tools=["echo"], enabled=False)
    assert await mgr.reload([disabled]) == []
    assert reg.get("mcp_fx_echo") is None
    # The native registry contract is not disturbed.
    assert reg.names() == []

    # Reload re-enabling selects the tool again.
    assert await mgr.reload([fast_config(selected_tools=["echo"])]) == ["mcp_fx_echo"]
    assert reg.get("mcp_fx_echo") is not None
    await mgr.close()


@pytest.mark.asyncio
async def test_reload_keeps_native_tools():
    from harness.finance_tools import register_finance_tools

    reg = ToolRegistry()
    register_finance_tools(reg)
    native = set(reg.names())
    mgr = MCPManager([fast_config(selected_tools=["echo"])])
    await mgr.start()
    mgr.register_selected_tools(reg)
    await mgr.reload([fast_config(selected_tools=["echo"])])
    assert native <= set(reg.names())
    await mgr.close()


@pytest.mark.asyncio
async def test_test_server_discovers_without_registering():
    reg = ToolRegistry()
    mgr = MCPManager([])
    result = await mgr.test_server(fast_config(selected_tools=["echo"]))
    assert result["state"] == "connected"
    assert {t["originalName"] for t in result["tools"]} >= {"echo", "write_thing"}
    assert result["catalogDigest"]
    # Nothing was registered by a test.
    assert reg.names() == []
    assert mgr.public_configs() == []


@pytest.mark.asyncio
async def test_test_server_failure_is_a_safe_diagnostic():
    mgr = MCPManager([])
    result = await mgr.test_server(raw_config("crash"))
    assert result["state"] == "failed"
    assert result["diagnostic"]


def test_catalog_digest_is_stable_and_schema_sensitive():
    from harness.mcp.manager import MCPToolDescriptor, _catalog_digest, _ServerRuntime

    rt = _ServerRuntime(fast_config())
    rt.descriptors = {
        "echo": MCPToolDescriptor(
            original_name="echo", eclipse_name="mcp_fx_echo", description="d",
            input_schema={"type": "object", "properties": {}}, effect="read",
            effect_source="annotation", selected=True, activatable=True,
        )
    }
    first = _catalog_digest(rt)
    assert first == _catalog_digest(rt)  # stable across calls
    rt.descriptors["echo"].input_schema = {
        "type": "object", "properties": {"text": {"type": "string"}}
    }
    assert _catalog_digest(rt) != first


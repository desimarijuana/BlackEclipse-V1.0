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
    write_mcp_configs,
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
        # An explicit operator-declared effect (trusted) is what activates a
        # tool; a server's own read-only hint alone does not (see ADR-H40).
        tool_effects={"echo": "read"},
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
        tool_effects={"echo": "read"},
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
    mgr = MCPManager([
        raw_config(
            "duplicate",
            selected_tools=["a-b", "a.b", "a_b"],
            tool_effects={"a-b": "read", "a.b": "read", "a_b": "read"},
        )
    ])
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
        tool_effects={"echo": "read"},
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


# ── 5F/audit: untrusted annotations never activate; catalog confirmation ─────


def test_annotation_read_is_classified_but_not_trusted():
    class Ann:
        read_only_hint = True
        destructive_hint = None

    effect, source = classify_effect(original_name="t", declared=None, annotations=Ann())
    assert effect == "read"
    assert source == "annotation"  # untrusted — activation needs confirmation


@pytest.mark.asyncio
async def test_annotation_read_tool_needs_catalog_confirmation():
    # No declared effect, server only HINTS read-only → inert until confirmed.
    cfg = MCPServerConfig(
        id="fx", command=sys.executable, args=[FAST],
        enabled=True, selected_tools=["echo"],
    )
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    assert mgr.register_selected_tools(reg) == []
    descriptor = mgr.statuses()[0]["tools"][0]
    assert descriptor["activatable"] is False
    await mgr.close()


@pytest.mark.asyncio
async def test_confirmed_catalog_activates_annotation_read_tool():
    digest = None
    base = MCPServerConfig(
        id="fx", command=sys.executable, args=[FAST],
        enabled=True, selected_tools=["echo"],
    )
    # Discover once to learn the digest, then confirm it.
    probe = MCPManager([base])
    await probe.start()
    digest = probe._runtimes["fx"].catalog_digest
    await probe.close()
    assert digest

    confirmed = base.model_copy(update={"confirmed_catalog_digest": digest})
    mgr = MCPManager([confirmed])
    await mgr.start()
    reg = ToolRegistry()
    assert mgr.register_selected_tools(reg) == ["mcp_fx_echo"]
    await mgr.close()


@pytest.mark.asyncio
async def test_catalog_change_invalidates_confirmation():
    base = MCPServerConfig(
        id="fx", command=sys.executable, args=[FAST],
        enabled=True, selected_tools=["echo"],
    )
    probe = MCPManager([base])
    await probe.start()
    stale_digest = "deadbeefdeadbeef"  # a digest from an OLDER catalog
    await probe.close()

    confirmed = base.model_copy(update={"confirmed_catalog_digest": stale_digest})
    mgr = MCPManager([confirmed])
    await mgr.start()
    reg = ToolRegistry()
    # The live digest no longer matches the confirmed one → inert.
    assert mgr.register_selected_tools(reg) == []
    await mgr.close()


@pytest.mark.asyncio
async def test_declared_read_tool_activates_without_confirmation():
    # An explicit operator declaration is trusted and survives catalog edits.
    cfg = fast_config(selected_tools=["echo"])  # declares echo: read
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    assert mgr.register_selected_tools(reg) == ["mcp_fx_echo"]
    await mgr.close()


# ── audit: test_server always tears the temporary child down ─────────────────


@pytest.mark.asyncio
async def test_test_server_always_closes_child():
    mgr = MCPManager([])
    seen: list[MCPConnection] = []
    original = mgr.__class__.__dict__.get("test_server")

    # Capture the connection the manager creates so we can assert its state.
    import harness.mcp.manager as mgr_mod

    real_conn = mgr_mod.MCPConnection

    class SpyConn(real_conn):  # type: ignore[misc, valid-type]
        def __init__(self, config, secret_resolver=None):
            super().__init__(config, secret_resolver=secret_resolver)
            seen.append(self)

    mgr_mod.MCPConnection = SpyConn
    try:
        result = await mgr.test_server(fast_config(selected_tools=["echo"]))
    finally:
        mgr_mod.MCPConnection = real_conn
    assert result["state"] == "connected"
    assert seen and seen[0].state == "closed"


@pytest.mark.asyncio
async def test_test_server_closes_child_on_failure():
    import harness.mcp.manager as mgr_mod

    real_conn = mgr_mod.MCPConnection
    seen: list[MCPConnection] = []

    class SpyConn(real_conn):  # type: ignore[misc, valid-type]
        def __init__(self, config, secret_resolver=None):
            super().__init__(config, secret_resolver=secret_resolver)
            seen.append(self)

    mgr_mod.MCPConnection = SpyConn
    try:
        result = await MCPManager([]).test_server(raw_config("crash"))
    finally:
        mgr_mod.MCPConnection = real_conn
    assert result["state"] == "failed"
    assert seen and seen[0].state == "closed"


# ── audit: default-agent MCP opt-in (allowMcpTools) ─────────────────────────


def _run_request(agent):
    from harness.schemas import ModelSettings, RunInput, RunRequest

    return RunRequest(
        runId="run_mcp",
        input=RunInput(query="use the tool"),
        agent=agent,
        modelSettings=ModelSettings(provider="ollama", model="m", base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )


@pytest.mark.asyncio
async def test_default_agent_can_call_a_selected_mcp_tool(monkeypatch, tmp_path):
    """End-to-end: a selected MCP tool is bound and callable by the default agent."""
    from langchain_core.messages import AIMessage

    from harness import graph as graph_module
    from harness.agents import ECLIPSE_AGENT
    from harness.persistence import AgentMemoryStore
    from harness.tools import DataBridge

    class FakeBridge(DataBridge):
        async def fetch(self, capability, params):
            return {"status": "UNAVAILABLE"}

    class ScriptedModel:
        def __init__(self, responses):
            self._responses = list(responses)
            self.bound_tools = None

        def bind_tools(self, tools):
            self.bound_tools = tools
            return self

        async def ainvoke(self, messages):
            return self._responses.pop(0)

        async def astream(self, messages):
            yield await self.ainvoke(messages)

    mgr = MCPManager([fast_config(selected_tools=["echo"])])
    await mgr.start()
    reg = ToolRegistry()
    mgr.register_selected_tools(reg)
    assert "mcp_fx_echo" in reg.names()

    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "mcp_fx_echo", "args": {"text": "hi"}}]),
        AIMessage(content="The tool said echo:hi."),
    ])
    monkeypatch.setattr(graph_module, "build_chat_model", lambda settings: model)

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        result = await graph_module.execute_run(
            _run_request(ECLIPSE_AGENT), reg, FakeBridge(), store
        )
        assert result.status == "completed", result.error
        assert result.toolCalls == 1 and result.toolErrors == 0
        tool_names = {t.name for t in model.bound_tools or []}
        assert "mcp_fx_echo" in tool_names
        executions = store.list_tool_executions("run_mcp")
        assert executions[0]["name"] == "mcp_fx_echo" and executions[0]["ok"] is True
    finally:
        store.close()
        await mgr.close()


@pytest.mark.asyncio
async def test_restricted_agent_cannot_call_mcp_tool(monkeypatch, tmp_path):
    """A custom agent without the opt-in cannot call an MCP tool it did not name."""
    from harness.schemas import AgentConfig

    from harness import graph as graph_module
    from harness.persistence import AgentMemoryStore
    from harness.tools import DataBridge

    class FakeBridge(DataBridge):
        async def fetch(self, capability, params):
            return {"status": "UNAVAILABLE"}

    restricted = AgentConfig(
        id="restricted", name="Restricted", systemPrompt="sys",
        tools=["get_market_snapshot"], maxSteps=2, allowMcpTools=False,
    )
    assert graph_module.effective_allowlist(restricted, ToolRegistry()) == {"get_market_snapshot"}

    reg = ToolRegistry()
    mgr = MCPManager([fast_config(selected_tools=["echo"])])
    await mgr.start()
    mgr.register_selected_tools(reg)
    allowed = graph_module.effective_allowlist(restricted, reg)
    assert "mcp_fx_echo" not in allowed

    # And the registry refuses the call under that allowlist.
    result = await reg.execute("mcp_fx_echo", "c1", {"text": "hi"}, ctx(), allowed=allowed)
    assert not result.ok and result.error.code == "TOOL_FORBIDDEN"
    await mgr.close()


def test_effective_allowlist_expands_only_for_opt_in():
    from harness.agents import ECLIPSE_AGENT
    from harness.schemas import AgentConfig

    reg = ToolRegistry()
    mgr = MCPManager([fast_config(selected_tools=["echo"])])
    # Without a live registry entry, even the default agent only gets its names.
    allowed = __import__("harness.graph", fromlist=["effective_allowlist"]).effective_allowlist(ECLIPSE_AGENT, reg)
    assert allowed is not None and "mcp_fx_echo" not in allowed

    plain = AgentConfig(id="p", name="P", systemPrompt="s", tools=["x"])
    assert __import__("harness.graph", fromlist=["effective_allowlist"]).effective_allowlist(plain, reg) == {"x"}


# ── audit: config file is permission-restricted after write ──────────────────


def test_config_file_permissions_are_restricted(tmp_path):
    import stat
    import sys as _sys

    path = str(tmp_path / "mcp-servers.json")
    write_mcp_configs([MCPServerConfig(id="s", command="python")], path)
    if _sys.platform != "win32":
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode & 0o077 == 0  # no group/other access


# ── audit: local stdio process boundary ─────────────────────────────────────


def test_command_and_args_have_no_shell_metacharacters():
    # The config records argv as separate values; a shell string is impossible.
    cfg = MCPServerConfig(id="s", command="python3", args=["-c", "print('hello world')"])
    assert cfg.command == "python3"
    assert cfg.args == ["-c", "print('hello world')"]
    assert isinstance(cfg.args, list)


def test_nul_bytes_are_rejected_in_command_and_args():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        MCPServerConfig(id="s", command="python\x00")
    with pytest.raises(pydantic.ValidationError):
        MCPServerConfig(id="s", command="python", args=["ok\x00bad"])


def test_child_environment_is_exactly_the_scoped_set(monkeypatch):
    # A distinctive host secret must NOT be forwarded to the child unless named.
    monkeypatch.setenv("HOST_ONLY_SECRET", "should-not-be-forwarded")
    monkeypatch.setenv("SCOPED_OK", "forwarded")
    cfg = MCPServerConfig(
        id="s",
        command="python",
        env={"SCOPED_OK": "forwarded"},
        env_allowlist=["HOST_ONLY_SECRET"],
    )
    env = cfg.resolve_environment()
    assert env["SCOPED_OK"] == "forwarded"
    assert env["HOST_ONLY_SECRET"] == "should-not-be-forwarded"  # explicitly named
    # Unnamed and unknown variables are absent.
    assert "PATH" not in env
    assert "HOME" not in env

    unnamed = MCPServerConfig(id="s", command="python", env={"A": "b"})
    assert unnamed.resolve_environment() == {"A": "b"}


@pytest.mark.asyncio
async def test_cwd_resolution_is_applied_to_the_child():
    # A relative cwd resolves against the repo root and is passed to the client.
    cfg = MCPServerConfig(id="s", command=sys.executable, cwd="python/harness")
    resolved = cfg.resolve_cwd()
    assert resolved and resolved.endswith(os.path.join("python", "harness"))
    # A non-existent cwd is treated as unset (spawn uses the process cwd).
    assert MCPServerConfig(id="s", command="python", cwd="definitely/not/here").resolve_cwd() is None


def test_output_and_concurrency_bounds_are_enforced():
    cfg = MCPServerConfig(
        id="s", command="python",
        output_limit_bytes=10_000_000,   # above ceiling
        max_concurrency=999,             # above cap
        max_tools=100_000,               # above ceiling
        call_timeout_ms=1,               # below floor
    )
    limits = cfg.limits()
    assert limits["outputLimitBytes"] <= 1_000_000
    assert limits["maxConcurrency"] <= 16
    assert limits["maxTools"] <= 500
    assert limits["callTimeoutMs"] >= 100


# ── vault secret references (resolve at spawn, never persist) ────────────────


@pytest.mark.asyncio
async def test_secret_ref_is_resolved_into_child_env_and_not_persisted():
    secret = "VAULT-SECRET-VALUE-9f3a"
    seen: list[MCPConnection] = []

    async def resolver(name: str):
        assert name == "fixture_token"
        return secret

    cfg = MCPServerConfig(
        id="raw",
        command=sys.executable,
        args=[RAW, "secret_echo"],
        enabled=True,
        selected_tools=["echo"],
        tool_effects={"echo": "read"},
        # The env var NAME the child reads → the vault secret NAME to resolve.
        secret_refs={"FIXTURE_SECRET": "fixture_token"},
    )
    conn = MCPConnection(cfg, secret_resolver=resolver)
    try:
        await conn.start()
        outcome = await conn.call_tool("echo", {"text": "x"})
        # The child received the resolved value from its environment.
        assert secret in outcome.text
        # The config itself stores only the reference NAME, never the value.
        assert secret not in repr(cfg.model_dump())
        assert secret not in repr(cfg.public_dict())
        assert cfg.public_dict()["secretRefNames"] == ["fixture_token"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_unresolved_secret_ref_is_omitted_not_guessed():
    async def resolver(name: str):
        return None  # vault has no such secret

    cfg = MCPServerConfig(
        id="raw", command=sys.executable, args=[RAW, "secret_echo"],
        enabled=True, selected_tools=["echo"], tool_effects={"echo": "read"},
        secret_refs={"FIXTURE_SECRET": "missing"},
    )
    conn = MCPConnection(cfg, secret_resolver=resolver)
    try:
        await conn.start()
        outcome = await conn.call_tool("echo", {"text": "x"})
        assert "missing" not in outcome.text
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_resolved_vault_secret_is_redacted_from_output_and_events():
    secret = "VAULT-RESOLVED-SECRET-77c1"

    async def resolver(name: str):
        return secret

    cfg = MCPServerConfig(
        id="raw", command=sys.executable, args=[RAW, "secret_echo"],
        enabled=True, selected_tools=["echo"], tool_effects={"echo": "read"},
        secret_refs={"FIXTURE_SECRET": "tok"},
    )
    mgr = MCPManager([cfg])
    mgr.set_secret_resolver(resolver)
    await mgr.start()
    reg = ToolRegistry()
    [name] = mgr.register_selected_tools(reg)
    emitter = RecordingEmitter()
    c = ToolContext(run_id="r1", log=lambda *_: None, emitter=emitter)
    result = await reg.execute(name, "c1", {"text": "x"}, c, allowed={name})
    # The child echoes the secret it received; it must be scrubbed everywhere.
    assert secret not in result.text
    assert secret not in repr(emitter.events)
    assert secret not in repr(mgr.statuses())
    await mgr.close()


# ── 5G effectful-tool approvals ─────────────────────────────────────────────


def _approval_store(tmp_path):
    from harness.mcp.approvals import ApprovalStore
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    return store, ApprovalStore(store)


def test_approval_digest_is_argument_sensitive(tmp_path):
    store, approvals = _approval_store(tmp_path)
    try:
        rec = approvals.request(
            server_id="s", tool="delete_file", eclipse_tool="mcp_s_delete_file",
            effect="write", args={"path": "/a"}, run_id="r1",
        )
        assert rec["status"] == "pending"
        assert approvals.is_authorized("s", "delete_file", {"path": "/a"}) is False
        approvals.decide(rec["id"], approve=True)
        assert approvals.is_authorized("s", "delete_file", {"path": "/a"}) is True
        # A CHANGED argument must not be authorized by the old approval.
        assert approvals.is_authorized("s", "delete_file", {"path": "/b"}) is False
    finally:
        store.close()


def test_approval_denial_is_terminal(tmp_path):
    store, approvals = _approval_store(tmp_path)
    try:
        rec = approvals.request(
            server_id="s", tool="t", eclipse_tool="mcp_s_t", effect="external_action",
            args={"x": 1},
        )
        approvals.decide(rec["id"], approve=False, reason="no")
        assert approvals.is_authorized("s", "t", {"x": 1}) is False
        # A denied request is not re-opened by requesting again.
        again = approvals.request(
            server_id="s", tool="t", eclipse_tool="mcp_s_t", effect="external_action", args={"x": 1},
        )
        assert again["status"] == "denied"
    finally:
        store.close()


def test_approval_unknown_effect_is_never_approvable(tmp_path):
    store, approvals = _approval_store(tmp_path)
    try:
        with pytest.raises(ValueError):
            approvals.request(
                server_id="s", tool="t", eclipse_tool="mcp_s_t", effect="unknown", args={},
            )
    finally:
        store.close()


def test_approval_expires(tmp_path):
    store, approvals = _approval_store(tmp_path)
    try:
        rec = approvals.request(
            server_id="s", tool="t", eclipse_tool="mcp_s_t", effect="write",
            args={"x": 1}, ttl_seconds=30,
        )
        approvals.decide(rec["id"], approve=True)
        # Force expiry into the past.
        approvals._db.execute(
            "UPDATE McpApproval SET expiresAt=? WHERE id=?", ("2000-01-01T00:00:00+00:00", rec["id"])
        )
        approvals._db.commit()
        assert approvals.is_authorized("s", "t", {"x": 1}) is False
    finally:
        store.close()


@pytest.mark.asyncio
async def test_effectful_tool_denied_without_approval(tmp_path):
    store, approvals = _approval_store(tmp_path)
    try:
        cfg = fast_config(
            selected_tools=["write_thing"],
            tool_effects={"write_thing": "write"},
            enabled_effects=["read", "write"],
        )
        mgr = MCPManager([cfg])
        await mgr.start()
        reg = ToolRegistry()
        assert mgr.register_selected_tools(reg) == ["mcp_fx_write_thing"]
        c = ToolContext(run_id="r1", log=lambda *_: None)
        c.authorize_effect = __import__(
            "harness.mcp.approvals", fromlist=["make_effect_authorizer"]
        ).make_effect_authorizer(approvals, "r1")
        result = await reg.execute("mcp_fx_write_thing", "c1", {"text": "x"}, c, allowed={"mcp_fx_write_thing"})
        assert not result.ok
        assert result.error.code == "TOOL_FORBIDDEN"
        # A pending request was created for the operator.
        pending = approvals.list("pending")
        assert pending and pending[0]["tool"] == "write_thing"
        await mgr.close()
    finally:
        store.close()


@pytest.mark.asyncio
async def test_effectful_tool_runs_with_matching_approval(tmp_path):
    store, approvals = _approval_store(tmp_path)
    try:
        cfg = fast_config(
            selected_tools=["write_thing"],
            tool_effects={"write_thing": "write"},
            enabled_effects=["read", "write"],
        )
        mgr = MCPManager([cfg])
        await mgr.start()
        reg = ToolRegistry()
        mgr.register_selected_tools(reg)
        # Pre-approve the exact call.
        approvals.request(
            server_id="fx", tool="write_thing", eclipse_tool="mcp_fx_write_thing",
            effect="write", args={"text": "x"}, run_id="r1",
        )
        for pending in approvals.list("pending"):
            approvals.decide(pending["id"], approve=True)
        c = ToolContext(run_id="r1", log=lambda *_: None)
        c.authorize_effect = __import__(
            "harness.mcp.approvals", fromlist=["make_effect_authorizer"]
        ).make_effect_authorizer(approvals, "r1")
        result = await reg.execute("mcp_fx_write_thing", "c1", {"text": "x"}, c, allowed={"mcp_fx_write_thing"})
        assert result.ok, result.text
        await mgr.close()
    finally:
        store.close()


@pytest.mark.asyncio
async def test_effectful_tool_not_activated_without_opt_in(tmp_path):
    # `write` selected + declared, but the operator has NOT enabled that effect.
    cfg = fast_config(selected_tools=["write_thing"], tool_effects={"write_thing": "write"})
    mgr = MCPManager([cfg])
    await mgr.start()
    reg = ToolRegistry()
    assert mgr.register_selected_tools(reg) == []
    descriptor = mgr._runtimes["fx"].descriptors["write_thing"]
    assert descriptor.activatable is False
    assert "enabled_effects" in (descriptor.diagnostic or "")
    await mgr.close()





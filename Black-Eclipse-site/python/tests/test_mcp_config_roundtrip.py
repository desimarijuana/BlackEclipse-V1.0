"""Phase 6.1 Milestone 1 — save round-trip integrity and no silent authority widening.

The contract under test:

    Absent means preserve; explicitly present means replace — including
    ``null``, ``false``, ``{}`` and ``[]`` for clearing.

A save must never silently change what a server is allowed to do. A caller that
omits a field (an older UI, an API client, a script) must not reset it, while the
UI can still clear a field because it always sends every field it owns.

Behavior contracts only: no test reads source text.
"""

from __future__ import annotations

import json
import sys

import pytest

from harness.mcp.config import (
    MCPServerConfig,
    load_mcp_configs,
    upsert_mcp_config,
    write_mcp_configs,
)

FIXTURES_DIR = __import__("os").path.join(__import__("os").path.dirname(__file__), "mcp_fixtures")
FAST = __import__("os").path.join(FIXTURES_DIR, "fastmcp_fixture.py")


def _full_config(server_id: str = "x") -> MCPServerConfig:
    """A fully-populated config exercising every Phase-6 field a user can set."""
    return MCPServerConfig(
        id=server_id,
        command="python",
        name="Full Server",
        transport="stdio",
        enabled=True,
        trust="untrusted",
        lazy=True,
        keepalive_interval=60,
        idle_timeout_seconds=120,
        max_lifetime_seconds=600,
        tools={"resources": True, "prompts": True},
        data_source_tools={"get_quote": "current_quote"},
        tool_effects={"get_quote": "read"},
        enabled_effects=["read", "write"],
        confirmed_catalog_digest="abc123",
        selected_tools={"include": ["get_*"], "exclude": ["get_secret"]},
        max_tools=25,
        startup_timeout_ms=5000,
        output_limit_bytes=50000,
        ssl_verify=True,
        protocol_version="2025-11-25",
        description="a full server",
    )


# The Phase-5E field set the current UI actually sends (the buggy payload).
_UI_PAYLOAD_FIELDS = {
    "id", "transport", "command", "args", "url", "auth", "env", "envAllowlist",
    "secretRefs", "cwd", "enabled", "selectedTools", "enabledEffects", "description",
}


def _ui_payload(server_id: str = "x", **overrides) -> MCPServerConfig:
    """Reconstruct the exact partial payload the current UI produces.

    Only the Phase-5E fields are supplied; every Phase-6 field is absent, which
    the old replace-all upsert interpreted as "reset to default".
    """
    base = {
        "id": server_id,
        "transport": "stdio",
        "command": "python",
        "args": [],
        "env": {},
        "envAllowlist": [],
        "secretRefs": {},
        "enabled": False,
        "selectedTools": ["get_quote"],
        "enabledEffects": ["read"],
        "description": "a full server",
    }
    base.update(overrides)
    return MCPServerConfig(**base)


# ── preserve on absent ──────────────────────────────────────────────────────


def test_partial_upsert_preserves_every_omitted_field(tmp_path):
    path = str(tmp_path / "mcp-servers.json")
    write_mcp_configs([_full_config()], path)
    upsert_mcp_config(_ui_payload(), path)
    server = load_mcp_configs(path)[0][0]
    full = _full_config()
    # `selectedTools`/`enabledEffects`/`description` are part of the Phase-5E UI
    # payload, so they are explicitly present and legitimately replaced. Every
    # field the payload does NOT mention must survive unchanged.
    for field in (
        "trust", "lazy", "keepalive_interval", "idle_timeout_seconds",
        "max_lifetime_seconds", "tools", "data_source_tools", "tool_effects",
        "confirmed_catalog_digest", "max_tools", "startup_timeout_ms",
        "output_limit_bytes", "ssl_verify", "protocol_version",
    ):
        assert getattr(server, field) == getattr(full, field), (
            f"omitted field {field!r} was reset: "
            f"{getattr(full, field)!r} -> {getattr(server, field)!r}"
        )


def test_absent_field_is_not_sent_by_a_subset_caller(tmp_path):
    """A caller that never mentions a field must not clear it, even if defaults
    would be falsy (`False`, `{}`, `[]`, `None`)."""
    path = str(tmp_path / "mcp-servers.json")
    write_mcp_configs([_full_config()], path)
    # A minimal upsert that supplies only id + command + enabled (like a
    # card-level enable toggle).
    upsert_mcp_config(MCPServerConfig(id="x", command="python", enabled=True), path)
    server = load_mcp_configs(path)[0][0]
    assert server.enabled is True
    assert server.trust == "untrusted"
    assert server.lazy is True
    assert server.tools == {"resources": True, "prompts": True}
    assert server.data_source_tools == {"get_quote": "current_quote"}
    assert server.tool_effects == {"get_quote": "read"}
    assert server.confirmed_catalog_digest == "abc123"


# ── clear on explicit presence ──────────────────────────────────────────────


def test_explicit_null_clears_an_optional_field(tmp_path):
    path = str(tmp_path / "mcp-servers.json")
    write_mcp_configs([_full_config()], path)
    upsert_mcp_config(
        MCPServerConfig(id="x", command="python", confirmed_catalog_digest=None),
        path,
    )
    server = load_mcp_configs(path)[0][0]
    assert server.confirmed_catalog_digest is None


def test_explicit_empty_collections_clear_fields(tmp_path):
    path = str(tmp_path / "mcp-servers.json")
    write_mcp_configs([_full_config()], path)
    upsert_mcp_config(
        MCPServerConfig(
            id="x", command="python",
            tool_effects={}, data_source_tools={}, tools={},
            selected_tools=[], enabled_effects=["read"],
        ),
        path,
    )
    server = load_mcp_configs(path)[0][0]
    assert server.tool_effects == {}
    assert server.data_source_tools == {}
    assert server.tools == {}
    assert server.selected_tools == []
    assert server.enabled_effects == ["read"]


def test_explicit_false_clears_a_boolean(tmp_path):
    path = str(tmp_path / "mcp-servers.json")
    write_mcp_configs([_full_config()], path)
    upsert_mcp_config(MCPServerConfig(id="x", command="python", lazy=False), path)
    server = load_mcp_configs(path)[0][0]
    assert server.lazy is False


# ── authority widening invariants ──────────────────────────────────────────


def test_omission_cannot_widen_trust_or_effects(tmp_path):
    path = str(tmp_path / "mcp-servers.json")
    write_mcp_configs([_full_config()], path)
    # The old UI payload omitted `trust`; that must not move untrusted -> full.
    upsert_mcp_config(_ui_payload(), path)
    server = load_mcp_configs(path)[0][0]
    assert server.is_untrusted() is True


def test_omission_cannot_drop_data_source_or_confirmation(tmp_path):
    path = str(tmp_path / "mcp-servers.json")
    write_mcp_configs([_full_config()], path)
    upsert_mcp_config(_ui_payload(), path)
    server = load_mcp_configs(path)[0][0]
    assert server.data_source_tools == {"get_quote": "current_quote"}
    assert server.confirmed_catalog_digest == "abc123"


def test_explicit_authority_change_is_honored(tmp_path):
    """If a caller explicitly sends a trust tier or effect, honour it — that is
    a deliberate operator action, not an accident of omission."""
    path = str(tmp_path / "mcp-servers.json")
    write_mcp_configs([_full_config()], path)
    upsert_mcp_config(
        MCPServerConfig(id="x", command="python", trust="full", enabled_effects=["read", "write"]),
        path,
    )
    server = load_mcp_configs(path)[0][0]
    assert server.trust == "full"
    assert server.enabled_effects == ["read", "write"]


# ── idempotent re-save ─────────────────────────────────────────────────────


def test_second_partial_save_changes_nothing_on_disk(tmp_path):
    path = str(tmp_path / "mcp-servers.json")
    write_mcp_configs([_full_config()], path)
    upsert_mcp_config(_ui_payload(), path)
    first = open(path, "rb").read()
    upsert_mcp_config(_ui_payload(), path)
    second = open(path, "rb").read()
    assert first == second


def test_full_round_trip_is_a_byte_stable_no_op(tmp_path):
    path = str(tmp_path / "mcp-servers.json")
    cfg = _full_config()
    write_mcp_configs([cfg], path)
    before = open(path, "rb").read()
    upsert_mcp_config(cfg, path)
    assert open(path, "rb").read() == before


# ── install / confirm preserve prior state ─────────────────────────────────


def test_install_reinstall_does_not_reset_user_changes(tmp_path, monkeypatch):
    path = str(tmp_path / "mcp-servers.json")
    monkeypatch.setenv("HARNESS_MCP_CONFIG", path)
    from harness.service import AgenticService

    svc = AgenticService()
    first = svc.install_mcp_integration("filesystem")
    assert first["success"] is True
    assert first["config"]["enabled"] is False

    # The operator then changes the installed entry through a partial upsert.
    upsert_mcp_config(
        MCPServerConfig(
            id="filesystem", command="npx",
            trust="untrusted", enabled=True, selected_tools=["read_file"],
            tool_effects={"read_file": "read"},
        ),
        path,
    )
    # Re-installing must not reset what the user changed.
    svc.install_mcp_integration("filesystem")
    server = next(s for s in load_mcp_configs(path)[0] if s.id == "filesystem")
    assert server.trust == "untrusted"
    assert server.enabled is True
    assert server.selected_tools == ["read_file"]
    assert server.tool_effects == {"read_file": "read"}


@pytest.mark.asyncio
async def test_confirm_preserves_everything_else(tmp_path, monkeypatch):
    path = str(tmp_path / "mcp-servers.json")
    monkeypatch.setenv("HARNESS_MCP_CONFIG", path)
    # Persist a full config with a live-ish digest set below.
    write_mcp_configs([_full_config("fx").model_copy(update={"command": sys.executable, "args": [FAST]})], path)
    from harness.service import AgenticService

    svc = AgenticService()
    await svc.start_mcp()
    try:
        digest = svc.mcp.catalog_digest_for("fx")
        assert digest
        result = await svc.confirm_mcp_catalog("fx")
        assert result["success"] is True
    finally:
        await svc.stop_mcp()
    server = load_mcp_configs(path)[0][0]
    assert server.confirmed_catalog_digest == digest
    # Everything else the user set must survive the confirm write path.
    assert server.trust == "untrusted"
    assert server.lazy is True
    assert server.tools == {"resources": True, "prompts": True}
    assert server.data_source_tools == {"get_quote": "current_quote"}
    assert server.tool_effects == {"get_quote": "read"}
    assert server.max_tools == 25


# ── lossless wire shape ────────────────────────────────────────────────────


# Keys public_dict emits that are NOT a persisted model field (computed view
# helpers). Their content is derived from persisted fields, so they are not fed
# back into the model.
_VIEW_ONLY_KEYS = {
    "env", "envKeys", "secretRefNames", "secretCount", "limits", "untrusted",
    "clientCertConfigured",
}

# Write-only / never-echoed fields: the view deliberately omits the value, so a
# round trip cannot and must not restore it from the view alone.
_WRITE_ONLY_FIELDS = {"client_cert", "client_key", "env"}


def _config_from_public(public: dict) -> MCPServerConfig:
    """Reconstruct a model from a public_dict view, exactly as the TS front door
    would: carry every persisted field the view echoes, rebuild env from key
    names, and omit nothing a caller can set."""
    payload = {k: v for k, v in public.items() if k not in _VIEW_ONLY_KEYS}
    if "envKeys" in public:
        payload["env"] = {k: k for k in public["envKeys"]}
    return MCPServerConfig(**payload)


def test_public_dict_round_trip_is_identity_for_surviving_keys():
    original = _full_config()
    view = original.public_dict()
    rebuilt = _config_from_public(view)
    again = rebuilt.public_dict()
    for key, value in view.items():
        if key in ("env", "envKeys"):
            # Env values are never echoed; only the key set must survive.
            continue
        assert again[key] == value, f"wire key {key!r} did not survive a round trip"
    # Write-only fields are explicitly lost from the view, not silently changed.
    assert "client_cert" not in view and "client_key" not in view


def test_every_public_dict_key_is_accounted_for_as_field_or_viewonly():
    """A new runtime field must appear on the wire — this catches a forgotten
    type addition without reading TS source."""
    view = _full_config().public_dict()
    model_fields = set(MCPServerConfig.model_fields.keys())
    camel = {MCPServerConfig.model_fields[f].alias or f for f in model_fields}
    camel.add("clientCert")  # view collapses client_cert/client_key to a boolean
    unknown = set(view) - camel - _VIEW_ONLY_KEYS
    assert unknown == set(), f"public_dict emits keys the model cannot consume: {unknown}"

"""Phase 6 Milestone 6 — presets, one-click install, and supply-chain audit.

Behavior contracts: every preset points at a real endpoint (no mcp.example.com),
install writes a DISABLED nothing-selected config, and the audit report is
read-only and offline by default.
"""

from __future__ import annotations

from harness.mcp.audit import supply_chain_report
from harness.mcp.config import MCPServerConfig
from harness.mcp.presets import INTEGRATIONS, integration, integration_to_config
from harness.mcp.screening import refusals, screen_entry


def test_no_preset_uses_example_com():
    for spec in INTEGRATIONS:
        assert spec.url is None or "mcp.example.com" not in spec.url
        assert "example.com" not in (spec.notes or "")


def test_oauth_presets_have_real_https_urls():
    oauth = [s for s in INTEGRATIONS if s.oauth]
    assert oauth, "expected OAuth-capable hosted integrations"
    for spec in oauth:
        assert spec.transport in ("http", "sse")
        assert spec.url and spec.url.startswith("https://")


def test_verified_presets_carry_a_date_and_basis():
    for spec in INTEGRATIONS:
        if spec.verified:
            assert spec.verified_at, f"{spec.id} is verified without a date"
            assert spec.verified_against, f"{spec.id} is verified without a basis"


def test_install_builds_disabled_nothing_selected_config():
    spec = integration("filesystem")
    entry = integration_to_config(spec)
    assert entry["enabled"] is False
    assert entry["selected_tools"] == []
    # And the built config parses + passes screening.
    assert refusals(screen_entry(entry)) == []
    MCPServerConfig(**entry)


def test_install_oauth_preset_sets_oauth_auth_no_secret():
    spec = integration("twelve_data")
    entry = integration_to_config(spec)
    assert entry["auth"] == {"kind": "oauth"}
    assert "secret_refs" not in entry


def test_supply_chain_report_is_offline_and_flags_unpinned():
    report = supply_chain_report()
    assert report["readOnly"] is True and report["offline"] is True
    packages = {p["package"] for p in report["packages"]}
    assert packages, "expected preset packages"
    # `npx -y mcp-google-sheets` is unpinned.
    assert any(not p["pinned"] for p in report["packages"])
    assert report["unpinnedCount"] >= 1


def test_supply_chain_report_includes_configured_command():
    class _Rt:
        pass

    class _Mgr:
        _runtimes = {}

    m = _Mgr()
    rt = _Rt()
    rt.config = MCPServerConfig(id="s", command="npx", args=["-y", "some-server"])
    m._runtimes = {"s": rt}
    report = supply_chain_report(m)
    assert any(p["package"] == "some-server" and p["source"] == "configured" for p in report["packages"])

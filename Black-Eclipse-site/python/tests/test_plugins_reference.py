"""Reference plugins: validate, install and enable through the real SDK."""

from __future__ import annotations

import pytest

from harness.plugins.loader import read_manifest

from plugins_helpers import BUNDLED, env

REFERENCE = ["github", "slack", "jira", "binance", "sec", "postgres"]
EXPECTED_TOOL = {
    "github": "plug_github_get_repo",
    "slack": "plug_slack_list_channels",
    "jira": "plug_jira_search_issues",
    "binance": "plug_binance_ticker",
    "sec": "plug_sec_company_filings",
    "postgres": "plug_postgres_query",
}


@pytest.mark.parametrize("plugin_id", REFERENCE)
def test_reference_manifest_is_valid(plugin_id):
    manifest, _raw = read_manifest(BUNDLED / plugin_id)
    assert manifest.id == plugin_id


@pytest.mark.parametrize("plugin_id", REFERENCE)
async def test_reference_plugin_installs_and_enables(env, plugin_id):
    result = await env.manager.install(plugin_id, enable=True, operator=True)
    assert result["ok"] is True
    assert env.manager.is_active(plugin_id)
    assert env.registry.get(EXPECTED_TOOL[plugin_id]) is not None
    caps = [c for c in env.manager.capabilities() if c["plugin_id"] == plugin_id]
    assert caps, f"{plugin_id} registered no capabilities"


async def test_marketplace_lists_bundled_reference_plugins(env):
    available = {e["id"] for e in env.manager.available()}
    assert set(REFERENCE).issubset(available)
    results = env.manager.search("market")
    assert any(e["id"] == "binance" for e in results)

"""Phase 6.1 Milestone 5 — the shipped example config is valid.

Every entry in `mcp-servers.example.json` must construct a real `MCPServerConfig`
so the documented Phase-6 keys are copy-pasteable, not aspirational prose.
"""

from __future__ import annotations

import json
import os

from harness.mcp.config import MCPServerConfig
from harness.mcp.screening import refusals, screen_entry

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "mcp-servers.example.json")


def _load() -> dict:
    with open(EXAMPLE, encoding="utf-8") as handle:
        return json.load(handle)


def test_example_config_parses_and_every_entry_is_a_valid_config():
    raw = _load()
    assert isinstance(raw.get("servers"), list) and raw["servers"]
    for entry in raw["servers"]:
        # Each documented entry parses against the current model...
        MCPServerConfig(**entry)
        # ...and is not refused by static screening.
        assert refusals(screen_entry(entry)) == [], f"{entry.get('id')} would be refused"


def test_example_config_demonstrates_the_phase_6_keys():
    raw = _load()
    ids = {e["id"] for e in raw["servers"]}
    assert "twelve-data" in ids  # auth: {kind: oauth}
    assert "remote-example" in ids

    blob = json.dumps(raw["servers"])
    # Interpolation, include/exclude, trust, lazy, capability toggles, data
    # sources, a CA path and mTLS must all be present as real examples.
    assert "${workspaceFolder}" in blob
    assert '"include"' in blob and '"exclude"' in blob
    assert '"trust": "untrusted"' in blob
    assert '"lazy": true' in blob
    assert '"resources": true' in blob
    assert '"data_source_tools"' in blob
    assert '"ssl_verify": "/etc/' in blob
    assert '"client_cert"' in blob
    assert '"kind": "oauth"' in blob


def test_example_remote_server_uses_oauth_with_no_secret():
    raw = _load()
    entry = next(e for e in raw["servers"] if e["id"] == "twelve-data")
    assert entry["auth"] == {"kind": "oauth"}
    assert "secret_refs" not in entry

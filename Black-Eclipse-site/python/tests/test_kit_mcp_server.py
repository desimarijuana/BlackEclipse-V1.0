"""Phase 9 acceptance test for the `mcp_server` kit.

The generated server must pass the MCP config layer's own validation
(`mcp/config.py`) — not a kit-local stub.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from harness.code.kits import render_kit
from harness.code.kits.loader import KitLoadError

_INPUTS = {"source_name": "acme_tools", "description": "An example tool server."}


def _load_module(tmp_path: Path, rel: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, tmp_path / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_generated_server_config_validates_in_the_mcp_layer(tmp_path):
    rendered = render_kit("mcp_server", _INPUTS)
    target = tmp_path / "python/harness/mcp_servers/acme_tools.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered["python/harness/mcp_servers/acme_tools.py"], encoding="utf-8")
    module = _load_module(tmp_path, "python/harness/mcp_servers/acme_tools.py", "kit_acme_tools")

    from harness.mcp.config import MCPServerConfig

    cfg = MCPServerConfig(**module.config())
    assert cfg.enabled is False
    assert cfg.selected_tools == []
    assert cfg.command and isinstance(cfg.args, list)


def test_generated_server_declares_effect_classes(tmp_path):
    rendered = render_kit("mcp_server", _INPUTS)
    target = tmp_path / "python/harness/mcp_servers/acme_tools.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered["python/harness/mcp_servers/acme_tools.py"], encoding="utf-8")
    module = _load_module(tmp_path, "python/harness/mcp_servers/acme_tools.py", "kit_acme_tools2")
    assert module.list_tools()
    assert all(t["effect"] in ("read", "write", "external_action", "unknown") for t in module.list_tools())


def test_missing_description_is_refused():
    with pytest.raises(KitLoadError):
        render_kit("mcp_server", {"source_name": "acme"})

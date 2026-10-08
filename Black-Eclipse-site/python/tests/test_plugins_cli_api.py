"""CLI + HTTP route coverage for the Plugin Platform."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

_BASE = Path(tempfile.mkdtemp(prefix="be-plug-api-"))
os.environ.setdefault("AGENT_MEMORY_DB_PATH", str(_BASE / "agent-memory.db"))
os.environ.setdefault("BLACK_ECLIPSE_PLUGIN_ROOT", str(_BASE / "root"))


def _scaffold(root: Path) -> None:
    from harness import cli

    assert cli.main(["plugin", "create", str(root), "--id", "cli-demo", "--json"]) == 0


def test_cli_create_validate_install_list(capsys, tmp_path):
    from harness import cli

    root = tmp_path / "cli-demo"
    assert cli.main(["plugin", "create", str(root), "--id", "cli-demo", "--json"]) == 0
    assert (root / "plugin.yaml").exists() and (root / "plugin.py").exists()
    assert cli.main(["plugin", "validate", str(root), "--json"]) == 0
    out = capsys.readouterr().out
    assert "cli-demo" in out

    assert cli.main(["plugin", "install", str(root), "--enable", "--json"]) == 0
    capsys.readouterr()  # discard install output
    assert cli.main(["plugin", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    ids = {p["pluginId"] for p in listed["plugins"]}
    assert "cli-demo" in ids

    assert cli.main(["plugin", "inspect", "cli-demo", "--json"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["plugin"]["pluginId"] == "cli-demo"

    assert cli.main(["plugin", "doctor", "cli-demo", "--json"]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["pluginId"] == "cli-demo"

    assert cli.main(["plugin", "disable", "cli-demo", "--json"]) == 0
    capsys.readouterr()
    assert cli.main(["plugin", "enable", "cli-demo", "--json"]) == 0
    capsys.readouterr()
    assert cli.main(["plugin", "package", str(root), "--json"]) == 0
    capsys.readouterr()
    assert (root / ".eclipse-plugin.json").exists()
    assert cli.main(["plugin", "uninstall", "cli-demo", "--json"]) == 0


def test_cli_search_and_capabilities(capsys):
    from harness import cli

    assert cli.main(["plugin", "search", "hello", "--json"]) == 0
    results = json.loads(capsys.readouterr().out)["results"]
    assert any(r["id"] == "hello-world" for r in results)
    assert cli.main(["plugin", "capabilities", "--json"]) == 0
    capsys.readouterr()


def test_router_lists_and_gates(tmp_path):
    from harness import deps
    from harness.events import EventBus
    from harness.persistence import AgentMemoryStore
    from harness.plugins.manager import PluginManager
    from harness.routers import plugins as routes
    from harness.tools import ToolRegistry

    from plugins_helpers import BUNDLED

    store = AgentMemoryStore(str(tmp_path / "api.db"))
    manager = PluginManager(store, ToolRegistry(), EventBus(), None,
                            plugins_dir=tmp_path / "plugins", bundled_dir=BUNDLED)
    deps.service.plugins = manager

    listed = routes.list_plugins(_=True)
    assert listed["success"] is True
    available = routes.available_plugins(_=True)
    assert available["success"] is True
    caps = routes.plugin_capabilities(_=True)
    assert caps["success"] is True

    # Install (operator) then health + inspect through the routes.
    import asyncio

    asyncio.run(manager.install("hello-world", enable=True, operator=True))
    health = routes.plugin_health("hello-world", _=True)
    assert health["pluginId"] == "hello-world"
    inspected = routes.inspect_plugin("hello-world", _=True)
    assert inspected["success"] is True

    # A missing plugin is a 404, not a crash.
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        routes.inspect_plugin("does-not-exist", _=True)

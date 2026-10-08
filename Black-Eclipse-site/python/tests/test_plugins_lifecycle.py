"""Plugin lifecycle: install/enable/disable/update/rollback/uninstall/repair + restart."""

from __future__ import annotations

import pytest

from harness.events import EventBus
from harness.persistence import AgentMemoryStore
from harness.plugins.manager import PluginManager
from harness.plugins.model import PluginState
from harness.tools import ToolRegistry

from plugins_helpers import BUNDLED, env, package


async def test_install_enable_disable_uninstall(env):
    manager = env.manager
    result = await env.install_hello(enable=False)
    assert result["plugin"]["status"] == "INSTALLED"
    assert manager.store.get_plugin("hello-world").enabled is False

    enabled = await manager.enable("hello-world", operator=True)
    assert enabled["ok"] is True
    assert manager.store.get_plugin("hello-world").status.value == "RUNNING"
    assert env.registry.get("plug_hello_world_greet") is not None
    assert manager.is_active("hello-world")

    await manager.disable("hello-world")
    assert manager.store.get_plugin("hello-world").status.value == "DISABLED"
    assert env.registry.get("plug_hello_world_greet") is None
    assert not manager.is_active("hello-world")

    await manager.uninstall("hello-world")
    assert manager.store.get_plugin("hello-world") is None
    assert env.registry.get("plug_hello_world_greet") is None


async def test_reenable_is_idempotent(env):
    await env.install_hello()
    again = await env.manager.enable("hello-world", operator=True)
    assert again.get("alreadyEnabled") is True


async def test_state_survives_restart(tmp_path):
    db = str(tmp_path / "agent-memory.db")
    plugins_dir = tmp_path / "plugins"
    store1 = AgentMemoryStore(db)
    manager1 = PluginManager(store1, ToolRegistry(), EventBus(), None,
                             plugins_dir=plugins_dir, bundled_dir=BUNDLED)
    await manager1.install("hello-world", enable=True, operator=True)

    # A fresh manager over the SAME database restores the enabled set.
    store2 = AgentMemoryStore(db)
    registry2 = ToolRegistry()
    manager2 = PluginManager(store2, registry2, EventBus(), None,
                             plugins_dir=plugins_dir, bundled_dir=BUNDLED)
    report = await manager2.start_enabled()
    assert "hello-world" in report["started"]
    assert registry2.get("plug_hello_world_greet") is not None


async def test_update_and_rollback(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    registry = ToolRegistry()
    manager = PluginManager(store, registry, EventBus(), None,
                            plugins_dir=tmp_path / "plugins", bundled_dir=BUNDLED)

    await manager.install_package(**package("acme-tool", "1.0.0"), enable=True, operator=True)
    assert manager.store.get_plugin("acme-tool").version == "1.0.0"

    # A successful update moves to 1.1.0 and stays running.
    await manager.update("acme-tool", package("acme-tool", "1.1.0"))
    record = manager.store.get_plugin("acme-tool")
    assert record.version == "1.1.0"
    assert record.status.value == "RUNNING"
    assert registry.get("plug_acme_tool_ping") is not None

    # An update whose entrypoint cannot load rolls back automatically.
    broken = package("acme-tool", "1.2.0", entrypoint="missing_module:Impl")
    with pytest.raises(Exception):
        await manager.update("acme-tool", broken)
    assert manager.store.get_plugin("acme-tool").version == "1.1.0"

    # Explicit rollback returns to the recorded earlier version.
    await manager.rollback("acme-tool", operator=True)
    assert manager.store.get_plugin("acme-tool").version == "1.0.0"


async def test_repair_restores_a_failed_plugin(env):
    await env.install_hello(enable=False)
    manager = env.manager
    # Simulate a corrupt state then repair.
    manager.store.set_state("hello-world", PluginState.FAILED, enabled=False)
    result = await manager.repair("hello-world", operator=True)
    assert result["ok"] is True
    assert manager.store.get_plugin("hello-world").status.value == "INSTALLED"


async def test_dependency_blocks_enable(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    manager = PluginManager(store, ToolRegistry(), EventBus(), None,
                            plugins_dir=tmp_path / "plugins", bundled_dir=BUNDLED)
    pkg = package("needs-dep", "1.0.0")
    pkg["manifest"]["dependencies"] = [{"id": "absent-dep", "version": "^1.0.0"}]
    await manager.install_package(**pkg)
    with pytest.raises(Exception) as exc:
        await manager.enable("needs-dep", operator=True)
    assert "dependenc" in str(exc.value).lower()


async def test_discovery_lists_bundled(env):
    found = {row.get("id") for row in env.manager.discover()}
    assert "hello-world" in found

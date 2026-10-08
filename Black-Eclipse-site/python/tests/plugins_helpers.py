"""Shared fixtures for the Plugin Platform tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from harness.events import EventBus
from harness.persistence import AgentMemoryStore
from harness.plugins.manager import PluginManager
from harness.tools import ToolContext, ToolRegistry

BUNDLED = Path(__file__).resolve().parents[1] / "harness" / "plugins" / "bundled"


class Env:
    def __init__(self, manager: PluginManager, registry: ToolRegistry, bus: EventBus, base: Path) -> None:
        self.manager = manager
        self.registry = registry
        self.bus = bus
        self.base = base

    def ctx(self) -> ToolContext:
        return ToolContext(run_id="test-run", log=lambda *_: None)

    def install_hello(self, *, enable: bool = True):
        return self.manager.install("hello-world", enable=enable, operator=True)


@pytest.fixture()
def env(tmp_path: Path) -> Env:
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    registry = ToolRegistry()
    bus = EventBus()
    manager = PluginManager(
        store, registry, bus, None,
        plugins_dir=tmp_path / "plugins",
        bundled_dir=BUNDLED,
    )
    return Env(manager, registry, bus, tmp_path)


def package(plugin_id: str, version: str = "1.0.0", *, permissions: list[str] | None = None,
            tools: list[dict[str, Any]] | None = None, requires_network: bool = False,
            entrypoint: str = "plugin:Impl", extra_files: dict[str, str] | None = None,
            storage: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an in-memory plugin package (manifest + files) for tests."""
    tools = tools or [{"name": "ping", "description": "ping", "permission": "read"}]
    manifest: dict[str, Any] = {
        "id": plugin_id,
        "name": plugin_id,
        "version": version,
        "runtime": {"type": "python", "entrypoint": entrypoint},
        "permissions": permissions or [],
        "contributes": {"tools": tools},
        "storage": storage or {},
    }
    tool_methods = "\n".join(
        f'    @tool(name="{t["name"]}", description="{t.get("description", "")}", '
        f'schema={{}}, permission="{t.get("permission", "read")}")\n'
        f"    async def {t['name']}(self, args, ctx):\n"
        f"        return {{'tool': '{t['name']}'}}\n"
        for t in tools
    )
    plugin_py = (
        "from harness.plugins.sdk import Plugin, tool\n\n\n"
        "class Impl(Plugin):\n" + (tool_methods or "    async def ping(self, args, ctx):\n        return 'pong'\n") +
        "\n\nplugin = Impl\n"
    )
    files = {"plugin.py": plugin_py}
    if extra_files:
        files.update(extra_files)
    return {"manifest": manifest, "files": files}


__all__ = ["Env", "BUNDLED", "package", "env"]

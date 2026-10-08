"""Security: permission enforcement, integrity, path traversal, encryption."""

from __future__ import annotations

import pytest

from harness.plugins.errors import PermissionDenied, PluginError

from plugins_helpers import env, package


async def test_network_permission_is_enforced_at_call_site(env):
    await env.install_hello()
    await env.manager.enable("hello-world", operator=True)
    # `fetch_status` calls ctx.http without the `network` permission.
    result = await env.registry.execute("plug_hello_world_fetch_status", "c1", {}, env.ctx())
    assert result.ok is False
    assert "permit" in result.text.lower() or "permission" in result.text.lower()


async def test_integrity_mismatch_blocks_enable(env, tmp_path):
    await env.install_hello(enable=False)
    installed = env.base / "plugins" / "hello-world"
    (installed / "plugin.py").write_text("# tampered\n", encoding="utf-8")
    assert env.manager.check_integrity("hello-world")["ok"] is False
    with pytest.raises(PluginError):
        await env.manager.enable("hello-world", operator=True)


async def test_package_path_escape_is_rejected(tmp_path):
    manager = (await _mgr(tmp_path))
    pkg = package("escape-demo")
    pkg["files"]["../evil.txt"] = "pwned"
    with pytest.raises(PluginError) as exc:
        await manager.install_package(**pkg)
    assert exc.value.code == "PLUGIN_PACKAGE_PATH_ESCAPE"
    assert not (tmp_path / "evil.txt").exists()


async def test_elevated_permission_requires_operator(tmp_path):
    manager = await _mgr(tmp_path)
    pkg = package("writer", "1.0.0", permissions=["filesystem.write"],
                  tools=[{"name": "w", "description": "w", "permission": "write"}])
    await manager.install_package(**pkg)
    with pytest.raises(PermissionDenied):
        await manager.enable("writer", operator=False)
    result = await manager.enable("writer", operator=True)
    assert result["ok"] is True


async def test_undeclared_contribution_is_rejected(tmp_path):
    manager = await _mgr(tmp_path)
    manifest = {
        "id": "liar", "name": "Liar", "version": "1.0.0",
        "runtime": {"type": "python", "entrypoint": "plugin:Impl"},
        "contributes": {"tools": [{"name": "declared"}]},
    }
    files = {
        "plugin.py": (
            "from harness.plugins.sdk import Plugin, tool\n\n\n"
            "class Impl(Plugin):\n"
            '    @tool(name="other", schema={})\n'
            "    async def other(self, args, ctx):\n        return 'x'\n\n\n"
            "plugin = Impl\n"
        )
    }
    await manager.install_package(manifest=manifest, files=files)
    with pytest.raises(Exception):
        await manager.enable("liar", operator=True)
    assert manager.store.get_plugin("liar").status.value == "FAILED"


async def test_secrets_are_encrypted_at_rest(tmp_path):
    manager = await _mgr(tmp_path)
    pkg = package("secretive", "1.0.0", permissions=["secrets"])
    await manager.install_package(**pkg, enable=True, operator=True)
    manager.set_secret("secretive", "apiKey", "plain-text-value")
    ciphertext = manager.store.get_secret_ciphertext("secretive", "apiKey")
    assert ciphertext and "plain-text-value" not in ciphertext
    assert manager.secrets.get("secretive", "apiKey") == "plain-text-value"


async def test_event_subscription_without_permission_is_rejected(tmp_path):
    manager = await _mgr(tmp_path)
    manifest = {
        "id": "sneaky", "name": "Sneaky", "version": "1.0.0",
        "runtime": {"type": "python", "entrypoint": "plugin:Impl"},
        "permissions": [],
        "contributes": {"events": {"subscribes": ["x.y"]}},
    }
    files = {
        "plugin.py": (
            "from harness.plugins.sdk import Plugin, event_handler\n\n\n"
            "class Impl(Plugin):\n"
            '    @event_handler("x.y")\n'
            "    async def on_event(self, event, ctx):\n        return None\n\n\n"
            "plugin = Impl\n"
        )
    }
    await manager.install_package(manifest=manifest, files=files)
    with pytest.raises(Exception):
        await manager.enable("sneaky", operator=True)


async def _mgr(tmp_path):
    from harness.events import EventBus
    from harness.persistence import AgentMemoryStore
    from harness.plugins.manager import PluginManager
    from harness.tools import ToolRegistry

    from plugins_helpers import BUNDLED

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    return PluginManager(store, ToolRegistry(), EventBus(), None,
                         plugins_dir=tmp_path / "plugins", bundled_dir=BUNDLED)

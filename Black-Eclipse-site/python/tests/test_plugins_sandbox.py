"""Process sandbox: untrusted plugins run in a child process with ctx proxying."""

from __future__ import annotations

import asyncio

from harness.plugins.sandbox import SandboxedPlugin

from plugins_helpers import env, package

PLUGIN_PY = (
    "import os\n"
    "from harness.plugins.sdk import Plugin, tool\n\n\n"
    "class Impl(Plugin):\n"
    '    @tool(name="greet", schema={})\n'
    "    async def greet(self, args, ctx):\n"
    "        return ctx.config.get('greeting', 'Hey')\n\n"
    '    @tool(name="kv", schema={"type": "object", "properties": {"v": {"type": "string"}}})\n'
    "    async def kv(self, args, ctx):\n"
    "        ctx.storage.set('seen', args.get('v', 'x'))\n"
    "        return ctx.storage.get('seen')\n\n"
    '    @tool(name="boom", schema={})\n'
    "    async def boom(self, args, ctx):\n"
    "        raise RuntimeError('intentional')\n\n"
    '    @tool(name="kill", schema={})\n'
    "    async def kill(self, args, ctx):\n"
    "        os._exit(7)\n\n\n"
    "plugin = Impl\n"
)


def _sandbox_package():
    manifest = {
        "id": "sbx-demo", "name": "Sandbox Demo", "version": "1.0.0",
        "runtime": {"type": "python", "entrypoint": "plugin:Impl"},
        "permissions": [],
        "contributes": {"tools": [
            {"name": "greet", "description": "g", "permission": "read"},
            {"name": "kv", "description": "k", "permission": "read"},
            {"name": "boom", "description": "b", "permission": "read"},
            {"name": "kill", "description": "k", "permission": "read"},
        ]},
        "configuration": [{"key": "greeting", "type": "string", "default": "Yo"}],
    }
    return {"manifest": manifest, "files": {"plugin.py": PLUGIN_PY}}


async def test_untrusted_plugin_runs_in_sandbox(env):
    manager = env.manager
    await manager.install_package(**_sandbox_package(), trust="untrusted", enable=True, operator=True)
    loaded = manager._active["sbx-demo"]
    assert isinstance(loaded.instance, SandboxedPlugin)

    greet = await env.registry.execute("plug_sbx_demo_greet", "c1", {}, env.ctx())
    assert greet.ok and greet.text == "Yo"

    kv = await env.registry.execute("plug_sbx_demo_kv", "c2", {"v": "stored"}, env.ctx())
    assert kv.ok and kv.text == "stored"
    # The write crossed the boundary into the host store.
    assert manager.store.kv_get("sbx-demo", "default", "seen") == "stored"


async def test_sandbox_tool_error_is_data_not_crash(env):
    manager = env.manager
    await manager.install_package(**_sandbox_package(), trust="untrusted", enable=True, operator=True)
    result = await env.registry.execute("plug_sbx_demo_boom", "c3", {}, env.ctx())
    assert result.ok is False
    assert manager.is_active("sbx-demo")  # a tool error does not kill the plugin


async def test_sandbox_crash_does_not_crash_core(env):
    manager = env.manager
    await manager.install_package(**_sandbox_package(), trust="untrusted", enable=True, operator=True)
    result = await env.registry.execute("plug_sbx_demo_kill", "c4", {}, env.ctx())
    assert result.ok is False
    # Eclipse Core is alive; a later call reports the sandbox is down (not a crash).
    follow = await env.registry.execute("plug_sbx_demo_greet", "c5", {}, env.ctx())
    assert follow.ok is False
    # Disable must not raise even though the child is gone.
    await manager.disable("sbx-demo")


async def test_trusted_plugin_is_not_sandboxed(env):
    manager = env.manager
    await manager.install_package(**package("plain", "1.0.0"), enable=True, operator=True)
    assert not isinstance(manager._active["plain"].instance, SandboxedPlugin)

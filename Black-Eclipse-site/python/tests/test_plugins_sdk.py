"""The hello-world reference plugin: every contribution surface via the SDK."""

from __future__ import annotations

import asyncio

import pytest

from plugins_helpers import env, package


async def _enabled(env):
    await env.install_hello()
    await env.manager.enable("hello-world", operator=True)
    return env.manager


async def test_tools_are_registered_with_provenance(env):
    manager = await _enabled(env)
    tool = env.registry.get("plug_hello_world_greet")
    assert tool is not None
    assert tool.effect_metadata["plugin_id"] == "hello-world"
    caps = manager.capabilities()
    assert any(c["capability"] == "greet" and c["plugin_id"] == "hello-world" for c in caps)


async def test_tool_invocation_and_config(env):
    manager = await _enabled(env)
    ctx = env.ctx()
    result = await env.registry.execute("plug_hello_world_greet", "c1", {"name": "Eclipse"}, ctx)
    assert result.ok
    assert result.text == "Hello, Eclipse."

    manager.set_config("hello-world", {"greeting": "Hi", "excited": True})
    result2 = await env.registry.execute("plug_hello_world_greet", "c2", {"name": "Eclipse"}, ctx)
    assert result2.text == "Hi, Eclipse!!!"


async def test_storage_is_scoped(env):
    manager = await _enabled(env)
    await env.registry.execute("plug_hello_world_greet", "c1", {"name": "Ada"}, env.ctx())
    assert manager.store.kv_get("hello-world", "default", "last_greeted") == "Ada"
    # A different plugin's namespace is empty.
    assert manager.store.kv_get("other-plugin", "default", "last_greeted") is None


async def test_command_runs(env):
    manager = await _enabled(env)
    out = await manager.run_command("hello-world", "status", {})
    assert out["ok"] is True
    assert out["result"]["plugin"] == "hello-world"


async def test_hook_receives_tool_call(env):
    manager = await _enabled(env)
    outcome = await manager.run_hook("before_tool_call", {"tool": "greet", "arguments": {}})
    assert outcome.proceed is True
    assert outcome.ran == 1
    assert manager.store.kv_get("hello-world", "default", "last_tool") == "greet"


async def test_event_subscription_round_trip(env):
    manager = await _enabled(env)
    seen: list[dict] = []
    env.bus.subscribe(lambda event: seen.append(event))
    env.bus.publish({"type": "hello.ping", "data": {"n": 1}, "runId": None})
    for _ in range(20):
        await asyncio.sleep(0.01)
        if any(e.get("type") == "hello.pong" for e in seen):
            break
    assert any(e.get("type") == "hello.pong" for e in seen)


async def test_secrets_roundtrip_and_masking(env):
    manager = await _enabled(env)
    manager.set_secret("hello-world", "apiKey", "s3cr3t-value")
    assert manager.secrets.get("hello-world", "apiKey") == "s3cr3t-value"
    assert "apiKey" in manager.secret_names("hello-world")
    view = manager.config_view("hello-world")
    api_field = next(f for f in view["fields"] if f["key"] == "apiKey")
    assert api_field["set"] is True
    assert api_field["value"] is None  # secrets are never returned


async def test_invoke_capability_by_bare_name(env):
    manager = await _enabled(env)
    result = await manager.invoke_capability("echo", {"value": "hi"}, env.ctx())
    assert result.ok


async def test_ui_panel_renders_a_safe_view_spec(env):
    manager = await _enabled(env)
    panels = manager.ui_panels("hello-world")
    assert panels and panels[0]["id"] == "hello-panel"
    rendered = await manager.render_ui("hello-world", "hello-panel")
    assert rendered["view"]["type"] == "keyvalue"
    assert any(item["label"] == "Plugin" for item in rendered["view"]["items"])
    with pytest.raises(Exception):
        await manager.render_ui("hello-world", "does-not-exist")


async def test_worker_ran_on_enable(env):
    manager = await _enabled(env)
    # The heartbeat worker (interval 0) runs once immediately.
    for _ in range(20):
        await asyncio.sleep(0.01)
        if manager.store.kv_get("hello-world", "default", "last_heartbeat") == "ok":
            break
    assert manager.store.kv_get("hello-world", "default", "last_heartbeat") == "ok"

"""Outbound webhook delivery (HMAC, DLQ) and the WebSocket client."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from harness.plugins.http import PluginHttp
from harness.plugins.permissions import GrantedPermissions

from plugins_helpers import env, package


def _capturing_transport(status: int = 200):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, json={"ok": status < 300})

    return httpx.MockTransport(handler), captured


def _webhook_package(direction: str = "outbound"):
    manifest = {
        "id": "hooker", "name": "Hooker", "version": "1.0.0",
        "runtime": {"type": "python", "entrypoint": "plugin:Impl"},
        "permissions": ["webhooks"],
        "contributes": {
            "tools": [{"name": "noop", "description": "n", "permission": "read"}],
            "webhooks": [{"id": "notify", "direction": direction}],
        },
    }
    files = {
        "plugin.py": (
            "from harness.plugins.sdk import Plugin, tool, webhook\n\n\n"
            "class Impl(Plugin):\n"
            '    @tool(name="noop", schema={})\n'
            "    async def noop(self, args, ctx):\n        return 'ok'\n\n"
            f'    @webhook("notify", direction="{direction}")\n'
            "    def notify(self):\n        return None\n\n\n"
            "plugin = Impl\n"
        )
    }
    return {"manifest": manifest, "files": files}


async def test_outbound_webhook_is_signed(env):
    manager = env.manager
    transport, captured = _capturing_transport(200)
    manager._oauth_transport = transport
    await manager.install_package(**_webhook_package("outbound"), enable=True, operator=True)
    manager.set_webhook_target("hooker", "notify", "https://hooks.example/x", signing_secret="s3cr3t")

    result = await manager.deliver_webhook("hooker", "notify", {"event": "ping", "n": 1})
    assert result["ok"] is True
    assert captured, "no delivery was made"
    request = captured[0]
    body = request.content.decode()
    expected = hmac.new(b"s3cr3t", body.encode(), hashlib.sha256).hexdigest()
    assert request.headers["x-signature-256"] == f"sha256={expected}"
    assert json.loads(body) == {"event": "ping", "n": 1}


async def test_outbound_webhook_dead_letters_on_failure(env):
    manager = env.manager
    transport, captured = _capturing_transport(500)
    manager._oauth_transport = transport
    await manager.install_package(**_webhook_package("outbound"), enable=True, operator=True)
    manager.set_webhook_target("hooker", "notify", "https://hooks.example/x")

    result = await manager.deliver_webhook("hooker", "notify", {"a": 1})
    assert result["ok"] is False
    assert result["deadLetter"] is True
    assert len(captured) == 3  # retried
    deliveries = manager.list_webhook_deliveries("hooker")
    assert any(d["status"] == "dead_letter" for d in deliveries)


async def test_inbound_webhook_signature_verified(env):
    manager = env.manager
    await manager.install_package(**_webhook_package("inbound"), enable=True, operator=True)
    manager.set_secret("hooker", "webhook:notify", "topsecret")
    payload = {"hello": "world"}
    body = json.dumps(payload)
    good = hmac.new(b"topsecret", body.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(Exception):
        await manager.handle_webhook("hooker", "notify", payload, {"x-hub-signature-256": "sha256=bad"})
    result = await manager.handle_webhook("hooker", "notify", payload, {"x-hub-signature-256": f"sha256={good}"})
    assert result["ok"] is True


async def test_websocket_requires_permission():
    http = PluginHttp("ws", GrantedPermissions.from_declared("ws", []))
    with pytest.raises(Exception):
        await http.connect_ws("ws://127.0.0.1:1")


async def test_websocket_echo_round_trip():
    websockets = pytest.importorskip("websockets")

    async def echo(ws):
        async for message in ws:
            await ws.send(message)

    async with websockets.serve(echo, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        http = PluginHttp("ws", GrantedPermissions.from_declared("ws", ["network"]))
        ws = await http.connect_ws(f"ws://127.0.0.1:{port}")
        async with ws:
            await ws.send("hello-ws")
            assert await ws.recv() == "hello-ws"

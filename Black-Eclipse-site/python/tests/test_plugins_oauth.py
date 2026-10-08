"""OAuth2 flows for plugins: client_credentials, authorization_code+PKCE, device_code, refresh, revoke."""

from __future__ import annotations

import urllib.parse

import httpx
import pytest

from harness.plugins.manifest import AuthenticationSpec
from harness.plugins.oauth import K_ACCESS, AuthRequired, OAuthClient, OAuthError

from plugins_helpers import env, package


class _DictSecrets:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, plugin_id, name):
        return self.data.get(name)

    def set(self, plugin_id, name, value):
        self.data[name] = value

    def has(self, plugin_id, name):
        return name in self.data

    def names(self, plugin_id):
        return sorted(self.data)

    def delete(self, plugin_id, name):
        self.data.pop(name, None)


def _transport(responses):
    """A MockTransport that returns queued (status, json) responses in order."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if not queue:
            return httpx.Response(500, json={"error": "no_queued_response"})
        status, body = queue.pop(0)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _spec(**over) -> AuthenticationSpec:
    data = {"type": "oauth2", "token_url": "https://auth.example/token",
            "grant": "client_credentials"}
    data.update(over)
    return AuthenticationSpec(**data)


async def test_client_credentials():
    secrets = _DictSecrets()
    secrets.set("p", "clientId", "cid")
    secrets.set("p", "clientSecret", "csecret")
    spec = _spec(grant="client_credentials")
    client = OAuthClient(secrets, "p", spec, transport=_transport([
        (200, {"access_token": "tok-1", "token_type": "Bearer", "expires_in": 3600}),
    ]))
    result = await client.start()
    assert result["authorized"] is True
    assert await client.token() == "tok-1"
    assert client.status()["authorized"] is True


async def test_authorization_code_pkce():
    secrets = _DictSecrets()
    spec = _spec(grant="authorization_code", authorization_url="https://auth.example/authorize",
                 redirect_uri="http://127.0.0.1:3000/callback")
    client = OAuthClient(secrets, "p", spec, transport=_transport([
        (200, {"access_token": "tok-2", "refresh_token": "ref-2", "expires_in": 3600}),
    ]))
    start = await client.start()
    assert "code_challenge=" in start["authorizationUrl"]
    assert "code_challenge_method=S256" in start["authorizationUrl"]
    assert start["state"]
    done = await client.complete("the-code", start["state"])
    assert done["authorized"] is True
    assert secrets.get("p", K_ACCESS) == "tok-2"
    # State is single-use.
    with pytest.raises(OAuthError):
        await client.complete("the-code", "wrong-state")


async def test_device_code_flow():
    secrets = _DictSecrets()
    spec = _spec(grant="device_code", device_authorization_url="https://auth.example/device")
    client = OAuthClient(secrets, "p", spec, transport=_transport([
        (200, {"device_code": "dev-1", "user_code": "WXYZ", "verification_uri": "https://auth.example/activate",
               "interval": 1, "expires_in": 600}),
        (400, {"error": "authorization_pending"}),
        (200, {"access_token": "tok-3", "token_type": "Bearer", "expires_in": 3600}),
    ]))
    start = await client.start()
    assert start["userCode"] == "WXYZ"
    pending = await client.poll_device()
    assert pending["pending"] is True
    done = await client.poll_device()
    assert done["authorized"] is True
    assert await client.token() == "tok-3"


async def test_refresh_when_expired():
    secrets = _DictSecrets()
    spec = _spec(grant="client_credentials")
    client = OAuthClient(secrets, "p", spec, transport=_transport([
        (200, {"access_token": "short", "refresh_token": "r", "expires_in": 0}),
        (200, {"access_token": "fresh", "expires_in": 3600}),
    ]))
    await client.start()
    # expires_in=0 ⇒ immediately expired; token() refreshes.
    assert await client.token() == "fresh"


async def test_token_requires_authorization():
    secrets = _DictSecrets()
    client = OAuthClient(secrets, "p", _spec(), transport=_transport([]))
    with pytest.raises(AuthRequired):
        await client.token()


async def test_revoke_clears_tokens():
    secrets = _DictSecrets()
    client = OAuthClient(secrets, "p", _spec(), transport=_transport([
        (200, {"access_token": "tok", "refresh_token": "r", "expires_in": 3600}),
    ]))
    await client.start()
    assert await client.token() == "tok"
    await client.revoke()
    assert secrets.get("p", K_ACCESS) is None
    assert client.status()["authorized"] is False


# ── manager integration ──────────────────────────────────────────────────────


async def test_manager_oauth_end_to_end(env):
    manager = env.manager
    manager._oauth_transport = _transport([
        (200, {"access_token": "mgr-tok", "refresh_token": "mgr-ref", "expires_in": 3600}),
    ])
    manifest = {
        "id": "oauth-demo", "name": "OAuth Demo", "version": "1.0.0",
        "runtime": {"type": "python", "entrypoint": "plugin:Impl"},
        "permissions": ["secrets"],
        "authentication": {"type": "oauth2", "grant": "client_credentials",
                           "token_url": "https://auth.example/token"},
        "contributes": {"tools": [{"name": "whoami", "description": "token", "permission": "read"}]},
    }
    files = {
        "plugin.py": (
            "from harness.plugins.sdk import Plugin, tool\n\n\n"
            "class Impl(Plugin):\n"
            '    @tool(name="whoami", schema={})\n'
            "    async def whoami(self, args, ctx):\n"
            "        return await ctx.auth.token()\n\n\n"
            "plugin = Impl\n"
        )
    }
    await manager.install_package(manifest=manifest, files=files, enable=True, operator=True)
    manager.set_secret("oauth-demo", "clientId", "cid")
    manager.set_secret("oauth-demo", "clientSecret", "csec")

    assert manager.auth_status("oauth-demo")["authorized"] is False
    result = await manager.oauth_start("oauth-demo")
    assert result["authorized"] is True
    assert manager.auth_status("oauth-demo")["authorized"] is True

    tool = await env.registry.execute("plug_oauth_demo_whoami", "c1", {}, env.ctx())
    assert tool.ok
    assert "mgr-tok" in tool.text

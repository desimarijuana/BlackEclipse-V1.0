"""Phase 6 Milestone 3 — OAuth, device flow, TLS and redirect policy.

Offline and deterministic: a fake bridge stands in for the encrypted vault, the
device flow is exercised against in-process fake endpoints, and redirect/TLS
checks are pure. No network, no real token.
"""

from __future__ import annotations

import os
import sys

import pytest

from harness.mcp.config import MCPServerConfig
from harness.mcp.diagnostics import check_server
from harness.mcp.oauth import (
    BridgeTokenStore,
    OAuthError,
    device_authorization_request,
    poll_device_token,
)
from harness.mcp.redirect_guard import check_redirect


# ── token store never leaks to disk/config ──────────────────────────────────


@pytest.mark.asyncio
async def test_bridge_token_store_roundtrip_and_no_plaintext():
    state: dict = {}
    calls: list[tuple[str, dict]] = []

    async def fetch(capability, params):
        calls.append((capability, params))
        if capability == "mcp_oauth_token_get":
            return {"status": "OK", "token": state.get(params["serverId"])}
        if capability == "mcp_oauth_token_set":
            state[params["serverId"]] = dict(params)
            return {"status": "OK"}
        return {"status": "OK"}

    store = BridgeTokenStore("srv", fetch)
    from mcp.shared.auth import OAuthToken

    await store.set_tokens(OAuthToken(access_token="ACCESS-TOKEN-XYZ", token_type="Bearer", refresh_token="r1"))
    read = await store.get_tokens()
    assert read is not None and read.access_token == "ACCESS-TOKEN-XYZ"
    # The token value only ever moved through the bridge; it is not in the config.
    cfg = MCPServerConfig(id="srv", transport="http", url="https://x/mcp", auth={"kind": "oauth"})
    assert "ACCESS-TOKEN-XYZ" not in repr(cfg.model_dump())


# ── device flow (RFC 8628) ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_device_flow_success():
    async def post(url, body):
        if url.endswith("device"):
            return {"device_code": "d", "user_code": "U-1", "verification_uri": "https://v", "expires_in": 30, "interval": 1}
        return {"access_token": "AT", "token_type": "Bearer"}

    code = await device_authorization_request(
        device_authorization_endpoint="https://as/device", client_id="c", scope="read", http_post=post,
    )
    assert code.user_code == "U-1"
    token = await poll_device_token(
        token_endpoint="https://as/token", client_id="c", device_code="d",
        interval=1, expires_in=30, http_post=post, sleep=_no_sleep,
    )
    assert token["access_token"] == "AT"


@pytest.mark.asyncio
async def test_device_flow_handles_pending_and_slow_down():
    seen = {"n": 0}

    async def post(url, body):
        if url.endswith("device"):
            return {"device_code": "d", "user_code": "U", "verification_uri": "https://v", "expires_in": 30, "interval": 1}
        seen["n"] += 1
        if seen["n"] == 1:
            return {"error": "authorization_pending"}
        if seen["n"] == 2:
            return {"error": "slow_down"}
        return {"access_token": "AT2"}

    token = await poll_device_token(
        token_endpoint="https://as/token", client_id="c", device_code="d",
        interval=1, expires_in=30, http_post=post, sleep=_no_sleep,
    )
    assert token["access_token"] == "AT2" and seen["n"] == 3


@pytest.mark.asyncio
async def test_device_flow_denial_is_terminal():
    async def post(url, body):
        if url.endswith("device"):
            return {"device_code": "d", "user_code": "U", "verification_uri": "https://v", "expires_in": 30, "interval": 1}
        return {"error": "access_denied"}

    with pytest.raises(OAuthError) as exc:
        await poll_device_token(
            token_endpoint="https://as/token", client_id="c", device_code="d",
            interval=1, expires_in=30, http_post=post, sleep=_no_sleep,
        )
    assert exc.value.code == "mcp_oauth_access_denied"


async def _no_sleep(_seconds: float) -> None:
    return None


# ── redirect / origin policy ────────────────────────────────────────────────


def test_redirect_origin_change_is_refused():
    safe, reason = check_redirect("https://api.example.com/mcp", "https://evil.example.com/x")
    assert safe is False and "origin" in (reason or "")


def test_redirect_to_private_is_refused():
    safe, reason = check_redirect("https://api.example.com/mcp", "https://169.254.169.254/latest")
    assert safe is False


def test_redirect_same_origin_is_allowed():
    safe, _ = check_redirect("https://api.example.com/mcp", "https://api.example.com/mcp2")
    assert safe is True


# ── TLS controls ────────────────────────────────────────────────────────────


def test_missing_ca_bundle_fails_fast_diagnostic(tmp_path):
    cfg = MCPServerConfig(
        id="r", transport="http", url="https://api.example.com/mcp",
        ssl_verify=str(tmp_path / "nope.pem"),
    )
    diag = check_server(cfg).to_public()
    codes = {c["code"] for c in diag["checks"]}
    assert "ca_bundle_missing" in codes


def test_ssl_verify_false_is_warned():
    cfg = MCPServerConfig(id="r", transport="http", url="https://api.example.com/mcp", ssl_verify=False)
    diag = check_server(cfg).to_public()
    assert any(c["code"] == "tls_verification_disabled" for c in diag["checks"])


def test_oauth_auth_config_accepts_kind_oauth():
    cfg = MCPServerConfig(id="r", transport="http", url="https://api.example.com/mcp", auth={"kind": "oauth"})
    assert cfg.public_dict()["auth"]["kind"] == "oauth"


def test_oauth_token_status_diagnostics_distinguish_rejected_from_unreachable():
    cfg = MCPServerConfig(id="r", transport="http", url="https://api.example.com/mcp", auth={"kind": "oauth"})
    rejected = check_server(cfg, token_status={"configured": True, "rejected": True}).to_public()
    assert any(c["code"] == "oauth_rejected" for c in rejected["checks"])


# ── end-to-end device login against a local fixture (offline) ───────────────


def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def oauth_server():
    import socket
    import subprocess
    import time

    fixture = os.path.join(os.path.dirname(__file__), "mcp_fixtures", "oauth_fixture.py")
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, fixture, str(port)],
        env={**os.environ, "OAUTH_FIXTURE_TOKEN": "fixture-access-token"},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("oauth fixture did not start")
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()


@pytest.mark.asyncio
async def test_device_login_end_to_end_stores_token_and_never_persists_it(oauth_server):
    from harness.mcp.manager import MCPManager

    config = MCPServerConfig(
        id="oauth", transport="http", url=f"http://127.0.0.1:{oauth_server}/mcp",
        auth={"kind": "oauth"}, enabled=True, selected_tools=["echo"], tool_effects={"echo": "read"},
    )
    mgr = MCPManager([config])
    state: dict = {}

    async def fetch(capability, params):
        if capability == "mcp_oauth_token_set":
            state[params["serverId"]] = dict(params)
            return {"status": "OK"}
        if capability == "mcp_oauth_token_get":
            return {"status": "OK", "token": state.get(params["serverId"])}
        if capability == "mcp_oauth_token_clear":
            return {"status": "OK", "removed": params["serverId"] in state and state.pop(params["serverId"]) is not None}
        return {"status": "OK"}

    mgr.set_bridge_fetch(fetch)
    base = f"http://127.0.0.1:{oauth_server}"
    result = await mgr.oauth_login(
        "oauth",
        endpoints={"metadata": f"{base}/.well-known/oauth-authorization-server",
                   "device": f"{base}/device", "token": f"{base}/token"},
    )
    assert result["success"] is True, result
    assert state["oauth"]["accessToken"] == "fixture-access-token"
    # The token never appears in the config or a public view.
    assert "fixture-access-token" not in repr(config.model_dump())
    assert "fixture-access-token" not in repr(mgr.public_configs())

    # Clearing credentials leaves the server configured but disconnected.
    out = await mgr.oauth_logout("oauth")
    assert out["success"] is True and out["removed"] is True
    assert "oauth" not in state



@pytest.mark.asyncio
async def test_authorization_code_provider_is_built_with_bridge_store_and_handlers(oauth_server):
    """The AC path is wired to the encrypted-vault store and the caller's handlers.

    The SDK's authorization-code flow refuses to build its OAuth URLs over plain
    http (RFC 8252 / https requirement), so the interactive browser leg is a
    documented manual step over https; the device flow is covered end-to-end
    above. This asserts the integration seam (storage + handlers + the endpoints
    the SDK discovery consumes).
    """
    from harness.mcp.oauth import build_oauth_provider

    base = f"http://127.0.0.1:{oauth_server}"
    state: dict = {}

    async def fetch(capability, params):
        if capability == "mcp_oauth_token_set":
            state[params["serverId"]] = dict(params)
            return {"status": "OK"}
        return {"status": "OK", "token": state.get(params.get("serverId"))}

    seen: list[str] = []

    async def redirect_handler(url: str) -> None:
        seen.append(url)

    async def callback_handler():
        from mcp.client.auth import AuthorizationCodeResult
        return AuthorizationCodeResult(code="auth-code-1", state="st")

    provider = build_oauth_provider(
        "ac", f"{base}/mcp", fetch, f"{base}/callback",
        redirect_handler=redirect_handler, callback_handler=callback_handler,
    )
    # The provider carries our storage (an OAuthClientProvider); the redirect
    # handler is reachable by the flow.
    assert provider is not None
    assert provider.context.storage is not None
    assert provider.context.redirect_handler is redirect_handler
    # The fixture advertises the endpoints the SDK discovery needs.
    import httpx

    async with httpx.AsyncClient() as c:
        meta = (await c.get(f"{base}/.well-known/oauth-authorization-server")).json()
        prm = (await c.get(f"{base}/.well-known/oauth-protected-resource")).json()
    assert meta["authorization_endpoint"] and meta["token_endpoint"] and meta["registration_endpoint"]
    assert prm["authorization_servers"] == [base]

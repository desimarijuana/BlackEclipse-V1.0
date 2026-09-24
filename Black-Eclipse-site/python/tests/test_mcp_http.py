"""Phase 5D — remote Streamable-HTTP transport, vault header auth, SSRF guard.

Offline and deterministic: a local Streamable-HTTP fixture server is launched as
a real subprocess on an ephemeral loopback port. No network, no external host.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import pytest

from harness.mcp.client import MCPConnection
from harness.mcp.config import MCPServerConfig
from harness.mcp.manager import MCPManager
from harness.mcp.ssrf import check_outbound_url
from harness.tools import ToolContext, ToolRegistry

FIXTURES = os.path.join(os.path.dirname(__file__), "mcp_fixtures")
HTTP_FIXTURE = os.path.join(FIXTURES, "http_fixture.py")
TOKEN = "fixture-token-xyz"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def http_server():
    port = _free_port()
    env = {**os.environ, "HTTP_FIXTURE_TOKEN": TOKEN}
    proc = subprocess.Popen(
        [sys.executable, HTTP_FIXTURE, str(port)], env=env,
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
            pytest.fail("http fixture did not start")
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()


def _http_config(port: int, **overrides) -> MCPServerConfig:
    data = dict(
        id="http",
        transport="http",
        url=f"http://127.0.0.1:{port}/mcp",
        enabled=True,
        selected_tools=["echo"],
        tool_effects={"echo": "read"},
        auth={"kind": "header", "name": "Authorization", "prefix": "Bearer ", "secretRef": "http_token"},
    )
    data.update(overrides)
    return MCPServerConfig(**data)


# ── transport selection / end-to-end ────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_transport_discovers_and_calls(http_server):
    async def resolver(name):
        return TOKEN if name == "http_token" else None

    conn = MCPConnection(_http_config(http_server), secret_resolver=resolver)
    try:
        await conn.start()
        assert conn.ready
        assert {t.name for t in conn.tools} >= {"echo"}
        out = await conn.call_tool("echo", {"text": "hi"})
        assert out.ok and "echo:hi" in out.text
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_http_header_auth_is_required_and_vault_backed(http_server):
    # A resolver that returns nothing → no Authorization header → 401 at the server.
    async def no_secret(name):
        return None

    conn = MCPConnection(_http_config(http_server), secret_resolver=no_secret)
    with pytest.raises(Exception):
        await conn.start()
    await conn.close()


@pytest.mark.asyncio
async def test_http_server_registers_only_selected_read_tool(http_server):
    async def resolver(name):
        return TOKEN if name == "http_token" else None

    mgr = MCPManager([_http_config(http_server)])
    mgr.set_secret_resolver(resolver)
    await mgr.start()
    reg = ToolRegistry()
    assert mgr.register_selected_tools(reg) == ["mcp_http_echo"]
    result = await reg.execute("mcp_http_echo", "c1", {"text": "x"}, ToolContext(run_id="r1", log=lambda *_: None), allowed={"mcp_http_echo"})
    assert result.ok and "echo:x" in result.text
    await mgr.close()


def test_http_auth_secret_never_in_public_view():
    cfg = _http_config(8123)
    public = cfg.public_dict()
    assert public["auth"]["secretRef"] == "http_token"
    assert "value" not in (public["auth"] or {})
    assert TOKEN not in repr(public)


# ── SSRF guard ──────────────────────────────────────────────────────────────


def test_ssrf_blocks_private_and_non_https_remotes():
    assert check_outbound_url("http://example.com/mcp")[0] is False       # http remote
    assert check_outbound_url("https://user:pass@example.com/mcp")[0] is False
    assert check_outbound_url("file:///etc/passwd")[0] is False
    assert check_outbound_url("http://10.0.0.5/mcp")[0] is False
    assert check_outbound_url("https://192.168.1.10/mcp")[0] is False
    assert check_outbound_url("https://169.254.169.254/latest/meta-data")[0] is False  # cloud metadata
    assert check_outbound_url("https://foo.internal/mcp")[0] is False


def test_ssrf_allows_loopback_http_for_local_testing():
    assert check_outbound_url("http://127.0.0.1:8765/mcp")[0] is True
    assert check_outbound_url("http://localhost:3000/mcp")[0] is True


@pytest.mark.asyncio
async def test_unsafe_remote_is_refused_before_connecting():
    # A private-IP https URL must be refused without any outbound attempt.
    cfg = _http_config(0, url="https://10.0.0.5/mcp")
    mgr = MCPManager([cfg])
    result = await mgr.test_server(cfg)
    assert result["state"] == "failed"
    assert "unsafe" in (result["diagnostic"] or "").lower()


# ── config validation ───────────────────────────────────────────────────────


def test_transport_requires_command_or_url():
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        MCPServerConfig(id="s", transport="stdio", command="")  # no command
    with pytest.raises(pydantic.ValidationError):
        MCPServerConfig(id="s", transport="http")  # no url
    with pytest.raises(pydantic.ValidationError):
        MCPServerConfig(id="s", transport="http", url="https://x/mcp", auth={"kind": "header"})  # no name/ref


def test_stdio_transport_default_unchanged():
    cfg = MCPServerConfig(id="s", command="python")
    assert cfg.transport == "stdio"
    assert cfg.public_dict()["transport"] == "stdio"

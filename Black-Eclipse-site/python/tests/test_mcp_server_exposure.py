"""Phase 6 Milestone 7 — Eclipse as an MCP server (read-only exposure).

Offline: an SDK client connects to the exposure ASGI app over a real loopback
port. Asserts the tool schemas reference no secret/env/vault key, pagination is
bounded, and an unauthenticated request is refused.
"""

from __future__ import annotations

import os
import socket
import threading
import time

import pytest
import uvicorn

from harness.mcp.server_exposure import (
    SERVED_PROTOCOL_VERSION,
    build_asgi_app,
    build_exposed_tools,
    build_mcp_server,
    call_exposed_tool,
    verify_client,
)

TOKEN = "eclipse-server-token-xyz"


class FakeService:
    def list_receipts(self, limit: int = 50):
        return [
            {"runId": f"run_{i}", "status": "completed", "createdAt": "2026-09-29T00:00:00Z"}
            for i in range(75)
        ]

    def get_receipt(self, run_id: str):
        if run_id == "run_1":
            return {"runId": "run_1", "status": "completed", "evidence": []}
        return None


# ── tool-schema hygiene ─────────────────────────────────────────────────────


def test_exposed_tool_schemas_reference_no_secrets():
    rows = build_exposed_tools()
    assert rows
    forbidden = ("secret", "token", "password", "apikey", "vault", "credential", "callback", "authorization", "bearer", "env")
    blob = repr(rows).lower()
    for tok in forbidden:
        assert tok not in blob, f"exposed schema references {tok!r}"


def test_status_tool_declares_read_only_and_protocol():
    result = call_exposed_tool("eclipse_status", {}, FakeService())
    assert result["isError"] is False
    assert SERVED_PROTOCOL_VERSION in result["content"][0]["text"]


def test_pagination_is_bounded():
    result = call_exposed_tool("eclipse_list_receipts", {"limit": 10_000, "offset": 0}, FakeService())
    import json

    payload = json.loads(result["content"][0]["text"])
    assert payload["limit"] <= 50
    assert len(payload["receipts"]) <= 50


def test_missing_receipt_is_a_structured_error_not_a_payload():
    result = call_exposed_tool("eclipse_get_receipt", {"runId": "nope"}, FakeService())
    assert result["isError"] is True
    assert result["rule"] == "receipt not found"


# ── auth ────────────────────────────────────────────────────────────────────


def test_verify_client_requires_the_dedicated_token(monkeypatch):
    monkeypatch.delenv("HARNESS_MCP_SERVER_TOKEN", raising=False)
    assert verify_client("Bearer anything") is False  # disabled, not open
    monkeypatch.setenv("HARNESS_MCP_SERVER_TOKEN", TOKEN)
    assert verify_client(None) is False
    assert verify_client("Bearer wrong") is False
    assert verify_client(f"Bearer {TOKEN}") is True


# ── end-to-end SDK client against a loopback server ─────────────────────────


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.mark.asyncio
async def test_sdk_client_lists_and_calls_a_read_tool(monkeypatch):
    monkeypatch.setenv("HARNESS_MCP_SERVER_TOKEN", TOKEN)
    port = _free_port()
    app = build_asgi_app(FakeService())
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        assert server.started, "exposure server did not start"

        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client, create_mcp_http_client

        url = f"http://127.0.0.1:{port}/mcp"
        http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {TOKEN}"})
        async with streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert {"eclipse_status", "eclipse_list_receipts"} <= names
                result = await session.call_tool("eclipse_status", {})
                assert result is not None
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_unauthenticated_client_is_refused(monkeypatch):
    monkeypatch.setenv("HARNESS_MCP_SERVER_TOKEN", TOKEN)
    port = _free_port()
    app = build_asgi_app(FakeService())

    # A bare HTTP request with no Authorization header must get 401 without the
    # MCP handshake ever starting.
    import httpx

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        resp = httpx.post(
            f"http://127.0.0.1:{port}/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert resp.status_code == 401
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_second_client_sse_transport_lists_tools(monkeypatch):
    """A second, independent client using the SSE transport also succeeds.

    This is the offline stand-in for the documented manual Hermes interop step:
    two distinct MCP clients (Streamable HTTP above, SSE here) against one server.
    """
    monkeypatch.setenv("HARNESS_MCP_SERVER_TOKEN", TOKEN)
    port = _free_port()
    # Serve the same read surface over SSE so a second client can drive it.
    from mcp.server.mcpserver import MCPServer

    server_obj = build_mcp_server(FakeService())
    sse_app = server_obj.sse_app()

    async def guarded(scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            if not verify_client(headers.get("authorization")):
                from starlette.responses import JSONResponse

                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await sse_app(scope, receive, send)

    config = uvicorn.Config(guarded, host="127.0.0.1", port=port, log_level="error")
    uvicorn_server = uvicorn.Server(config)
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if uvicorn_server.started:
                break
            time.sleep(0.1)
        assert uvicorn_server.started

        from mcp import ClientSession
        from mcp.client.sse import sse_client

        url = f"http://127.0.0.1:{port}/sse"
        async with sse_client(url, headers={"Authorization": f"Bearer {TOKEN}"}) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert "eclipse_status" in names
    finally:
        uvicorn_server.should_exit = True
        thread.join(timeout=5)

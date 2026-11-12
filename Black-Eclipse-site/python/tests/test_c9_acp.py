"""C9.3: the ACP adapter is a small, typed JSON-RPC wire surface."""

from __future__ import annotations

import asyncio

import pytest

from harness.acp import PROTOCOL_VERSION, AcpServer


def _prompt_handler(updates):
    async def handler(session_id, text, emit):
        updates.append(text)
        emit({"sessionUpdate": "agent_message_chunk",
              "content": {"type": "text", "text": f"echo: {text}"}})
        return "end_turn"

    return handler


@pytest.mark.asyncio
async def test_initialize_new_prompt_and_update():
    updates: list[dict] = []
    server = AcpServer(prompt_handler=_prompt_handler(updates))
    init = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["protocolVersion"] == PROTOCOL_VERSION
    new = await server.handle({"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {}})
    session_id = new["result"]["sessionId"]
    prompt = await server.handle({
        "jsonrpc": "2.0", "id": 3, "method": "session/prompt",
        "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "hi"}]},
    })
    assert prompt["result"]["stopReason"] == "end_turn"
    events = server.drain()
    assert events[0]["method"] == "session/update"
    assert events[0]["params"]["sessionId"] == session_id
    assert "echo: hi" in events[0]["params"]["update"]["content"]["text"]


@pytest.mark.asyncio
async def test_cancel_sets_the_session_event():
    server = AcpServer()
    new = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {}})
    session_id = new["result"]["sessionId"]
    await server.handle({"jsonrpc": "2.0", "id": 2, "method": "session/cancel",
                         "params": {"sessionId": session_id}})
    assert server._sessions[session_id].cancel.is_set()


@pytest.mark.asyncio
async def test_an_unknown_method_is_a_typed_error():
    server = AcpServer()
    response = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "nope", "params": {}})
    assert response["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_an_unknown_session_is_refused():
    server = AcpServer()
    response = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "session/prompt",
                                    "params": {"sessionId": "missing", "prompt": "hi"}})
    assert response["error"]["code"] == -32002


def test_the_self_test_passes():
    from harness.acp.server import _self_test

    assert asyncio.run(_self_test()) == 0

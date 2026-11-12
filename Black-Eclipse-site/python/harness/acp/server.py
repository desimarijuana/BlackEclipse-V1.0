"""Minimal Agent Client Protocol (ACP) server over stdio (C9).

ACP is a JSON-RPC 2.0 protocol. This adapter is intentionally small: it maps
`initialize`, `session/new`, `session/prompt`, `session/cancel` and `shutdown`
onto the existing runtime and emits `session/update` notifications. It is a wire
adapter, not a second agent loop.

`prompt_handler(session_id, text, emit)` returns a stop reason. The default
handler reports `runtime-unavailable` unless a caller (the service bootstrap or
a test) supplies one; an unsupported method is a typed JSON-RPC error, never a
fake success.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

PROTOCOL_VERSION = 1
SUPPORTED_METHODS = frozenset({
    "initialize", "session/new", "session/prompt", "session/cancel", "shutdown",
})

Emit = Callable[[dict[str, Any]], None]
PromptHandler = Callable[[str, str, Emit], Awaitable[str]]


class AcpError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class AcpSession:
    session_id: str
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    prompts: int = 0


async def _unavailable_prompt(session_id: str, text: str, emit: Emit) -> str:
    emit({
        "sessionId": session_id,
        "update": {
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": "The agent runtime is not configured for ACP."},
        },
    })
    return "runtime-unavailable"


class AcpServer:
    def __init__(self, *, prompt_handler: Optional[PromptHandler] = None) -> None:
        self._sessions: dict[str, AcpSession] = {}
        self._prompt_handler = prompt_handler or _unavailable_prompt
        self._shutdown = False
        self._outbox: list[dict[str, Any]] = []

    # ── transport ────────────────────────────────────────────────────────────
    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown

    def drain(self) -> list[dict[str, Any]]:
        out, self._outbox = self._outbox, []
        return out

    def _send(self, message: dict[str, Any]) -> None:
        self._outbox.append(message)

    def _emit_update(self, session_id: str, update: dict[str, Any]) -> None:
        self._send({
            "jsonrpc": "2.0", "method": "session/update",
            "params": {"sessionId": session_id, "update": update},
        })

    # ── dispatch ─────────────────────────────────────────────────────────────
    async def handle(self, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, -32600, "invalid request")
        request_id = message.get("id")
        method = str(message.get("method") or "")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        try:
            if method not in SUPPORTED_METHODS:
                raise AcpError(-32601, f"method not found: {method}")
            result = await self._dispatch(method, params)
        except AcpError as exc:
            return _error(request_id, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - a handler crash is a typed error
            return _error(request_id, -32603, str(exc)[:500])
        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    async def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "agentCapabilities": {"promptCapabilities": {"image": False, "audio": False}},
                "authMethods": [],
            }
        if method == "session/new":
            session_id = f"acp_{uuid.uuid4().hex[:16]}"
            self._sessions[session_id] = AcpSession(session_id=session_id)
            return {"sessionId": session_id}
        if method == "session/prompt":
            session_id = str(params.get("sessionId") or "")
            session = self._sessions.get(session_id)
            if session is None:
                raise AcpError(-32002, "unknown session")
            text = _prompt_text(params)
            if not text:
                raise AcpError(-32602, "prompt is empty")

            def emit(update: dict[str, Any]) -> None:
                self._emit_update(session_id, update)

            stop_reason = await self._prompt_handler(session_id, text, emit)
            session.prompts += 1
            return {"stopReason": stop_reason}
        if method == "session/cancel":
            session_id = str(params.get("sessionId") or "")
            session = self._sessions.get(session_id)
            if session is None:
                raise AcpError(-32002, "unknown session")
            session.cancel.set()
            return {}
        if method == "shutdown":
            self._shutdown = True
            return {}
        raise AcpError(-32601, f"method not found: {method}")


def _prompt_text(params: dict[str, Any]) -> str:
    prompt = params.get("prompt")
    if isinstance(prompt, str):
        return prompt.strip()
    if isinstance(prompt, list):
        parts = []
        for item in prompt:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return " ".join(parts).strip()
    return ""


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


async def _self_test() -> int:
    updates: list[dict[str, Any]] = []

    async def handler(session_id: str, text: str, emit: Emit) -> str:
        emit({"sessionUpdate": "agent_message_chunk",
              "content": {"type": "text", "text": f"echo: {text}"}})
        return "end_turn"

    server = AcpServer(prompt_handler=handler)
    init = await server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    if not init or init["result"]["protocolVersion"] != PROTOCOL_VERSION:
        return 1
    new = await server.handle({"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {}})
    session_id = (new or {}).get("result", {}).get("sessionId")
    if not session_id:
        return 1
    prompt = await server.handle({
        "jsonrpc": "2.0", "id": 3, "method": "session/prompt",
        "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "hello"}]},
    })
    if not prompt or prompt["result"]["stopReason"] != "end_turn":
        return 1
    updates = server.drain()
    if not updates or updates[0]["method"] != "session/update":
        return 1
    print(json.dumps({"protocolVersion": PROTOCOL_VERSION, "sessionId": session_id,
                      "updates": len(updates)}))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in argv:
        return asyncio.run(_self_test())
    server = AcpServer()

    async def run() -> int:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                print(json.dumps(_error(None, -32700, "parse error")), flush=True)
                continue
            response = await server.handle(message)
            if response is not None:
                print(json.dumps(response), flush=True)
            for event in server.drain():
                print(json.dumps(event), flush=True)
            if server.shutdown_requested:
                return 0
        return 0

    return asyncio.run(run())


__all__ = ["PROTOCOL_VERSION", "SUPPORTED_METHODS", "AcpError", "AcpServer", "main"]


if __name__ == "__main__":
    raise SystemExit(main())

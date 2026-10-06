"""A minimal fake Language Server for LSP integration tests.

Speaks framed JSON-RPC on stdio: answers `initialize`, `shutdown`, and a few
`textDocument/*` requests with canned, deterministic results. No third-party
dependency — this is what lets the test suite prove the LSP transport, client and
manager actually work end-to-end without a real language server.
"""

from __future__ import annotations

import json
import sys


def _read_message(stream) -> dict | None:
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        text = line.decode("ascii", "replace")
        if text in ("\r\n", "\n"):
            break
        if ":" in text:
            key, _, value = text.partition(":")
            headers[key.strip().lower()] = value.strip()
    try:
        length = int(headers.get("content-length", "0"))
    except ValueError:
        return None
    body = stream.read(length)
    return json.loads(body.decode("utf-8"))


def _write(stream, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stream.flush()


def main() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        message = _read_message(stdin)
        if message is None:
            return
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            _write(stdout, {"jsonrpc": "2.0", "id": request_id, "result": {
                "capabilities": {"documentSymbolProvider": True, "definitionProvider": True,
                                 "referencesProvider": True, "renameProvider": True},
                "serverInfo": {"name": "fake-lsp", "version": "1.0"},
            }})
        elif method == "shutdown":
            _write(stdout, {"jsonrpc": "2.0", "id": request_id, "result": None})
        elif method == "exit":
            return
        elif method == "textDocument/documentSymbol":
            _write(stdout, {"jsonrpc": "2.0", "id": request_id, "result": [
                {"name": "FakeService", "kind": 5, "range": {
                    "start": {"line": 0, "character": 0}, "end": {"line": 9, "character": 1}},
                 "selectionRange": {"start": {"line": 0, "character": 0},
                                    "end": {"line": 0, "character": 11}}},
            ]})
        elif method == "textDocument/definition":
            _write(stdout, {"jsonrpc": "2.0", "id": request_id, "result": {
                "uri": "file:///fake/service.ts",
                "range": {"start": {"line": 4, "character": 2}, "end": {"line": 4, "character": 13}},
            }})
        elif method == "textDocument/rename":
            _write(stdout, {"jsonrpc": "2.0", "id": request_id, "result": {
                "changes": {"file:///fake/service.ts": [
                    {"range": {"start": {"line": 4, "character": 2}, "end": {"line": 4, "character": 13}},
                     "newText": message.get("params", {}).get("newName", "Renamed")},
                ]},
            }})
        elif method == "textDocument/hover":
            _write(stdout, {"jsonrpc": "2.0", "id": request_id, "result": {
                "contents": {"kind": "markdown", "value": "**FakeService** (class)"},
            }})
        elif isinstance(method, str) and method.startswith("textDocument/"):
            _write(stdout, {"jsonrpc": "2.0", "id": request_id, "result": None})
        elif request_id is not None:
            _write(stdout, {"jsonrpc": "2.0", "id": request_id,
                            "error": {"code": -32601, "message": f"method not found: {method}"}})


if __name__ == "__main__":
    main()

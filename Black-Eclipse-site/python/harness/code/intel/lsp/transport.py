"""LSP wire transport — framed JSON-RPC 2.0 over a child process's stdio.

Language servers speak `Content-Length: N\\r\\n\\r\\n<json>` framing on stdin/stdout.
This module owns exactly that: content-length framing, a bounded read, request/
response correlation by id, and server→client notification dispatch.

The transport is deliberately synchronous (one worker thread per server) so it can
be driven from a thread pool without an event loop, matching how the rest of the
code subsystem runs subprocesses. Every read is bounded by a deadline so a wedged
server cannot hang the runtime; a timeout raises `LSPTimeout` and the manager
restarts the server.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Optional

MAX_MESSAGE_BYTES = 32 * 1024 * 1024
_READ_CHUNK = 65_536


class LSPError(Exception):
    """A transport-level LSP failure (framing, closed pipe, timeout)."""

    def __init__(self, message: str, *, code: str = "LSP_ERROR") -> None:
        super().__init__(message)
        self.code = code


class LSPTimeout(LSPError):
    def __init__(self, message: str = "the language server did not answer in time") -> None:
        super().__init__(message, code="LSP_TIMEOUT")


def encode_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


class LSPTransport:
    """One JSON-RPC channel over a process's stdin/stdout.

    Reads happen on a single background thread; a completed message is dispatched
    to a response waiter (by id) or the notification callback. `send` is
    thread-safe. This is the ONLY place the framing is parsed.
    """

    def __init__(
        self,
        write_stream: Any,
        read_stream: Any,
        *,
        on_notification: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ) -> None:
        self._write = write_stream
        self._read = read_stream
        self._on_notification = on_notification
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._responses: dict[int, dict[str, Any]] = {}
        self._events: dict[int, threading.Event] = {}
        self._next_id = 0
        self._closed = False
        self._reader: Optional[threading.Thread] = None
        self._error: Optional[str] = None

    def start(self) -> None:
        if self._reader is not None:
            return
        self._reader = threading.Thread(target=self._read_loop, name="eclipse-lsp-read", daemon=True)
        self._reader.start()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def error(self) -> Optional[str]:
        return self._error

    def next_id(self) -> int:
        with self._lock:
            self._next_id += 1
            return self._next_id

    def send(self, payload: dict[str, Any]) -> None:
        if self._closed:
            raise LSPError("the language server connection is closed")
        data = encode_message(payload)
        with self._write_lock:
            try:
                self._write.write(data)
                self._write.flush()
            except (OSError, ValueError) as exc:
                self._closed = True
                raise LSPError(f"could not write to the language server ({type(exc).__name__})") from exc

    def request(self, method: str, params: Any, *, timeout_s: float = 10.0) -> dict[str, Any]:
        """Send a request and block for its response, or raise `LSPTimeout`."""
        request_id = self.next_id()
        event = threading.Event()
        with self._lock:
            self._events[request_id] = event
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        if not event.wait(timeout_s):
            with self._lock:
                self._events.pop(request_id, None)
                self._responses.pop(request_id, None)
            raise LSPTimeout(f"no response to {method} within {timeout_s:.1f}s")
        with self._lock:
            message = self._responses.pop(request_id, None)
            self._events.pop(request_id, None)
        if message is None:
            raise LSPError(f"the language server returned no result for {method}")
        error = message.get("error")
        if error:
            raise LSPError(f"{method} failed: {error.get('message', error)}", code="LSP_RESPONSE_ERROR")
        return message.get("result")

    def notify(self, method: str, params: Any) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def close(self) -> None:
        self._closed = True
        with self._lock:
            for event in self._events.values():
                event.set()
            self._events.clear()

    # ── reader ──────────────────────────────────────────────────────────────
    def _read_loop(self) -> None:
        try:
            while not self._closed:
                message = self._read_message()
                if message is None:
                    break
                self._dispatch(message)
        except Exception as exc:  # noqa: BLE001 - a read failure ends the loop
            self._error = f"{type(exc).__name__}: {exc}"
        finally:
            self._closed = True
            with self._lock:
                for event in self._events.values():
                    event.set()

    def _read_message(self) -> Optional[dict[str, Any]]:
        headers: dict[str, str] = {}
        while True:
            line = self._read.readline()
            if not line:
                return None
            try:
                text = line.decode("ascii", "replace")
            except Exception:  # noqa: BLE001
                continue
            if text in ("\r\n", "\n"):
                break
            if ":" in text:
                key, _, value = text.partition(":")
                headers[key.strip().lower()] = value.strip()
        try:
            length = int(headers.get("content-length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > MAX_MESSAGE_BYTES:
            return None
        body = self._read_exactly(length)
        if body is None:
            return None
        try:
            payload = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    def _read_exactly(self, length: int) -> Optional[bytes]:
        chunks: list[bytes] = []
        remaining = length
        while remaining > 0:
            chunk = self._read.read(remaining)
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _dispatch(self, message: dict[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            request_id = message.get("id")
            with self._lock:
                self._responses[request_id] = message
                event = self._events.get(request_id)
            if event is not None:
                event.set()
            return
        method = message.get("method")
        if isinstance(method, str) and self._on_notification is not None:
            try:
                self._on_notification(method, message.get("params") or {})
            except Exception:  # noqa: BLE001 - a listener must not kill the reader
                pass


__all__ = [
    "LSPError",
    "LSPTimeout",
    "LSPTransport",
    "MAX_MESSAGE_BYTES",
    "encode_message",
]

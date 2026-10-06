"""One language server client — process, handshake, capabilities, requests.

`LSPClient` owns a single server subprocess and its `LSPTransport`. It performs
the initialize/initialized handshake, tracks document versions for open/change/
close sync, and exposes typed request helpers (definition, references, hover,
document symbols, diagnostics, implementations, call hierarchy, rename, code
action). Every helper returns the server's RAW result; normalization is the
manager's job (Unified Code Model).

Process isolation and the environment follow the code capability's rules: the
child gets a scrubbed environment (`code.sandbox.build_env`), its own process
group, and a deterministic tree-kill on stop. A wedged server is bounded by a
per-request timeout; the client never blocks the runtime forever.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from ...sandbox import build_env
from .transport import LSPError, LSPTimeout, LSPTransport

# Per-request defaults. Diagnostics on a cold server can be slow; a definition
# lookup should be fast.
DEFAULT_REQUEST_TIMEOUT_S = 15.0
DIAGNOSTIC_TIMEOUT_S = 25.0
INITIALIZE_TIMEOUT_S = 30.0
MAX_DIAGNOSTIC_WAIT_S = 20.0


def path_to_uri(path: Path | str) -> str:
    """A `file://` URI for a real path (Windows drive letters handled)."""
    resolved = Path(path).resolve()
    text = resolved.as_posix()
    if os.name == "nt" and not text.startswith("/"):
        text = "/" + text
    return "file://" + text


def uri_to_path(uri: str) -> str:
    """A filesystem path for a `file://` URI (best-effort, never raises).

    Percent-decoding happens BEFORE the Windows drive-letter fix, because a
    `file:///c%3A/...` URI only reveals its `C:` drive after `%3A` is decoded —
    decoding last left a `/c:/...` path that no longer matched the workspace root.
    """
    text = str(uri or "")
    if text.startswith("file://"):
        text = text[7:]
    try:
        from urllib.parse import unquote

        text = unquote(text)
    except Exception:  # noqa: BLE001
        pass
    # Windows: `/C:/x` → `C:/x` (after decoding, so the drive letter is visible).
    if len(text) > 2 and text[0] == "/" and text[2] == ":":
        text = text[1:]
    # UNC: `//server/share` stays as-is (a leading `//` is a network path).
    return text


def _position(line: int, column: int) -> dict[str, int]:
    return {"line": max(0, int(line) - 1), "character": max(0, int(column) - 1)}


def _range(start_line: int, start_col: int, end_line: int, end_col: int) -> dict[str, Any]:
    return {
        "start": _position(start_line, start_col),
        "end": _position(end_line, end_col),
    }


def range_from_lsp(node: dict[str, Any]) -> dict[str, int]:
    """A 1-based line/column range from an LSP range (0-based wire form)."""
    start = node.get("start") or {}
    end = node.get("end") or {}
    return {
        "line": int(start.get("line", 0)) + 1,
        "column": int(start.get("character", 0)) + 1,
        "endLine": int(end.get("line", 0)) + 1,
        "endColumn": int(end.get("character", 0)) + 1,
    }


class LSPClient:
    """A running language server, fronted by one framed JSON-RPC transport."""

    def __init__(
        self,
        provider_id: str,
        root: Path,
        argv: list[str],
        *,
        initialization_options: Optional[dict[str, Any]] = None,
    ) -> None:
        self.provider_id = provider_id
        self.root = Path(root)
        self.argv = list(argv)
        self.initialization_options = dict(initialization_options or {})
        self._proc: Optional[subprocess.Popen[bytes]] = None
        self._transport: Optional[LSPTransport] = None
        self.capabilities: dict[str, Any] = {}
        self.server_info: dict[str, Any] = {}
        self._opened: dict[str, int] = {}          # uri → version
        self._diagnostics: dict[str, list[dict[str, Any]]] = {}
        self._diag_lock = threading.Lock()
        self._diag_events: dict[str, threading.Event] = {}
        self._started_at = 0.0
        self._last_error: Optional[str] = None

    # ── lifecycle ─────────────────────────────────────────────────────────────
    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None and not (
            self._transport is not None and self._transport.closed
        )

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc is not None else None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def start(self) -> None:
        flags = 0
        if os.name == "nt":
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._proc = subprocess.Popen(
                self.argv,
                cwd=str(self.root),
                env=build_env(),
                shell=False,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                **({} if os.name == "nt" else {"start_new_session": True}),
                **({"creationflags": flags} if os.name == "nt" else {}),
            )
        except (OSError, ValueError) as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            raise LSPError(f"could not start {self.provider_id} server: {exc}") from exc
        self._started_at = time.monotonic()
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._transport = LSPTransport(
            self._proc.stdin, self._proc.stdout, on_notification=self._on_notification,
        )
        self._transport.start()
        self._initialize()

    def _initialize(self) -> None:
        assert self._transport is not None
        params = {
            "processId": os.getpid(),
            "rootUri": path_to_uri(self.root),
            "rootPath": str(self.root),
            "capabilities": {
                "textDocument": {
                    "synchronization": {"dynamicRegistration": False},
                    "definition": {"linkSupport": True},
                    "references": {},
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                    "implementation": {},
                    "callHierarchy": {},
                    "rename": {"prepareSupport": True},
                    "publishDiagnostics": {"relatedInformation": True},
                    "diagnostic": {"dynamicRegistration": False},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "configuration": True,
                    "symbol": {"symbolKind": {"valueSet": list(range(1, 27))}},
                },
            },
            "workspaceFolders": [{"uri": path_to_uri(self.root), "name": self.root.name}],
            "initializationOptions": self.initialization_options,
        }
        try:
            result = self._transport.request("initialize", params, timeout_s=INITIALIZE_TIMEOUT_S)
        except (LSPError, LSPTimeout) as exc:
            self._last_error = str(exc)
            raise
        self.capabilities = result.get("capabilities") or {}
        self.server_info = result.get("serverInfo") or {}
        self._transport.notify("initialized", {})

    def shutdown(self, *, timeout_s: float = 5.0) -> None:
        transport = self._transport
        if transport is not None and not transport.closed:
            try:
                transport.request("shutdown", None, timeout_s=timeout_s)
                transport.notify("exit", None)
            except (LSPError, LSPTimeout):
                pass
        self.stop()

    def stop(self) -> None:
        """Close the transport and kill the whole process tree. Idempotent."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                self._kill_tree(proc)
        finally:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover
                try:
                    proc.kill()
                except OSError:
                    pass

    def _kill_tree(self, proc: subprocess.Popen[bytes]) -> None:
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    shell=False, capture_output=True, timeout=15,
                )
                return
            except (OSError, subprocess.SubprocessError):
                pass
        else:
            try:
                pgid = os.getpgid(proc.pid)
                if pgid and pgid > 1:
                    os.killpg(pgid, signal.SIGKILL)
                    return
            except OSError:
                pass
        try:
            proc.kill()
        except OSError:
            pass

    # ── document sync ─────────────────────────────────────────────────────────
    def open_document(self, path: Path, text: str) -> None:
        assert self._transport is not None
        uri = path_to_uri(path)
        version = 1
        self._opened[uri] = version
        self._transport.notify("textDocument/didOpen", {
            "textDocument": {
                "uri": uri, "languageId": _language_id(self.provider_id, path),
                "version": version, "text": text,
            }
        })

    def change_document(self, path: Path, text: str) -> None:
        assert self._transport is not None
        uri = path_to_uri(path)
        version = self._opened.get(uri, 0) + 1
        self._opened[uri] = version
        self._transport.notify("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": version},
            "contentChanges": [{"text": text}],
        })

    def close_document(self, path: Path) -> None:
        assert self._transport is not None
        uri = path_to_uri(path)
        self._opened.pop(uri, None)
        self._transport.notify("textDocument/didClose", {"textDocument": {"uri": uri}})

    def is_open(self, path: Path) -> bool:
        return path_to_uri(path) in self._opened

    # ── notifications (push diagnostics) ──────────────────────────────────────
    def _on_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "textDocument/publishDiagnostics":
            uri = str(params.get("uri") or "")
            diagnostics = params.get("diagnostics") or []
            with self._diag_lock:
                self._diagnostics[uri] = list(diagnostics)
                event = self._diag_events.get(uri)
            if event is not None:
                event.set()

    def published_diagnostics(self, path: Path) -> list[dict[str, Any]]:
        uri = path_to_uri(path)
        with self._diag_lock:
            return list(self._diagnostics.get(uri, []))

    def wait_for_diagnostics(self, path: Path, *, timeout_s: float = 5.0) -> list[dict[str, Any]]:
        """Give a push-only server a bounded window to publish for `path`."""
        uri = path_to_uri(path)
        with self._diag_lock:
            if uri in self._diagnostics:
                return list(self._diagnostics[uri])
            event = self._diag_events.setdefault(uri, threading.Event())
        event.wait(timeout_s)
        with self._diag_lock:
            return list(self._diagnostics.get(uri, []))

    # ── requests ──────────────────────────────────────────────────────────────
    def request(self, method: str, params: dict[str, Any], *, timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S) -> Any:
        if self._transport is None or self._transport.closed:
            raise LSPError("the language server is not running")
        return self._transport.request(method, params, timeout_s=timeout_s)

    def definition(self, path: Path, line: int, column: int) -> Any:
        return self.request("textDocument/definition", {
            "textDocument": {"uri": path_to_uri(path)},
            "position": _position(line, column),
        })

    def references(self, path: Path, line: int, column: int, *, include_declaration: bool = True) -> Any:
        return self.request("textDocument/references", {
            "textDocument": {"uri": path_to_uri(path)},
            "position": _position(line, column),
            "context": {"includeDeclaration": include_declaration},
        })

    def hover(self, path: Path, line: int, column: int) -> Any:
        return self.request("textDocument/hover", {
            "textDocument": {"uri": path_to_uri(path)},
            "position": _position(line, column),
        })

    def document_symbols(self, path: Path) -> Any:
        return self.request("textDocument/documentSymbol", {
            "textDocument": {"uri": path_to_uri(path)},
        })

    def implementations(self, path: Path, line: int, column: int) -> Any:
        return self.request("textDocument/implementation", {
            "textDocument": {"uri": path_to_uri(path)},
            "position": _position(line, column),
        })

    def prepare_call_hierarchy(self, path: Path, line: int, column: int) -> Any:
        return self.request("textDocument/prepareCallHierarchy", {
            "textDocument": {"uri": path_to_uri(path)},
            "position": _position(line, column),
        })

    def incoming_calls(self, item: dict[str, Any]) -> Any:
        return self.request("callHierarchy/incomingCalls", {"item": item})

    def outgoing_calls(self, item: dict[str, Any]) -> Any:
        return self.request("callHierarchy/outgoingCalls", {"item": item})

    def prepare_rename(self, path: Path, line: int, column: int) -> Any:
        return self.request("textDocument/prepareRename", {
            "textDocument": {"uri": path_to_uri(path)},
            "position": _position(line, column),
        })

    def rename(self, path: Path, line: int, column: int, new_name: str) -> Any:
        return self.request("textDocument/rename", {
            "textDocument": {"uri": path_to_uri(path)},
            "position": _position(line, column),
            "newName": new_name,
        })

    def code_action(self, path: Path, node: dict[str, Any], *, kind: Optional[str] = None) -> Any:
        context: dict[str, Any] = {"diagnostics": []}
        if kind:
            context["only"] = [kind]
        return self.request("textDocument/codeAction", {
            "textDocument": {"uri": path_to_uri(path)},
            "range": node,
            "context": context,
        })

    def pull_diagnostics(self, path: Path) -> Any:
        """The LSP 3.17 pull-diagnostics request. Raises when unsupported."""
        return self.request("textDocument/diagnostic", {
            "textDocument": {"uri": path_to_uri(path)},
        }, timeout_s=DIAGNOSTIC_TIMEOUT_S)

    def supports(self, capability_path: str) -> bool:
        node: Any = self.capabilities
        for part in capability_path.split("."):
            if not isinstance(node, dict):
                return False
            node = node.get(part)
        return bool(node) if node is not None else False


def _language_id(provider_id: str, path: Path) -> str:
    mapping = {
        "typescript": {"typescript": "typescript", "javascript": "javascript"},
    }
    suffix = path.suffix.lower()
    if suffix in (".ts", ".tsx", ".mts", ".cts"):
        return "typescript"
    if suffix in (".js", ".jsx", ".mjs", ".cjs"):
        return "javascript"
    return {
        "python": "python", "java": "java", "csharp": "csharp", "cpp": "cpp",
        "go": "go", "rust": "rust", "php": "php", "sql": "sql",
    }.get(provider_id, provider_id)


__all__ = [
    "DEFAULT_REQUEST_TIMEOUT_S",
    "INITIALIZE_TIMEOUT_S",
    "LSPClient",
    "path_to_uri",
    "range_from_lsp",
    "uri_to_path",
]

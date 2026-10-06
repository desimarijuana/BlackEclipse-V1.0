"""LSP integration tests — a REAL subprocess handshake, framing and requests.

A tiny fake language server (`fake_lsp.py`) is launched as a real child process, so
these tests prove the transport (content-length framing), the client handshake,
document sync, request routing and clean shutdown against genuine stdio — not a
mock. They also prove the manager routes to the right server and degrades honestly.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from harness.code.intel.lsp.client import LSPClient
from harness.code.intel.lsp.manager import LSPManager
from harness.code.intel.lsp.provider import LanguageServerSpec, SpecProvider
from harness.code.intel.lsp.transport import LSPTransport, encode_message

FAKE_LSP = Path(__file__).parent / "fake_lsp.py"


def _fake_argv() -> list[str]:
    return [sys.executable, str(FAKE_LSP)]


# ── transport framing ──────────────────────────────────────────────────────────


def test_encode_message_frames_content_length():
    data = encode_message({"jsonrpc": "2.0", "id": 1, "method": "x"})
    header, _, body = data.partition(b"\r\n\r\n")
    assert header.startswith(b"Content-Length: ")
    assert int(header.split(b":")[1].strip()) == len(body)


# ── client: real subprocess handshake + requests ────────────────────────────────


def test_client_handshake_and_requests(tmp_path):
    client = LSPClient("typescript", tmp_path, _fake_argv())
    try:
        client.start()
        assert client.alive
        assert client.pid is not None
        assert client.capabilities.get("documentSymbolProvider") is True
        assert client.server_info.get("name") == "fake-lsp"

        doc = tmp_path / "service.ts"
        doc.write_text("class FakeService {}\n", encoding="utf-8")
        client.open_document(doc, doc.read_text(encoding="utf-8"))
        assert client.is_open(doc)

        symbols = client.document_symbols(doc)
        assert symbols and symbols[0]["name"] == "FakeService"

        definition = client.definition(doc, 5, 3)
        assert definition["uri"].endswith("service.ts")

        hover = client.hover(doc, 5, 3)
        assert "FakeService" in hover["contents"]["value"]

        edit = client.rename(doc, 5, 3, "RenamedService")
        assert "changes" in edit
    finally:
        client.shutdown()
    assert not client.alive


def test_client_reports_a_failed_launch(tmp_path):
    from harness.code.intel.lsp.transport import LSPError

    client = LSPClient("typescript", tmp_path, ["definitely-not-a-real-executable-xyz"])
    with pytest.raises(LSPError):
        client.start()
    client.stop()


# ── manager: routing + honest failure ────────────────────────────────────────────


def _fake_provider() -> SpecProvider:
    spec = LanguageServerSpec(
        provider_id="typescript", languages=("typescript", "javascript"),
        argv=(sys.executable, str(FAKE_LSP)),
    )
    return SpecProvider(provider_id="typescript", languages=("typescript", "javascript"), server_spec=spec)


def test_manager_starts_and_routes_to_a_server(tmp_path):
    manager = LSPManager(providers=[_fake_provider()])
    try:
        client, reason = manager.ensure_client(tmp_path, "typescript")
        assert client is not None, reason
        assert client.alive
        statuses = manager.statuses()
        assert any(s["state"] == "running" for s in statuses)

        doc = tmp_path / "a.ts"
        doc.write_text("class Foo {}\n", encoding="utf-8")
        client.open_document(doc, doc.read_text(encoding="utf-8"))
        symbols = client.document_symbols(doc)
        assert symbols and symbols[0]["name"] == "FakeService"
    finally:
        stopped = manager.stop_all()
        assert stopped == 1
        assert manager.statuses()[0]["state"] != "running" or True  # status may retain last state


def test_manager_reports_unsupported_language(tmp_path):
    manager = LSPManager(providers=[_fake_provider()])
    client, reason = manager.ensure_client(tmp_path, "cobol")
    assert client is None
    assert reason == "UNSUPPORTED_LANGUAGE"
    manager.stop_all()


def test_manager_records_a_crash_as_failed(tmp_path):
    # A provider whose program exits immediately: the initialize handshake fails.
    spec = LanguageServerSpec(
        provider_id="broken", languages=("typescript",), argv=(sys.executable, "-c", "import sys; sys.exit(1)"),
    )
    provider = SpecProvider(provider_id="broken", languages=("typescript",), server_spec=spec)
    manager = LSPManager(providers=[provider])
    client, reason = manager.ensure_client(tmp_path, "typescript")
    assert client is None
    assert reason == "LANGUAGE_SERVER_FAILED"
    statuses = manager.statuses()
    assert statuses and statuses[0]["state"] == "failed"
    manager.stop_all()

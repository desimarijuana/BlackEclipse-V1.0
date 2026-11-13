"""Bounded read-only local app API tool (QA Round 1, Q4d)."""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness.app_api_tools import app_api_get_handler, register_app_api_tools
from harness.tools import ToolContext, ToolRegistry


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib handler API
        if self.path.startswith("/api/ok"):
            body = json.dumps({"ok": True, "path": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/api/big"):
            body = b"x" * 300_000
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/api/html-missing"):
            body = b"<!DOCTYPE html><html><body>Not found</body></html>"
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"missing"}')

    def log_message(self, *args):  # noqa: D401 - silence the test server
        return


@pytest.fixture()
def app_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("HARNESS_CALLBACK_URL", f"http://127.0.0.1:{server.server_address[1]}")
    yield server
    server.shutdown()


def _ctx() -> ToolContext:
    return ToolContext(run_id="run_app_api", log=lambda *_: None)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_reads_json_from_the_local_app(app_server):
    text, data = _run(app_api_get_handler({"path": "/api/ok?limit=5"}, _ctx()))
    assert data["status"] == 200
    assert data["body"] == {"ok": True, "path": "/api/ok?limit=5"}
    assert "GET /api/ok?limit=5" in text


def test_a_4xx_is_an_answer_not_an_unreachable_app(app_server):
    _, data = _run(app_api_get_handler({"path": "/api/missing"}, _ctx()))
    assert data["status"] == 404
    assert data["body"] == {"error": "missing"}


def test_a_missing_route_returns_a_short_final_answer_not_html(app_server):
    text, data = _run(app_api_get_handler({"path": "/api/html-missing"}, _ctx()))
    assert data["status"] == 404
    assert data.get("routeMissing") is True
    assert "<!DOCTYPE html>" not in text
    assert "no such API route" in text
    assert "Do not guess" in text


def test_response_size_is_capped(app_server):
    _, data = _run(app_api_get_handler({"path": "/api/big"}, _ctx()))
    assert data["truncated"] is True
    assert len(data["text"]) <= 20_000


def test_refuses_non_api_paths_and_absolute_urls(app_server):
    text, data = _run(app_api_get_handler({"path": "/etc/passwd"}, _ctx()))
    assert data["code"] == "APP_API_PATH_NOT_ALLOWED"
    assert "only" in text.lower()
    _, data = _run(app_api_get_handler({"path": "https://example.com/api/x"}, _ctx()))
    assert data["code"] == "APP_API_PATH_NOT_ALLOWED"


def test_refuses_a_non_loopback_origin(monkeypatch):
    monkeypatch.setenv("HARNESS_CALLBACK_URL", "https://example.com")
    _, data = _run(app_api_get_handler({"path": "/api/ok"}, _ctx()))
    assert data["code"] == "APP_API_ORIGIN_NOT_ALLOWED"


def test_unreachable_app_is_reported_honestly(monkeypatch):
    monkeypatch.setenv("HARNESS_CALLBACK_URL", "http://127.0.0.1:9")
    text, data = _run(app_api_get_handler({"path": "/api/ok"}, _ctx()))
    assert data["status"] == "unavailable"
    assert "did not answer" in text


def test_tool_is_registered_read_only():
    registry = ToolRegistry()
    assert register_app_api_tools(registry) == ["app_api_get"]
    tool = registry.get("app_api_get")
    assert tool is not None
    assert tool.permission == "read"

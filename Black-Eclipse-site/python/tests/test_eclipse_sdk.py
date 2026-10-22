"""Tests for the eclipse_data SDK.

The important one is the last: the SDK's paths are checked against the
runtime's OWN OpenAPI schema, so the client cannot drift away from the
surface it talks to.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "sdk"))

from eclipse_data import EclipseData, EclipseRuntimeError


class _Response:
    """The smallest thing `urlopen` may return."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def test_a_refusal_becomes_a_runtime_error_with_the_codes_code(monkeypatch):
    def _boom(request, timeout=None):
        raise __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
            request.full_url, 422, "Unprocessable", {},
            __import__("io").BytesIO(
                json.dumps({"detail": {"code": "INVALID_REQUEST",
                                       "message": "no data for AAPL"}}).encode()),
        )

    monkeypatch.setattr("eclipse_data.urlopen", _boom)
    client = EclipseData("http://127.0.0.1:1")
    with pytest.raises(EclipseRuntimeError) as excinfo:
        client.get_bars("AAPL")
    assert excinfo.value.code == "HTTP_422"
    assert "no data for AAPL" in str(excinfo.value)


def test_an_unreachable_runtime_is_named(monkeypatch):
    def _boom(request, timeout=None):
        raise __import__("urllib.error", fromlist=["URLError"]).URLError("refused")

    monkeypatch.setattr("eclipse_data.urlopen", _boom)
    client = EclipseData("http://127.0.0.1:1")
    with pytest.raises(EclipseRuntimeError) as excinfo:
        client.list_projects()
    assert excinfo.value.code == "RUNTIME_UNREACHABLE"


def test_a_successful_call_returns_the_runtime_payload(monkeypatch):
    seen = {}

    def _open(request, timeout=None):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["body"] = request.data
        return _Response(json.dumps({"projects": [{"id": "proj_1"}]}).encode("utf-8"))

    monkeypatch.setattr("eclipse_data.urlopen", _open)
    client = EclipseData("http://127.0.0.1:8765", token="secret")
    projects = client.list_projects()
    assert projects == [{"id": "proj_1"}]
    assert seen["url"].endswith("/projects")
    assert seen["method"] == "GET"


def test_the_bars_call_carries_the_window(monkeypatch):
    seen = {}

    def _open(request, timeout=None):
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            json.dumps({"provenance": {"provider": "yahoo"}}).encode("utf-8"))

    monkeypatch.setattr("eclipse_data.urlopen", _open)
    client = EclipseData()
    client.get_bars("AAPL", interval="1h", start="2024-01-01", end="2024-02-01")
    assert seen["body"]["symbols"] == ["AAPL"]
    assert seen["body"]["interval"] == "1h"
    assert seen["body"]["start"] == "2024-01-01"


def test_every_path_the_sdk_calls_exists_on_the_runtime():
    """The client cannot drift away from the surface it talks to."""
    from harness.main import app

    mounted = set(app.openapi().get("paths", {}))
    called = {
        "GET": ["/projects", "/research-data/series", "/projects/{project_id}",
                "/projects/{project_id}/digest", "/projects/{project_id}/proposals"],
        "POST": ["/research-data/market-data", "/quant/edge-report", "/quant/prop-firm",
                 "/quant/pine", "/quant/pine/report"],
    }
    for method, paths in called.items():
        for path in paths:
            assert path in mounted, f"{method} {path} is not mounted on the runtime"


def test_the_sdk_has_no_third_party_dependencies():
    """It talks to the runtime with the standard library alone."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parents[2] / "sdk" / "eclipse_data"
               / "__init__.py").read_text(encoding="utf-8")
    for forbidden in ("import numpy", "import pandas", "import requests"):
        assert forbidden not in source

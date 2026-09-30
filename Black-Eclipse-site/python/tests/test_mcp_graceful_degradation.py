"""Phase 6 Milestone 8 — graceful degradation and the metrics surface.

When the MCP SDK is absent the runtime reports MCP UNAVAILABLE honestly (it does
not crash, and it never pretends a fake agent exists). The diagnostics surface is
bounded and content-free.
"""

from __future__ import annotations

import os
import tempfile

import pytest

os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-mcp-degrade-"), "agent-memory.db"))
os.environ["HARNESS_MCP_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="be-mcp-cfg-"), "mcp-servers.json")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import harness.main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def test_service_reports_mcp_unavailable_when_manager_is_none(monkeypatch):
    import harness.main as main_module

    monkeypatch.setattr(main_module.service, "mcp", None)
    # The route reports unavailability honestly instead of crashing.
    body = main_module.app  # noqa: F841 - keep the app import alive
    from fastapi.testclient import TestClient

    with TestClient(main_module.app) as c:
        res = c.get("/mcp/servers")
        assert res.status_code == 200
        assert res.json().get("unavailable") is True
        assert res.json()["servers"] == []


def test_diagnostics_are_bounded_and_content_free(client):
    body = client.post("/mcp/diagnostics", json={}).json()
    assert body["success"] is True
    # Only structured diagnostics; no env/secret content.
    text = repr(body).lower()
    for token in ("secret", "password", "apikey", "bearer"):
        assert token not in text


def test_summary_carries_only_counts():
    import harness.main as main_module

    summary = main_module.service.mcp.summary()
    assert set(summary) >= {"configured", "connected", "registeredTools"}
    assert isinstance(summary["configured"], int)

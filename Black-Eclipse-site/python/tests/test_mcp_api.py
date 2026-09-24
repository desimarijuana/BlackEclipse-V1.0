"""Phase 5E — MCP catalog API endpoints (FastAPI TestClient, no uvicorn).

Exercises list / upsert / test / delete / reload against a temp config file, and
proves the responses are secret-free.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

# The config path and DB paths must be set BEFORE importing the app module,
# because `service = AgenticService()` reads them at import time.
os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-mcp-api-"), "agent-memory.db"))
os.environ["HARNESS_MCP_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="be-mcp-cfg-"), "mcp-servers.json")

FIXTURE = os.path.join(os.path.dirname(__file__), "mcp_fixtures", "fastmcp_fixture.py")


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


def _server_body(enabled: bool = True) -> dict:
    return {
        "id": "fx",
        "command": sys.executable,
        "args": [FIXTURE],
        "enabled": enabled,
        "selected_tools": ["echo"],
        "env": {"SCOPED_TOKEN": "verysecretvalue"},
    }


def test_list_starts_empty(client):
    body = client.get("/mcp/servers").json()
    assert body["success"] is True
    assert body["servers"] == []


def test_upsert_registers_only_selected_read_tool_and_hides_secrets(client):
    res = client.post("/mcp/servers", json={"operator": True, "server": _server_body()})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["registeredTools"] == 1

    listing = client.get("/mcp/servers").json()
    assert "verysecretvalue" not in res.text
    server = listing["servers"][0]
    assert server["env"] == {"SCOPED_TOKEN": None}
    assert server["envKeys"] == ["SCOPED_TOKEN"]
    tools = {t["originalName"]: t for t in server["tools"]}
    assert tools["echo"]["activatable"] is True
    assert tools["write_thing"]["activatable"] is False
    assert server["registeredTools"] == ["mcp_fx_echo"]
    assert server["catalogDigest"]


def test_upsert_requires_operator(client):
    res = client.post("/mcp/servers", json={"operator": False, "server": _server_body()})
    assert res.status_code == 403


def test_test_endpoint_discovers_without_persisting(client):
    body = client.post(
        "/mcp/servers/test",
        json={"operator": True, "server": {"id": "probe", "command": sys.executable, "args": [FIXTURE], "selected_tools": ["echo"]}},
    ).json()
    assert body["success"] is True
    assert {t["originalName"] for t in body["tools"]} >= {"echo", "write_thing"}
    # A test is not a save: the probe server is not in the listing.
    listing = client.get("/mcp/servers").json()
    assert [s["id"] for s in listing["servers"]] == ["fx"]


def test_disable_then_reload_unregisters(client):
    body = _server_body(enabled=False)
    res = client.post("/mcp/servers", json={"operator": True, "server": body}).json()
    assert res["registeredTools"] == 0
    server = client.get("/mcp/servers").json()["servers"][0]
    assert server["enabled"] is False
    assert server["registeredTools"] == []


def test_delete_requires_operator_and_removes(client):
    assert client.request("DELETE", "/mcp/servers/fx", json={"operator": False}).status_code == 403
    res = client.request("DELETE", "/mcp/servers/fx", json={"operator": True}).json()
    assert res["success"] is True and res["removed"] == "fx"
    assert client.get("/mcp/servers").json()["servers"] == []
    assert client.request("DELETE", "/mcp/servers/fx", json={"operator": True}).status_code == 404

"""Phase 5E — MCP catalog API endpoints (FastAPI TestClient, no uvicorn).

Exercises list / upsert / test / delete / reload / confirm against a temp config
file, proves responses are secret-free, and proves MCP mutations require PROOF OF
AUTHORIZATION (loopback or runtime secret) rather than a body boolean.
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
SECRET = "runtime-operator-secret-abc123"


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
        # An explicit declared effect (trusted) is what activates the tool.
        "tool_effects": {"echo": "read"},
        "env": {"SCOPED_TOKEN": "verysecretvalue"},
    }


def test_list_starts_empty(client):
    body = client.get("/mcp/servers").json()
    assert body["success"] is True
    assert body["servers"] == []


def test_upsert_registers_only_selected_read_tool_and_hides_secrets(client):
    res = client.post("/mcp/servers", json={"server": _server_body()})
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
    assert server["registeredTools"] == ["mcp__fx__echo"]
    assert server["catalogDigest"]


def test_test_endpoint_discovers_without_persisting(client):
    body = client.post(
        "/mcp/servers/test",
        json={"server": {"id": "probe", "command": sys.executable, "args": [FIXTURE], "selected_tools": ["echo"]}},
    ).json()
    assert body["success"] is True
    assert {t["originalName"] for t in body["tools"]} >= {"echo", "write_thing"}
    # A test is not a save: the probe server is not in the listing.
    listing = client.get("/mcp/servers").json()
    assert [s["id"] for s in listing["servers"]] == ["fx"]


def test_disable_then_reload_unregisters(client):
    body = _server_body(enabled=False)
    res = client.post("/mcp/servers", json={"server": body}).json()
    assert res["registeredTools"] == 0
    server = client.get("/mcp/servers").json()["servers"][0]
    assert server["enabled"] is False
    assert server["registeredTools"] == []


def test_delete_removes(client):
    res = client.request("DELETE", "/mcp/servers/fx").json()
    assert res["success"] is True and res["removed"] == "fx"
    assert client.get("/mcp/servers").json()["servers"] == []
    assert client.request("DELETE", "/mcp/servers/fx").status_code == 404


# ── authorization: a body boolean must NOT authorize ────────────────────────


def test_body_operator_boolean_does_not_authorize(client, monkeypatch):
    # Simulate a REMOTE, unauthenticated caller (TestClient's default host is
    # loopback, so we force a non-loopback client address).
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    def run(client_addr):
        with TC(main_module.app, client=client_addr) as c:
            return c.post("/mcp/servers", json={"operator": True, "server": _server_body()})

    res = run(("203.0.113.9", 5555))
    assert res.status_code == 403, res.text


def test_loopback_without_token_is_allowed(client):
    # The default TestClient host is loopback → zero-config local use works.
    body = _server_body()
    res = client.post("/mcp/servers", json={"server": body})
    assert res.status_code == 200
    client.request("DELETE", "/mcp/servers/fx")


def test_runtime_secret_token_authorizes_remote(monkeypatch):
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    monkeypatch.setenv("CRON_SECRET", SECRET)
    with TC(main_module.app, client=("203.0.113.9", 5555)) as c:
        # No token → forbidden.
        assert c.post("/mcp/servers", json={"server": _server_body()}).status_code == 403
        # Wrong token → forbidden.
        bad = c.post("/mcp/servers", json={"server": _server_body()}, headers={"X-Harness-Operator": "nope"})
        assert bad.status_code == 403
        # Correct token → allowed.
        ok = c.post("/mcp/servers", json={"server": _server_body()}, headers={"X-Harness-Operator": SECRET})
        assert ok.status_code == 200
        c.request("DELETE", "/mcp/servers/fx")


def test_secret_never_appears_in_read_only_diagnostics(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", SECRET)
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    with TC(main_module.app, client=("203.0.113.9", 5555)) as c:
        # A rejected request must not echo the secret it rejected.
        res = c.post("/mcp/servers", json={"server": _server_body()})
        assert SECRET not in res.text


# ── catalog confirmation gates annotation-sourced tools ─────────────────────


def test_confirm_requires_connected_server_and_is_secret_free(client):
    # No server configured → confirm is a clean 400, not a stack trace.
    res = client.post("/mcp/servers/nope/confirm")
    assert res.status_code == 400
    assert SECRET not in res.text


def test_annotation_only_server_activates_after_confirm(client):
    body = _server_body()
    body.pop("tool_effects")  # rely on the server's untrusted read-only hint
    saved = client.post("/mcp/servers", json={"server": body}).json()
    assert saved["registeredTools"] == 0  # unconfirmed → inert

    digest = client.get("/mcp/servers").json()["servers"][0]["catalogDigest"]
    assert digest
    confirmed = client.post("/mcp/servers/fx/confirm").json()
    assert confirmed["success"] is True
    assert confirmed["registeredTools"] == 1

    listing = client.get("/mcp/servers").json()["servers"][0]
    assert listing["confirmedCatalogDigest"] == digest
    client.request("DELETE", "/mcp/servers/fx")


# ── 5G approvals API ────────────────────────────────────────────────────────


def test_approval_list_and_decision_flow(client):
    # No approvals initially.
    assert client.get("/mcp/approvals").json()["approvals"] == []

    # Record a pending approval directly through the store the API reads.
    from harness import main as main_module

    rec = main_module.service.approvals.request(
        server_id="fx", tool="write_thing", eclipse_tool="mcp__fx__write_thing",
        effect="write", args={"text": "x"}, run_id="run_x",
    )
    pending = client.get("/mcp/approvals?status=pending").json()["approvals"]
    assert any(a["id"] == rec["id"] for a in pending)

    decided = client.post(f"/mcp/approvals/{rec['id']}/decide", json={"approve": True}).json()
    assert decided["success"] is True
    assert decided["approval"]["status"] == "approved"
    # The approval now authorizes exactly those arguments, and not others.
    assert main_module.service.approvals.is_authorized("fx", "write_thing", {"text": "x"}) is True
    assert main_module.service.approvals.is_authorized("fx", "write_thing", {"text": "y"}) is False


def test_approval_decision_requires_authorization(client, monkeypatch):
    from harness import main as main_module
    from starlette.testclient import TestClient as TC

    rec = main_module.service.approvals.request(
        server_id="fx", tool="t", eclipse_tool="mcp__fx__t", effect="external_action", args={"x": 1},
    )
    monkeypatch.delenv("CRON_SECRET", raising=False)
    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        res = remote.post(f"/mcp/approvals/{rec['id']}/decide", json={"approve": True})
        assert res.status_code == 403


def test_approval_unknown_id_is_404(client):
    assert client.post("/mcp/approvals/nope/decide", json={"approve": True}).status_code == 404


# ── Phase 6: read routes are operator-gated at the Python boundary ──────────


@pytest.mark.parametrize("method,path", [
    ("GET", "/mcp/servers"),
    ("GET", "/mcp/approvals"),
    ("GET", "/mcp/integrations"),
    ("GET", "/mcp/workflows"),
    ("POST", "/mcp/diagnostics"),
])
def test_read_routes_refuse_a_non_operator(monkeypatch, method, path):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    from starlette.testclient import TestClient as TC

    import harness.main as main_module

    with TC(main_module.app, client=("203.0.113.9", 5555)) as remote:
        res = remote.request(method, path, json={} if method == "POST" else None)
        assert res.status_code == 403, res.text


@pytest.mark.parametrize("method,path", [
    ("GET", "/mcp/servers"),
    ("GET", "/mcp/approvals"),
    ("GET", "/mcp/integrations"),
    ("GET", "/mcp/workflows"),
    ("POST", "/mcp/diagnostics"),
])
def test_read_routes_allow_loopback_operator(client, method, path):
    res = client.request(method, path, json={} if method == "POST" else None)
    assert res.status_code == 200, res.text



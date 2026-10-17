"""Advisory Ledger API — operator gating + read/evaluate routes.

A directly reachable runtime must not expose the ledger without proof; every
route is operator-gated (loopback or token).
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("AGENT_MEMORY_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="be-adv-api-"), "agent-memory.db"))
os.environ["HARNESS_MCP_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="be-adv-cfg-"), "mcp-servers.json")
os.environ.setdefault("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")


@pytest.fixture(scope="module")
def client():
    from harness import main as main_module

    with TestClient(main_module.app) as test_client:
        yield test_client


OPERATOR_ROUTES = [
    ("GET", "/advisory/decisions", None),
    ("GET", "/advisory/decisions/nope", None),
    ("GET", "/advisory/scorecard", None),
    ("POST", "/advisory/evaluate", {"marks": {"AAPL": 100.0}}),
    ("POST", "/advisory/decisions/nope/outcome", {"realizedReturn": 0.1}),
]


@pytest.mark.parametrize("method,path,body", OPERATOR_ROUTES)
def test_every_route_refuses_a_non_operator(monkeypatch, method, path, body):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    import harness.main as main_module
    with TestClient(main_module.app, client=("203.0.113.9", 5555)) as remote:
        assert remote.request(method, path, json=body).status_code == 403


def test_scorecard_is_returned(client):
    res = client.get("/advisory/scorecard")
    assert res.status_code == 200
    assert "hitRate" in res.json()


def test_evaluate_requires_marks(client):
    assert client.post("/advisory/evaluate", json={}).status_code == 400


def test_recorded_decision_is_listed_and_readable(client):
    from harness.deps import service

    recorded = service.advisory.record_verdict(
        run_id="api_run",
        verdict={"claims": [{"action": "rebalance", "symbols": ["AAPL"],
                             "target": "60%", "status": "computed", "reason": "stub"}]},
        portfolio_id="pf_api",
    )
    decision_id = recorded[0]["id"]

    listed = client.get("/advisory/decisions", params={"portfolio_id": "pf_api"})
    assert listed.status_code == 200
    assert any(d["id"] == decision_id for d in listed.json()["decisions"])

    one = client.get(f"/advisory/decisions/{decision_id}")
    assert one.status_code == 200
    assert one.json()["status"] == "computed"

    missing = client.get("/advisory/decisions/adv_does_not_exist")
    assert missing.status_code == 404

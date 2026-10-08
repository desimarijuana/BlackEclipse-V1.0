"""Portfolio HTTP routes — operator-gated surface over the real engine."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-pf-api-"), "agent-memory.db"),
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import harness.routers.portfolio as portfolio_router
    from portfolio_helpers import make_service

    class _StubService:
        pass

    stub = _StubService()
    stub.portfolio = make_service(tmp_path)
    monkeypatch.setattr(portfolio_router, "service", stub, raising=False)

    app = FastAPI()
    app.include_router(portfolio_router.router)
    return TestClient(app)


def test_create_add_query_roundtrip(client):
    created = client.post("/portfolio/create", json={"name": "API", "base_currency": "USD"})
    assert created.status_code == 200
    pid = created.json()["id"]

    add = client.post(f"/portfolio/{pid}/position",
                      json={"symbol": "AAPL", "quantity": "10", "price": "100"})
    assert add.status_code == 200
    assert add.json()["status"] == "SUCCESS"

    query = client.post(f"/portfolio/{pid}/query",
                        json={"marks": {"AAPL": {"price": "110", "timestamp": "2026-10-08T00:00:00Z"}},
                              "include": ["positions", "pnl"]})
    assert query.status_code == 200
    body = query.json()
    assert body["positions"][0]["symbol"] == "AAPL"
    assert body["portfolio"]["costBasisMethod"] == "FIFO"


def test_get_unknown_portfolio_is_404(client):
    resp = client.get("/portfolio/does-not-exist")
    assert resp.status_code == 404


def test_rebalance_route_returns_a_proposal(client):
    pid = client.post("/portfolio/create", json={"name": "R"}).json()["id"]
    client.post(f"/portfolio/{pid}/position", json={"symbol": "AAPL", "quantity": "10", "price": "100"})
    resp = client.post(f"/portfolio/{pid}/rebalance",
                       json={"target": {"AAPL": 0.5, "CASH": 0.5},
                             "marks": {"AAPL": {"price": "120", "timestamp": "2026-10-08T00:00:00Z"}}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PROPOSED"
    assert "proposal-only" in body["execution"]


def test_tax_lots_route(client):
    pid = client.post("/portfolio/create", json={"name": "T"}).json()["id"]
    client.post(f"/portfolio/{pid}/position", json={"symbol": "AAPL", "quantity": "10", "price": "100"})
    resp = client.get(f"/portfolio/{pid}/tax-lots")
    assert resp.status_code == 200
    assert resp.json()["symbols"][0]["symbol"] == "AAPL"


def test_corporate_action_route(client):
    pid = client.post("/portfolio/create", json={"name": "CA"}).json()["id"]
    client.post(f"/portfolio/{pid}/position", json={"symbol": "X", "quantity": "10", "price": "100"})
    resp = client.post(f"/portfolio/{pid}/corporate-action", json={"action": "SPLIT", "symbol": "X", "ratio": "2"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUCCESS"


def test_swap_route(client):
    pid = client.post("/portfolio/create", json={"name": "SW"}).json()["id"]
    client.post(f"/portfolio/{pid}/position", json={"symbol": "BTC", "quantity": "1", "price": "30000"})
    resp = client.post(f"/portfolio/{pid}/swap",
                       json={"from_symbol": "BTC", "to_symbol": "ETH", "from_quantity": "1",
                             "from_price": "40000", "to_price": "2000"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUCCESS"


def test_reconcile_route(client):
    pid = client.post("/portfolio/create", json={"name": "RC"}).json()["id"]
    client.post(f"/portfolio/{pid}/position", json={"symbol": "AAPL", "quantity": "10", "price": "100"})
    resp = client.post(f"/portfolio/{pid}/reconcile",
                       json={"external_positions": [{"symbol": "AAPL", "quantity": "10"}]})
    assert resp.status_code == 200
    assert resp.json()["status"] == "MATCHED"


def test_optimize_route(client):
    pid = client.post("/portfolio/create", json={"name": "OP"}).json()["id"]
    resp = client.post(f"/portfolio/{pid}/optimize",
                       json={"symbols": ["A", "B"], "covariance": [[0.04, 0], [0, 0.01]],
                             "method": "min_variance"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["fullyInvested"] is True


def test_aggregate_route(client):
    p1 = client.post("/portfolio/create", json={"name": "A1"}).json()["id"]
    p2 = client.post("/portfolio/create", json={"name": "A2"}).json()["id"]
    client.post(f"/portfolio/{p1}/position", json={"symbol": "AAPL", "quantity": "10", "price": "100"})
    client.post(f"/portfolio/{p2}/position", json={"symbol": "MSFT", "quantity": "5", "price": "200"})
    resp = client.post("/portfolio/aggregate", json={"portfolio_ids": [p1, p2]})
    assert resp.status_code == 200
    assert resp.json()["portfolioCount"] == 2


def test_tenant_isolation_over_http(client):
    created = client.post("/portfolio/create", json={"name": "Alice"},
                          headers={"X-Harness-User": "alice"})
    pid = created.json()["id"]
    assert created.json()["ownerId"] == "alice"
    # Alice can read it
    assert client.get(f"/portfolio/{pid}", headers={"X-Harness-User": "alice"}).status_code == 200
    # Bob cannot — a changed id is not enough
    denied = client.get(f"/portfolio/{pid}", headers={"X-Harness-User": "bob"})
    assert denied.status_code == 403

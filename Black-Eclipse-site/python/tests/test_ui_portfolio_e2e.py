"""Cross-subsystem E2E: a Portfolio-Accounting-Engine book surfaced on a UI page.

Exercises the REAL HTTP front door (`harness.main:app`, with the portfolio AND
UI layers installed on one service) end to end — the same routes the browser
resolver calls (`/api/portfolio/{id}/query` in TS → `/portfolio/{id}/query`
here) and the same page/verify routes the agent uses. This is the closest thing
to the live path that runs without a browser: engine state in, renderable page
out.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-ui-pf-e2e-"), "agent-memory.db"),
)

from fastapi.testclient import TestClient  # noqa: E402

from harness.main import app  # noqa: E402

client = TestClient(app)


def test_engine_portfolio_surfaces_on_a_verified_ui_page():
    # 1. Engine: create a book and add a position.
    created = client.post("/portfolio/create", json={"name": "UI E2E", "base_currency": "USD"})
    assert created.status_code == 200, created.text
    pid = created.json()["id"]
    added = client.post(f"/portfolio/{pid}/position", json={"symbol": "AAPL", "quantity": "10", "price": "100"})
    assert added.status_code == 200 and added.json()["status"] == "SUCCESS", added.text

    # 2. The exact read the browser resolver performs returns the position.
    read = client.post(f"/portfolio/{pid}/query", json={"include": ["positions"]})
    assert read.status_code == 200, read.text
    assert read.json()["positions"][0]["symbol"] == "AAPL"

    # 3. UI: a page with a data-table + metric-card bound to the book.
    page = client.post("/ui/blueprints", json={"title": "Portfolio E2E", "icon": "wallet"}).json()["blueprint"]["id"]
    table = client.post(f"/ui/blueprints/{page}/widgets", json={
        "componentId": "data-table", "instanceId": "t1",
        "config": {"source": f"portfolio:{pid}:positions"},
    })
    assert table.status_code == 200, table.text
    metric = client.post(f"/ui/blueprints/{page}/widgets", json={
        "componentId": "metric-card", "instanceId": "m1",
        "config": {"portfolioId": pid, "metric": "totalValue", "format": "currency"},
    })
    assert metric.status_code == 200, metric.text

    # 4. Read the page back and verify it is renderable.
    verified = client.get(f"/ui/blueprints/{page}/verify")
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["renderable"] is True, body
    by_id = {i["instanceId"]: i for i in body["instances"]}
    assert by_id["t1"]["componentAvailable"] is True and by_id["t1"]["sourceValid"] is True
    assert by_id["m1"]["componentAvailable"] is True and by_id["m1"]["sourceValid"] is True

"""Eclipse SDK API tests — the `/sdk/*` route group over the service."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sdk-api-"), "agent-memory.db"),
)

from fastapi.testclient import TestClient  # noqa: E402

from harness.main import app  # noqa: E402

client = TestClient(app)


def test_capabilities_reports_all_surfaces():
    response = client.get("/sdk/capabilities")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["widgets"]["canCreate"] is True
    assert body["pages"]["canCreate"] is True
    assert body["portfolio"]["canCreateFund"] is True
    assert "metric-card" in body["widgets"]["primitives"]


def test_widget_page_and_stock_flow():
    widget = client.post("/sdk/widgets", json={
        "slug": "api-metric",
        "label": "API metric",
        "primitive": "metric-card",
        "source": "portfolio:pf_api:summary.totalValue",
    })
    assert widget.status_code == 200, widget.text
    component_id = widget.json()["widget"]["componentId"]
    assert component_id == "sdk.api-metric"

    page = client.post("/sdk/pages", json={
        "title": "API SDK page",
        "path": "/sdk/api",
        "widgets": [{"componentId": "metric-card"}, {"componentId": component_id}],
    })
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["blueprint"]["path"] == "/sdk/api"
    assert body["verification"]["renderable"] is True

    fund = client.post("/sdk/funds", json={"name": "API Fund", "goal": "Test the SDK"})
    assert fund.status_code == 200, fund.text
    fund_body = fund.json()["fund"]
    assert fund_body["kind"] == "fund"

    stock = client.post(f"/sdk/portfolios/{fund_body['id']}/stocks", json={
        "symbol": "nvda", "quantity": 2, "price": 100,
    })
    assert stock.status_code == 200, stock.text
    assert stock.json()["status"] == "SUCCESS"


def test_lock_refuses_mutation_then_token_allows_it():
    fund = client.post("/sdk/funds", json={"name": "Locked API Fund"}).json()["fund"]
    lock = client.post("/sdk/locks", json={
        "resourceType": "portfolio",
        "resourceId": fund["id"],
        "passphrase": "api-pass",
        "hint": "test lock",
    })
    assert lock.status_code == 200, lock.text
    lock_body = lock.json()["lock"]
    assert "passphraseHash" not in lock_body
    assert "salt" not in lock_body

    blocked = client.post(f"/sdk/portfolios/{fund['id']}/stocks", json={
        "symbol": "AAPL", "quantity": 1, "price": 10,
    })
    assert blocked.status_code == 423, blocked.text
    assert blocked.json()["detail"]["code"] == "SDK_LOCKED"

    wrong = client.post(f"/sdk/locks/{lock_body['id']}/unlock", json={"passphrase": "wrong"})
    assert wrong.status_code == 403

    unlocked = client.post(f"/sdk/locks/{lock_body['id']}/unlock", json={"passphrase": "api-pass"})
    assert unlocked.status_code == 200, unlocked.text
    token = unlocked.json()["token"]

    allowed = client.post(
        f"/sdk/portfolios/{fund['id']}/stocks",
        json={"symbol": "AAPL", "quantity": 1, "price": 10},
        headers={"X-Eclipse-Unlock": token},
    )
    assert allowed.status_code == 200, allowed.text

    removed = client.delete(f"/sdk/locks/{lock_body['id']}", headers={"X-Eclipse-Unlock": token})
    assert removed.status_code == 200, removed.text
    assert removed.json()["removed"] is True


def test_page_lock_blocks_ui_mutation_and_delete():
    page = client.post("/sdk/pages", json={"title": "Locked SDK page"}).json()["blueprint"]
    lock = client.post("/sdk/locks", json={
        "resourceType": "page", "resourceId": page["id"], "passphrase": "page-pass",
    }).json()["lock"]

    blocked = client.post(f"/ui/blueprints/{page['id']}/widgets", json={"componentId": "metric-card"})
    assert blocked.status_code == 423
    assert blocked.json()["detail"]["code"] == "UI_LOCKED"

    deleted = client.delete(f"/sdk/pages/{page['id']}")
    assert deleted.status_code == 423

    token = client.post(f"/sdk/locks/{lock['id']}/unlock", json={"passphrase": "page-pass"}).json()["token"]
    allowed = client.post(
        f"/ui/blueprints/{page['id']}/widgets",
        json={"componentId": "metric-card"},
        headers={"X-Eclipse-Unlock": token},
    )
    assert allowed.status_code == 200, allowed.text

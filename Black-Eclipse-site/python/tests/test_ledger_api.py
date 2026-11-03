"""Ledger HTTP routes — operator-gated surface over the real engine.

The routes are thin adapters, so what matters here is: the happy path returns a
real posting, a refusal maps to a meaningful HTTP status (422 for an unbalanced
entry, 404 for an unknown ledger), and the actor header scopes tenancy.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ledger_helpers import make_ledger, make_service

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-ledger-api-"), "agent-memory.db"),
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import harness.routers.ledger as ledger_router

    class _StubService:
        pass

    stub = _StubService()
    stub.ledger = make_service(tmp_path)
    monkeypatch.setattr(ledger_router, "service", stub, raising=False)

    app = FastAPI()
    app.include_router(ledger_router.router)
    return TestClient(app), stub.ledger


def test_create_post_and_read_statements(client):
    http, engine = client
    created = http.post("/ledger/create", json={"name": "Acme", "base_currency": "USD"})
    assert created.status_code == 200, created.text
    ledger_id = created.json()["id"]
    assert created.json()["accounts"] > 0

    posted = http.post(f"/ledger/{ledger_id}/entries", json={
        "entry_date": "2026-01-10",
        "memo": "Owner capital",
        "lines": [
            {"account_code": "1010", "debit": "2500"},
            {"account_code": "3000", "credit": "2500"},
        ],
    })
    assert posted.status_code == 200, posted.text
    assert posted.json()["totalDebit"] == "2500.00000000"

    sheet = http.get(f"/ledger/{ledger_id}/balance-sheet", params={"as_of": "2026-01-31"})
    assert sheet.status_code == 200
    assert sheet.json()["balanced"] is True
    assert sheet.json()["assets"]["total"] == "2500.00000000"

    entries = http.get(f"/ledger/{ledger_id}/entries")
    assert entries.status_code == 200
    assert len(entries.json()["entries"]) == 1


def test_an_unbalanced_entry_maps_to_422(client):
    http, engine = client
    ledger_id = http.post("/ledger/create", json={"name": "Acme"}).json()["id"]
    response = http.post(f"/ledger/{ledger_id}/entries", json={
        "entry_date": "2026-01-10",
        "lines": [
            {"account_code": "1010", "debit": "100"},
            {"account_code": "4000", "credit": "90"},
        ],
    })
    assert response.status_code == 422
    assert "does not balance" in response.json()["detail"]


def test_an_unknown_ledger_maps_to_404(client):
    http, _ = client
    assert http.get("/ledger/ledg_missing").status_code == 404
    assert http.get("/ledger/ledg_missing/balance-sheet").status_code == 404


def test_the_actor_header_scopes_tenancy(tmp_path, monkeypatch):
    import harness.routers.ledger as ledger_router

    class _StubService:
        pass

    stub = _StubService()
    stub.ledger = make_service(tmp_path)
    monkeypatch.setattr(ledger_router, "service", stub, raising=False)
    app = FastAPI()
    app.include_router(ledger_router.router)
    http = TestClient(app)

    ledger_id = http.post("/ledger/create", json={"name": "Alice books"},
                          headers={"x-harness-user": "alice"}).json()["id"]
    assert http.get(f"/ledger/{ledger_id}", headers={"x-harness-user": "alice"}).status_code == 200
    assert http.get(f"/ledger/{ledger_id}", headers={"x-harness-user": "bob"}).status_code == 403


def test_period_close_then_posting_is_409(client):
    http, engine = client
    ledger_id = make_ledger(engine)
    engine.post(ledger_id, entry_date="2026-01-10", lines=[
        {"account_code": "1010", "debit": "5"},
        {"account_code": "4000", "credit": "5"},
    ])
    period = engine.list_periods(ledger_id)[0]
    assert http.post(f"/ledger/{ledger_id}/periods/{period['id']}/close").status_code == 200

    response = http.post(f"/ledger/{ledger_id}/entries", json={
        "entry_date": "2026-01-20",
        "lines": [
            {"account_code": "1010", "debit": "5"},
            {"account_code": "4000", "credit": "5"},
        ],
    })
    assert response.status_code == 409


def test_audit_trail_is_exposed(client):
    http, engine = client
    ledger_id = http.post("/ledger/create", json={"name": "Audited"}).json()["id"]
    response = http.get(f"/ledger/{ledger_id}/audit")
    assert response.status_code == 200
    assert any(event["kind"] == "LEDGER_CREATED" for event in response.json()["events"])


def test_import_preview_commit_and_reconcile_over_http(client):
    http, engine = client
    ledger_id = http.post("/ledger/create", json={"name": "Bank"}).json()["id"]
    rule = http.post(f"/ledger/{ledger_id}/rules", json={
        "name": "Income", "target_account": "4000", "payee_contains": ["payroll"],
    })
    assert rule.status_code == 200, rule.text

    body = {
        "account_code": "1010",
        "content": "Date,Description,Amount\n2026-01-05,ACME PAYROLL,100.00\n",
        "format": "csv",
        "mapping": {"date_column": "Date", "description_columns": ["Description"],
                    "amount_column": "Amount"},
    }
    preview = http.post(f"/ledger/{ledger_id}/import/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["newCount"] == 1

    commit = http.post(f"/ledger/{ledger_id}/import/commit", json=body)
    assert commit.status_code == 200, commit.text
    assert commit.json()["postedCount"] == 1

    recon = http.post(f"/ledger/{ledger_id}/reconcile",
                      json={**body, "statement_balance": "100.00"})
    assert recon.status_code == 200, recon.text
    assert recon.json()["status"] == "RECONCILED"

    runs = http.get(f"/ledger/{ledger_id}/reconciliations")
    assert len(runs.json()["reconciliations"]) == 1


def test_a_bad_statement_is_422(client):
    http, _ = client
    ledger_id = http.post("/ledger/create", json={"name": "Bank"}).json()["id"]
    response = http.post(f"/ledger/{ledger_id}/import/preview", json={
        "account_code": "1010",
        "content": "Date,Description,Amount\n05/01/2026,Rent,10\n",
        "format": "csv",
        "mapping": {"date_column": "Date", "description_columns": ["Description"],
                    "amount_column": "Amount"},
    })
    assert response.status_code == 422


def test_subledger_over_http(client):
    http, engine = client
    ledger_id = http.post("/ledger/create", json={"name": "Sales"}).json()["id"]

    party = http.post(f"/ledger/{ledger_id}/parties",
                      json={"name": "Acme", "kind": "CUSTOMER"})
    assert party.status_code == 200, party.text

    tax = http.post(f"/ledger/{ledger_id}/tax-codes", json={
        "code": "VAT-S", "jurisdiction": "GB", "rate": "0.20", "account_code": "2100",
    })
    assert tax.status_code == 200, tax.text

    invoice = http.post(f"/ledger/{ledger_id}/documents", json={
        "kind": "INVOICE", "party_id": party.json()["id"], "issue_date": "2026-01-15",
        "lines": [{"account_code": "4000", "unit_price": "100", "tax_code": "VAT-S"}],
    })
    assert invoice.status_code == 200, invoice.text
    assert invoice.json()["total"] == "120.00000000"

    paid = http.post(f"/ledger/{ledger_id}/documents/{invoice.json()['id']}/pay",
                     json={"date": "2026-01-20", "amount": "120",
                           "bank_account": "1010"})
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "PAID"

    aging = http.get(f"/ledger/{ledger_id}/aging", params={"kind": "AR",
                                                          "as_of": "2026-01-31"})
    assert aging.status_code == 200
    assert aging.json()["reconciled"] is True


def test_an_unknown_party_is_404(client):
    http, _ = client
    ledger_id = http.post("/ledger/create", json={"name": "Sales"}).json()["id"]
    response = http.post(f"/ledger/{ledger_id}/documents", json={
        "kind": "INVOICE", "party_id": "pty_missing", "issue_date": "2026-01-15",
        "lines": [{"account_code": "4000", "unit_price": "10"}],
    })
    assert response.status_code == 404


def test_groups_consolidation_and_export_over_http(client):
    http, engine = client
    parent = http.post("/ledger/create", json={"name": "Parent"}).json()["id"]
    sub = http.post("/ledger/create", json={"name": "Sub"}).json()["id"]

    group = http.post("/ledger/groups", json={"name": "Group", "base_currency": "USD"})
    assert group.status_code == 200, group.text
    group_id = group.json()["id"]
    assert http.post(f"/ledger/groups/{group_id}/members",
                     json={"ledger_id": parent}).status_code == 200
    assert http.post(f"/ledger/groups/{group_id}/members",
                     json={"ledger_id": sub}).status_code == 200

    listing = http.get("/ledger/groups")
    assert listing.status_code == 200
    assert len(listing.json()["groups"][0]["members"]) == 2

    consolidated = http.post(f"/ledger/groups/{group_id}/consolidate",
                             json={"as_of": "2026-01-31"})
    assert consolidated.status_code == 200, consolidated.text
    assert consolidated.json()["status"] == "CONSOLIDATED"

    exported = http.get(f"/ledger/{parent}/export", params={"format": "json"})
    assert exported.status_code == 200, exported.text
    assert exported.json()["contentType"] == "application/json"

    refused = http.get(f"/ledger/{parent}/export", params={"format": "saft"})
    assert refused.status_code == 422

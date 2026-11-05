"""Ledger agent tools: registration, effects, and the handler contract.

The registry rejects dotted names, so the flat `ledger_*` family is the contract.
A tool must (a) be registered exactly once, (b) declare `ledger.write` for every
mutation, and (c) refuse honestly with a structured error rather than raising —
including when the service is not attached to the run.
"""

from __future__ import annotations

import asyncio
from typing import Any

from harness.ledger import tools as ledger_tools
from ledger_helpers import make_service


class _Registry:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def register(self, definition: Any) -> None:
        assert definition.name not in self.tools, f"{definition.name} registered twice"
        self.tools[definition.name] = definition


class _Ctx:
    def __init__(self, service: Any) -> None:
        self.ledger_service = service
        self.user_id = None


def _registered() -> dict[str, Any]:
    registry = _Registry()
    ledger_tools.register_ledger_tools(registry)
    return registry.tools


def _call(name: str, args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    return asyncio.run(_registered()[name].handler(args, ctx))


def test_every_ledger_tool_registers_once_and_names_are_flat():
    tools = _registered()
    assert set(tools) == set(ledger_tools.LEDGER_TOOLS)
    for name in tools:
        assert "." not in name


def test_every_write_tool_declares_the_ledger_effect():
    tools = _registered()
    for name in ledger_tools.LEDGER_WRITE_TOOLS:
        assert tools[name].permission == "write"
        assert tools[name].effect == "ledger.write"
    for name in ledger_tools.LEDGER_READ_TOOLS:
        assert tools[name].permission == "read"
        assert not tools[name].effect


def test_the_tool_round_trip_posts_and_reads(tmp_path):
    ctx = _Ctx(make_service(tmp_path))

    _, payload = _call("ledger_create", {"name": "Tools Ltd", "base_currency": "USD"}, ctx)
    assert payload["status"] == "SUCCESS"
    ledger_id = payload["ledger"]["id"]

    text, payload = _call("ledger_post", {
        "ledger_id": ledger_id,
        "entry_date": "2026-01-10",
        "memo": "Sale",
        "lines": [
            {"account_code": "1100", "debit": "1200"},
            {"account_code": "4000", "credit": "1200"},
        ],
    }, ctx)
    assert payload["status"] == "SUCCESS"
    assert "Posted entry #1" in text

    _, payload = _call("ledger_balance_sheet",
                       {"ledger_id": ledger_id, "as_of": "2026-01-31"}, ctx)
    assert payload["balanced"] is True
    assert payload["assets"]["total"] == "1200.00000000"


def test_an_unbalanced_posting_returns_a_structured_failure(tmp_path):
    ctx = _Ctx(make_service(tmp_path))
    _, created = _call("ledger_create", {"name": "X"}, ctx)
    ledger_id = created["ledger"]["id"]

    text, payload = _call("ledger_post", {
        "ledger_id": ledger_id,
        "entry_date": "2026-01-10",
        "lines": [
            {"account_code": "1010", "debit": "100"},
            {"account_code": "4000", "credit": "10"},
        ],
    }, ctx)
    assert payload["status"] == "FAILED"
    assert payload["error"]["code"] == "UNBALANCED_ENTRY"
    assert "Ledger error (UNBALANCED_ENTRY)" in text


def test_a_missing_service_reports_ledger_unavailable():
    _, payload = _call("ledger_list", {}, _Ctx(None))
    assert payload["status"] == "FAILED"
    assert payload["error"]["code"] == "LEDGER_UNAVAILABLE"


def test_the_inactive_account_tool_round_trips(tmp_path):
    ctx = _Ctx(make_service(tmp_path))
    _, created = _call("ledger_create", {"name": "X"}, ctx)
    ledger_id = created["ledger"]["id"]

    _, payload = _call("ledger_set_account_active",
                       {"ledger_id": ledger_id, "code": "6400", "active": False}, ctx)
    assert payload["active"] is False


def test_the_import_and_reconcile_tools_round_trip(tmp_path):
    ctx = _Ctx(make_service(tmp_path))
    _, created = _call("ledger_create", {"name": "Import Ltd"}, ctx)
    ledger_id = created["ledger"]["id"]

    _, rule = _call("ledger_rule_create", {
        "ledger_id": ledger_id, "name": "Income", "target_account": "4000",
        "payee_contains": ["payroll"],
    }, ctx)
    assert rule["targetAccount"] == "4000"

    content = "Date,Description,Amount\n2026-01-05,ACME PAYROLL,100.00\n"
    mapping = {"date_column": "Date", "description_columns": ["Description"],
               "amount_column": "Amount"}
    _, preview = _call("ledger_import_preview", {
        "ledger_id": ledger_id, "account_code": "1010", "content": content,
        "mapping": mapping,
    }, ctx)
    assert preview["newCount"] == 1
    assert preview["categorisedCount"] == 1
    assert preview["rows"][0]["accountCode"] == "4000"

    _, commit = _call("ledger_import_commit", {
        "ledger_id": ledger_id, "account_code": "1010", "content": content,
        "mapping": mapping,
    }, ctx)
    assert commit["postedCount"] == 1

    _, recon = _call("ledger_reconcile_statement", {
        "ledger_id": ledger_id, "account_code": "1010", "content": content,
        "mapping": mapping, "statement_balance": "100.00",
    }, ctx)
    assert recon["status"] == "RECONCILED"
    assert recon["matchedCount"] == 1


def test_the_subledger_tools_round_trip(tmp_path):
    ctx = _Ctx(make_service(tmp_path))
    _, created = _call("ledger_create", {"name": "Sales Ltd"}, ctx)
    ledger_id = created["ledger"]["id"]

    _, party = _call("ledger_party_create", {
        "ledger_id": ledger_id, "name": "Acme Client", "kind": "CUSTOMER",
    }, ctx)
    assert party["kind"] == "CUSTOMER"

    _, tax = _call("ledger_tax_code_create", {
        "ledger_id": ledger_id, "code": "VAT-S", "jurisdiction": "GB",
        "rate": "0.20", "account_code": "2100",
    }, ctx)
    assert tax["accountCode"] == "2100"

    _, invoice = _call("ledger_document_create", {
        "ledger_id": ledger_id, "kind": "INVOICE", "party_id": party["id"],
        "issue_date": "2026-01-15",
        "lines": [{"account_code": "4000", "quantity": "2", "unit_price": "500",
                   "tax_code": "VAT-S"}],
    }, ctx)
    assert invoice["total"] == "1200.00000000"

    _, paid = _call("ledger_document_pay", {
        "ledger_id": ledger_id, "document_id": invoice["id"],
        "date": "2026-01-20", "amount": "1200", "bank_account": "1010",
    }, ctx)
    assert paid["status"] == "PAID"

    _, report = _call("ledger_aging",
                      {"ledger_id": ledger_id, "kind": "AR", "as_of": "2026-01-31"}, ctx)
    assert report["openTotal"] == "0.00000000"
    assert report["reconciled"] is True


def test_the_group_and_export_tools_round_trip(tmp_path):
    service = make_service(tmp_path)
    ctx = _Ctx(service)
    _, first = _call("ledger_create", {"name": "Parent"}, ctx)
    _, second = _call("ledger_create", {"name": "Sub"}, ctx)
    parent = first["ledger"]["id"]
    sub = second["ledger"]["id"]

    _, group = _call("ledger_group_create", {"name": "Group"}, ctx)
    _call("ledger_group_add_member",
          {"group_id": group["id"], "ledger_id": parent}, ctx)
    _call("ledger_group_add_member",
          {"group_id": group["id"], "ledger_id": sub}, ctx)

    _, listing = _call("ledger_group_list", {}, ctx)
    assert len(listing["groups"][0]["members"]) == 2

    _, consolidated = _call("ledger_consolidate",
                            {"group_id": group["id"], "as_of": "2026-01-31"}, ctx)
    assert consolidated["status"] == "CONSOLIDATED"

    _, exported = _call("ledger_export",
                        {"ledger_id": parent, "format": "trial_balance_csv"}, ctx)
    assert exported["contentType"] == "text/csv"
    assert "Account Code" in exported["content"]

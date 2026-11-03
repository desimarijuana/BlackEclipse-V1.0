"""Statement reconciliation: matched / mismatched / missing / unknown, and the
balance check that makes a "reconciled" claim mean something.
"""

from __future__ import annotations

import pytest

from harness.ledger.errors import LedgerError
from harness.ledger.importers import CsvMapping
from ledger_helpers import line, make_ledger, make_service

CSV = """Date,Description,Amount
2026-01-05,ACME PAYROLL,2500.00
2026-01-06,Office rent,-1200.00
2026-01-07,STARBUCKS,-4.50
"""

MAPPING = CsvMapping(
    date_column="Date",
    description_columns=("Description",),
    amount_column="Amount",
)

CLOSING = "1295.50"


def _imported(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    svc.create_rule(lid, name="Rent", target_account="6100", payee_contains=["rent"])
    svc.create_rule(lid, name="Income", target_account="4000", payee_contains=["payroll"])
    svc.create_rule(lid, name="Coffee", target_account="6600", payee_contains=["starbucks"])
    svc.commit_import(lid, account_code="1010", content=CSV, statement_format="csv",
                      mapping=MAPPING)
    return svc, lid


def _reconcile(svc, lid, content, **kwargs):
    return svc.reconcile_statement(
        lid, account_code="1010", content=content, statement_format="csv",
        mapping=MAPPING, **kwargs,
    )


def test_imported_rows_reconcile_by_external_id(tmp_path):
    svc, lid = _imported(tmp_path)
    before = svc.get_ledger(lid)["summary"]["entryCount"]
    run = _reconcile(svc, lid, CSV, statement_balance=CLOSING)
    assert run["status"] == "RECONCILED"
    assert run["balanceStatus"] == "BALANCED"
    assert run["matchedCount"] == 3
    assert run["mismatchCount"] == 0
    assert run["missingCount"] == 0
    assert {item["method"] for item in run["items"]} == {"EXTERNAL_ID"}
    # A reconciliation is a report: the journal is untouched.
    assert svc.get_ledger(lid)["summary"]["entryCount"] == before


def test_a_manual_entry_matches_by_amount_and_date(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    svc.post(lid, entry_date="2026-01-10", lines=[
        line("1010", debit="500"), line("4000", credit="500"),
    ])
    content = "Date,Description,Amount\n2026-01-12,Client payment,500.00\n"
    run = _reconcile(svc, lid, content, statement_balance="500.00")
    assert run["matchedCount"] == 1
    assert run["items"][0]["method"] == "AMOUNT_DATE"
    assert run["status"] == "RECONCILED"


def test_an_amount_outside_tolerance_is_a_mismatch(tmp_path):
    svc, lid = _imported(tmp_path)
    content = CSV.replace("-1200.00", "-1150.00")
    run = _reconcile(svc, lid, content, statement_balance=CLOSING)
    assert run["mismatchCount"] == 1
    mismatch = next(item for item in run["items"] if item["status"] == "MISMATCH")
    assert mismatch["detail"]["difference"] == "-50.00000000"
    # The balance is off by the same 50, so the run cannot be reconciled.
    assert run["status"] == "UNRECONCILED"


def test_a_row_with_no_counterpart_is_missing(tmp_path):
    svc, lid = _imported(tmp_path)
    content = CSV + "2026-03-01,Ghost charge,-77.00\n"
    run = _reconcile(svc, lid, content, statement_balance="1218.50")
    missing = [item for item in run["items"] if item["status"] == "MISSING"]
    assert len(missing) == 1
    assert missing[0]["description"] == "Ghost charge"
    assert run["missingCount"] == 1


def test_two_identical_candidates_are_unknown_not_a_guess(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    for _ in range(2):
        svc.post(lid, entry_date="2026-01-10", lines=[
            line("1010", debit="500"), line("4000", credit="500"),
        ])
    content = "Date,Description,Amount\n2026-01-10,Client payment,500.00\n"
    run = _reconcile(svc, lid, content, statement_balance="1000.00")
    assert run["unknownCount"] == 1
    assert run["items"][0]["status"] == "UNKNOWN"
    assert len(run["items"][0]["detail"]["candidates"]) == 2


def test_without_a_statement_balance_the_run_is_incomplete(tmp_path):
    svc, lid = _imported(tmp_path)
    run = _reconcile(svc, lid, CSV)
    assert run["status"] == "INCOMPLETE"
    assert run["balanceStatus"] == "UNKNOWN"
    assert run["difference"] is None
    assert run["matchedCount"] == 3


def test_an_unbalanced_declared_balance_is_reported_with_the_difference(tmp_path):
    svc, lid = _imported(tmp_path)
    run = _reconcile(svc, lid, CSV, statement_balance="1200.00")
    assert run["balanceStatus"] == "UNBALANCED"
    assert run["difference"] == "-95.50000000"
    assert run["status"] == "UNRECONCILED"


def test_ledger_entries_not_on_the_statement_are_reported(tmp_path):
    svc, lid = _imported(tmp_path)
    svc.post(lid, entry_date="2026-01-06", lines=[
        line("6100", debit="100"), line("1010", credit="100"),
    ])
    run = _reconcile(svc, lid, CSV, statement_balance=CLOSING)
    assert len(run["unpresented"]) == 1
    assert run["unpresented"][0]["amount"] == "-100.00000000"
    assert run["status"] == "UNRECONCILED"


def test_reconciling_a_non_cash_account_is_refused(tmp_path):
    svc, lid = _imported(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.reconcile_statement(lid, account_code="6100", content=CSV,
                                statement_format="csv", mapping=MAPPING,
                                statement_balance=CLOSING)
    assert info.value.code == "IMPORT_ACCOUNT_INVALID"


def test_a_run_is_persisted_and_readable(tmp_path):
    svc, lid = _imported(tmp_path)
    run = _reconcile(svc, lid, CSV, statement_balance=CLOSING)
    runs = svc.list_reconciliations(lid)
    assert runs[0]["id"] == run["id"]
    full = svc.get_reconciliation(lid, run["id"])
    assert full["status"] == "RECONCILED"
    assert len(full["items"]) == 3
    assert full["closingBalance"] == "1295.50000000"


def test_an_unknown_reconciliation_id_is_a_named_error(tmp_path):
    svc, lid = _imported(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.get_reconciliation(lid, "rec_missing")
    assert info.value.code == "RECONCILIATION_NOT_FOUND"

"""Statements derived from postings, with the accounting equation as a check.

The golden case below is the smallest business that exercises every statement:

  2026-01-01  Dr Bank 10,000      / Cr Share capital 10,000   (financing)
  2026-01-10  Dr Receivable 2,400 / Cr Sales 2,400            (no cash yet)
  2026-01-15  Dr COGS 800         / Cr Inventory 800          (no cash yet)
  2026-01-20  Dr Rent 500         / Cr Bank 500               (operating)

Closing: bank 9,500 · receivable 2,400 · inventory -800 · equity 10,000 +
earnings 1,100 = 11,100 = assets. Cash: +10,000 financing, -500 operating.
"""

from __future__ import annotations

from ledger_helpers import line, make_ledger, make_service, post

DATE = "2026-01-31"


def _golden(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    post(svc, lid, "2026-01-01", [line("1010", debit="10000"), line("3000", credit="10000")])
    post(svc, lid, "2026-01-10", [line("1100", debit="2400"), line("4000", credit="2400")])
    post(svc, lid, "2026-01-15", [line("5000", debit="800"), line("1200", credit="800")])
    post(svc, lid, "2026-01-20", [line("6100", debit="500"), line("1010", credit="500")])
    return svc, lid


def _amount(payload, key):
    return payload[key]


def test_trial_balance_is_balanced_and_totals_are_exact(tmp_path):
    svc, lid = _golden(tmp_path)
    trial = svc.trial_balance(lid, as_of=DATE)
    assert trial["balanced"] is True
    assert trial["totals"]["closingDebit"] == trial["totals"]["closingCredit"]
    assert trial["totals"]["closingDebit"] == "13200.00000000"
    rows = {row["code"]: row for row in trial["rows"]}
    assert rows["1010"]["closingDebit"] == "9500.00000000"
    assert rows["4000"]["closingCredit"] == "2400.00000000"


def test_trial_balance_with_a_start_shows_opening_plus_movement(tmp_path):
    svc, lid = _golden(tmp_path)
    post(svc, lid, "2026-02-05", [line("6100", debit="300"), line("1010", credit="300")])
    trial = svc.trial_balance(lid, as_of="2026-02-28", start="2026-02-01")
    rows = {row["code"]: row for row in trial["rows"]}
    assert rows["6100"]["openingDebit"] == "500.00000000"
    assert rows["6100"]["debit"] == "300.00000000"
    assert rows["6100"]["closingDebit"] == "800.00000000"
    assert trial["balanced"] is True


def test_balance_sheet_satisfies_the_accounting_equation(tmp_path):
    svc, lid = _golden(tmp_path)
    sheet = svc.balance_sheet(lid, as_of=DATE)
    assert sheet["balanced"] is True
    assert sheet["assets"]["total"] == "11100.00000000"
    assert sheet["liabilities"]["total"] == "0.00000000"
    # equity = share capital 10,000 + current earnings 1,100
    assert sheet["equity"]["total"] == "11100.00000000"
    assert sheet["currentEarnings"] == "1100.00000000"
    assert all(check["ok"] for check in sheet["checks"])


def test_income_statement_splits_gross_and_operating(tmp_path):
    svc, lid = _golden(tmp_path)
    pnl = svc.income_statement(lid, start="2026-01-01", end="2026-01-31")
    assert pnl["revenue"]["total"] == "2400.00000000"
    assert pnl["costOfSales"]["total"] == "800.00000000"
    assert pnl["grossProfit"] == "1600.00000000"
    assert pnl["operatingExpenses"]["total"] == "500.00000000"
    assert pnl["netIncome"] == "1100.00000000"
    assert pnl["balanced"] is True


def test_income_statement_is_scoped_to_the_range(tmp_path):
    svc, lid = _golden(tmp_path)
    post(svc, lid, "2026-02-10", [line("4000", credit="700"), line("1100", debit="700")])
    january = svc.income_statement(lid, start="2026-01-01", end="2026-01-31")
    february = svc.income_statement(lid, start="2026-02-01", end="2026-02-28")
    assert january["revenue"]["total"] == "2400.00000000"
    assert february["revenue"]["total"] == "700.00000000"


def test_balance_sheet_earnings_reconcile_to_the_income_statement(tmp_path):
    svc, lid = _golden(tmp_path)
    sheet = svc.balance_sheet(lid, as_of=DATE)
    pnl = svc.income_statement(lid, start="2026-01-01", end=DATE)
    assert sheet["currentEarnings"] == pnl["netIncome"]


def test_cash_flow_classifies_operating_and_financing(tmp_path):
    svc, lid = _golden(tmp_path)
    flow = svc.cash_flow(lid, start="2026-01-01", end=DATE)
    assert flow["financing"] == "10000.00000000"
    assert flow["operating"] == "-500.00000000"
    assert flow["investing"] == "0.00000000"
    assert flow["netChange"] == "9500.00000000"
    assert flow["closingCash"] == "9500.00000000"
    assert flow["complete"] is True
    assert flow["balanced"] is True


def test_cash_flow_reports_an_explicit_unclassified_bucket(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    # A cash account the operator created without a cash-flow category.
    svc.create_account(lid, code="1080", name="Uncategorised bank", account_type="ASSET",
                       is_cash=True)
    svc.create_account(lid, code="2900", name="Odd liability", account_type="LIABILITY")
    post(svc, lid, "2026-01-10", [line("1080", debit="250"), line("2900", credit="250")])
    flow = svc.cash_flow(lid, start="2026-01-01", end=DATE)
    assert flow["unclassified"] == "250.00000000"
    assert flow["complete"] is False
    assert flow["netChange"] == "250.00000000"


def test_an_empty_book_still_produces_coherent_statements(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    sheet = svc.balance_sheet(lid, as_of=DATE)
    assert sheet["balanced"] is True
    assert sheet["assets"]["total"] == "0.00000000"
    pnl = svc.income_statement(lid, start="2026-01-01", end=DATE)
    assert pnl["netIncome"] == "0.00000000"
    flow = svc.cash_flow(lid, start="2026-01-01", end=DATE)
    assert flow["complete"] is True


def test_contra_assets_reduce_the_asset_total(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    post(svc, lid, "2026-01-02", [line("1500", debit="5000"), line("3000", credit="5000")])
    post(svc, lid, "2026-01-03", [line("6900", debit="1000"), line("1510", credit="1000")])
    sheet = svc.balance_sheet(lid, as_of=DATE)
    # 5,000 fixed assets - 1,000 accumulated depreciation = 4,000
    assert sheet["assets"]["total"] == "4000.00000000"
    assert sheet["balanced"] is True


def test_a_reversal_removes_its_effect_from_every_statement(tmp_path):
    svc, lid = _golden(tmp_path)
    entries = svc.list_entries(lid, limit=10)
    rent = next(e for e in entries if e["memo"] == "" and e["entryDate"] == "2026-01-20")
    svc.reverse(lid, rent["id"], entry_date="2026-01-25")

    pnl = svc.income_statement(lid, start="2026-01-01", end=DATE)
    assert pnl["operatingExpenses"]["total"] == "0.00000000"
    assert pnl["netIncome"] == "1600.00000000"
    sheet = svc.balance_sheet(lid, as_of=DATE)
    assert sheet["balanced"] is True
    flow = svc.cash_flow(lid, start="2026-01-01", end=DATE)
    assert flow["operating"] == "0.00000000"
    assert flow["closingCash"] == "10000.00000000"

"""The posting contract: balance, sides, currency, immutability, periods.

Every test here asserts a REFUSAL as often as a success. A ledger whose failure
modes are untested is a ledger that will one day post a wrong number.
"""

from __future__ import annotations

import pytest

from harness.ledger.errors import LedgerError
from ledger_helpers import line, make_ledger, make_service, post


def _codes(exc: LedgerError) -> str:
    return exc.code


# ── Creation ─────────────────────────────────────────────────────────────────


def test_create_installs_a_chart_and_base_currency(tmp_path):
    svc = make_service(tmp_path)
    ledger = svc.create_ledger("Acme Ltd", base_currency="GBP")
    assert ledger["baseCurrency"] == "GBP"
    accounts = svc.list_accounts(ledger["id"])
    assert len(accounts) == ledger["accounts"]
    assert any(a["code"] == "1000" and a["isCash"] for a in accounts)
    assert any(a["code"] == "4000" and a["type"] == "REVENUE" for a in accounts)


def test_unknown_chart_template_is_refused(tmp_path):
    svc = make_service(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.create_ledger("X", chart_template="ifrs17")
    assert info.value.code == "UNSUPPORTED_CHART"


def test_minimal_chart_is_smaller_than_standard(tmp_path):
    svc = make_service(tmp_path)
    minimal = svc.create_ledger("M", chart_template="minimal")
    standard = svc.create_ledger("S", chart_template="standard")
    assert minimal["accounts"] < standard["accounts"]


# ── Balance ──────────────────────────────────────────────────────────────────


def test_a_balanced_entry_posts(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    entry = post(svc, lid, "2026-01-05", [
        line("1010", debit="1500.00"),
        line("3000", credit="1500.00"),
    ], memo="Owner capital")
    assert entry["status"] == "POSTED"
    assert entry["entryNo"] == 1
    assert entry["totalDebit"] == "1500.00000000"
    assert entry["totalCredit"] == "1500.00000000"
    assert entry["duplicate"] is False


def test_an_unbalanced_entry_is_refused_with_the_exact_difference(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-05", [
            line("1010", debit="100.00"),
            line("4000", credit="99.99"),
        ])
    assert info.value.code == "UNBALANCED_ENTRY"
    assert info.value.details["difference"] == "0.01000000"


def test_a_cent_split_across_three_lines_balances_exactly(tmp_path):
    # 100.00 split three ways: 33.33 + 33.33 + 33.34. A float ledger rounds here.
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    post(svc, lid, "2026-01-05", [
        line("6100", debit="33.33"),
        line("6200", debit="33.33"),
        line("6300", debit="33.34"),
        line("1010", credit="100.00"),
    ])
    trial = svc.trial_balance(lid, as_of="2026-01-31")
    assert trial["balanced"] is True


def test_a_negative_amount_is_refused(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-05", [
            line("1010", debit="-100"),
            line("4000", credit="-100"),
        ])
    assert info.value.code == "NEGATIVE_AMOUNT"


def test_a_line_cannot_be_both_a_debit_and_a_credit(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-05", [
            line("1010", debit="100", credit="100"),
            line("4000", credit="100"),
        ])
    assert info.value.code == "DUPLICATE_LINE_SIDE"


def test_an_empty_line_is_refused(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-05", [
            line("1010"),
            line("4000", credit="100"),
        ])
    assert info.value.code == "EMPTY_LINE"


def test_a_single_line_entry_is_refused(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-05", [line("1010", debit="100")])
    assert info.value.code == "INVALID_ENTRY"


def test_an_unknown_account_is_refused(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-05", [
            line("7777", debit="100"),
            line("4000", credit="100"),
        ])
    assert info.value.code == "ACCOUNT_NOT_FOUND"


def test_an_inactive_account_cannot_receive_a_posting(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    svc.set_account_active(lid, "6400", False)
    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-05", [
            line("6400", debit="100"),
            line("1010", credit="100"),
        ])
    assert info.value.code == "ACCOUNT_INACTIVE"


# ── Currency ────────────────────────────────────────────────────────────────


def test_a_foreign_line_without_a_rate_is_refused(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-05", [
            line("1010", debit="100", currency="EUR"),
            line("4000", credit="100"),
        ])
    assert info.value.code == "MISSING_FX"


def test_a_foreign_line_uses_the_supplied_rate(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    entry = post(svc, lid, "2026-01-05", [
        line("1010", debit="100", currency="EUR", fx_rate="1.10"),
        line("4000", credit="110", currency="USD"),
    ])
    assert entry["totalDebit"] == "110.00000000"
    assert entry["lines"][0]["currency"] == "EUR"
    assert entry["lines"][0]["baseDebit"] == "110.00000000"


def test_a_rate_on_a_base_currency_line_is_refused(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-05", [
            line("1010", debit="100", fx_rate="1.1"),
            line("4000", credit="100"),
        ])
    assert info.value.code == "MISSING_FX"


def test_an_account_in_another_currency_cannot_be_posted_in_the_base(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc, currency="USD")
    svc.create_account(lid, code="1050", name="EUR bank", account_type="ASSET",
                       currency="EUR", is_cash=True)
    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-05", [
            line("1050", debit="100", currency="USD"),
            line("4000", credit="100"),
        ])
    assert info.value.code == "CURRENCY_MISMATCH"


# ── Idempotency ─────────────────────────────────────────────────────────────


def test_a_retried_import_does_not_double_post(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    lines = [line("1010", debit="100"), line("4000", credit="100")]
    first = post(svc, lid, "2026-01-05", lines, source="import", external_id="csv-1")
    second = post(svc, lid, "2026-01-05", lines, source="import", external_id="csv-1")
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert first["id"] == second["id"]
    assert svc.get_ledger(lid)["summary"]["entryCount"] == 1


def test_entries_without_an_external_id_are_not_deduplicated(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    lines = [line("1010", debit="100"), line("4000", credit="100")]
    post(svc, lid, "2026-01-05", lines)
    post(svc, lid, "2026-01-05", lines)
    assert svc.get_ledger(lid)["summary"]["entryCount"] == 2


# ── Immutability + reversal ─────────────────────────────────────────────────


def test_a_reversal_nets_the_original_to_zero(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    entry = post(svc, lid, "2026-01-05", [
        line("6100", debit="500"), line("1010", credit="500"),
    ])
    reversal = svc.reverse(lid, entry["id"], entry_date="2026-01-06")
    assert reversal["reversesEntryId"] == entry["id"]
    original = svc.get_entry(lid, entry["id"])
    assert original["status"] == "REVERSED"
    assert original["reversedByEntryId"] == reversal["id"]

    trial = svc.trial_balance(lid, as_of="2026-01-31")
    for row in trial["rows"]:
        assert row["closingDebit"] == "0.00000000"
        assert row["closingCredit"] == "0.00000000"


def test_an_entry_cannot_be_reversed_twice(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    entry = post(svc, lid, "2026-01-05", [
        line("6100", debit="500"), line("1010", credit="500"),
    ])
    svc.reverse(lid, entry["id"])
    with pytest.raises(LedgerError) as info:
        svc.reverse(lid, entry["id"])
    assert info.value.code == "ALREADY_REVERSED"


def test_a_reversal_lands_in_the_period_of_its_own_date(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    entry = post(svc, lid, "2026-01-20", [
        line("6100", debit="500"), line("1010", credit="500"),
    ])
    reversal = svc.reverse(lid, entry["id"], entry_date="2026-02-02")
    assert reversal["entryDate"] == "2026-02-02"
    assert reversal["periodId"] != entry["periodId"]


# ── Periods ─────────────────────────────────────────────────────────────────


def test_posting_creates_the_period_it_lands_in(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    post(svc, lid, "2026-03-15", [line("1010", debit="1"), line("4000", credit="1")])
    periods = svc.list_periods(lid)
    assert len(periods) == 1
    assert periods[0]["startDate"] == "2026-03-01"
    assert periods[0]["endDate"] == "2026-03-31"
    assert periods[0]["status"] == "OPEN"


def test_a_fiscal_year_starting_in_april_maps_months_correctly(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc, month=4)
    post(svc, lid, "2026-03-15", [line("1010", debit="1"), line("4000", credit="1")])
    period = svc.list_periods(lid)[0]
    assert (period["fiscalYear"], period["periodNo"]) == (2025, 12)


def test_a_closed_period_refuses_postings_until_reopened(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    post(svc, lid, "2026-01-10", [line("1010", debit="1"), line("4000", credit="1")])
    period = svc.list_periods(lid)[0]
    svc.close_period(lid, period_id=period["id"])

    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-20", [line("1010", debit="1"), line("4000", credit="1")])
    assert info.value.code == "PERIOD_CLOSED"

    svc.reopen_period(lid, period["id"])
    post(svc, lid, "2026-01-20", [line("1010", debit="1"), line("4000", credit="1")])


def test_a_locked_period_can_never_be_reopened(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    post(svc, lid, "2026-01-10", [line("1010", debit="1"), line("4000", credit="1")])
    period = svc.list_periods(lid)[0]
    svc.close_period(lid, period_id=period["id"])
    svc.lock_period(lid, period["id"])

    with pytest.raises(LedgerError) as info:
        svc.reopen_period(lid, period["id"])
    assert info.value.code == "PERIOD_LOCKED"

    with pytest.raises(LedgerError) as info:
        post(svc, lid, "2026-01-20", [line("1010", debit="1"), line("4000", credit="1")])
    assert info.value.code == "PERIOD_LOCKED"


def test_a_period_with_a_suspense_balance_cannot_close(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    post(svc, lid, "2026-01-10", [line("9999", debit="50"), line("1010", credit="50")])
    period = svc.list_periods(lid)[0]
    with pytest.raises(LedgerError) as info:
        svc.close_period(lid, period_id=period["id"])
    assert info.value.code == "PERIOD_NOT_READY"
    assert info.value.details["findings"][0]["code"] == "SUSPENSE_BALANCE"


def test_an_open_period_cannot_be_locked(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    post(svc, lid, "2026-01-10", [line("1010", debit="1"), line("4000", credit="1")])
    period = svc.list_periods(lid)[0]
    with pytest.raises(LedgerError) as info:
        svc.lock_period(lid, period["id"])
    assert info.value.code == "PERIOD_CLOSED"


# ── Accounts + tenancy ─────────────────────────────────────────────────────


def test_a_duplicate_account_code_is_refused(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        svc.create_account(lid, code="1000", name="Another cash", account_type="ASSET")
    assert info.value.code == "ACCOUNT_EXISTS"


def test_an_account_code_must_be_bounded(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        svc.create_account(lid, code="not a code!", name="Bad", account_type="ASSET")
    assert info.value.code == "INVALID_ACCOUNT"


def test_an_account_type_must_be_in_the_vocabulary(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    with pytest.raises(LedgerError) as info:
        svc.create_account(lid, code="8000", name="Weird", account_type="CASH")
    assert info.value.code == "INVALID_ACCOUNT_TYPE"


def test_a_contra_account_created_by_the_operator_keeps_its_flags(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    account = svc.create_account(lid, code="1520", name="Accumulated amortisation",
                                 account_type="ASSET", is_contra=True,
                                 cash_flow_category="INVESTING")
    assert account["isContra"] is True
    assert account["cashFlowCategory"] == "INVESTING"


def test_an_actor_may_not_read_another_owners_ledger(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc, owner="alice")
    with pytest.raises(LedgerError) as info:
        svc.get_ledger(lid, actor_id="bob")
    assert info.value.code == "LEDGER_FORBIDDEN"
    assert svc.get_ledger(lid, actor_id="alice")["name"] == "Test Books"


def test_the_audit_trail_records_the_posting(tmp_path):
    svc = make_service(tmp_path)
    lid = make_ledger(svc)
    post(svc, lid, "2026-01-05", [line("1010", debit="1"), line("4000", credit="1")],
         actor_id=None)
    kinds = [event["kind"] for event in svc.audit_log(lid)]
    assert "LEDGER_CREATED" in kinds
    assert "ENTRY_POSTED" in kinds

"""The period close and FX revaluation.

The close is a documented checklist with severities: a blocker refuses the close,
a warning does not. Revaluation is a base-currency adjustment at a supplied rate,
idempotent per account+date+rate.
"""

from __future__ import annotations

import pytest

from harness.ledger.errors import LedgerError
from ledger_helpers import line, make_ledger, make_service, post


def _svc(tmp_path):
    svc = make_service(tmp_path)
    return svc, make_ledger(svc)


def _eur_accounts(svc, lid):
    svc.create_account(lid, code="1050", name="EUR bank", account_type="ASSET",
                       currency="EUR", is_cash=True)
    svc.create_account(lid, code="4950", name="FX gain", account_type="REVENUE")
    svc.create_account(lid, code="6950", name="FX loss", account_type="EXPENSE",
                       subtype="OPERATING_EXPENSE")


def _eur_balance(svc, lid):
    post(svc, lid, "2026-01-05", [
        line("1050", debit="1000", currency="EUR", fx_rate="1.10"),
        line("4000", credit="1100"),
    ])


# ── the checklist ──────────────────────────────────────────────────────────


def test_a_clean_period_reports_ready_and_records_the_run(tmp_path):
    svc, lid = _svc(tmp_path)
    post(svc, lid, "2026-01-10", [line("1010", debit="100"), line("4000", credit="100")])
    period = svc.list_periods(lid)[0]
    report = svc.close_report(lid, period_id=period["id"])
    assert report["status"] == "READY"
    assert report["blockerCount"] == 0
    assert report["runId"]

    runs = svc.list_close_runs(lid)
    assert runs[0]["id"] == report["runId"]
    full = svc.get_close_run(lid, report["runId"])
    assert full["detail"]["checks"]
    assert full["startDate"] == "2026-01-01"


def test_a_suspense_balance_is_a_blocker_and_refuses_the_close(tmp_path):
    svc, lid = _svc(tmp_path)
    post(svc, lid, "2026-01-10", [line("9999", debit="50"), line("1010", credit="50")])
    period = svc.list_periods(lid)[0]
    report = svc.close_report(lid, period_id=period["id"])
    assert report["status"] == "BLOCKED"
    assert report["findings"][0]["code"] == "SUSPENSE_BALANCE"

    with pytest.raises(LedgerError) as info:
        svc.close_period(lid, period_id=period["id"])
    assert info.value.code == "PERIOD_NOT_READY"
    assert info.value.details["findings"][0]["code"] == "SUSPENSE_BALANCE"


def test_warnings_do_not_block_a_close(tmp_path):
    svc, lid = _svc(tmp_path)
    post(svc, lid, "2026-01-10", [line("1010", debit="100"), line("4000", credit="100")])
    period = svc.list_periods(lid)[0]
    report = svc.close_report(lid, period_id=period["id"])
    codes = {finding["code"] for finding in report["findings"]}
    assert "RECONCILIATION_NOT_CURRENT" in codes        # cash moved, never reconciled
    assert report["status"] == "READY"
    closed = svc.close_period(lid, period_id=period["id"])
    assert closed["status"] == "CLOSED"
    assert closed["close"]["warningCount"] >= 1


def test_a_negative_cash_balance_is_reported(tmp_path):
    svc, lid = _svc(tmp_path)
    post(svc, lid, "2026-01-10", [line("6500", debit="50"), line("1010", credit="50")])
    period = svc.list_periods(lid)[0]
    report = svc.close_report(lid, period_id=period["id"])
    finding = next(f for f in report["findings"] if f["code"] == "NEGATIVE_CASH")
    assert finding["severity"] == "warning"
    assert finding["accountCode"] == "1010"


def test_a_schedule_still_due_is_a_warning(tmp_path):
    svc, lid = _svc(tmp_path)
    post(svc, lid, "2026-01-10", [line("1010", debit="1"), line("4000", credit="1")])
    svc.create_schedule(lid, name="Van", kind="DEPRECIATION", cost="1200", periods=3,
                        expense_account="6900", contra_account="1510",
                        start_date="2026-01-31")
    period = svc.list_periods(lid)[0]
    report = svc.close_report(lid, period_id=period["id"])
    assert any(f["code"] == "SCHEDULE_DUE" for f in report["findings"])
    assert report["status"] == "READY"


def test_two_entries_with_the_same_memo_are_flagged(tmp_path):
    svc, lid = _svc(tmp_path)
    for _ in range(2):
        post(svc, lid, "2026-01-10", [line("6100", debit="10"), line("1010", credit="10")],
             memo="Office rent")
    period = svc.list_periods(lid)[0]
    report = svc.close_report(lid, period_id=period["id"])
    assert any(f["code"] == "POSSIBLE_DUPLICATE" for f in report["findings"])


def test_an_unknown_close_run_is_a_named_error(tmp_path):
    svc, lid = _svc(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.get_close_run(lid, "cls_missing")
    assert info.value.code == "CLOSE_RUN_NOT_FOUND"


# ── FX revaluation ─────────────────────────────────────────────────────────


def test_a_stronger_foreign_currency_revalues_an_asset_up(tmp_path):
    svc, lid = _svc(tmp_path)
    _eur_accounts(svc, lid)
    _eur_balance(svc, lid)

    preview = svc.preview_revaluation(
        lid, as_of="2026-01-31", rates={"EUR": "1.20"},
        gain_account="4950", loss_account="6950",
    )
    item = next(i for i in preview["items"] if i["accountCode"] == "1050")
    assert item["foreignBalance"] == "1000.00000000"
    assert item["currentBase"] == "1100.00000000"
    assert item["targetBase"] == "1200.00000000"
    assert item["delta"] == "100.00000000"
    assert item["status"] == "REVALUE"

    result = svc.post_revaluation(
        lid, as_of="2026-01-31", rates={"EUR": "1.20"},
        gain_account="4950", loss_account="6950",
    )
    assert result["postedCount"] == 1
    trial = svc.trial_balance(lid, as_of="2026-01-31")
    rows = {row["code"]: row for row in trial["rows"]}
    assert rows["1050"]["closingDebit"] == "1200.00000000"
    assert rows["4950"]["closingCredit"] == "100.00000000"
    assert trial["balanced"] is True


def test_revaluation_is_idempotent_and_a_rate_change_trues_up(tmp_path):
    svc, lid = _svc(tmp_path)
    _eur_accounts(svc, lid)
    _eur_balance(svc, lid)
    args = dict(as_of="2026-01-31", gain_account="4950", loss_account="6950")

    assert svc.post_revaluation(lid, rates={"EUR": "1.20"}, **args)["postedCount"] == 1
    again = svc.post_revaluation(lid, rates={"EUR": "1.20"}, **args)
    # Convergent, not merely idempotent: the book already equals the target, so
    # there is nothing to post (and nothing is posted twice).
    assert again["postedCount"] == 0
    assert next(i for i in again["items"] if i["accountCode"] == "1050")["status"] == "NO_CHANGE"

    moved = svc.post_revaluation(lid, rates={"EUR": "1.25"}, **args)
    assert moved["postedCount"] == 1
    trial = svc.trial_balance(lid, as_of="2026-01-31")
    rows = {row["code"]: row for row in trial["rows"]}
    assert rows["1050"]["closingDebit"] == "1250.00000000"


def test_a_stronger_foreign_currency_revalues_a_liability_into_a_loss(tmp_path):
    svc, lid = _svc(tmp_path)
    _eur_accounts(svc, lid)
    svc.create_account(lid, code="2550", name="EUR loan", account_type="LIABILITY",
                       currency="EUR")
    post(svc, lid, "2026-01-05", [
        line("1050", debit="1000", currency="EUR", fx_rate="1.10"),
        line("2550", credit="1000", currency="EUR", fx_rate="1.10"),
    ])
    result = svc.post_revaluation(
        lid, as_of="2026-01-31", rates={"EUR": "1.20"},
        gain_account="4950", loss_account="6950",
    )
    assert result["postedCount"] == 2
    trial = svc.trial_balance(lid, as_of="2026-01-31")
    rows = {row["code"]: row for row in trial["rows"]}
    assert rows["6950"]["closingDebit"] == "100.00000000"   # the loan costs more
    assert rows["4950"]["closingCredit"] == "100.00000000"  # the bank is worth more
    assert rows["2550"]["closingCredit"] == "1200.00000000"
    assert trial["balanced"] is True


def test_a_missing_rate_is_reported_and_nothing_is_posted(tmp_path):
    svc, lid = _svc(tmp_path)
    _eur_accounts(svc, lid)
    _eur_balance(svc, lid)
    preview = svc.preview_revaluation(
        lid, as_of="2026-01-31", rates={"GBP": "1.30"},
        gain_account="4950", loss_account="6950",
    )
    assert preview["revalueCount"] == 0
    assert preview["rateRequired"] == ["1050"]
    assert preview["items"][0]["status"] == "RATE_REQUIRED"


def test_revaluation_needs_both_counter_accounts(tmp_path):
    svc, lid = _svc(tmp_path)
    _eur_accounts(svc, lid)
    with pytest.raises(LedgerError) as info:
        svc.post_revaluation(lid, as_of="2026-01-31", rates={"EUR": "1.2"},
                             gain_account="4950", loss_account="7777")
    assert info.value.code == "REVALUATION_INVALID"


def test_a_base_currency_account_is_not_a_revaluation_candidate(tmp_path):
    svc, lid = _svc(tmp_path)
    _eur_accounts(svc, lid)
    post(svc, lid, "2026-01-05", [line("1010", debit="100"), line("4000", credit="100")])
    preview = svc.preview_revaluation(
        lid, as_of="2026-01-31", rates={"EUR": "1.20"},
        gain_account="4950", loss_account="6950",
    )
    assert [item["accountCode"] for item in preview["items"]] == ["1050"]

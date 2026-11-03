"""Depreciation, amortisation and accruals — exact schedules, no posting surprises.

The interesting properties are arithmetic: a straight-line schedule must sum to
exactly `cost − salvage`, a declining-balance schedule must never take the book
below salvage, and every period must land on a month end. Posting is exercised
through the normal journal path (so a closed period refuses it), and a re-run must
not repeat a period.
"""

from __future__ import annotations

import pytest

from harness.ledger.errors import LedgerError
from harness.ledger.schedules import build_schedule
from ledger_helpers import line, make_ledger, make_service, post


def _svc(tmp_path):
    svc = make_service(tmp_path)
    return svc, make_ledger(svc)


# ── the maths, without a database ──────────────────────────────────────────


def _schedule(**kwargs):
    defaults = dict(
        ledger_id="l1", name="Asset", kind="DEPRECIATION", cost="100",
        periods=3, expense_account="6900", contra_account="1510",
        start_date="2026-01-15",
    )
    defaults.update(kwargs)
    return build_schedule(**defaults)


def test_straight_line_sums_exactly_to_the_depreciable_base():
    schedule = _schedule(cost="100", periods=3, salvage="0")
    amounts = [entry.amount for entry in schedule.entries]
    assert sum(amounts) == 100
    assert amounts[0] == amounts[1]
    assert amounts[2] >= amounts[0]


def test_straight_line_remainder_goes_to_the_last_period():
    schedule = _schedule(cost="100", periods=3, salvage="0")
    assert [f"{entry.amount:f}" for entry in schedule.entries] == [
        "33.33333333", "33.33333333", "33.33333334",
    ]


def test_entries_land_on_consecutive_month_ends():
    schedule = _schedule(start_date="2026-01-31", periods=3)
    assert [entry.date for entry in schedule.entries] == [
        "2026-01-31", "2026-02-28", "2026-03-31",
    ]


def test_declining_balance_never_goes_below_salvage_and_floors_at_it():
    schedule = _schedule(cost="1000", salvage="990", periods=12, method="DECLINING_BALANCE")
    amounts = [entry.amount for entry in schedule.entries]
    assert sum(amounts) == 10           # exactly the depreciable remainder
    assert amounts[0] == 10
    assert all(amount >= 0 for amount in amounts)


def test_declining_balance_is_front_loaded():
    schedule = _schedule(cost="1200", salvage="0", periods=12, method="DECLINING_BALANCE")
    amounts = [entry.amount for entry in schedule.entries]
    assert amounts[0] > amounts[-1]
    assert sum(amounts) <= 1200


@pytest.mark.parametrize("kwargs,code", [
    ({"cost": "0"}, "SCHEDULE_INVALID"),
    ({"salvage": "100"}, "SCHEDULE_INVALID"),
    ({"periods": 0}, "SCHEDULE_INVALID"),
    ({"periods": 9999}, "SCHEDULE_INVALID"),
    ({"method": "SUM_OF_YEARS"}, "SCHEDULE_INVALID"),
    ({"kind": "LEASE"}, "SCHEDULE_INVALID"),
    ({"expense_account": "6900", "contra_account": "6900"}, "SCHEDULE_INVALID"),
])
def test_invalid_terms_are_refused(kwargs, code):
    with pytest.raises(LedgerError) as info:
        _schedule(**kwargs)
    assert info.value.code == code


# ── posting ────────────────────────────────────────────────────────────────


def test_posting_a_schedule_is_idempotent_and_completes(tmp_path):
    svc, lid = _svc(tmp_path)
    schedule = svc.create_schedule(
        lid, name="Van", kind="DEPRECIATION", cost="1200", periods=3,
        expense_account="6900", contra_account="1510", start_date="2026-01-31",
        salvage="0",
    )
    first = svc.post_schedule(lid, schedule["id"], through="2026-01-31")
    assert first["postedCount"] == 1
    assert first["postedThrough"] == 1

    again = svc.post_schedule(lid, schedule["id"], through="2026-01-31")
    assert again["postedCount"] == 0

    rest = svc.post_schedule(lid, schedule["id"], through="2026-12-31")
    assert rest["postedCount"] == 2
    assert rest["status"] == "COMPLETE"

    trial = svc.trial_balance(lid, as_of="2026-12-31")
    assert trial["balanced"] is True
    rows = {row["code"]: row for row in trial["rows"]}
    assert rows["6900"]["closingDebit"] == "1200.00000000"
    assert rows["1510"]["closingCredit"] == "1200.00000000"


def test_a_schedule_stops_at_the_first_period_that_cannot_post(tmp_path):
    svc, lid = _svc(tmp_path)
    schedule = svc.create_schedule(
        lid, name="Laptop", kind="DEPRECIATION", cost="300", periods=3,
        expense_account="6900", contra_account="1510", start_date="2026-01-31",
    )
    svc.post(lid, entry_date="2026-01-02", lines=[
        line("1010", debit="1"), line("4000", credit="1"),
    ])
    period = svc.list_periods(lid)[0]
    svc.close_period(lid, period_id=period["id"])

    result = svc.post_schedule(lid, schedule["id"], through="2026-03-31")
    assert result["postedCount"] == 0
    assert result["errorCount"] == 1
    assert result["errors"][0]["code"] == "PERIOD_CLOSED"
    assert result["postedThrough"] == 0

    # Reopening lets the schedule continue from the same point.
    svc.reopen_period(lid, period["id"])
    resumed = svc.post_schedule(lid, schedule["id"], through="2026-03-31")
    assert resumed["postedCount"] == 3
    assert resumed["status"] == "COMPLETE"


def test_a_schedule_into_a_missing_account_is_refused_at_creation(tmp_path):
    svc, lid = _svc(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.create_schedule(lid, name="X", kind="DEPRECIATION", cost="10", periods=2,
                            expense_account="6900", contra_account="7777",
                            start_date="2026-01-31")
    assert info.value.code == "ACCOUNT_NOT_FOUND"


# ── accruals ───────────────────────────────────────────────────────────────


def test_an_accrual_and_its_reversal_net_to_zero(tmp_path):
    svc, lid = _svc(tmp_path)
    result = svc.post_accrual(
        lid, entry_date="2026-01-31", amount="250",
        debit_account="6300", credit_account="2200",
        memo="January accountant fee", reversal_date="2026-02-01",
        reference="jan-accountant",
    )
    assert result["postedCount"] == 2

    trial = svc.trial_balance(lid, as_of="2026-02-28")
    assert trial["balanced"] is True
    assert all(row["closingDebit"] == "0.00000000"
               and row["closingCredit"] == "0.00000000" for row in trial["rows"])

    january = svc.income_statement(lid, start="2026-01-01", end="2026-01-31")
    assert january["operatingExpenses"]["total"] == "250.00000000"
    february = svc.income_statement(lid, start="2026-02-01", end="2026-02-28")
    assert february["operatingExpenses"]["total"] == "-250.00000000"


def test_a_reference_makes_the_accrual_pair_idempotent(tmp_path):
    svc, lid = _svc(tmp_path)
    args = dict(entry_date="2026-01-31", amount="250", debit_account="6300",
                credit_account="2200", reversal_date="2026-02-01",
                reference="jan-accrual")
    svc.post_accrual(lid, **args)
    again = svc.post_accrual(lid, **args)
    assert all(entry["duplicate"] for entry in again["entries"])
    assert svc.get_ledger(lid)["summary"]["entryCount"] == 2


def test_a_reversal_must_be_after_the_accrual(tmp_path):
    svc, lid = _svc(tmp_path)
    with pytest.raises(LedgerError) as info:
        svc.post_accrual(lid, entry_date="2026-01-31", amount="10",
                         debit_account="6300", credit_account="2200",
                         reversal_date="2026-01-31")
    assert info.value.code == "SCHEDULE_INVALID"

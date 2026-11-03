"""Depreciation, amortisation and accruals — deterministic schedules.

A schedule is a small, versioned contract: cost, salvage, life, method, the two
accounts, and a start date. From that the engine derives EVERY period's entry in
advance, so the operator can inspect the whole life of the asset before the first
posting.

Exactness rules:

  * Straight line divides the depreciable base and gives the LAST period the
    remainder, so `Σ entries == cost − salvage` exactly — no accumulated cent.
  * Declining balance applies `factor / periods` to the opening book value each
    month and never takes the book below salvage; when the calculated charge would
    overshoot, the remaining depreciable amount is taken and the schedule ends.
  * A period whose charge rounds to zero produces no entry (a zero posting is not
    a posting), but the period is still consumed so it is never "due" forever.

Nothing here posts. `build_entries` returns proposals; the service posts them
through the one journal path, idempotently (`sched:<scheduleId>:<sequence>`).
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Optional, Sequence

from .errors import SCHEDULE_INVALID, LedgerError
from .money import D, ZERO, q_money

KINDS = ("DEPRECIATION", "AMORTISATION")
METHODS = ("STRAIGHT_LINE", "DECLINING_BALANCE")
MAX_PERIODS = 600


def _schedule_id() -> str:
    return f"sch_{uuid.uuid4().hex[:20]}"


@dataclass(frozen=True)
class ScheduleEntry:
    sequence: int
    date: str
    amount: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "date": self.date,
                "amount": f"{q_money(self.amount):f}"}


@dataclass
class Schedule:
    id: str
    ledger_id: str
    kind: str
    name: str
    method: str
    start_date: str
    periods: int
    cost: Decimal
    salvage: Decimal
    expense_account: str
    contra_account: str
    currency: str = "USD"
    factor: Decimal = Decimal("2")
    status: str = "ACTIVE"
    posted_through: int = 0
    created_by: Optional[str] = None
    created_at: str = ""
    entries: list[ScheduleEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ledgerId": self.ledger_id,
            "kind": self.kind,
            "name": self.name,
            "method": self.method,
            "startDate": self.start_date,
            "periods": self.periods,
            "cost": f"{q_money(self.cost):f}",
            "salvage": f"{q_money(self.salvage):f}",
            "expenseAccount": self.expense_account,
            "contraAccount": self.contra_account,
            "currency": self.currency,
            "factor": f"{self.factor:f}",
            "status": self.status,
            "postedThrough": self.posted_through,
            "createdBy": self.created_by,
            "createdAt": self.created_at,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def build_schedule(
    ledger_id: str,
    *,
    name: str,
    kind: str,
    cost: object,
    periods: int,
    expense_account: str,
    contra_account: str,
    start_date: object,
    salvage: object = ZERO,
    method: str = "STRAIGHT_LINE",
    factor: object = "2",
    currency: str = "USD",
    schedule_id: Optional[str] = None,
    created_at: str = "",
) -> Schedule:
    """Validate the terms and derive every period's entry, up front."""
    clean_name = str(name or "").strip()
    if not clean_name:
        raise LedgerError(SCHEDULE_INVALID, "a schedule needs a name", {})
    clean_kind = str(kind or "").strip().upper()
    if clean_kind not in KINDS:
        raise LedgerError(
            SCHEDULE_INVALID,
            f"`kind` must be one of {', '.join(KINDS)}",
            {"kind": str(kind)},
        )
    clean_method = str(method or "STRAIGHT_LINE").strip().upper()
    if clean_method not in METHODS:
        raise LedgerError(
            SCHEDULE_INVALID,
            f"`method` must be one of {', '.join(METHODS)}",
            {"method": str(method)},
        )
    try:
        total_cost = D(cost)
        residual = D(salvage) if salvage not in (None, "") else ZERO
    except (ValueError, TypeError) as exc:
        raise LedgerError(SCHEDULE_INVALID, "`cost`/`salvage` must be decimal literals",
                          {}) from exc
    if total_cost <= ZERO:
        raise LedgerError(SCHEDULE_INVALID, "`cost` must be > 0", {"cost": str(cost)})
    if residual < ZERO:
        raise LedgerError(SCHEDULE_INVALID, "`salvage` must be >= 0", {})
    if residual >= total_cost:
        raise LedgerError(
            SCHEDULE_INVALID,
            "`salvage` must be less than `cost` (otherwise there is nothing to depreciate)",
            {"cost": f"{total_cost:f}", "salvage": f"{residual:f}"},
        )
    try:
        count = int(periods)
    except (TypeError, ValueError) as exc:
        raise LedgerError(SCHEDULE_INVALID, "`periods` must be an integer",
                          {"periods": str(periods)}) from exc
    if not 1 <= count <= MAX_PERIODS:
        raise LedgerError(SCHEDULE_INVALID, f"`periods` must be 1..{MAX_PERIODS}", {})
    for account, field_name in ((expense_account, "expense_account"),
                                (contra_account, "contra_account")):
        if not str(account or "").strip():
            raise LedgerError(SCHEDULE_INVALID, f"`{field_name}` is required", {})
    if str(expense_account).strip() == str(contra_account).strip():
        raise LedgerError(SCHEDULE_INVALID,
                          "`expense_account` and `contra_account` must differ", {})
    try:
        start = date.fromisoformat(str(start_date)[:10])
    except ValueError as exc:
        raise LedgerError(SCHEDULE_INVALID,
                          f"`start_date` must be an ISO date; got {start_date!r}",
                          {"startDate": str(start_date)}) from exc
    try:
        decline = D(factor) if factor not in (None, "") else Decimal("2")
    except (ValueError, TypeError) as exc:
        raise LedgerError(SCHEDULE_INVALID, "`factor` must be a decimal", {}) from exc
    if decline <= ZERO:
        raise LedgerError(SCHEDULE_INVALID, "`factor` must be > 0", {})

    schedule = Schedule(
        id=schedule_id or _schedule_id(),
        ledger_id=ledger_id,
        kind=clean_kind,
        name=clean_name,
        method=clean_method,
        start_date=start.isoformat(),
        periods=count,
        cost=total_cost,
        salvage=residual,
        expense_account=str(expense_account).strip(),
        contra_account=str(contra_account).strip(),
        currency=str(currency or "USD").upper(),
        factor=decline,
        created_at=created_at,
    )
    schedule.entries = _entries_for(schedule)
    return schedule


def _entries_for(schedule: Schedule) -> list[ScheduleEntry]:
    if schedule.method == "STRAIGHT_LINE":
        amounts = _straight_line(schedule.cost - schedule.salvage, schedule.periods)
    else:
        amounts = _declining(schedule.cost, schedule.salvage, schedule.periods,
                             schedule.factor)
    start = date.fromisoformat(schedule.start_date)
    out: list[ScheduleEntry] = []
    for index, amount in enumerate(amounts, start=1):
        year, month = _add_months(start.year, start.month, index - 1)
        out.append(ScheduleEntry(sequence=index, date=month_end(year, month).isoformat(),
                                 amount=amount))
    return out


def _straight_line(base: Decimal, periods: int) -> list[Decimal]:
    if base <= ZERO:
        return [ZERO] * periods
    per = q_money(base / Decimal(periods))
    amounts = [per] * (periods - 1)
    amounts.append(q_money(base - per * Decimal(periods - 1)))
    return amounts


def _declining(cost: Decimal, salvage: Decimal, periods: int,
               factor: Decimal) -> list[Decimal]:
    rate = factor / Decimal(periods)
    book = cost
    amounts: list[Decimal] = []
    for _ in range(periods):
        remaining = book - salvage
        if remaining <= ZERO:
            amounts.append(ZERO)
            continue
        charge = q_money(book * rate)
        if charge <= ZERO or charge >= remaining:
            charge = q_money(remaining)
        amounts.append(charge)
        book = book - charge
    return amounts


def accrual_entries(
    *,
    entry_date: str,
    amount: object,
    debit_account: str,
    credit_account: str,
    memo: str = "",
    reversal_date: Optional[str] = None,
    reference: Optional[str] = None,
) -> list[dict[str, Any]]:
    """A month-end accrual, optionally paired with its automatic reversal.

    Both legs are returned as ordinary postings; the caller decides whether to
    post them. `reference` makes the pair idempotent across a retried run.
    """
    try:
        value = q_money(D(amount))
    except (ValueError, TypeError) as exc:
        raise LedgerError(SCHEDULE_INVALID, "`amount` must be a decimal literal",
                          {"amount": str(amount)}) from exc
    if value <= ZERO:
        raise LedgerError(SCHEDULE_INVALID, "`amount` must be > 0", {"amount": str(amount)})
    for account, field_name in ((debit_account, "debit_account"),
                                (credit_account, "credit_account")):
        if not str(account or "").strip():
            raise LedgerError(SCHEDULE_INVALID, f"`{field_name}` is required", {})
    if str(debit_account).strip() == str(credit_account).strip():
        raise LedgerError(SCHEDULE_INVALID,
                          "`debit_account` and `credit_account` must differ", {})
    try:
        main_date = date.fromisoformat(str(entry_date)[:10]).isoformat()
    except ValueError as exc:
        raise LedgerError(SCHEDULE_INVALID, "`entry_date` must be an ISO date",
                          {"entryDate": str(entry_date)}) from exc
    main = {
        "entry_date": main_date,
        "memo": str(memo or "Accrual")[:1000],
        "source": "adjustment",
        "external_id": f"accrual:{reference}:main" if reference else None,
        "lines": [
            {"account_code": str(debit_account).strip(), "debit": f"{value:f}"},
            {"account_code": str(credit_account).strip(), "credit": f"{value:f}"},
        ],
    }
    if reversal_date in (None, ""):
        return [main]
    try:
        reverse_date = date.fromisoformat(str(reversal_date)[:10]).isoformat()
    except ValueError as exc:
        raise LedgerError(SCHEDULE_INVALID, "`reversal_date` must be an ISO date",
                          {"reversalDate": str(reversal_date)}) from exc
    if reverse_date <= main_date:
        raise LedgerError(SCHEDULE_INVALID,
                          "`reversal_date` must be after `entry_date`",
                          {"entryDate": main_date, "reversalDate": reverse_date})
    return [
        main,
        {
            "entry_date": reverse_date,
            "memo": f"Reversal of accrual ({main['memo']})"[:1000],
            "source": "adjustment",
            "external_id": f"accrual:{reference}:reverse" if reference else None,
            "lines": [
                {"account_code": str(credit_account).strip(), "debit": f"{value:f}"},
                {"account_code": str(debit_account).strip(), "credit": f"{value:f}"},
            ],
        },
    ]


def due_entries(schedule: Schedule, through: str) -> list[ScheduleEntry]:
    """Entries after the posted mark whose period end is on/before `through`."""
    return [
        entry for entry in schedule.entries
        if entry.sequence > schedule.posted_through and entry.date <= through
    ]


def schedule_lines(schedule: Schedule, entry: ScheduleEntry) -> list[dict[str, str]]:
    """Dr expense / Cr accumulated depreciation (or prepaid) for one period."""
    amount = f"{entry.amount:f}"
    return [
        {"account_code": schedule.expense_account, "debit": amount},
        {"account_code": schedule.contra_account, "credit": amount},
    ]


__all__ = [
    "KINDS",
    "MAX_PERIODS",
    "METHODS",
    "Schedule",
    "ScheduleEntry",
    "accrual_entries",
    "build_schedule",
    "due_entries",
    "month_end",
    "schedule_lines",
]

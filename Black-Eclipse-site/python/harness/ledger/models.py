"""Typed contracts for the General Ledger.

The book is a **double-entry ledger**: every posting is a balanced set of lines,
each line touching exactly one account on exactly one side (debit or credit).
Amounts are `Decimal`, quantized to money places at the input boundary and never
mid-computation. There is no binary float anywhere in a balance.

Immutability: a `JournalEntry` is written once. A correction is a *new* entry
that reverses the old one (`reverses_entry_id` ↔ `reversed_by_entry_id`), so the
history of the book is append-only and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from .money import ZERO

# ── Closed vocabularies ───────────────────────────────────────────────────────

#: The five account types. `normal_balance` is derived from this, never guessed.
ACCOUNT_TYPES = ("ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE")

DEBIT_TYPES = frozenset({"ASSET", "EXPENSE"})
CREDIT_TYPES = frozenset({"LIABILITY", "EQUITY", "REVENUE"})

DEBIT = "DEBIT"
CREDIT = "CREDIT"

#: Cash-flow classification of a balance-sheet account. A movement in a cash
#: account is attributed to the category of the COUNTER line's account. An
#: unclassified counter line is reported in an explicit bucket, never guessed.
CASH_FLOW_CATEGORIES = ("OPERATING", "INVESTING", "FINANCING", "UNCLASSIFIED")

PERIOD_STATUSES = ("OPEN", "CLOSED", "LOCKED")
ENTRY_STATUSES = ("POSTED", "REVERSED")


def normal_balance(account_type: str) -> str:
    """The side on which an account of this type increases."""
    return DEBIT if account_type in DEBIT_TYPES else CREDIT


def validate_account_type(account_type: str) -> str:
    upper = str(account_type or "").strip().upper()
    if upper not in ACCOUNT_TYPES:
        from .errors import INVALID_ACCOUNT_TYPE, LedgerError

        raise LedgerError(
            INVALID_ACCOUNT_TYPE,
            f"account type must be one of {', '.join(ACCOUNT_TYPES)}; got {account_type!r}",
            {"allowed": list(ACCOUNT_TYPES)},
        )
    return upper


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AccountTemplate:
    """One line of a bundled chart of accounts (data, not a code branch)."""

    code: str
    name: str
    type: str
    subtype: str = ""
    cash_flow_category: str = ""
    is_cash: bool = False
    is_contra: bool = False


@dataclass
class Account:
    id: str
    ledger_id: str
    code: str
    name: str
    type: str
    subtype: str = ""
    normal_balance: str = DEBIT
    parent_code: Optional[str] = None
    currency: str = ""
    cash_flow_category: str = ""
    is_cash: bool = False
    is_contra: bool = False
    active: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ledgerId": self.ledger_id,
            "code": self.code,
            "name": self.name,
            "type": self.type,
            "subtype": self.subtype,
            "normalBalance": self.normal_balance,
            "parentCode": self.parent_code,
            "currency": self.currency,
            "cashFlowCategory": self.cash_flow_category,
            "isCash": self.is_cash,
            "isContra": self.is_contra,
            "active": self.active,
            "createdAt": self.created_at,
        }


@dataclass(frozen=True)
class LineSpec:
    """A line as supplied by a caller, before validation."""

    account_code: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    currency: str = ""
    fx_rate: Optional[Decimal] = None
    memo: Optional[str] = None
    dimensions: dict[str, str] = field(default_factory=dict)
    #: The amount is ALREADY in the ledger's base currency and adjusts the
    #: carrying value without touching the account's transaction-currency
    #: balance. Only period-end revaluation uses this; it is the one sanctioned
    #: way to write to a foreign-currency account in the base currency.
    base_only: bool = False


@dataclass
class JournalLine:
    """A validated, persisted line with both transaction and base amounts."""

    id: str
    entry_id: str
    line_no: int
    account_code: str
    account_id: str
    debit: Decimal
    credit: Decimal
    base_debit: Decimal
    base_credit: Decimal
    currency: str = ""
    fx_rate: Optional[Decimal] = None
    memo: Optional[str] = None
    dimensions: dict[str, str] = field(default_factory=dict)
    base_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "lineNo": self.line_no,
            "accountCode": self.account_code,
            "accountId": self.account_id,
            "debit": money(self.debit),
            "credit": money(self.credit),
            "baseDebit": money(self.base_debit),
            "baseCredit": money(self.base_credit),
            "currency": self.currency,
            "fxRate": None if self.fx_rate is None else format(self.fx_rate, "f"),
            "memo": self.memo,
            "dimensions": dict(self.dimensions or {}),
            "baseOnly": self.base_only,
        }


@dataclass
class JournalEntry:
    id: str
    ledger_id: str
    entry_no: int
    entry_date: str
    period_id: str
    memo: str = ""
    source: str = "manual"
    external_id: Optional[str] = None
    status: str = "POSTED"
    reverses_entry_id: Optional[str] = None
    reversed_by_entry_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str = ""
    lines: list[JournalLine] = field(default_factory=list)

    def to_dict(self, *, include_lines: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "ledgerId": self.ledger_id,
            "entryNo": self.entry_no,
            "entryDate": self.entry_date,
            "periodId": self.period_id,
            "memo": self.memo,
            "source": self.source,
            "externalId": self.external_id,
            "status": self.status,
            "reversesEntryId": self.reverses_entry_id,
            "reversedByEntryId": self.reversed_by_entry_id,
            "createdBy": self.created_by,
            "createdAt": self.created_at,
            "totalDebit": money(sum((line.base_debit for line in self.lines), ZERO)),
            "totalCredit": money(sum((line.base_credit for line in self.lines), ZERO)),
            "lineCount": len(self.lines),
        }
        if include_lines:
            payload["lines"] = [line.to_dict() for line in self.lines]
        return payload


@dataclass
class Period:
    id: str
    ledger_id: str
    fiscal_year: int
    period_no: int
    start_date: str
    end_date: str
    status: str = "OPEN"
    closed_at: Optional[str] = None
    closed_by: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ledgerId": self.ledger_id,
            "fiscalYear": self.fiscal_year,
            "periodNo": self.period_no,
            "startDate": self.start_date,
            "endDate": self.end_date,
            "status": self.status,
            "closedAt": self.closed_at,
            "closedBy": self.closed_by,
        }


@dataclass
class Ledger:
    id: str
    name: str
    base_currency: str = "USD"
    owner_id: Optional[str] = None
    fiscal_year_start_month: int = 1
    chart_template: str = "standard"
    status: str = "ACTIVE"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "baseCurrency": self.base_currency,
            "ownerId": self.owner_id,
            "fiscalYearStartMonth": self.fiscal_year_start_month,
            "chartTemplate": self.chart_template,
            "status": self.status,
            "metadata": dict(self.metadata or {}),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


def money(value: Decimal) -> str:
    """Exact decimal string for transport (never scientific notation)."""
    from .money import money_str

    return money_str(value) or "0.00000000"


__all__ = [
    "ACCOUNT_TYPES",
    "CASH_FLOW_CATEGORIES",
    "CREDIT",
    "CREDIT_TYPES",
    "DEBIT",
    "DEBIT_TYPES",
    "ENTRY_STATUSES",
    "PERIOD_STATUSES",
    "Account",
    "AccountTemplate",
    "JournalEntry",
    "JournalLine",
    "Ledger",
    "LineSpec",
    "Period",
    "money",
    "normal_balance",
    "validate_account_type",
]

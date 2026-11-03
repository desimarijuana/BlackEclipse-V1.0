"""Chart of accounts: bundled templates (data) + account construction rules.

A chart of accounts is DATA. Templates ship as tuples so a new template is a new
entry, never an `if template == ...` branch. The account TYPE is the only thing
that decides a normal balance, and that rule lives in one place
(`models.normal_balance`).

Design choices worth knowing:
  * Codes are free-form-but-bounded text (`^[0-9A-Za-z][0-9A-Za-z.\\-]{0,15}$`),
    because real charts use `1000`, `1000.01` and `1000-01` interchangeably.
  * `cash_flow_category` is only meaningful for balance-sheet accounts. A
    revenue/expense account is always OPERATING by construction; the statement
    engine never needs to ask.
  * `is_cash` marks the accounts the cash-flow statement treats as cash. Nothing
    is inferred from a name.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

from .errors import ACCOUNT_EXISTS, INVALID_ACCOUNT, UNSUPPORTED_CHART, LedgerError
from .models import (
    Account,
    AccountTemplate,
    validate_account_type,
    normal_balance,
)

_CODE_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.\-]{0,15}$")

#: Bundled charts. Adding one is adding a key here — no code path changes.
CHARTS: dict[str, tuple[AccountTemplate, ...]] = {
    # A general trading/services business. Deliberately conservative: every
    # account is one a bookkeeper would recognise, and no jurisdiction-specific
    # tax account is invented (VAT/GST is a single control account the operator
    # files against; the rate rules live outside this engine).
    "standard": (
        AccountTemplate("1000", "Cash", "ASSET", "CURRENT_ASSET", "", True),
        AccountTemplate("1010", "Bank", "ASSET", "CURRENT_ASSET", "", True),
        AccountTemplate("1020", "Petty cash", "ASSET", "CURRENT_ASSET", "", True),
        AccountTemplate("1100", "Accounts receivable", "ASSET", "RECEIVABLE", "OPERATING"),
        AccountTemplate("1200", "Inventory", "ASSET", "INVENTORY", "OPERATING"),
        AccountTemplate("1300", "Prepaid expenses", "ASSET", "PREPAID", "OPERATING"),
        AccountTemplate("1500", "Fixed assets", "ASSET", "FIXED_ASSET", "INVESTING"),
        AccountTemplate("1510", "Accumulated depreciation", "ASSET", "FIXED_ASSET",
                         "INVESTING", False, True),
        # Intercompany balances: a group consolidation eliminates these pairs, so
        # they carry a SUBTYPE rather than a name convention.
        AccountTemplate("1800", "Intercompany receivable", "ASSET",
                         "INTERCOMPANY_RECEIVABLE", "OPERATING"),
        AccountTemplate("2000", "Accounts payable", "LIABILITY", "PAYABLE", "OPERATING"),
        AccountTemplate("2100", "Sales tax payable", "LIABILITY", "TAX", "OPERATING"),
        AccountTemplate("2200", "Accrued liabilities", "LIABILITY", "ACCRUAL", "OPERATING"),
        AccountTemplate("2300", "Payroll liabilities", "LIABILITY", "PAYROLL", "OPERATING"),
        AccountTemplate("2500", "Long-term debt", "LIABILITY", "LONG_TERM_LIABILITY",
                         "FINANCING"),
        AccountTemplate("2800", "Intercompany payable", "LIABILITY",
                         "INTERCOMPANY_PAYABLE", "OPERATING"),
        AccountTemplate("3000", "Share capital", "EQUITY", "CAPITAL", "FINANCING"),
        AccountTemplate("3100", "Retained earnings", "EQUITY", "RETAINED", "FINANCING"),
        AccountTemplate("3200", "Owner's drawings", "EQUITY", "DRAWINGS", "FINANCING",
                         False, True),
        AccountTemplate("4000", "Sales revenue", "REVENUE", "REVENUE"),
        AccountTemplate("4800", "Intercompany revenue", "REVENUE",
                         "INTERCOMPANY_REVENUE"),
        AccountTemplate("4900", "Other income", "REVENUE", "OTHER_INCOME"),
        AccountTemplate("5000", "Cost of goods sold", "EXPENSE", "COGS"),
        AccountTemplate("6000", "Payroll expense", "EXPENSE", "PAYROLL"),
        AccountTemplate("6100", "Rent", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6200", "Utilities", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6300", "Professional fees", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6400", "Advertising", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6500", "Bank fees", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6600", "Software and subscriptions", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6800", "Intercompany expense", "EXPENSE",
                         "INTERCOMPANY_EXPENSE"),
        AccountTemplate("6900", "Depreciation expense", "EXPENSE", "DEPRECIATION"),
        # The one place an import can park a line it could not classify. It is a
        # real account so the trial balance still balances; a non-zero suspense
        # balance is reported as a close blocker, never hidden.
        AccountTemplate("9999", "Suspense", "ASSET", "SUSPENSE", "OPERATING"),
    ),
    # A single-owner service business: no inventory, no COGS, owner's drawings.
    "sole_trader": (
        AccountTemplate("1000", "Cash", "ASSET", "CURRENT_ASSET", "", True),
        AccountTemplate("1010", "Bank", "ASSET", "CURRENT_ASSET", "", True),
        AccountTemplate("1100", "Accounts receivable", "ASSET", "RECEIVABLE", "OPERATING"),
        AccountTemplate("1500", "Equipment", "ASSET", "FIXED_ASSET", "INVESTING"),
        AccountTemplate("1510", "Accumulated depreciation", "ASSET", "FIXED_ASSET",
                         "INVESTING", False, True),
        AccountTemplate("2000", "Accounts payable", "LIABILITY", "PAYABLE", "OPERATING"),
        AccountTemplate("2100", "Sales tax payable", "LIABILITY", "TAX", "OPERATING"),
        AccountTemplate("3000", "Owner's capital", "EQUITY", "CAPITAL", "FINANCING"),
        AccountTemplate("3100", "Retained earnings", "EQUITY", "RETAINED", "FINANCING"),
        AccountTemplate("3200", "Owner's drawings", "EQUITY", "DRAWINGS", "FINANCING",
                         False, True),
        AccountTemplate("4000", "Service revenue", "REVENUE", "REVENUE"),
        AccountTemplate("4900", "Other income", "REVENUE", "OTHER_INCOME"),
        AccountTemplate("6000", "Contractor costs", "EXPENSE", "COGS"),
        AccountTemplate("6100", "Rent", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6200", "Utilities", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6300", "Professional fees", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6400", "Marketing", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6500", "Bank fees", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("6900", "Depreciation expense", "EXPENSE", "DEPRECIATION"),
        AccountTemplate("9999", "Suspense", "ASSET", "SUSPENSE", "OPERATING"),
    ),
    # The minimal book: enough to post and produce the three statements.
    "minimal": (
        AccountTemplate("1000", "Cash", "ASSET", "CURRENT_ASSET", "", True),
        AccountTemplate("1100", "Accounts receivable", "ASSET", "RECEIVABLE", "OPERATING"),
        AccountTemplate("2000", "Accounts payable", "LIABILITY", "PAYABLE", "OPERATING"),
        AccountTemplate("3000", "Equity", "EQUITY", "CAPITAL", "FINANCING"),
        AccountTemplate("4000", "Revenue", "REVENUE", "REVENUE"),
        AccountTemplate("5000", "Cost of sales", "EXPENSE", "COGS"),
        AccountTemplate("6000", "Operating expenses", "EXPENSE", "OPERATING_EXPENSE"),
        AccountTemplate("9999", "Suspense", "ASSET", "SUSPENSE", "OPERATING"),
    ),
}


def chart_templates() -> list[str]:
    return sorted(CHARTS)


def template_accounts(template: str) -> tuple[AccountTemplate, ...]:
    key = str(template or "standard").strip().lower()
    if key not in CHARTS:
        raise LedgerError(
            UNSUPPORTED_CHART,
            f"unknown chart template {template!r}; available: {', '.join(chart_templates())}",
            {"available": chart_templates()},
        )
    return CHARTS[key]


def validate_code(code: str) -> str:
    text = str(code or "").strip()
    if not _CODE_RE.match(text):
        raise LedgerError(
            INVALID_ACCOUNT,
            f"account code {code!r} must be 1-16 characters of letters, digits, '.', or '-' "
            "and start with a letter or digit",
            {"code": code},
        )
    return text


def build_account(
    ledger_id: str,
    *,
    account_id: str,
    code: str,
    name: str,
    account_type: str,
    subtype: str = "",
    parent_code: str | None = None,
    currency: str = "",
    cash_flow_category: str = "",
    is_cash: bool = False,
    is_contra: bool = False,
    created_at: str = "",
) -> Account:
    """Construct and validate one account. Never mutates an existing one."""
    clean_code = validate_code(code)
    clean_name = str(name or "").strip()
    if not clean_name:
        raise LedgerError(INVALID_ACCOUNT, "an account needs a name", {"code": clean_code})
    kind = validate_account_type(account_type)
    category = str(cash_flow_category or "").strip().upper()
    if kind in ("REVENUE", "EXPENSE"):
        # Income-statement accounts are operating by definition; a caller that
        # says otherwise is mistaken, not authoritative.
        category = "OPERATING"
    elif category and category not in ("OPERATING", "INVESTING", "FINANCING", "UNCLASSIFIED"):
        raise LedgerError(
            INVALID_ACCOUNT,
            f"cash flow category must be OPERATING, INVESTING, FINANCING or UNCLASSIFIED; "
            f"got {cash_flow_category!r}",
            {"code": clean_code},
        )
    return Account(
        id=account_id,
        ledger_id=ledger_id,
        code=clean_code,
        name=clean_name,
        type=kind,
        subtype=str(subtype or "").strip().upper(),
        normal_balance=normal_balance(kind),
        parent_code=(str(parent_code).strip() or None) if parent_code else None,
        currency=str(currency or "").strip().upper(),
        cash_flow_category=category,
        is_cash=bool(is_cash),
        is_contra=bool(is_contra),
        active=True,
        created_at=created_at,
    )


def accounts_from_template(
    template: str,
    *,
    ledger_id: str,
    id_factory,
    created_at: str = "",
) -> Sequence[Account]:
    """Materialise a bundled chart into concrete accounts (ids are injected).

    Template accounts carry NO currency restriction: a standard account accepts a
    posting in any currency and the amount is translated to the ledger's base
    currency through the line's `fx_rate`. An account that must be restricted to
    one currency (a EUR bank account, say) is created explicitly with
    `currency='EUR'`.
    """
    out: list[Account] = []
    for row in template_accounts(template):
        out.append(
            build_account(
                ledger_id,
                account_id=id_factory(),
                code=row.code,
                name=row.name,
                account_type=row.type,
                subtype=row.subtype,
                cash_flow_category=row.cash_flow_category,
                is_cash=row.is_cash,
                is_contra=row.is_contra,
                created_at=created_at,
            )
        )
    return out


def index_by_code(accounts: Iterable[Account]) -> dict[str, Account]:
    return {account.code: account for account in accounts}


def ensure_unique_codes(accounts: Iterable[Account]) -> None:
    seen: dict[str, str] = {}
    for account in accounts:
        if account.code in seen:
            raise LedgerError(
                ACCOUNT_EXISTS,
                f"duplicate account code {account.code!r}",
                {"code": account.code},
            )
        seen[account.code] = account.id


__all__ = [
    "CHARTS",
    "build_account",
    "accounts_from_template",
    "chart_templates",
    "ensure_unique_codes",
    "index_by_code",
    "template_accounts",
    "validate_code",
]

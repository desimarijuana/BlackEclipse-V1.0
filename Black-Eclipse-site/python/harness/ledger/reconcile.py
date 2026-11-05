"""Statement reconciliation — statement rows against the ledger, honestly.

The vocabulary is the Portfolio engine's, on purpose: MATCHED / MISMATCH /
MISSING / UNKNOWN. A reconciliation is a *report*, not a mutation: nothing here
touches the journal, and a run is persisted so the conclusion can be re-read.

Matching is deterministic and layered:

  1. **EXTERNAL_ID** — the ledger entry was posted from this exact statement row
     (its `external_id` is derived from the row's stable identity). Matched when
     the amount agrees within tolerance; MISMATCH when it does not.
  2. **AMOUNT_DATE** — one ledger entry on this account whose amount is within
     tolerance and whose date is within the window. Exactly one candidate is a
     match; more than one is UNKNOWN (never "pick the first").
  3. **MISMATCH** — a candidate exists in the window but the amounts disagree;
     the difference is reported.
  4. **MISSING** — nothing in the ledger resembles the row.

A row that is only in the ledger (an unpresented cheque, a bank charge not yet on
the statement) is reported as `inLedgerNotOnStatement`; that is information, not
a failure.

The balance check needs the statement's closing balance. Without it the run is
`INCOMPLETE` and says why — it never reports RECONCILED on rows alone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from .errors import (
    IMPORT_ACCOUNT_INVALID,
    RECONCILIATION_INVALID,
    RECONCILIATION_NOT_FOUND,
    LedgerError,
)
from .importers import CsvMapping, parse_statement
from .money import D, ZERO, q_money, q_rate

MATCH_WINDOW_DAYS = 5
TOLERANCE = Decimal("0.01")


def _run_id() -> str:
    return f"rec_{uuid.uuid4().hex[:20]}"


def _item_id() -> str:
    return f"rei_{uuid.uuid4().hex[:20]}"


@dataclass
class LedgerLine:
    entry_id: str
    entry_date: str
    amount: Decimal          # debit - credit: positive means money IN
    memo: str
    external_id: Optional[str]


def _ledger_lines(service: Any, ledger_id: str, account_code: str,
                  start: Optional[str], end: Optional[str],
                  window_days: int) -> list[LedgerLine]:
    lower = None
    if start:
        lower = (date.fromisoformat(start) - timedelta(days=window_days)).isoformat()
    upper = None
    if end:
        upper = (date.fromisoformat(end) + timedelta(days=window_days)).isoformat()
    postings = service.store.postings(ledger_id, start=lower, end=upper,
                                      account_code=account_code)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in postings:
        grouped.setdefault(row["entryId"], []).append(row)
    lines: list[LedgerLine] = []
    for entry_id, rows in grouped.items():
        # Signed from the ACCOUNT's point of view: for an asset cash account a
        # debit is money IN and a credit is money OUT — the statement's own sign.
        amount = sum(((row["baseDebit"] or ZERO) - (row["baseCredit"] or ZERO)
                      for row in rows), ZERO)
        first = rows[0]
        memo = str(first.get("memo") or "")
        external_id = first.get("externalId")
        lines.append(LedgerLine(
            entry_id=entry_id,
            entry_date=first["entryDate"],
            amount=amount,
            memo=memo,
            external_id=external_id,
        ))
    lines.sort(key=lambda line: (line.entry_date, line.entry_id))
    return lines


def run(
    service: Any,
    ledger_id: str,
    *,
    account_code: str,
    content: str,
    statement_format: str = "csv",
    mapping: Optional[CsvMapping] = None,
    start: object = None,
    end: object = None,
    tolerance: object = TOLERANCE,
    window_days: int = MATCH_WINDOW_DAYS,
    statement_balance: object = None,
    fx_rate: object = None,
    actor_id: Optional[str] = None,
) -> dict[str, Any]:
    ledger = service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    accounts = {account.code: account for account in service.store.list_accounts(ledger_id)}
    account = accounts.get(str(account_code or "").strip())
    if account is None or not account.is_cash:
        raise LedgerError(
            IMPORT_ACCOUNT_INVALID,
            f"{account_code!r} is not a cash account in this ledger; reconcile a bank/cash "
            "account",
            {"accountCode": account_code},
        )
    try:
        tol = D(tolerance) if tolerance not in (None, "") else TOLERANCE
    except (ValueError, TypeError) as exc:
        raise LedgerError(RECONCILIATION_INVALID, "`tolerance` is not a decimal",
                          {"tolerance": str(tolerance)}) from exc
    if tol < ZERO:
        raise LedgerError(RECONCILIATION_INVALID, "`tolerance` must be >= 0", {})
    window = max(0, min(int(window_days or 0), 60))

    parsed = parse_statement(
        content, statement_format, mapping=mapping,
        account_ref=f"{ledger_id}:{account.code}",
        default_currency=ledger.base_currency,
    )
    rate: Optional[Decimal] = None
    if fx_rate not in (None, ""):
        try:
            rate = q_rate(D(fx_rate))
        except (ValueError, TypeError) as exc:
            raise LedgerError(RECONCILIATION_INVALID, "`fx_rate` is not a decimal",
                              {"fxRate": str(fx_rate)}) from exc
        if rate <= ZERO:
            raise LedgerError(RECONCILIATION_INVALID, "`fx_rate` must be > 0", {})
    base = ledger.base_currency.upper()
    foreign = [row for row in parsed.rows if row.currency.upper() != base]
    if foreign and rate is None:
        raise LedgerError(
            RECONCILIATION_INVALID,
            f"the statement is in {foreign[0].currency} but the ledger is in {base}; "
            "supply `fx_rate` so amounts are comparable",
            {"statementCurrency": foreign[0].currency, "baseCurrency": base},
        )
    if rate is not None:
        parsed.rows = [
            row if row.currency.upper() == base
            else replace(row, amount=q_money(row.amount * rate))
            for row in parsed.rows
        ]
    start_iso = str(start)[:10] if start else min(row.date for row in parsed.rows)
    end_iso = str(end)[:10] if end else max(row.date for row in parsed.rows)
    if start_iso > end_iso:
        raise LedgerError(RECONCILIATION_INVALID, "`start` is after `end`",
                          {"start": start_iso, "end": end_iso})

    lines = _ledger_lines(service, ledger_id, account.code, start_iso, end_iso, window)
    by_external = {line.external_id: line for line in lines if line.external_id}
    consumed: set[str] = set()
    items: list[dict[str, Any]] = []

    for row in parsed.rows:
        external = _row_external(account.code, row.external_id)
        match = by_external.get(external)
        if match is not None:
            difference = q_money(match.amount - row.amount)
            consumed.add(match.entry_id)
            if abs(difference) <= tol:
                items.append(_item(row, "MATCHED", "EXTERNAL_ID", match,
                                   {"difference": f"{difference:f}"}))
            else:
                items.append(_item(row, "MISMATCH", "EXTERNAL_ID", match,
                                   {"difference": f"{difference:f}",
                                    "reason": "the posted amount differs from the statement"}))
            continue

        candidates = [
            line for line in lines
            if line.entry_id not in consumed
            and abs(line.amount - row.amount) <= tol
            and _within(line.entry_date, row.date, window)
        ]
        if len(candidates) == 1:
            consumed.add(candidates[0].entry_id)
            items.append(_item(row, "MATCHED", "AMOUNT_DATE", candidates[0], {}))
            continue
        if len(candidates) > 1:
            items.append(_item(
                row, "UNKNOWN", "AMBIGUOUS", None,
                {"candidates": [candidate.entry_id for candidate in candidates],
                 "reason": f"{len(candidates)} ledger entries match this amount/date window"},
            ))
            continue
        near = [
            line for line in lines
            if line.entry_id not in consumed and _within(line.entry_date, row.date, window)
        ]
        if near:
            closest = min(near, key=lambda line: abs(line.amount - row.amount))
            consumed.add(closest.entry_id)
            items.append(_item(
                row, "MISMATCH", "AMOUNT_DATE", closest,
                {"difference": f"{q_money(closest.amount - row.amount):f}",
                 "reason": "a ledger entry in the window has a different amount"},
            ))
            continue
        items.append(_item(row, "MISSING", None, None, {}))

    unpresented = [
        {
            "entryId": line.entry_id,
            "entryDate": line.entry_date,
            "amount": f"{q_money(line.amount):f}",
            "memo": line.memo,
            "externalId": line.external_id,
        }
        for line in lines
        if line.entry_id not in consumed and start_iso <= line.entry_date <= end_iso
    ]

    opening_balance, closing_balance = _ledger_balances(service, ledger_id, account.code,
                                                        start_iso, end_iso)
    declared: Optional[Decimal] = None
    if statement_balance not in (None, ""):
        try:
            declared = q_money(D(statement_balance))
        except (ValueError, TypeError) as exc:
            raise LedgerError(RECONCILIATION_INVALID, "`statement_balance` is not a decimal",
                              {"statementBalance": str(statement_balance)}) from exc
    difference = None if declared is None else q_money(declared - closing_balance)
    balance_status = (
        "UNKNOWN" if difference is None
        else ("BALANCED" if abs(difference) <= tol else "UNBALANCED")
    )

    counts = {
        "matchedCount": sum(1 for item in items if item["status"] == "MATCHED"),
        "mismatchCount": sum(1 for item in items if item["status"] == "MISMATCH"),
        "missingCount": sum(1 for item in items if item["status"] == "MISSING"),
        "unknownCount": sum(1 for item in items if item["status"] == "UNKNOWN"),
    }
    if difference is None:
        overall = "INCOMPLETE"
    elif balance_status == "BALANCED" and counts["mismatchCount"] == 0 \
            and counts["missingCount"] == 0 and counts["unknownCount"] == 0:
        overall = "RECONCILED"
    else:
        overall = "UNRECONCILED"

    run_id = _run_id()
    record = service.store.insert_reconciliation(
        {
            "id": run_id,
            "ledgerId": ledger_id,
            "accountCode": account.code,
            "startDate": start_iso,
            "endDate": end_iso,
            "statementBalance": None if declared is None else f"{declared:f}",
            "openingBalance": f"{opening_balance:f}",
            "closingBalance": f"{closing_balance:f}",
            "difference": None if difference is None else f"{difference:f}",
            "tolerance": f"{tol:f}",
            **counts,
            "status": overall,
            "detail": {
                "format": parsed.format,
                "currency": parsed.currency,
                "windowDays": window,
                "balanceStatus": balance_status,
                "fxRate": None if rate is None else f"{rate:f}",
                "unpresented": unpresented,
                "warnings": list(parsed.warnings),
            },
            "createdBy": actor_id,
        },
        [
            {
                "id": _item_id(),
                **item,
            }
            for item in items
        ],
    )
    service.store.audit(
        ledger_id, "STATEMENT_RECONCILED", subject_id=run_id, actor=actor_id,
        detail={"accountCode": account.code, "status": overall, **counts},
    )
    return {
        "id": run_id,
        "ledgerId": ledger_id,
        "accountCode": account.code,
        "startDate": start_iso,
        "endDate": end_iso,
        "status": overall,
        "balanceStatus": balance_status,
        "tolerance": f"{tol:f}",
        "openingBalance": f"{opening_balance:f}",
        "closingBalance": f"{closing_balance:f}",
        "statementBalance": None if declared is None else f"{declared:f}",
        "difference": None if difference is None else f"{difference:f}",
        **counts,
        "items": items,
        "unpresented": unpresented,
        "warnings": list(parsed.warnings),
        "detail": {
            "format": parsed.format,
            "currency": parsed.currency,
            "windowDays": window,
        },
        "createdAt": record["createdAt"],
    }


def _row_external(account_code: str, row_external_id: str) -> str:
    return f"stmt:{account_code}:{row_external_id}"


def _within(entry_date: str, row_date: str, window_days: int) -> bool:
    try:
        left = date.fromisoformat(str(entry_date)[:10])
        right = date.fromisoformat(str(row_date)[:10])
    except ValueError:
        return False
    return abs((left - right).days) <= window_days


def _item(row: Any, status: str, method: Optional[str],
          line: Optional[LedgerLine], detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "rowNo": row.row_no,
        "entryDate": row.date,
        "description": row.description,
        "amount": f"{q_money(row.amount):f}",
        "status": status,
        "method": method,
        "entryId": line.entry_id if line is not None else None,
        "detail": detail,
    }


def _ledger_balances(service: Any, ledger_id: str, account_code: str,
                     start: str, end: str) -> tuple[Decimal, Decimal]:
    before = service.store.postings(
        ledger_id, account_code=account_code,
        end=(date.fromisoformat(start) - timedelta(days=1)).isoformat(),
    )
    opening = sum(((row["baseDebit"] or ZERO) - (row["baseCredit"] or ZERO)
                   for row in before), ZERO)
    through = service.store.postings(ledger_id, account_code=account_code, end=end)
    closing = sum(((row["baseDebit"] or ZERO) - (row["baseCredit"] or ZERO)
                   for row in through), ZERO)
    return q_money(opening), q_money(closing)


def list_runs(service: Any, ledger_id: str, *, limit: int = 50,
              actor_id: Optional[str] = None) -> list[dict[str, Any]]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    return service.store.list_reconciliations(ledger_id, limit=limit)


def get_run(service: Any, ledger_id: str, run_id: str, *,
            actor_id: Optional[str] = None) -> dict[str, Any]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    record = service.store.get_reconciliation(str(run_id))
    if record is None or record["ledgerId"] != ledger_id:
        raise LedgerError(RECONCILIATION_NOT_FOUND,
                          f"reconciliation {run_id} not found", {"runId": run_id})
    return record


__all__ = [
    "MATCH_WINDOW_DAYS",
    "TOLERANCE",
    "LedgerLine",
    "get_run",
    "list_runs",
    "run",
]

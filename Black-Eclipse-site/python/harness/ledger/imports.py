"""Statement import pipeline: parse → categorise → preview → post.

A preview and a commit run over the SAME deterministic steps, so what the
operator sees is what gets posted. The only differences are that a commit writes
journal entries (through `LedgerService.post`, the one posting path) and records a
batch row.

What a row becomes, given `amount` from the statement's point of view:

    amount < 0 (money left the account)   Dr <categorised account> / Cr <bank>
    amount > 0 (money arrived)            Dr <bank> / Cr <categorised account>

That is the whole rule. A liability target (a loan repayment) works without a
special case because the sign picks the bank side, not the target side.

Never done here:
  * a guess when no rule matches — the row goes to the suspense account,
  * a silent FX conversion — a foreign-currency row without a rate is reported
    as `REQUIRES_FX` and is not posted,
  * a duplicate posting — the ledger entry's `external_id` is derived from the
    statement row's stable identity, so a re-import is idempotent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from .errors import IMPORT_ACCOUNT_INVALID, LedgerError
from .importers import CsvMapping, ParsedStatement, StatementRow, parse_statement
from .models import Account
from .money import D, ZERO, q_money, q_rate
from .rules import Categorisation, categorise


def _batch_id() -> str:
    return f"imp_{uuid.uuid4().hex[:20]}"


def statement_external_id(account_code: str, row: StatementRow) -> str:
    return f"stmt:{account_code}:{row.external_id}"


@dataclass
class ImportRow:
    row: StatementRow
    categorisation: Categorisation
    status: str
    lines: list[dict[str, str]] = field(default_factory=list)
    entry_id: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = self.row.to_dict()
        payload.update({
            "accountCode": self.categorisation.account_code,
            "method": self.categorisation.method,
            "ruleId": self.categorisation.rule_id,
            "ruleName": self.categorisation.rule_name,
            "ruleVersion": self.categorisation.rule_version,
            "reason": self.reason or self.categorisation.reason,
            "status": self.status,
            "entryId": self.entry_id,
            "lines": list(self.lines),
        })
        return payload


def _prepare(
    service: Any,
    ledger_id: str,
    *,
    account_code: str,
    content: str,
    statement_format: str,
    mapping: Optional[CsvMapping],
    fx_rate: object = None,
    actor_id: Optional[str] = None,
) -> tuple[dict[str, Any], ParsedStatement, list[ImportRow]]:
    ledger = service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001 - same package
    accounts: list[Account] = service.store.list_accounts(ledger_id)
    accounts_by_code = {account.code: account for account in accounts}
    account = accounts_by_code.get(str(account_code or "").strip())
    if account is None:
        raise LedgerError(
            IMPORT_ACCOUNT_INVALID,
            f"account {account_code!r} does not exist in this ledger",
            {"accountCode": account_code},
        )
    if not account.active:
        raise LedgerError(
            IMPORT_ACCOUNT_INVALID, f"account {account.code!r} is inactive",
            {"accountCode": account.code},
        )
    if account.currency and account.currency.upper() != ledger.base_currency.upper():
        # A bank account held in another currency is fine; the rows simply need a
        # rate. Saying so here beats refusing every row one at a time.
        if fx_rate in (None, ""):
            raise LedgerError(
                IMPORT_ACCOUNT_INVALID,
                f"account {account.code!r} is in {account.currency}; supply `fx_rate` "
                "to import this statement",
                {"accountCode": account.code, "accountCurrency": account.currency},
            )

    parsed = parse_statement(
        content, statement_format, mapping=mapping,
        account_ref=f"{ledger_id}:{account.code}",
        default_currency=ledger.base_currency,
    )
    rules = service.store.list_rules(ledger_id, active_only=True)
    rate: Optional[Decimal] = q_rate(D(fx_rate)) if fx_rate not in (None, "") else None

    prepared: list[ImportRow] = []
    for row in parsed.rows:
        existing = service.store.find_by_external(
            ledger_id, "import", statement_external_id(account.code, row)
        )
        categorisation = categorise(row, rules, accounts_by_code)
        foreign = row.currency.upper() != ledger.base_currency.upper()
        status = "NEW"
        reason = categorisation.reason
        if existing is not None:
            status = "DUPLICATE"
            reason = f"already posted as entry #{existing.entry_no}"
        elif foreign and rate is None:
            status = "REQUIRES_FX"
            reason = (f"row is in {row.currency} but no fx_rate was supplied; "
                      "it will not be posted until a rate is given")
        prepared.append(ImportRow(
            row=row,
            categorisation=categorisation,
            status=status,
            lines=_proposed_lines(account, row, categorisation, rate,
                                  base_currency=ledger.base_currency),
            entry_id=existing.id if existing is not None else None,
            reason=reason,
        ))

    totals = {
        "rowCount": len(prepared),
        "newCount": sum(1 for item in prepared if item.status == "NEW"),
        "duplicateCount": sum(1 for item in prepared if item.status == "DUPLICATE"),
        "requiresFxCount": sum(1 for item in prepared if item.status == "REQUIRES_FX"),
        "categorisedCount": sum(1 for item in prepared if item.categorisation.method == "RULE"),
        "suspenseCount": sum(1 for item in prepared
                             if item.categorisation.method == "SUSPENSE"),
        "totalIn": f"{q_money(parsed.total_in):f}",
        "totalOut": f"{q_money(parsed.total_out):f}",
        "net": f"{q_money(parsed.total_in + parsed.total_out):f}",
        "closingBalance": parsed.to_dict(rows=False)["closingBalance"],
    }
    return totals, parsed, prepared


def _proposed_lines(account: Account, row: StatementRow,
                    categorisation: Categorisation,
                    rate: Optional[Decimal],
                    *,
                    base_currency: str) -> list[dict[str, str]]:
    amount = abs(row.amount)
    target = categorisation.account_code
    line_extra: dict[str, str] = {}
    if rate is not None and row.currency.upper() != str(base_currency).upper():
        line_extra = {"currency": row.currency.upper(), "fx_rate": f"{rate:f}"}
    if row.amount < ZERO:
        lines = [
            {"account_code": target, "debit": f"{amount:f}", **line_extra},
            {"account_code": account.code, "credit": f"{amount:f}", **line_extra},
        ]
    else:
        lines = [
            {"account_code": account.code, "debit": f"{amount:f}", **line_extra},
            {"account_code": target, "credit": f"{amount:f}", **line_extra},
        ]
    return lines


def preview(
    service: Any,
    ledger_id: str,
    *,
    account_code: str,
    content: str,
    statement_format: str = "csv",
    mapping: Optional[CsvMapping] = None,
    fx_rate: object = None,
    actor_id: Optional[str] = None,
) -> dict[str, Any]:
    totals, parsed, prepared = _prepare(
        service, ledger_id, account_code=account_code, content=content,
        statement_format=statement_format, mapping=mapping, fx_rate=fx_rate,
        actor_id=actor_id,
    )
    return {
        "mode": "preview",
        "ledgerId": ledger_id,
        "accountCode": account_code,
        "format": parsed.format,
        "currency": parsed.currency,
        **totals,
        "rows": [item.to_dict() for item in prepared],
        "warnings": list(parsed.warnings),
        "requiresFx": totals["requiresFxCount"] > 0,
    }


def commit(
    service: Any,
    ledger_id: str,
    *,
    account_code: str,
    content: str,
    statement_format: str = "csv",
    mapping: Optional[CsvMapping] = None,
    fx_rate: object = None,
    batch_ref: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> dict[str, Any]:
    totals, parsed, prepared = _prepare(
        service, ledger_id, account_code=account_code, content=content,
        statement_format=statement_format, mapping=mapping, fx_rate=fx_rate,
        actor_id=actor_id,
    )
    batch_id = _batch_id()
    posted: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for item in prepared:
        if item.status != "NEW":
            continue
        try:
            entry = service.post(
                ledger_id,
                entry_date=item.row.date,
                lines=item.lines,
                memo=item.row.description or f"Statement row {item.row.row_no}",
                source="import",
                external_id=statement_external_id(account_code, item.row),
                actor_id=actor_id,
            )
        except LedgerError as exc:
            errors.append({
                "rowNo": item.row.row_no,
                "date": item.row.date,
                "description": item.row.description,
                "amount": f"{q_money(item.row.amount):f}",
                "code": exc.code,
                "message": exc.message,
            })
            continue
        posted.append({
            "rowNo": item.row.row_no,
            "entryId": entry["id"],
            "entryNo": entry["entryNo"],
            "date": entry["entryDate"],
            "amount": f"{q_money(item.row.amount):f}",
            "accountCode": item.categorisation.account_code,
            "method": item.categorisation.method,
            "ruleId": item.categorisation.rule_id,
            "duplicate": entry.get("duplicate", False),
        })

    status = "COMPLETE"
    if errors and posted:
        status = "PARTIAL"
    elif errors and not posted:
        status = "FAILED"

    record = service.store.insert_import_batch({
        "id": batch_id,
        "ledgerId": ledger_id,
        "accountCode": account_code,
        "source": "import",
        "format": parsed.format,
        "batchRef": batch_ref,
        "rowCount": totals["rowCount"],
        "postedCount": len(posted),
        "duplicateCount": totals["duplicateCount"],
        "errorCount": len(errors),
        "status": status,
        "detail": {
            "totals": totals,
            "errors": errors,
            "warnings": list(parsed.warnings),
            "fxRate": None if fx_rate in (None, "") else str(fx_rate),
        },
        "createdBy": actor_id,
    })
    service.store.audit(
        ledger_id, "STATEMENT_IMPORTED", subject_id=batch_id, actor=actor_id,
        detail={"accountCode": account_code, "posted": len(posted),
                "errors": len(errors), "status": status},
    )
    return {
        "mode": "commit",
        "batchId": batch_id,
        "status": status,
        "ledgerId": ledger_id,
        "accountCode": account_code,
        "format": parsed.format,
        **totals,
        "postedCount": len(posted),
        "errorCount": len(errors),
        "entries": posted,
        "errorRows": errors,
        "warnings": list(parsed.warnings),
        "batch": record,
    }


def list_batches(service: Any, ledger_id: str, *, limit: int = 50,
                 actor_id: Optional[str] = None) -> list[dict[str, Any]]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    return service.store.list_import_batches(ledger_id, limit=limit)


__all__ = [
    "ImportRow",
    "commit",
    "list_batches",
    "preview",
    "statement_external_id",
]

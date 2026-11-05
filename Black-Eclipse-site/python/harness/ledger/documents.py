"""The AR/AP subledger: customers, vendors, invoices, bills, payments, aging.

A document is a *contract to post*: it computes its own lines (net + tax), posts
them through the ONE journal path, and records the open item. Everything else —
what is outstanding, what is overdue — is derived from the document and its
allocations on every read. There is no cached balance on a party.

Why this shape:

  * **One posting path.** A document is not a second journal; it is a validated
    batch of lines handed to `LedgerService.post`. If it does not balance, it does
    not exist.
  * **Control accounts are discovered, not configured.** The first active account
    with subtype `RECEIVABLE` (invoices) or `PAYABLE` (bills) is the control
    account; a caller may override it. Zero-config, and a missing one is a named
    error rather than a silently invented account.
  * **Tax is configured data.** A tax code names its rate, jurisdiction and GL
    account. There is no built-in rate table — see `tax.py`.
  * **Aging reconciles to the ledger.** The open-item total is checked against the
    control account's closing balance; a difference is reported, never hidden.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional, Sequence

from .errors import (
    ACCOUNT_NOT_FOUND,
    CONTROL_ACCOUNT_MISSING,
    DOCUMENT_HAS_PAYMENTS,
    DOCUMENT_INVALID,
    DOCUMENT_NOT_FOUND,
    DOCUMENT_NUMBER_EXISTS,
    DOCUMENT_OVERPAID,
    DOCUMENT_VOID,
    PARTY_INVALID,
    PARTY_NOT_FOUND,
    TAX_CODE_INVALID,
    TAX_CODE_NOT_FOUND,
    LedgerError,
)
from .money import D, ZERO, q_money
from .parties import build_party
from .tax import TaxCode, build_tax_code, split_net_and_tax

KINDS = ("INVOICE", "BILL")
OPEN_STATUSES = ("POSTED", "PARTIALLY_PAID")
_DEFAULT_TERMS = {"INVOICE": 30, "BILL": 30}


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


# ── parties ──────────────────────────────────────────────────────────────────


def create_party(service: Any, ledger_id: str, *, name: str, kind: str, **kwargs: Any) -> dict:
    ledger = service._require(ledger_id, actor_id=kwargs.get("actor_id"))  # noqa: SLF001
    party = build_party(ledger_id, name=name, kind=kind,
                        party_id=_id("pty"), **{
                            key: value for key, value in kwargs.items()
                            if key in ("email", "tax_id", "currency",
                                       "payment_terms_days")
                        })
    service.subledger.insert_party(party)
    service.store.audit(ledger_id, "PARTY_CREATED", subject_id=party.id,
                        actor=kwargs.get("actor_id"),
                        detail={"name": party.name, "kind": party.kind})
    return party.to_dict()


def list_parties(service: Any, ledger_id: str, *, kind: Optional[str] = None,
                 active_only: bool = True, actor_id: Optional[str] = None) -> list[dict]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    return service.subledger.list_parties(ledger_id, kind=kind, active_only=active_only)


# ── tax codes ───────────────────────────────────────────────────────────────


def create_tax_code(service: Any, ledger_id: str, *, code: str, name: str = "",
                     jurisdiction: str, rate: object, account_code: str,
                     kind: str = "VAT", price_includes_tax: bool = False,
                     actor_id: Optional[str] = None) -> dict:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    if service.subledger.get_tax_code(ledger_id, code) is not None:
        raise LedgerError(TAX_CODE_INVALID,
                          f"tax code {str(code).upper()!r} already exists",
                          {"code": str(code)})
    account = service.store.get_account(ledger_id, str(account_code).strip())
    if account is None:
        raise LedgerError(ACCOUNT_NOT_FOUND,
                          f"tax account {account_code!r} does not exist",
                          {"accountCode": str(account_code)})
    tax_code = build_tax_code(ledger_id, code=code, name=name,
                              jurisdiction=jurisdiction, rate=rate,
                              account_code=account_code, kind=kind,
                              price_includes_tax=price_includes_tax,
                              tax_id=_id("tax"))
    service.subledger.insert_tax_code(tax_code)
    service.store.audit(ledger_id, "TAX_CODE_CREATED", subject_id=tax_code.id,
                        actor=actor_id, detail=tax_code.to_dict())
    return tax_code.to_dict()


def list_tax_codes(service: Any, ledger_id: str, *, active_only: bool = True,
                   actor_id: Optional[str] = None) -> list[dict]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    return service.subledger.list_tax_codes(ledger_id, active_only=active_only)


# ── documents ───────────────────────────────────────────────────────────────


@dataclass
class ComputedLine:
    description: str
    account_code: str
    quantity: Decimal
    unit_price: Decimal
    net: Decimal
    tax: Decimal
    tax_code: Optional[str]
    tax_account: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "accountCode": self.account_code,
            "quantity": f"{self.quantity:f}",
            "unitPrice": f"{self.unit_price:f}",
            "net": f"{self.net:f}",
            "tax": f"{self.tax:f}",
            "taxCode": self.tax_code,
        }


def _resolve_tax(service: Any, ledger_id: str, code: Optional[str]) -> Optional[TaxCode]:
    if not code:
        return None
    row = service.subledger.get_tax_code(ledger_id, code)
    if row is None:
        raise LedgerError(
            TAX_CODE_NOT_FOUND,
            f"tax code {str(code).upper()!r} is not configured for this ledger",
            {"taxCode": str(code)},
        )
    return TaxCode(
        id=row["id"], ledger_id=row["ledgerId"], code=row["code"], name=row["name"],
        jurisdiction=row["jurisdiction"], rate=D(row["rate"]), kind=row["kind"],
        account_code=row["accountCode"],
        price_includes_tax=bool(row["priceIncludesTax"]),
        active=bool(row["active"]), created_at=row["createdAt"],
    )


def _computed_lines(service: Any, ledger_id: str,
                    lines: Sequence[dict[str, Any]]) -> list[ComputedLine]:
    if not isinstance(lines, (list, tuple)) or not lines:
        raise LedgerError(DOCUMENT_INVALID, "a document needs at least one line", {})
    accounts = {account.code: account for account in service.store.list_accounts(ledger_id)}
    out: list[ComputedLine] = []
    for index, raw in enumerate(lines, start=1):
        if not isinstance(raw, dict):
            raise LedgerError(DOCUMENT_INVALID, f"line {index}: expected an object",
                              {"line": index})
        account_code = str(raw.get("account_code") or raw.get("accountCode") or "").strip()
        account = accounts.get(account_code)
        if account is None:
            raise LedgerError(ACCOUNT_NOT_FOUND,
                              f"line {index}: account {account_code!r} does not exist",
                              {"line": index, "accountCode": account_code})
        if not account.active:
            raise LedgerError(ACCOUNT_NOT_FOUND,
                              f"line {index}: account {account_code!r} is inactive",
                              {"line": index, "accountCode": account_code})
        try:
            quantity = D(raw.get("quantity") if raw.get("quantity") is not None else 1)
            unit_price = D(raw.get("unit_price") if raw.get("unit_price") is not None
                           else raw.get("unitPrice") if raw.get("unitPrice") is not None
                           else raw.get("amount"))
        except (ValueError, TypeError) as exc:
            raise LedgerError(DOCUMENT_INVALID,
                              f"line {index}: quantity/unit_price must be decimals",
                              {"line": index}) from exc
        if quantity <= ZERO:
            raise LedgerError(DOCUMENT_INVALID, f"line {index}: quantity must be > 0",
                              {"line": index})
        if unit_price < ZERO:
            raise LedgerError(DOCUMENT_INVALID,
                              f"line {index}: unit_price must be >= 0", {"line": index})
        tax_code = _resolve_tax(service, ledger_id,
                                raw.get("tax_code") or raw.get("taxCode"))
        gross = q_money(quantity * unit_price)
        net, tax = split_net_and_tax(gross, tax_code) if tax_code else (gross, ZERO)
        out.append(ComputedLine(
            description=str(raw.get("description") or account.name).strip()[:500],
            account_code=account_code,
            quantity=quantity,
            unit_price=unit_price,
            net=net,
            tax=tax,
            tax_code=tax_code.code if tax_code else None,
            tax_account=tax_code.account_code if tax_code else None,
        ))
    return out


def _control_account(service: Any, ledger_id: str, kind: str,
                     override: Optional[str]) -> str:
    if override:
        account = service.store.get_account(ledger_id, str(override).strip())
        if account is None:
            raise LedgerError(CONTROL_ACCOUNT_MISSING,
                              f"control account {override!r} does not exist",
                              {"accountCode": str(override)})
        return account.code
    wanted = "RECEIVABLE" if kind == "INVOICE" else "PAYABLE"
    for account in service.store.list_accounts(ledger_id):
        if account.active and account.subtype == wanted:
            return account.code
    raise LedgerError(
        CONTROL_ACCOUNT_MISSING,
        f"no active {wanted} account is configured; add one (or pass "
        f"`{'receivable_account' if kind == 'INVOICE' else 'payable_account'}`)",
        {"subtype": wanted},
    )


def _posting_lines(kind: str, control: str, computed: Sequence[ComputedLine],
                   total: Decimal) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    taxes: dict[str, Decimal] = {}
    for line in computed:
        if line.tax_account:
            taxes[line.tax_account] = taxes.get(line.tax_account, ZERO) + line.tax
    if kind == "INVOICE":
        lines.append({"account_code": control, "debit": f"{total:f}"})
        for line in computed:
            if line.net:
                lines.append({"account_code": line.account_code, "credit": f"{line.net:f}"})
        for account, amount in sorted(taxes.items()):
            if amount:
                lines.append({"account_code": account, "credit": f"{amount:f}"})
    else:
        for line in computed:
            if line.net:
                lines.append({"account_code": line.account_code, "debit": f"{line.net:f}"})
        for account, amount in sorted(taxes.items()):
            if amount:
                lines.append({"account_code": account, "debit": f"{amount:f}"})
        lines.append({"account_code": control, "credit": f"{total:f}"})
    return lines


def create_document(
    service: Any,
    ledger_id: str,
    *,
    kind: str,
    party_id: str,
    issue_date: object,
    lines: Sequence[dict[str, Any]],
    due_date: object = None,
    number: Optional[str] = None,
    memo: str = "",
    reference: Optional[str] = None,
    receivable_account: Optional[str] = None,
    payable_account: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> dict[str, Any]:
    ledger = service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    clean_kind = str(kind or "").strip().upper()
    if clean_kind not in KINDS:
        raise LedgerError(DOCUMENT_INVALID,
                          f"`kind` must be one of {', '.join(KINDS)}", {"kind": str(kind)})
    party = service.subledger.get_party(str(party_id or ""))
    if party is None or party["ledgerId"] != ledger_id:
        raise LedgerError(PARTY_NOT_FOUND, f"party {party_id!r} not found",
                          {"partyId": str(party_id)})
    expected = "CUSTOMER" if clean_kind == "INVOICE" else "VENDOR"
    if party["kind"] != expected:
        raise LedgerError(
            PARTY_INVALID,
            f"a {clean_kind.lower()} needs a {expected.lower()}; "
            f"{party['name']!r} is a {party['kind'].lower()}",
            {"partyId": party["id"], "partyKind": party["kind"]},
        )
    if not party["active"]:
        raise LedgerError(PARTY_INVALID, f"party {party['name']!r} is inactive",
                          {"partyId": party["id"]})
    try:
        issued = date.fromisoformat(str(issue_date)[:10])
    except ValueError as exc:
        raise LedgerError(DOCUMENT_INVALID, "`issue_date` must be an ISO date",
                          {"issueDate": str(issue_date)}) from exc
    if due_date in (None, ""):
        due = issued + timedelta(days=int(party.get("paymentTermsDays") or 30))
    else:
        try:
            due = date.fromisoformat(str(due_date)[:10])
        except ValueError as exc:
            raise LedgerError(DOCUMENT_INVALID, "`due_date` must be an ISO date",
                              {"dueDate": str(due_date)}) from exc
    if due < issued:
        raise LedgerError(DOCUMENT_INVALID, "`due_date` is before `issue_date`",
                          {"issueDate": issued.isoformat(), "dueDate": due.isoformat()})

    computed = _computed_lines(service, ledger_id, lines)
    subtotal = sum((line.net for line in computed), ZERO)
    tax_total = sum((line.tax for line in computed), ZERO)
    total = q_money(subtotal + tax_total)
    if total <= ZERO:
        raise LedgerError(DOCUMENT_INVALID, "a document total must be > 0", {})

    control = _control_account(
        service, ledger_id, clean_kind,
        receivable_account if clean_kind == "INVOICE" else payable_account,
    )
    document_id = _id("doc")
    chosen = str(number or "").strip() or service.subledger.next_document_number(
        ledger_id, clean_kind
    )
    if service.subledger.document_number_exists(ledger_id, clean_kind, chosen):
        raise LedgerError(
            DOCUMENT_NUMBER_EXISTS,
            f"{clean_kind.lower()} number {chosen!r} already exists in this ledger",
            {"number": chosen},
        )

    entry = service.post(
        ledger_id,
        entry_date=issued.isoformat(),
        lines=_posting_lines(clean_kind, control, computed, total),
        memo=str(memo or f"{clean_kind.title()} {chosen} — {party['name']}")[:1000],
        source="document",
        external_id=f"doc:{document_id}",
        actor_id=actor_id,
    )
    record = service.subledger.insert_document({
        "id": document_id,
        "ledgerId": ledger_id,
        "kind": clean_kind,
        "number": chosen,
        "partyId": party["id"],
        "partyName": party["name"],
        "issueDate": issued.isoformat(),
        "dueDate": due.isoformat(),
        "currency": ledger.base_currency,
        "lines": [line.to_dict() for line in computed],
        "subtotal": f"{subtotal:f}",
        "taxTotal": f"{tax_total:f}",
        "total": f"{total:f}",
        "controlAccount": control,
        "status": "POSTED",
        "journalEntryId": entry["id"],
        "memo": str(memo or "")[:1000],
        "reference": reference,
        "createdBy": actor_id,
    })
    service.store.audit(
        ledger_id, "DOCUMENT_POSTED", subject_id=document_id, actor=actor_id,
        detail={"kind": clean_kind, "number": chosen, "total": f"{total:f}",
                "controlAccount": control},
    )
    payload = dict(record)
    payload["outstanding"] = f"{total:f}"
    payload["allocations"] = []
    return payload


def get_document(service: Any, ledger_id: str, document_id: str, *,
                 actor_id: Optional[str] = None) -> dict[str, Any]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    document = service.subledger.require_document(str(document_id))
    if document["ledgerId"] != ledger_id:
        raise LedgerError(DOCUMENT_NOT_FOUND, f"document {document_id} not found",
                          {"documentId": document_id})
    return _with_balance(service, document)


def list_documents(service: Any, ledger_id: str, *, kind: Optional[str] = None,
                   party_id: Optional[str] = None, status: Optional[str] = None,
                   limit: int = 100, actor_id: Optional[str] = None) -> list[dict]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    rows = service.subledger.list_documents(ledger_id, kind=kind, party_id=party_id,
                                            status=status, limit=limit)
    return [_with_balance(service, row) for row in rows]


def _with_balance(service: Any, document: dict[str, Any]) -> dict[str, Any]:
    allocated = service.subledger.allocated_total(document["id"])
    total = D(document["total"])
    payload = dict(document)
    payload["allocations"] = service.subledger.allocations(document["id"])
    payload["paid"] = f"{allocated:f}"
    payload["outstanding"] = f"{q_money(total - allocated):f}"
    return payload


def pay_document(
    service: Any,
    ledger_id: str,
    document_id: str,
    *,
    date_paid: object,
    amount: object,
    bank_account: str,
    reference: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> dict[str, Any]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    document = service.subledger.require_document(str(document_id))
    if document["ledgerId"] != ledger_id:
        raise LedgerError(DOCUMENT_NOT_FOUND, f"document {document_id} not found",
                          {"documentId": document_id})
    if document["status"] == "VOID":
        raise LedgerError(DOCUMENT_VOID, f"{document['number']} is void",
                          {"documentId": document_id})
    try:
        value = q_money(D(amount))
    except (ValueError, TypeError) as exc:
        raise LedgerError(DOCUMENT_INVALID, "`amount` must be a decimal literal",
                          {"amount": str(amount)}) from exc
    if value <= ZERO:
        raise LedgerError(DOCUMENT_INVALID, "`amount` must be > 0", {})
    try:
        when = date.fromisoformat(str(date_paid)[:10]).isoformat()
    except ValueError as exc:
        raise LedgerError(DOCUMENT_INVALID, "`date` must be an ISO date",
                          {"date": str(date_paid)}) from exc
    bank = service.store.get_account(ledger_id, str(bank_account).strip())
    if bank is None or not bank.is_cash:
        raise LedgerError(DOCUMENT_INVALID,
                          f"{bank_account!r} is not a cash account in this ledger",
                          {"accountCode": str(bank_account)})

    allocated = service.subledger.allocated_total(document["id"])
    outstanding = q_money(D(document["total"]) - allocated)
    if value > outstanding:
        raise LedgerError(
            DOCUMENT_OVERPAID,
            f"payment {value:f} exceeds the outstanding {outstanding:f} on "
            f"{document['number']}",
            {"documentId": document["id"], "outstanding": f"{outstanding:f}"},
        )
    control = _control_account(
        service, ledger_id, document["kind"],
        document.get("controlAccount") or None,
    )
    if document["kind"] == "INVOICE":
        lines = [
            {"account_code": bank.code, "debit": f"{value:f}"},
            {"account_code": control, "credit": f"{value:f}"},
        ]
    else:
        lines = [
            {"account_code": control, "debit": f"{value:f}"},
            {"account_code": bank.code, "credit": f"{value:f}"},
        ]
    key = str(reference or "").strip() or f"{when}:{value:f}"
    entry = service.post(
        ledger_id,
        entry_date=when,
        lines=lines,
        memo=f"Payment of {document['number']}",
        source="payment",
        external_id=f"pay:{document['id']}:{key}",
        actor_id=actor_id,
    )
    if entry.get("duplicate"):
        # The payment was already recorded under this reference: do NOT insert a
        # second allocation. Report the state the first call produced.
        already = service.subledger.allocated_total(document["id"])
        return {
            "documentId": document["id"],
            "number": document["number"],
            "entryId": entry["id"],
            "entryNo": entry["entryNo"],
            "amount": f"{value:f}",
            "paid": f"{q_money(already):f}",
            "outstanding": f"{q_money(D(document['total']) - already):f}",
            "status": service.subledger.require_document(document["id"])["status"],
            "duplicate": True,
        }
    service.subledger.insert_allocation({
        "id": _id("all"),
        "ledgerId": ledger_id,
        "documentId": document["id"],
        "entryId": entry["id"],
        "date": when,
        "amount": f"{value:f}",
    })
    remaining = q_money(outstanding - value)
    status = "PAID" if remaining == ZERO else "PARTIALLY_PAID"
    service.subledger.set_document_status(document["id"], status)
    service.store.audit(
        ledger_id, "DOCUMENT_PAID", subject_id=document["id"], actor=actor_id,
        detail={"amount": f"{value:f}", "outstanding": f"{remaining:f}", "status": status},
    )
    return {
        "documentId": document["id"],
        "number": document["number"],
        "entryId": entry["id"],
        "entryNo": entry["entryNo"],
        "amount": f"{value:f}",
        "paid": f"{q_money(allocated + value):f}",
        "outstanding": f"{remaining:f}",
        "status": status,
        "duplicate": bool(entry.get("duplicate")),
    }


def void_document(service: Any, ledger_id: str, document_id: str, *,
                  reason: str = "", actor_id: Optional[str] = None) -> dict[str, Any]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    document = service.subledger.require_document(str(document_id))
    if document["ledgerId"] != ledger_id:
        raise LedgerError(DOCUMENT_NOT_FOUND, f"document {document_id} not found",
                          {"documentId": document_id})
    if document["status"] == "VOID":
        return _with_balance(service, document)
    if service.subledger.allocations(document["id"]):
        raise LedgerError(
            DOCUMENT_HAS_PAYMENTS,
            f"{document['number']} has payments allocated; reversing them is the "
            "correct way to undo it",
            {"documentId": document["id"]},
        )
    entry = service.store.require_entry(document["journalEntryId"])
    if not entry.reversed_by_entry_id:
        service.reverse(ledger_id, entry.id, memo=f"Void {document['number']}: {reason}"[:1000],
                        actor_id=actor_id)
    service.subledger.set_document_status(document["id"], "VOID")
    service.store.audit(ledger_id, "DOCUMENT_VOIDED", subject_id=document["id"],
                        actor=actor_id, detail={"number": document["number"],
                                                "reason": reason})
    return _with_balance(service, service.subledger.require_document(document["id"]))


# ── aging ───────────────────────────────────────────────────────────────────

_BUCKETS = ("current", "1-30", "31-60", "61-90", "90+")


def _bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


def aging(service: Any, ledger_id: str, *, kind: str = "AR", as_of: object = None,
          actor_id: Optional[str] = None) -> dict[str, Any]:
    service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    direction = str(kind or "AR").strip().upper()
    if direction not in ("AR", "AP"):
        raise LedgerError(DOCUMENT_INVALID, "`kind` must be AR or AP", {"kind": str(kind)})
    document_kind = "INVOICE" if direction == "AR" else "BILL"
    try:
        when = date.fromisoformat(str(as_of)[:10]) if as_of else date.today()
    except ValueError as exc:
        raise LedgerError(DOCUMENT_INVALID, "`as_of` must be an ISO date",
                          {"asOf": str(as_of)}) from exc

    control = _control_account(service, ledger_id, document_kind, None)
    documents = service.subledger.list_documents(
        ledger_id, kind=document_kind, status=None, limit=1000
    )
    rows: list[dict[str, Any]] = []
    buckets = {name: ZERO for name in _BUCKETS}
    by_party: dict[str, dict[str, Any]] = {}
    for document in documents:
        if document["status"] == "VOID":
            continue
        if str(document["issueDate"]) > when.isoformat():
            continue
        # Outstanding is derived AT the report date from the allocations, not read
        # from today's status: an invoice paid in February is still open on 31 Jan.
        allocated = service.subledger.allocated_total(document["id"], as_of=when.isoformat())
        outstanding = sum((D(document["total"]), -allocated), ZERO)
        if outstanding <= ZERO:
            continue
        due = date.fromisoformat(document["dueDate"])
        days = (when - due).days
        bucket = _bucket(days)
        buckets[bucket] += outstanding
        rows.append({
            "id": document["id"],
            "number": document["number"],
            "partyId": document["partyId"],
            "partyName": document["partyName"],
            "issueDate": document["issueDate"],
            "dueDate": document["dueDate"],
            "daysOverdue": days,
            "bucket": bucket,
            "total": document["total"],
            "paid": f"{q_money(allocated):f}",
            "outstanding": f"{q_money(outstanding):f}",
        })
        entry = by_party.setdefault(document["partyId"], {
            "partyId": document["partyId"], "partyName": document["partyName"],
            "outstanding": ZERO, "oldestDays": 0, "documents": 0,
            "buckets": {name: ZERO for name in _BUCKETS},
        })
        entry["outstanding"] += outstanding
        entry["documents"] += 1
        entry["oldestDays"] = max(entry["oldestDays"], days)
        entry["buckets"][bucket] += outstanding

    open_total = sum(buckets.values(), ZERO)
    trial = service.trial_balance(ledger_id, as_of=when)
    account_row = next((row for row in trial["rows"] if row["code"] == control), None)
    if account_row is None:
        control_balance = ZERO
    elif direction == "AR":
        control_balance = D(account_row["closingDebit"]) - D(account_row["closingCredit"])
    else:
        control_balance = D(account_row["closingCredit"]) - D(account_row["closingDebit"])
    difference = q_money(open_total - control_balance)

    parties = []
    for entry in by_party.values():
        payload = dict(entry)
        payload["outstanding"] = f"{q_money(entry['outstanding']):f}"
        payload["buckets"] = {key: f"{q_money(value):f}" for key, value in entry["buckets"].items()}
        parties.append(payload)
    parties.sort(key=lambda row: D(row["outstanding"]), reverse=True)

    checks = [
        {
            "name": "open-items-equal-control-account",
            "ok": difference == ZERO,
            "detail": f"open {q_money(open_total):f} vs control {q_money(control_balance):f} "
                      f"(difference {difference:f})",
        }
    ]
    return {
        "kind": direction,
        "asOf": when.isoformat(),
        "controlAccount": control,
        "controlBalance": f"{q_money(control_balance):f}",
        "openTotal": f"{q_money(open_total):f}",
        "difference": f"{difference:f}",
        "buckets": {key: f"{q_money(value):f}" for key, value in buckets.items()},
        "parties": parties,
        "documents": rows,
        "checks": checks,
        "reconciled": difference == ZERO,
    }


__all__ = [
    "KINDS",
    "OPEN_STATUSES",
    "aging",
    "create_document",
    "create_party",
    "create_tax_code",
    "get_document",
    "list_documents",
    "list_parties",
    "list_tax_codes",
    "pay_document",
    "void_document",
]

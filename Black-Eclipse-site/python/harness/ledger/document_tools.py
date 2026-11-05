"""Agent tools for the AR/AP subledger.

Split from `tools.py` to keep both files readable; it registers on the SAME
registry through `register_ledger_tools`. Names stay in the `ledger_*` family and
mutations carry effect `ledger.write`, so the existing `ledger_write` authorizer
owns them without a second approval path.
"""

from __future__ import annotations

from typing import Any

from .errors import LedgerError
from .money import D, ZERO
from .tools import READ, WRITE, WRITE_EFFECT, _actor, _fail, _guarded, _ledger_id, _service

DOCUMENT_READ_TOOLS = [
    "ledger_party_list", "ledger_tax_code_list", "ledger_document_list",
    "ledger_document_get", "ledger_aging",
]

DOCUMENT_WRITE_TOOLS = [
    "ledger_party_create", "ledger_tax_code_create", "ledger_document_create",
    "ledger_document_void", "ledger_document_pay",
]

DOCUMENT_TOOLS = DOCUMENT_READ_TOOLS + DOCUMENT_WRITE_TOOLS


async def ledger_party_create(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = service.create_party(
            _ledger_id(args),
            name=str(args.get("name") or ""),
            kind=str(args.get("kind") or ""),
            email=args.get("email"),
            tax_id=args.get("tax_id") or args.get("taxId"),
            currency=args.get("currency") or "",
            payment_terms_days=int(args.get("payment_terms_days")
                                   or args.get("paymentTermsDays") or 30),
            actor_id=_actor(ctx),
        )
    except LedgerError as exc:
        return _fail(exc)
    return f"Created {payload['kind'].lower()} {payload['name']!r} ({payload['id']}).", payload


async def ledger_party_list(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    rows = service.list_parties(_ledger_id(args),
                                kind=args.get("kind"),
                                active_only=bool(args.get("active_only", True)),
                                actor_id=_actor(ctx))
    lines = [f"{len(rows)} party(ies):"]
    for row in rows:
        lines.append(f"  {row['kind']:<8} {row['name']}  [{row['id']}]")
    return "\n".join(lines), {"parties": rows}


async def ledger_tax_code_create(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = service.create_tax_code(
            _ledger_id(args),
            code=str(args.get("code") or ""),
            name=str(args.get("name") or args.get("code") or ""),
            jurisdiction=str(args.get("jurisdiction") or ""),
            rate=args.get("rate"),
            account_code=str(args.get("account_code") or args.get("accountCode") or ""),
            kind=str(args.get("kind") or "VAT"),
            price_includes_tax=bool(args.get("price_includes_tax")
                                    or args.get("priceIncludesTax") or False),
            actor_id=_actor(ctx),
        )
    except LedgerError as exc:
        return _fail(exc)
    return (
        f"Created tax code {payload['code']} ({payload['jurisdiction']}, "
        f"{D(payload['rate']) * 100:f}%) posting to {payload['accountCode']}."
    ), payload


async def ledger_tax_code_list(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    rows = service.list_tax_codes(_ledger_id(args),
                                  active_only=bool(args.get("active_only", True)),
                                  actor_id=_actor(ctx))
    lines = [f"{len(rows)} tax code(s):"]
    for row in rows:
        lines.append(
            f"  {row['code']:<16} {row['jurisdiction']}  {D(row['rate']) * 100:f}%  → "
            f"{row['accountCode']}"
        )
    return "\n".join(lines), {"taxCodes": rows}


async def ledger_document_create(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = service.create_document(
            _ledger_id(args),
            kind=str(args.get("kind") or ""),
            party_id=str(args.get("party_id") or args.get("partyId") or ""),
            issue_date=args.get("issue_date") or args.get("issueDate"),
            due_date=args.get("due_date") or args.get("dueDate"),
            number=args.get("number"),
            memo=str(args.get("memo") or ""),
            reference=args.get("reference"),
            lines=args.get("lines") or [],
            receivable_account=args.get("receivable_account")
            or args.get("receivableAccount"),
            payable_account=args.get("payable_account") or args.get("payableAccount"),
            actor_id=_actor(ctx),
        )
    except LedgerError as exc:
        return _fail(exc)
    return (
        f"Posted {payload['kind'].lower()} {payload['number']} for {payload['partyName']}: "
        f"net {payload['subtotal']}, tax {payload['taxTotal']}, total {payload['total']} "
        f"(due {payload['dueDate']})."
    ), payload


async def ledger_document_list(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    rows = service.list_documents(_ledger_id(args),
                                  kind=args.get("kind"),
                                  party_id=args.get("party_id") or args.get("partyId"),
                                  status=args.get("status"),
                                  limit=int(args.get("limit") or 100),
                                  actor_id=_actor(ctx))
    lines = [f"{len(rows)} document(s):"]
    for row in rows:
        lines.append(
            f"  {row['kind']:<7} {row['number']:<10} {row['partyName']:<24} "
            f"total {row['total']}  outstanding {row['outstanding']}  [{row['status']}]"
        )
    return "\n".join(lines), {"documents": rows}


async def ledger_document_get(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = service.get_document(
            _ledger_id(args), str(args.get("document_id") or args.get("documentId") or ""),
            actor_id=_actor(ctx),
        )
    except LedgerError as exc:
        return _fail(exc)
    return (
        f"{payload['kind'].title()} {payload['number']} ({payload['partyName']}): "
        f"total {payload['total']}, paid {payload['paid']}, "
        f"outstanding {payload['outstanding']} [{payload['status']}]."
    ), payload


async def ledger_document_void(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = service.void_document(
            _ledger_id(args), str(args.get("document_id") or args.get("documentId") or ""),
            reason=str(args.get("reason") or ""), actor_id=_actor(ctx),
        )
    except LedgerError as exc:
        return _fail(exc)
    return f"{payload['number']} is void (reversed in the journal).", payload


async def ledger_document_pay(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = service.pay_document(
            _ledger_id(args),
            str(args.get("document_id") or args.get("documentId") or ""),
            date_paid=args.get("date") or args.get("date_paid") or args.get("datePaid"),
            amount=args.get("amount"),
            bank_account=str(args.get("bank_account") or args.get("bankAccount") or ""),
            reference=args.get("reference"),
            actor_id=_actor(ctx),
        )
    except LedgerError as exc:
        return _fail(exc)
    text = (
        f"Allocated {payload['amount']} to {payload['number']}: paid {payload['paid']}, "
        f"outstanding {payload['outstanding']} [{payload['status']}]."
    )
    if payload.get("duplicate"):
        text += " This payment reference was already recorded; nothing new was posted."
    return text, payload


async def ledger_aging(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        payload = service.aging(
            _ledger_id(args), kind=str(args.get("kind") or "AR"),
            as_of=args.get("as_of") or args.get("asOf"), actor_id=_actor(ctx),
        )
    except LedgerError as exc:
        return _fail(exc)
    buckets = payload["buckets"]
    text = (
        f"{payload['kind']} aging at {payload['asOf']}: open {payload['openTotal']} "
        f"(current {buckets['current']}, 1-30 {buckets['1-30']}, 31-60 {buckets['31-60']}, "
        f"61-90 {buckets['61-90']}, 90+ {buckets['90+']}); control account "
        f"{payload['controlAccount']} shows {payload['controlBalance']}."
    )
    if not payload["reconciled"]:
        text += f" DIFFERENCE of {payload['difference']} against the control account."
    return text, payload


def register_document_tools(registry: Any) -> None:
    from ..tools import ToolDefinition  # noqa: PLC0415

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             permission: str, effect: Any = None, timeout: int = 20_000) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema,
            handler=_guarded(handler),
            permission=permission, risk="low" if permission == READ else "medium",
            timeout_ms=timeout, effect=effect,
        ))

    lid = {"ledger_id": {"type": "string", "description": "Ledger id."}}

    _def("ledger_party_create",
         "Create a customer or vendor (`kind` CUSTOMER|VENDOR) for invoices and bills.",
         ledger_party_create,
         {"type": "object", "properties": {
             **lid, "name": {"type": "string"},
             "kind": {"type": "string", "enum": ["CUSTOMER", "VENDOR"]},
             "email": {"type": "string"}, "tax_id": {"type": "string"},
             "currency": {"type": "string"},
             "payment_terms_days": {"type": "integer", "minimum": 0, "maximum": 365}},
          "required": ["ledger_id", "name", "kind"]},
         WRITE, WRITE_EFFECT)
    _def("ledger_party_list", "List customers and vendors.",
         ledger_party_list,
         {"type": "object", "properties": {
             **lid, "kind": {"type": "string", "enum": ["CUSTOMER", "VENDOR"]},
             "active_only": {"type": "boolean"}}, "required": ["ledger_id"]},
         READ)
    _def("ledger_tax_code_create",
         "Configure a tax code for this ledger. A RATE IS NOT BUNDLED: the operator "
         "supplies the jurisdiction, the fraction (0.20 = 20%) and the GL account the "
         "tax posts to. A document naming an unconfigured code is refused.",
         ledger_tax_code_create,
         {"type": "object", "properties": {
             **lid, "code": {"type": "string"},
             "name": {"type": "string"}, "jurisdiction": {"type": "string"},
             "rate": {"type": "string", "description": "Decimal fraction, e.g. 0.20."},
             "account_code": {"type": "string"},
             "kind": {"type": "string", "enum": ["VAT", "GST", "SALES_TAX", "OTHER"]},
             "price_includes_tax": {"type": "boolean"}},
          "required": ["ledger_id", "code", "jurisdiction", "rate", "account_code"]},
         WRITE, WRITE_EFFECT)
    _def("ledger_tax_code_list", "Configured tax codes.",
         ledger_tax_code_list,
         {"type": "object", "properties": {**lid, "active_only": {"type": "boolean"}},
          "required": ["ledger_id"]},
         READ)
    _def("ledger_document_create",
         "Post an invoice (`kind` INVOICE, a customer owes you) or a bill (`kind` BILL, "
         "you owe a vendor). Each line names an `account_code` (revenue/expense), "
         "`quantity` and `unit_price`, and optionally a `tax_code`. The entry posts "
         "through the normal journal path; the open item is tracked for aging.",
         ledger_document_create,
         {"type": "object", "properties": {
             **lid,
             "kind": {"type": "string", "enum": ["INVOICE", "BILL"]},
             "party_id": {"type": "string"},
             "issue_date": {"type": "string"}, "due_date": {"type": "string"},
             "number": {"type": "string", "description": "Defaults to INV-/BILL-NNNN."},
             "memo": {"type": "string"}, "reference": {"type": "string"},
             "receivable_account": {"type": "string",
                                    "description": "Override the AR control account."},
             "payable_account": {"type": "string",
                                 "description": "Override the AP control account."},
             "lines": {"type": "array", "minItems": 1, "items": {
                 "type": "object",
                 "properties": {
                     "description": {"type": "string"},
                     "account_code": {"type": "string"},
                     "quantity": {"type": "string"},
                     "unit_price": {"type": "string"},
                     "tax_code": {"type": "string"},
                 },
                 "required": ["account_code", "unit_price"],
             }}},
          "required": ["ledger_id", "kind", "party_id", "issue_date", "lines"]},
         WRITE, WRITE_EFFECT)
    _def("ledger_document_list",
         "List invoices/bills with total, paid and outstanding amounts.",
         ledger_document_list,
         {"type": "object", "properties": {
             **lid, "kind": {"type": "string", "enum": ["INVOICE", "BILL"]},
             "party_id": {"type": "string"},
             "status": {"type": "string",
                        "enum": ["POSTED", "PARTIALLY_PAID", "PAID", "VOID"]},
             "limit": {"type": "integer"}}, "required": ["ledger_id"]},
         READ)
    _def("ledger_document_get", "One invoice/bill with its allocations and balance.",
         ledger_document_get,
         {"type": "object", "properties": {**lid, "document_id": {"type": "string"}},
          "required": ["ledger_id", "document_id"]},
         READ)
    _def("ledger_document_void",
         "Void an unpaid invoice/bill by reversing its journal entry. A document with "
         "payments must be un-received through a reversing payment instead.",
         ledger_document_void,
         {"type": "object", "properties": {
             **lid, "document_id": {"type": "string"}, "reason": {"type": "string"}},
          "required": ["ledger_id", "document_id"]},
         WRITE, WRITE_EFFECT)
    _def("ledger_document_pay",
         "Allocate a payment to an invoice/bill (Dr bank / Cr AR, or Dr AP / Cr bank). "
         "`reference` makes a retried payment idempotent; over-payment is refused.",
         ledger_document_pay,
         {"type": "object", "properties": {
             **lid, "document_id": {"type": "string"}, "date": {"type": "string"},
             "amount": {"type": "string"}, "bank_account": {"type": "string"},
             "reference": {"type": "string"}},
          "required": ["ledger_id", "document_id", "date", "amount", "bank_account"]},
         WRITE, WRITE_EFFECT)
    _def("ledger_aging",
         "Receivable (`kind` AR) or payable (`kind` AP) aging: current, 1-30, 31-60, "
         "61-90 and 90+ buckets by party, derived from open documents and reconciled "
         "against the control account.",
         ledger_aging,
         {"type": "object", "properties": {
             **lid, "kind": {"type": "string", "enum": ["AR", "AP"]},
             "as_of": {"type": "string"}}, "required": ["ledger_id"]},
         READ)


__all__ = [
    "DOCUMENT_READ_TOOLS",
    "DOCUMENT_TOOLS",
    "DOCUMENT_WRITE_TOOLS",
    "register_document_tools",
]

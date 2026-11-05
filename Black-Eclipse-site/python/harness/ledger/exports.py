"""Export a ledger: journal CSV, trial-balance CSV, a complete JSON bundle, XBRL.

Three honest constraints shape this module:

1. **Text in, text out.** An export returns `{format, filename, contentType,
   content}`; persisting it (the Artifact Center, a file, an email) is the
   caller's job. That keeps the module pure and testable.
2. **XBRL here is a real instance document, not a filing.** It declares the
   XBRL 2.1 instance namespace, a context, a unit and the primary-statement
   facts under a LOCAL namespace. There is no IFRS/GAAP taxonomy linkbase, so it
   is explicitly labelled as not taxonomy-conformant — a filing still needs a
   taxonomy mapping, which is a per-jurisdiction decision.
3. **SAF-T is refused.** It is a jurisdiction-specific audit file with a mandated
   schema, version and validation rules. Emitting a look-alike would be worse
   than not exporting: `UNSUPPORTED_EXPORT` names what is missing and why.

Amounts are exact decimal strings everywhere; nothing is rounded for display.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Optional
from xml.sax.saxutils import escape

from .errors import UNSUPPORTED_EXPORT, LedgerError
from .money import D, ZERO, q_money

FORMATS = ("journal_csv", "trial_balance_csv", "json", "xbrl")
_MAX_ENTRIES = 5000
_MAX_CSV_ROWS = 200_000

_REFUSALS = {
    "saft": "SAF-T is a jurisdiction-specific audit file with a mandated schema "
            "version and validation rules; this engine does not implement any of "
            "them, and a look-alike would be indistinguishable from a compliant one. "
            "Use `json` or `journal_csv` and map them with the filing tool.",
    "pdf": "a PDF statement needs a renderer; build one from the JSON export or the "
           "existing `document_create` builders.",
}


def export(service: Any, ledger_id: str, *, fmt: str = "journal_csv",
           start: object = None, end: object = None, limit: int = 5000,
           actor_id: Optional[str] = None) -> dict[str, Any]:
    ledger = service._require(ledger_id, actor_id=actor_id)  # noqa: SLF001
    kind = str(fmt or "").strip().lower()
    if kind in _REFUSALS:
        raise LedgerError(UNSUPPORTED_EXPORT, _REFUSALS[kind],
                          {"format": kind, "supported": list(FORMATS)})
    if kind not in FORMATS:
        raise LedgerError(
            UNSUPPORTED_EXPORT,
            f"unsupported export format {fmt!r}; supported: {', '.join(FORMATS)}",
            {"format": kind, "supported": list(FORMATS)},
        )
    start_iso = str(start)[:10] if start else None
    end_iso = str(end)[:10] if end else None
    if start_iso and end_iso and start_iso > end_iso:
        raise LedgerError(UNSUPPORTED_EXPORT, "`start` is after `end`",
                          {"start": start_iso, "end": end_iso})
    bound = max(1, min(int(limit or 5000), _MAX_ENTRIES))
    entries = service.list_entries(ledger_id, start=start_iso, end=end_iso,
                                   limit=bound, actor_id=actor_id)
    accounts = {row["code"]: row for row in service.list_accounts(ledger_id, actor_id=actor_id)}
    # A statement export without an explicit range means "the whole book", not
    # "this month" — so anchor the start at the first posting.
    effective_start = start_iso or service.store.first_entry_date(ledger_id) or end_iso

    if kind == "journal_csv":
        content, truncated = _journal_csv(entries, accounts)
        filename = f"{ledger_id}-journal.csv"
        content_type = "text/csv"
    elif kind == "trial_balance_csv":
        content, truncated = _trial_balance_csv(service, ledger_id,
                                                effective_start, end_iso), False
        filename = f"{ledger_id}-trial-balance.csv"
        content_type = "text/csv"
    elif kind == "json":
        content, truncated = _json_bundle(service, ledger_id, ledger, accounts,
                                          effective_start, end_iso, bound), len(entries) >= bound
        filename = f"{ledger_id}.json"
        content_type = "application/json"
    else:
        content, truncated = _xbrl(service, ledger_id, ledger,
                                   effective_start, end_iso), False
        filename = f"{ledger_id}.xbrl"
        content_type = "application/xml"

    service.store.audit(ledger_id, "LEDGER_EXPORTED", subject_id=ledger_id,
                        actor=actor_id,
                        detail={"format": kind, "entries": len(entries),
                                "truncated": truncated})
    return {
        "format": kind,
        "ledgerId": ledger_id,
        "filename": filename,
        "contentType": content_type,
        "content": content,
        "entryCount": len(entries),
        "truncated": truncated,
        "warning": (f"export stopped at {bound} entries; narrow the date range for a "
                    "complete journal") if truncated else None,
    }


def _journal_csv(entries: list[dict[str, Any]],
                 accounts: dict[str, dict[str, Any]]) -> tuple[str, bool]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Date", "Entry", "Reference", "Description", "Account Code",
                     "Account Name", "Debit", "Credit", "Currency", "Source"])
    rows = 0
    for entry in entries:
        for line in entry.get("lines", []):
            if rows >= _MAX_CSV_ROWS:
                return buffer.getvalue(), True
            code = str(line.get("accountCode") or "")
            writer.writerow([
                entry.get("entryDate") or "",
                f"#{entry.get('entryNo')}",
                entry.get("externalId") or "",
                entry.get("memo") or "",
                code,
                (accounts.get(code) or {}).get("name") or "",
                line.get("baseDebit") or "0",
                line.get("baseCredit") or "0",
                line.get("currency") or "",
                entry.get("source") or "",
            ])
            rows += 1
    return buffer.getvalue(), False


def _trial_balance_csv(service: Any, ledger_id: str,
                       start: Optional[str], end: Optional[str]) -> str:
    report = service.trial_balance(ledger_id, as_of=end, start=start,
                                   include_zero=False)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Account Code", "Account Name", "Type", "Opening Debit",
                     "Opening Credit", "Debit", "Credit", "Closing Debit",
                     "Closing Credit"])
    for row in report["rows"]:
        writer.writerow([row["code"], row["name"], row["type"], row["openingDebit"],
                         row["openingCredit"], row["debit"], row["credit"],
                         row["closingDebit"], row["closingCredit"]])
    writer.writerow(["", "", "", "", "", report["totals"]["debit"],
                     report["totals"]["credit"], report["totals"]["closingDebit"],
                     report["totals"]["closingCredit"]])
    return buffer.getvalue()


def _json_bundle(service: Any, ledger_id: str, ledger: Any,
                 accounts: dict[str, dict[str, Any]], start: Optional[str],
                 end: Optional[str], bound: int) -> str:
    entries = service.list_entries(ledger_id, start=start, end=end, limit=bound)
    payload = {
        "exportVersion": 1,
        "ledger": ledger.to_dict() if hasattr(ledger, "to_dict") else ledger,
        "accounts": list(accounts.values()),
        "trialBalance": service.trial_balance(ledger_id, as_of=end, start=start),
        "balanceSheet": service.balance_sheet(ledger_id, as_of=end),
        "incomeStatement": service.income_statement(ledger_id, start=start, end=end),
        "cashFlow": service.cash_flow(ledger_id, start=start, end=end),
        "entries": entries,
        "truncatedEntries": len(entries) >= bound,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def _xbrl(service: Any, ledger_id: str, ledger: Any,
          start: Optional[str], end: Optional[str]) -> str:
    sheet = service.balance_sheet(ledger_id, as_of=end)
    pnl = service.income_statement(ledger_id, start=start, end=end)
    currency = (ledger.base_currency if hasattr(ledger, "base_currency")
                else ledger["baseCurrency"])
    period_start = start or (pnl.get("startDate") or end or "")
    period_end = end or (pnl.get("endDate") or "")

    def fact(name: str, value: Any) -> str:
        amount = q_money(D(value))
        return (f'  <be:{name} contextRef="C1" unitRef="U1" decimals="2">'
                f'{amount:f}</be:{name}>')

    facts = "\n".join([
        fact("Assets", sheet["assets"]["total"]),
        fact("Liabilities", sheet["liabilities"]["total"]),
        fact("Equity", sheet["equity"]["total"]),
        fact("Revenue", pnl["revenue"]["total"]),
        fact("Expenses", pnl["totalExpenses"]),
        fact("NetIncome", pnl["netIncome"]),
    ])
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- Generated by Black Eclipse. This is a well-formed XBRL 2.1 INSTANCE\n"
        "     document, but it is NOT taxonomy-conformant: the facts use a local\n"
        "     namespace and no IFRS/GAAP taxonomy linkbase is declared. Filing still\n"
        "     requires a jurisdiction's taxonomy mapping. -->\n"
        '<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"\n'
        '            xmlns:iso4217="http://www.xbrl.org/2003/iso4217"\n'
        '            xmlns:be="http://black-eclipse.local/xbrl/ledger">\n'
        '  <xbrli:context id="C1">\n'
        "    <xbrli:entity>\n"
        f'      <xbrli:identifier scheme="black-eclipse:ledger">'
        f"{escape(str(ledger_id))}</xbrli:identifier>\n"
        "    </xbrli:entity>\n"
        "    <xbrli:period>\n"
        f"      <xbrli:startDate>{period_start}</xbrli:startDate>\n"
        f"      <xbrli:endDate>{period_end}</xbrli:endDate>\n"
        "    </xbrli:period>\n"
        "  </xbrli:context>\n"
        '  <xbrli:unit id="U1">\n'
        f"    <xbrli:measure>iso4217:{escape(currency)}</xbrli:measure>\n"
        "  </xbrli:unit>\n"
        f"{facts}\n"
        "</xbrli:xbrl>\n"
    )


__all__ = ["FORMATS", "export"]

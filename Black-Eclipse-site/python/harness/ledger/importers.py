"""Statement parsers: CSV, OFX and QIF → normalised rows.

Three rules shape this module:

1. **The format is declared, never guessed.** A caller names `csv`, `ofx` or
   `qif`; guessing from a filename or a first byte is how a QIF gets read as CSV
   and a column shifts by one.
2. **The date format is declared, never guessed.** `01/02/2026` is 1 February in
   most of the world and 2 January in the US. The mapping states the format; an
   unparseable date is a named row error, not a coin flip.
3. **Every row gets a stable identity.** `external_id` is the bank's own FITID
   when the file provides one, otherwise a hash over the row's identity plus an
   occurrence counter. That is what makes a re-import idempotent.

Nothing here posts to the ledger. A parser only produces `StatementRow`s; the
import pipeline (`imports.py`) decides what to do with them.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from .errors import (
    IMPORT_ROW_INVALID,
    INVALID_MAPPING,
    INVALID_STATEMENT,
    UNSUPPORTED_STATEMENT_FORMAT,
    LedgerError,
)
from .money import D, ZERO, q_money

FORMATS = ("csv", "ofx", "qif")

_DATE_FORMATS = ("%Y-%m-%d", "%Y%m%d")
_CURRENCY_SYMBOLS = ("$", "£", "€", "¥", "₹")


@dataclass(frozen=True)
class CsvMapping:
    """How to read ONE bank's CSV export. Declared, never inferred."""

    date_column: str
    description_columns: tuple[str, ...] = ()
    amount_column: str = ""
    debit_column: str = ""
    credit_column: str = ""
    currency_column: str = ""
    balance_column: str = ""
    delimiter: str = ","
    date_format: str = "%Y-%m-%d"
    decimal_separator: str = "."
    thousands_separator: str = ""
    skip_rows: int = 0
    default_currency: str = ""

    def validate(self) -> "CsvMapping":
        if not str(self.date_column or "").strip():
            raise LedgerError(INVALID_MAPPING, "`date_column` is required", {})
        has_amount = bool(str(self.amount_column or "").strip())
        has_split = bool(str(self.debit_column or "").strip()
                         or str(self.credit_column or "").strip())
        if has_amount and has_split:
            raise LedgerError(
                INVALID_MAPPING,
                "declare either `amount_column` or `debit_column`/`credit_column`, not both",
                {},
            )
        if not has_amount and not has_split:
            raise LedgerError(
                INVALID_MAPPING,
                "declare `amount_column`, or `debit_column` and/or `credit_column`",
                {},
            )
        if str(self.delimiter) == "":
            raise LedgerError(INVALID_MAPPING, "`delimiter` cannot be empty", {})
        if self.decimal_separator not in (".", ","):
            raise LedgerError(INVALID_MAPPING, "`decimal_separator` must be '.' or ','", {})
        if self.thousands_separator and self.thousands_separator == self.decimal_separator:
            raise LedgerError(
                INVALID_MAPPING,
                "`thousands_separator` and `decimal_separator` cannot be the same",
                {},
            )
        sample = date(2000, 1, 2)
        try:
            round_trip = datetime.strptime(
                sample.strftime(self.date_format), self.date_format
            ).date()
        except ValueError as exc:
            raise LedgerError(
                INVALID_MAPPING,
                f"`date_format` is not a strftime pattern that parses a date: {exc}",
                {"dateFormat": self.date_format},
            ) from exc
        if round_trip != sample:
            raise LedgerError(
                INVALID_MAPPING,
                "`date_format` must include day, month and year (it drops one of them)",
                {"dateFormat": self.date_format, "roundTrip": round_trip.isoformat()},
            )
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CsvMapping":
        if not isinstance(payload, dict):
            raise LedgerError(INVALID_MAPPING, "`mapping` must be an object", {})
        descriptions = payload.get("description_columns") or payload.get("descriptionColumns") or ()
        if isinstance(descriptions, str):
            descriptions = (descriptions,)
        return cls(
            date_column=str(payload.get("date_column") or payload.get("dateColumn") or ""),
            description_columns=tuple(str(item) for item in descriptions),
            amount_column=str(payload.get("amount_column") or payload.get("amountColumn") or ""),
            debit_column=str(payload.get("debit_column") or payload.get("debitColumn") or ""),
            credit_column=str(payload.get("credit_column") or payload.get("creditColumn") or ""),
            currency_column=str(payload.get("currency_column") or payload.get("currencyColumn") or ""),
            balance_column=str(payload.get("balance_column") or payload.get("balanceColumn") or ""),
            delimiter=str(payload.get("delimiter") or ","),
            date_format=str(payload.get("date_format") or payload.get("dateFormat") or "%Y-%m-%d"),
            decimal_separator=str(payload.get("decimal_separator") or payload.get("decimalSeparator") or "."),
            thousands_separator=str(
                payload.get("thousands_separator") or payload.get("thousandsSeparator") or ""
            ),
            skip_rows=int(payload.get("skip_rows") or payload.get("skipRows") or 0),
            default_currency=str(payload.get("default_currency") or payload.get("defaultCurrency") or ""),
        )


@dataclass(frozen=True)
class StatementRow:
    row_no: int
    date: str
    description: str
    amount: Decimal
    currency: str
    external_id: str
    balance: Optional[Decimal] = None
    raw: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rowNo": self.row_no,
            "date": self.date,
            "description": self.description,
            "amount": f"{q_money(self.amount):f}",
            "currency": self.currency,
            "externalId": self.external_id,
            "balance": None if self.balance is None else f"{q_money(self.balance):f}",
        }


@dataclass
class ParsedStatement:
    format: str
    currency: str
    rows: list[StatementRow] = field(default_factory=list)
    closing_balance: Optional[Decimal] = None
    warnings: list[str] = field(default_factory=list)
    skipped: int = 0

    @property
    def total_in(self) -> Decimal:
        return sum((row.amount for row in self.rows if row.amount > ZERO), ZERO)

    @property
    def total_out(self) -> Decimal:
        return sum((row.amount for row in self.rows if row.amount < ZERO), ZERO)

    def to_dict(self, *, rows: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "format": self.format,
            "currency": self.currency,
            "rowCount": len(self.rows),
            "skipped": self.skipped,
            "totalIn": f"{q_money(self.total_in):f}",
            "totalOut": f"{q_money(self.total_out):f}",
            "net": f"{q_money(self.total_in + self.total_out):f}",
            "closingBalance": (
                None if self.closing_balance is None else f"{q_money(self.closing_balance):f}"
            ),
            "warnings": list(self.warnings),
        }
        if rows:
            payload["rows"] = [row.to_dict() for row in self.rows]
        return payload


# ── primitives ────────────────────────────────────────────────────────────────


def parse_date(text: str, fmt: str) -> date:
    """Parse with the DECLARED format, then ISO. Anything else is refused."""
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty date")
    for pattern in (fmt, *_DATE_FORMATS):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"date {raw!r} does not match {fmt!r}")


def parse_decimal(text: Any, *, decimal_separator: str = ".",
                  thousands_separator: str = "") -> Decimal:
    """Parse a printed amount exactly. Parentheses mean negative.

    A float is never produced: the digits are cleaned and parsed as Decimal.
    """
    raw = str(text if text is not None else "").strip()
    if not raw:
        raise ValueError("empty amount")
    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative = True
        raw = raw[1:-1].strip()
    for symbol in _CURRENCY_SYMBOLS:
        raw = raw.replace(symbol, "")
    raw = raw.strip()
    if thousands_separator:
        raw = raw.replace(thousands_separator, "")
    if decimal_separator != ".":
        raw = raw.replace(decimal_separator, ".")
    if not raw or raw in ("-", "+"):
        raise ValueError("empty amount")
    try:
        amount = D(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"unparseable amount {text!r}") from exc
    return q_money(-amount if negative else amount)


def make_external_id(account_ref: str, when: str, amount: Decimal,
                     description: str, occurrence: int = 0) -> str:
    seed = f"{account_ref}|{when}|{q_money(amount):f}|{description}|{occurrence}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]


# ── entry point ───────────────────────────────────────────────────────────────


def parse_statement(
    content: str,
    fmt: str,
    *,
    mapping: Optional[CsvMapping] = None,
    account_ref: str = "",
    default_currency: str = "USD",
) -> ParsedStatement:
    kind = str(fmt or "").strip().lower()
    if kind not in FORMATS:
        raise LedgerError(
            UNSUPPORTED_STATEMENT_FORMAT,
            f"unsupported statement format {fmt!r}; expected one of {', '.join(FORMATS)}",
            {"format": str(fmt), "supported": list(FORMATS)},
        )
    if not isinstance(content, str) or not content.strip():
        raise LedgerError(INVALID_STATEMENT, "the statement is empty", {"format": kind})
    if kind == "csv":
        if mapping is None:
            raise LedgerError(INVALID_MAPPING, "a CSV import needs a column mapping", {})
        return _parse_csv(content, mapping.validate(), account_ref, default_currency)
    if kind == "ofx":
        return _parse_ofx(content, account_ref, default_currency)
    return _parse_qif(content, mapping, account_ref, default_currency)


# ── CSV ───────────────────────────────────────────────────────────────────────


def _parse_csv(content: str, mapping: CsvMapping, account_ref: str,
               default_currency: str) -> ParsedStatement:
    text = content.lstrip("\ufeff")
    lines = text.splitlines()
    if mapping.skip_rows:
        lines = lines[mapping.skip_rows:]
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=mapping.delimiter)
    if reader.fieldnames is None:
        raise LedgerError(INVALID_STATEMENT, "the CSV has no header row", {})
    fields = {(name or "").strip(): name for name in reader.fieldnames}
    required = [mapping.date_column]
    required += [c for c in (mapping.amount_column, mapping.debit_column,
                             mapping.credit_column) if c]
    missing = [name for name in required if name not in fields]
    if missing:
        raise LedgerError(
            INVALID_MAPPING,
            f"the CSV has no column(s) {', '.join(missing)}; found {', '.join(fields)}",
            {"missing": missing, "columns": list(fields)},
        )

    out = ParsedStatement(format="csv", currency=(default_currency or "USD").upper())
    occurrences: dict[str, int] = {}
    for index, raw_row in enumerate(reader, start=1):
        values = {(key or "").strip(): (value or "").strip()
                  for key, value in raw_row.items() if key is not None}
        if not any(values.get(name) for name in fields):
            out.skipped += 1
            continue
        try:
            when = parse_date(values.get(mapping.date_column, ""), mapping.date_format)
            amount = _csv_amount(values, mapping)
            if amount == ZERO:
                out.skipped += 1
                continue
        except ValueError as exc:
            raise LedgerError(
                IMPORT_ROW_INVALID,
                f"CSV row {index}: {exc}",
                {"row": index, "values": values},
            ) from exc
        description = " ".join(
            values.get(column, "") for column in mapping.description_columns
        ).strip()
        currency = (
            values.get(mapping.currency_column, "").upper()
            if mapping.currency_column else ""
        ) or (mapping.default_currency or out.currency)
        when_iso = when.isoformat()
        seed = f"{when_iso}|{amount:f}|{description}"
        occurrence = occurrences.get(seed, 0)
        occurrences[seed] = occurrence + 1
        balance: Optional[Decimal] = None
        if mapping.balance_column and values.get(mapping.balance_column):
            try:
                balance = parse_decimal(
                    values[mapping.balance_column],
                    decimal_separator=mapping.decimal_separator,
                    thousands_separator=mapping.thousands_separator,
                )
            except ValueError as exc:
                raise LedgerError(IMPORT_ROW_INVALID, f"CSV row {index}: {exc}",
                                  {"row": index}) from exc
        out.rows.append(StatementRow(
            row_no=index,
            date=when_iso,
            description=description,
            amount=amount,
            currency=currency.upper(),
            external_id=make_external_id(account_ref, when_iso, amount, description, occurrence),
            balance=balance,
            raw=values,
        ))
    _finish(out, account_ref)
    return out


def _csv_amount(values: dict[str, str], mapping: CsvMapping) -> Decimal:
    if mapping.amount_column:
        return parse_decimal(
            values.get(mapping.amount_column, ""),
            decimal_separator=mapping.decimal_separator,
            thousands_separator=mapping.thousands_separator,
        )
    debit = parse_decimal(
        values.get(mapping.debit_column, "0") or "0",
        decimal_separator=mapping.decimal_separator,
        thousands_separator=mapping.thousands_separator,
    ) if mapping.debit_column else ZERO
    credit = parse_decimal(
        values.get(mapping.credit_column, "0") or "0",
        decimal_separator=mapping.decimal_separator,
        thousands_separator=mapping.thousands_separator,
    ) if mapping.credit_column else ZERO
    return q_money(credit - debit)


# ── OFX ───────────────────────────────────────────────────────────────────────


def _tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>\s*([^<\r\n]*)", text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_ofx(content: str, account_ref: str, default_currency: str) -> ParsedStatement:
    currency = (_tag(content, "CURDEF") or default_currency or "USD").upper()
    out = ParsedStatement(format="ofx", currency=currency)
    blocks = re.split(r"<STMTTRN>", content, flags=re.IGNORECASE)[1:]
    if not blocks:
        raise LedgerError(INVALID_STATEMENT, "the OFX file has no <STMTTRN> records", {})
    occurrences: dict[str, int] = {}
    for index, block in enumerate(blocks, start=1):
        block = re.split(r"</?BANKTRANLIST>", block, maxsplit=1, flags=re.IGNORECASE)[0]
        posted = _tag(block, "DTPOSTED")
        if len(posted) < 8:
            raise LedgerError(
                IMPORT_ROW_INVALID, f"OFX transaction {index} has no usable DTPOSTED",
                {"row": index},
            )
        try:
            when = datetime.strptime(posted[:8], "%Y%m%d").date()
        except ValueError as exc:
            raise LedgerError(
                IMPORT_ROW_INVALID,
                f"OFX transaction {index} has an invalid DTPOSTED {posted!r}",
                {"row": index},
            ) from exc
        try:
            amount = q_money(D(_tag(block, "TRNAMT")))
        except (ValueError, TypeError) as exc:
            raise LedgerError(
                IMPORT_ROW_INVALID,
                f"OFX transaction {index} has an invalid TRNAMT {_tag(block, 'TRNAMT')!r}",
                {"row": index},
            ) from exc
        name = _tag(block, "NAME")
        memo = _tag(block, "MEMO")
        description = " ".join(part for part in (name, memo) if part).strip()
        when_iso = when.isoformat()
        fitid = _tag(block, "FITID")
        if fitid:
            external_id = f"ofx:{fitid}"
        else:
            seed = f"{when_iso}|{amount:f}|{description}"
            occurrence = occurrences.get(seed, 0)
            occurrences[seed] = occurrence + 1
            external_id = make_external_id(account_ref, when_iso, amount, description, occurrence)
        out.rows.append(StatementRow(
            row_no=index, date=when_iso, description=description, amount=amount,
            currency=currency, external_id=external_id, raw={"fitid": fitid},
        ))
    ledger_bal = re.search(r"<LEDGERBAL>.*?<BALAMT>\s*([^<\r\n]+)",
                           content, re.IGNORECASE | re.DOTALL)
    if ledger_bal:
        try:
            out.closing_balance = q_money(D(ledger_bal.group(1).strip()))
        except (ValueError, TypeError):
            out.warnings.append("the OFX LEDGERBAL amount could not be parsed; ignored")
    _finish(out, account_ref)
    return out


# ── QIF ───────────────────────────────────────────────────────────────────────


def _parse_qif(content: str, mapping: Optional[CsvMapping], account_ref: str,
               default_currency: str) -> ParsedStatement:
    fmt = mapping.date_format if mapping else "%m/%d/%Y"
    currency = (mapping.default_currency if mapping else "") or default_currency or "USD"
    out = ParsedStatement(format="qif", currency=currency.upper())
    occurrences: dict[str, int] = {}
    for index, record in enumerate(content.split("^"), start=1):
        fields: dict[str, str] = {}
        for line in record.splitlines():
            line = line.strip()
            if not line or line.startswith("!"):
                continue
            fields[line[0]] = line[1:].strip()
        if not fields:
            continue
        if "D" not in fields or "T" not in fields:
            out.warnings.append(f"QIF record {index} has no date/amount; skipped")
            out.skipped += 1
            continue
        try:
            when = parse_date(fields["D"], fmt)
        except ValueError as exc:
            raise LedgerError(
                IMPORT_ROW_INVALID,
                f"QIF record {index}: {exc}. Declare `date_format` explicitly "
                "(QIF day/month order is ambiguous).",
                {"row": index, "date": fields.get("D")},
            ) from exc
        try:
            amount = parse_decimal(fields["T"])
        except ValueError as exc:
            raise LedgerError(IMPORT_ROW_INVALID, f"QIF record {index}: {exc}",
                              {"row": index}) from exc
        if amount == ZERO:
            out.skipped += 1
            continue
        payee = fields.get("P", "")
        memo = fields.get("M", "")
        description = " ".join(part for part in (payee, memo) if part).strip()
        when_iso = when.isoformat()
        seed = f"{when_iso}|{amount:f}|{description}"
        occurrence = occurrences.get(seed, 0)
        occurrences[seed] = occurrence + 1
        out.rows.append(StatementRow(
            row_no=index, date=when_iso, description=description, amount=amount,
            currency=out.currency,
            external_id=make_external_id(account_ref, when_iso, amount, description, occurrence),
            raw=fields,
        ))
    _finish(out, account_ref)
    return out


def _finish(out: ParsedStatement, account_ref: str) -> None:
    """Order rows by date (stable) and refuse a statement with no usable rows."""
    if not out.rows:
        raise LedgerError(
            INVALID_STATEMENT,
            "no usable transactions were found in the statement",
            {"format": out.format, "skipped": out.skipped},
        )
    out.rows.sort(key=lambda row: (row.date, row.row_no))
    seen: set[str] = set()
    for row in out.rows:
        if row.external_id in seen:
            # The bank repeated its own FITID, or an occurrence counter collided.
            # Silently merging them would drop a transaction, so say so.
            raise LedgerError(
                IMPORT_ROW_INVALID,
                f"two statement rows share the identity {row.external_id!r} "
                f"(row {row.row_no}); the file cannot be imported unambiguously",
                {"row": row.row_no, "externalId": row.external_id},
            )
        seen.add(row.external_id)


__all__ = [
    "CsvMapping",
    "FORMATS",
    "ParsedStatement",
    "StatementRow",
    "make_external_id",
    "parse_date",
    "parse_decimal",
    "parse_statement",
]

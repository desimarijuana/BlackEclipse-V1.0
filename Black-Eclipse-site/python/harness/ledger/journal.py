"""Posting rules — the heart of the double-entry contract.

A posting is accepted only when ALL of the following hold. There is no partial
acceptance and no auto-correction:

  1. At least two lines.
  2. Each line names an existing, ACTIVE account in this ledger.
  3. Each line carries exactly one side: a positive debit XOR a positive credit.
     Negative amounts are refused (use the other side) so a "credit of -50"
     can never masquerade as a debit.
  4. Amounts are quantized to money places at the boundary, then Σ base debit
     must EQUAL Σ base credit exactly. A difference of one cent is a refusal
     (`UNBALANCED_ENTRY`) carrying the exact difference — never rounded away.
  5. Currency: a line in the base currency needs no rate. A line in another
     currency MUST carry a positive `fx_rate`, because inventing one is
     fabricating a number. The base amount is `q_money(amount × rate)`.
  6. The entry date lands in an OPEN fiscal period (see `periods.require_open`).

Immutability is enforced by the store, not by convention: there is no update path
for a posted entry. A correction is `reverse_lines()` on the original, posted as
a NEW entry that links back to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from .errors import (
    ACCOUNT_INACTIVE,
    ACCOUNT_NOT_FOUND,
    CURRENCY_MISMATCH,
    DUPLICATE_LINE_SIDE,
    EMPTY_LINE,
    INVALID_AMOUNT,
    INVALID_ENTRY,
    MISSING_FX,
    NEGATIVE_AMOUNT,
    UNBALANCED_ENTRY,
    LedgerError,
)
from .models import Account, LineSpec
from .money import D, ZERO, q_money, q_rate

MAX_LINES = 500
MAX_MEMO = 1000
MAX_DIMENSIONS = 20


@dataclass
class ValidatedLine:
    line_no: int
    account: Account
    debit: Decimal
    credit: Decimal
    base_debit: Decimal
    base_credit: Decimal
    currency: str
    fx_rate: Optional[Decimal]
    memo: Optional[str]
    dimensions: dict[str, str] = field(default_factory=dict)
    base_only: bool = False


def _amount(value: object, *, field_name: str, line_no: int) -> Decimal:
    if value is None or value == "":
        return ZERO
    try:
        amount = D(value)
    except (ValueError, TypeError) as exc:
        raise LedgerError(
            INVALID_AMOUNT,
            f"line {line_no}: `{field_name}` is not a decimal literal ({value!r})",
            {"line": line_no, "field": field_name},
        ) from exc
    if amount < ZERO:
        raise LedgerError(
            NEGATIVE_AMOUNT,
            f"line {line_no}: `{field_name}` must be >= 0; post the other side instead",
            {"line": line_no, "field": field_name, "value": str(value)},
        )
    return q_money(amount)


def _memo(value: object, *, line_no: int) -> Optional[str]:
    text = str(value or "").strip()
    if len(text) > MAX_MEMO:
        raise LedgerError(
            INVALID_ENTRY,
            f"line {line_no}: memo exceeds {MAX_MEMO} characters",
            {"line": line_no},
        )
    return text or None


def _dimensions(value: object, *, line_no: int) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise LedgerError(
            INVALID_ENTRY, f"line {line_no}: `dimensions` must be an object", {"line": line_no}
        )
    if len(value) > MAX_DIMENSIONS:
        raise LedgerError(
            INVALID_ENTRY,
            f"line {line_no}: at most {MAX_DIMENSIONS} dimensions",
            {"line": line_no},
        )
    out: dict[str, str] = {}
    for key, item in value.items():
        clean_key = str(key).strip()
        clean_val = str(item).strip()
        if not clean_key or len(clean_key) > 40 or len(clean_val) > 120:
            raise LedgerError(
                INVALID_ENTRY, f"line {line_no}: invalid dimension {key!r}", {"line": line_no}
            )
        out[clean_key] = clean_val
    return out


def validate_lines(
    lines: Sequence[LineSpec | dict],
    accounts_by_code: dict[str, Account],
    *,
    base_currency: str,
) -> list[ValidatedLine]:
    """Validate a whole posting. Returns base amounts; raises on any violation."""
    if not isinstance(lines, (list, tuple)) or len(lines) < 2:
        raise LedgerError(
            INVALID_ENTRY,
            "a journal entry needs at least two lines (one debit and one credit)",
            {"lineCount": len(lines) if isinstance(lines, (list, tuple)) else 0},
        )
    if len(lines) > MAX_LINES:
        raise LedgerError(
            INVALID_ENTRY, f"an entry may have at most {MAX_LINES} lines", {"lineCount": len(lines)}
        )

    base = str(base_currency or "USD").strip().upper()
    validated: list[ValidatedLine] = []
    for index, raw in enumerate(lines, start=1):
        spec = _as_spec(raw, index)
        code = str(spec.account_code or "").strip()
        if not code:
            raise LedgerError(EMPTY_LINE, f"line {index}: `account_code` is required", {"line": index})
        account = accounts_by_code.get(code)
        if account is None:
            raise LedgerError(
                ACCOUNT_NOT_FOUND,
                f"line {index}: account {code!r} does not exist in this ledger",
                {"line": index, "accountCode": code},
            )
        if not account.active:
            raise LedgerError(
                ACCOUNT_INACTIVE,
                f"line {index}: account {code!r} is inactive",
                {"line": index, "accountCode": code},
            )

        debit = _amount(spec.debit, field_name="debit", line_no=index)
        credit = _amount(spec.credit, field_name="credit", line_no=index)
        if debit == ZERO and credit == ZERO:
            raise LedgerError(
                EMPTY_LINE,
                f"line {index}: exactly one of debit/credit must be greater than zero",
                {"line": index},
            )
        if debit != ZERO and credit != ZERO:
            raise LedgerError(
                DUPLICATE_LINE_SIDE,
                f"line {index}: a line cannot be both a debit and a credit",
                {"line": index, "debit": str(debit), "credit": str(credit)},
            )

        fx_rate_supplied = spec.fx_rate is not None and str(spec.fx_rate).strip() != ""

        if spec.base_only:
            # A base-currency adjustment to the carrying value. The account's
            # transaction-currency restriction does not apply (the foreign
            # balance is deliberately untouched); an fx rate is meaningless here.
            currency = str(spec.currency or base).strip().upper()
            if fx_rate_supplied:
                raise LedgerError(
                    MISSING_FX,
                    f"line {index}: a base-only line must not carry an fx_rate",
                    {"line": index},
                )
            if currency != base:
                raise LedgerError(
                    CURRENCY_MISMATCH,
                    f"line {index}: a base-only line must be in the base currency ({base})",
                    {"line": index, "currency": currency},
                )
            base_debit, base_credit = debit, credit
            validated.append(
                ValidatedLine(
                    line_no=index,
                    account=account,
                    debit=debit,
                    credit=credit,
                    base_debit=base_debit,
                    base_credit=base_credit,
                    currency=currency,
                    fx_rate=None,
                    memo=_memo(spec.memo, line_no=index),
                    dimensions=_dimensions(spec.dimensions, line_no=index),
                    base_only=True,
                )
            )
            continue

        currency = str(spec.currency or account.currency or base).strip().upper()
        if account.currency and currency != account.currency.upper():
            raise LedgerError(
                CURRENCY_MISMATCH,
                f"line {index}: account {code!r} is denominated in {account.currency}, "
                f"not {currency}",
                {"line": index, "accountCode": code, "accountCurrency": account.currency,
                 "lineCurrency": currency},
            )

        rate: Optional[Decimal] = None
        if currency == base:
            if fx_rate_supplied:
                declared = None
                try:
                    declared = D(spec.fx_rate)
                except (ValueError, TypeError) as exc:
                    raise LedgerError(
                        MISSING_FX, f"line {index}: invalid fx_rate", {"line": index}
                    ) from exc
                if declared != 1:
                    raise LedgerError(
                        MISSING_FX,
                        f"line {index}: account is in the base currency ({base}); "
                        "an fx_rate applies only to a foreign-currency line",
                        {"line": index},
                    )
            base_debit, base_credit = debit, credit
        else:
            if spec.fx_rate is None or str(spec.fx_rate).strip() == "":
                raise LedgerError(
                    MISSING_FX,
                    f"line {index}: line is in {currency} but no fx_rate was supplied",
                    {"line": index, "currency": currency, "baseCurrency": base},
                )
            try:
                rate = q_rate(D(spec.fx_rate))
            except (ValueError, TypeError) as exc:
                raise LedgerError(
                    MISSING_FX, f"line {index}: invalid fx_rate", {"line": index}
                ) from exc
            if rate <= ZERO:
                raise LedgerError(
                    MISSING_FX, f"line {index}: fx_rate must be > 0", {"line": index}
                )
            base_debit = q_money(debit * rate)
            base_credit = q_money(credit * rate)

        validated.append(
            ValidatedLine(
                line_no=index,
                account=account,
                debit=debit,
                credit=credit,
                base_debit=base_debit,
                base_credit=base_credit,
                currency=currency,
                fx_rate=rate,
                memo=_memo(spec.memo, line_no=index),
                dimensions=_dimensions(spec.dimensions, line_no=index),
            )
        )

    assert_balanced(validated)
    return validated


def _as_spec(raw: LineSpec | dict, index: int) -> LineSpec:
    if isinstance(raw, LineSpec):
        return raw
    if not isinstance(raw, dict):
        raise LedgerError(
            INVALID_ENTRY, f"line {index}: expected an object", {"line": index}
        )
    rate = raw.get("fx_rate")
    if rate in (None, ""):
        rate = raw.get("fxRate")
    return LineSpec(
        account_code=str(raw.get("account_code") or raw.get("accountCode") or ""),
        debit=D(raw.get("debit") or 0),
        credit=D(raw.get("credit") or 0),
        currency=str(raw.get("currency") or ""),
        fx_rate=None if rate in (None, "") else rate,
        memo=raw.get("memo"),
        dimensions=raw.get("dimensions") or {},
        base_only=bool(raw.get("base_only") or raw.get("baseOnly") or False),
    )


def totals(lines: Iterable[ValidatedLine]) -> tuple[Decimal, Decimal]:
    debit = ZERO
    credit = ZERO
    for line in lines:
        debit += line.base_debit
        credit += line.base_credit
    return debit, credit


def assert_balanced(lines: Iterable[ValidatedLine]) -> None:
    """Σ base debit == Σ base credit, exactly. Refuse otherwise."""
    debit, credit = totals(lines)
    if debit != credit:
        difference = debit - credit
        raise LedgerError(
            UNBALANCED_ENTRY,
            f"entry does not balance: debits {debit} vs credits {credit} "
            f"(difference {difference})",
            {
                "totalDebit": f"{debit:f}",
                "totalCredit": f"{credit:f}",
                "difference": f"{difference:f}",
            },
        )
    if debit == ZERO:
        raise LedgerError(
            INVALID_ENTRY, "an entry with a zero total is not a posting", {"totalDebit": "0"}
        )


def reverse_lines(lines: Sequence[ValidatedLine]) -> list[LineSpec]:
    """The mirror of an entry: every debit becomes a credit and vice versa."""
    mirrored: list[LineSpec] = []
    for line in lines:
        mirrored.append(
            LineSpec(
                account_code=line.account.code,
                debit=line.credit,
                credit=line.debit,
                currency=line.currency,
                fx_rate=line.fx_rate,
                memo=line.memo,
                dimensions=dict(line.dimensions or {}),
                base_only=line.base_only,
            )
        )
    return mirrored


def reverse_journal_lines(lines: Sequence[Any]) -> list[LineSpec]:
    """Mirror a PERSISTED entry's lines (a `JournalLine` carries the same sides)."""
    return [
        LineSpec(
            account_code=line.account_code,
            debit=line.credit,
            credit=line.debit,
            currency=line.currency,
            fx_rate=line.fx_rate,
            memo=line.memo,
            dimensions=dict(line.dimensions or {}),
            base_only=getattr(line, "base_only", False),
        )
        for line in lines
    ]


__all__ = [
    "MAX_LINES",
    "MAX_MEMO",
    "ValidatedLine",
    "assert_balanced",
    "reverse_journal_lines",
    "reverse_lines",
    "totals",
    "validate_lines",
]

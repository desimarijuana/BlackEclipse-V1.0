"""Tax codes — configured data, never a bundled rate.

There is deliberately **no built-in table of tax rates**. A rate is a fact about a
jurisdiction on a date; shipping one would be a fabricated financial fact that
silently goes stale. Instead:

  * the operator (or a pack file they trust) configures a `TaxCode` per
    jurisdiction + rate + GL account;
  * a document that names a tax code the ledger does not have is refused with
    `TAX_CODE_NOT_FOUND`;
  * a pack for a jurisdiction that is not configured is refused with
    `UNSUPPORTED_TAX_JURISDICTION`, never approximated.

Rounding: tax is computed **per line** and quantized half-even to money places,
so the sum of the lines is the tax total — there is no header-level re-rounding
that could disagree with the lines.

Inclusive pricing is supported (`price_includes_tax`): the line amount already
contains tax, the net is recovered by division, and the tax is the remainder, so
`net + tax == amount` exactly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from .errors import TAX_CODE_INVALID, LedgerError
from .money import D, ZERO, q_money, q_rate

TAX_KINDS = ("VAT", "GST", "SALES_TAX", "OTHER")


@dataclass
class TaxCode:
    id: str
    ledger_id: str
    code: str
    name: str
    jurisdiction: str
    rate: Decimal
    kind: str = "VAT"
    account_code: str = ""
    price_includes_tax: bool = False
    active: bool = True
    created_at: str = ""

    @property
    def label(self) -> str:
        return f"{self.code} ({self.rate * 100:.2f}%)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ledgerId": self.ledger_id,
            "code": self.code,
            "name": self.name,
            "jurisdiction": self.jurisdiction,
            "rate": f"{self.rate:f}",
            "kind": self.kind,
            "accountCode": self.account_code,
            "priceIncludesTax": self.price_includes_tax,
            "active": self.active,
            "createdAt": self.created_at,
        }


def build_tax_code(
    ledger_id: str,
    *,
    code: str,
    name: str,
    jurisdiction: str,
    rate: object,
    account_code: str,
    kind: str = "VAT",
    price_includes_tax: bool = False,
    tax_id: Optional[str] = None,
    created_at: str = "",
) -> TaxCode:
    clean_code = str(code or "").strip().upper()
    if not clean_code or len(clean_code) > 32:
        raise LedgerError(TAX_CODE_INVALID, "a tax code needs a code of 1-32 characters",
                          {"code": str(code)})
    clean_jurisdiction = str(jurisdiction or "").strip().upper()
    if not clean_jurisdiction:
        raise LedgerError(TAX_CODE_INVALID, "a tax code needs a jurisdiction",
                          {"code": clean_code})
    try:
        value = q_rate(D(rate))
    except (ValueError, TypeError) as exc:
        raise LedgerError(TAX_CODE_INVALID, "`rate` must be a decimal fraction (0.20 = 20%)",
                          {"rate": str(rate)}) from exc
    if value < ZERO or value >= 1:
        raise LedgerError(
            TAX_CODE_INVALID,
            "`rate` must be a fraction in [0, 1): 0.20 means 20%, not 20",
            {"rate": f"{value:f}"},
        )
    clean_kind = str(kind or "VAT").strip().upper()
    if clean_kind not in TAX_KINDS:
        raise LedgerError(TAX_CODE_INVALID,
                          f"`kind` must be one of {', '.join(TAX_KINDS)}", {"kind": str(kind)})
    if not str(account_code or "").strip():
        raise LedgerError(TAX_CODE_INVALID,
                          "a tax code needs `account_code` (where the tax posts)",
                          {"code": clean_code})
    return TaxCode(
        id=tax_id or f"tax_{uuid.uuid4().hex[:20]}",
        ledger_id=ledger_id,
        code=clean_code,
        name=str(name or clean_code).strip(),
        jurisdiction=clean_jurisdiction,
        rate=value,
        kind=clean_kind,
        account_code=str(account_code).strip(),
        price_includes_tax=bool(price_includes_tax),
        created_at=created_at,
    )


def split_net_and_tax(amount: Decimal, code: TaxCode) -> tuple[Decimal, Decimal]:
    """`(net, tax)` for one line, with `net + tax == amount` exactly."""
    gross = q_money(amount)
    if code.rate == ZERO:
        return gross, ZERO
    if code.price_includes_tax:
        net = q_money(gross / (Decimal(1) + code.rate))
        return net, q_money(gross - net)
    return gross, q_money(gross * code.rate)


def jurisdiction_pack(jurisdiction: str, codes: list[dict[str, Any]],
                      ledger_id: str, *, make_id=None, created_at: str = "") -> list[TaxCode]:
    """Validate a caller-supplied pack for ONE jurisdiction.

    This is the only way a set of rates enters a ledger: a file or payload the
    operator chose. A code whose jurisdiction does not match the pack is refused
    rather than quietly filed under the wrong country.
    """
    target = str(jurisdiction or "").strip().upper()
    if not target:
        raise LedgerError(
            UNSUPPORTED_TAX_JURISDICTION,
            "a tax pack must name the jurisdiction it belongs to",
            {},
        )
    if not isinstance(codes, list) or not codes:
        raise LedgerError(
            UNSUPPORTED_TAX_JURISDICTION,
            f"the {target} tax pack carries no codes",
            {"jurisdiction": target},
        )
    out: list[TaxCode] = []
    for entry in codes:
        if not isinstance(entry, dict):
            raise LedgerError(TAX_CODE_INVALID, "each pack entry must be an object", {})
        declared = str(entry.get("jurisdiction") or target).strip().upper()
        if declared != target:
            raise LedgerError(
                UNSUPPORTED_TAX_JURISDICTION,
                f"a code declares jurisdiction {declared} inside the {target} pack",
                {"jurisdiction": target, "code": entry.get("code")},
            )
        out.append(build_tax_code(
            ledger_id,
            code=str(entry.get("code") or ""),
            name=str(entry.get("name") or entry.get("code") or ""),
            jurisdiction=target,
            rate=entry.get("rate"),
            account_code=str(entry.get("account_code") or entry.get("accountCode") or ""),
            kind=str(entry.get("kind") or "VAT"),
            price_includes_tax=bool(entry.get("price_includes_tax")
                                    or entry.get("priceIncludesTax") or False),
            tax_id=make_id() if make_id else None,
            created_at=created_at,
        ))
    return out


__all__ = [
    "TAX_KINDS",
    "TaxCode",
    "build_tax_code",
    "jurisdiction_pack",
    "split_net_and_tax",
]

"""Customers and vendors — the parties an AR/AP document belongs to.

A party is deliberately thin: a name, a kind, optional contact/tax identifiers and
a payment term. The ledger keeps no balance ON the party — the balance is the open
documents, derived on every read. That is what makes aging impossible to drift
from the documents.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from .errors import PARTY_INVALID, LedgerError

PARTY_KINDS = ("CUSTOMER", "VENDOR")


@dataclass
class Party:
    id: str
    ledger_id: str
    name: str
    kind: str
    email: Optional[str] = None
    tax_id: Optional[str] = None
    currency: str = ""
    payment_terms_days: int = 30
    active: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ledgerId": self.ledger_id,
            "name": self.name,
            "kind": self.kind,
            "email": self.email,
            "taxId": self.tax_id,
            "currency": self.currency,
            "paymentTermsDays": self.payment_terms_days,
            "active": self.active,
            "createdAt": self.created_at,
        }


def build_party(
    ledger_id: str,
    *,
    name: str,
    kind: str,
    email: Optional[str] = None,
    tax_id: Optional[str] = None,
    currency: str = "",
    payment_terms_days: int = 30,
    party_id: Optional[str] = None,
    created_at: str = "",
) -> Party:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise LedgerError(PARTY_INVALID, "a party needs a name", {})
    if len(clean_name) > 120:
        raise LedgerError(PARTY_INVALID, "a party name may be at most 120 characters",
                          {"name": clean_name})
    clean_kind = str(kind or "").strip().upper()
    if clean_kind not in PARTY_KINDS:
        raise LedgerError(
            PARTY_INVALID,
            f"`kind` must be one of {', '.join(PARTY_KINDS)}",
            {"kind": str(kind)},
        )
    try:
        terms = int(payment_terms_days)
    except (TypeError, ValueError) as exc:
        raise LedgerError(PARTY_INVALID, "`payment_terms_days` must be an integer", {}) from exc
    if not 0 <= terms <= 365:
        raise LedgerError(PARTY_INVALID, "`payment_terms_days` must be 0..365",
                          {"paymentTermsDays": terms})
    clean_currency = str(currency or "").strip().upper()
    if clean_currency and (len(clean_currency) != 3 or not clean_currency.isalpha()):
        raise LedgerError(PARTY_INVALID, "`currency` must be a 3-letter ISO code or blank",
                          {"currency": clean_currency})
    clean_email = str(email or "").strip() or None
    if clean_email and ("@" not in clean_email or len(clean_email) > 254):
        raise LedgerError(PARTY_INVALID, "`email` is not a usable address",
                          {"email": clean_email})
    return Party(
        id=party_id or f"pty_{uuid.uuid4().hex[:20]}",
        ledger_id=ledger_id,
        name=clean_name,
        kind=clean_kind,
        email=clean_email,
        tax_id=(str(tax_id or "").strip() or None),
        currency=clean_currency,
        payment_terms_days=terms,
        created_at=created_at,
    )


__all__ = ["PARTY_KINDS", "Party", "build_party"]

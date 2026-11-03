"""Shared helpers for the general-ledger test suite."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Optional

from harness.ledger.service import LedgerService
from harness.ledger.store import LedgerStore
from harness.persistence import AgentMemoryStore


def make_service(tmp_path: Optional[str] = None) -> LedgerService:
    base = str(tmp_path) if tmp_path else tempfile.mkdtemp(prefix="be-ledger-")
    path = os.path.join(base, "ledger-test.db")
    return LedgerService(LedgerStore(AgentMemoryStore(path)))


def make_ledger(
    service: LedgerService,
    *,
    template: str = "standard",
    currency: str = "USD",
    month: int = 1,
    owner: Optional[str] = None,
) -> str:
    return service.create_ledger(
        "Test Books", base_currency=currency, chart_template=template,
        fiscal_year_start_month=month, owner_id=owner,
    )["id"]


def line(code: str, *, debit: str = "0", credit: str = "0", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"account_code": code, "debit": debit, "credit": credit}
    payload.update(extra)
    return payload


def post(service: LedgerService, ledger_id: str, entry_date: str,
         lines: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    return service.post(ledger_id, entry_date=entry_date, lines=lines, **kwargs)


def balances(service: LedgerService, ledger_id: str, as_of: str) -> dict[str, str]:
    """Closing balance per account code, as exact strings."""
    trial = service.trial_balance(ledger_id, as_of=as_of)
    out: dict[str, str] = {}
    for row in trial["rows"]:
        out[row["code"]] = row["closingDebit"] if row["closingDebit"] != "0.00000000" \
            else row["closingCredit"]
    return out

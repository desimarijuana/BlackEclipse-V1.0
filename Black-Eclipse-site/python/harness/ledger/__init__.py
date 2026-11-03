"""The General Ledger — a double-entry book of record for real accounting work.

The Portfolio Accounting Engine answers "what am I holding and what is it worth".
This package answers a different question: "what did the business earn, owe, own
and spend, and can you prove it from the entries". They are separate books on
purpose — one is a securities ledger, the other a company ledger.

Layout (each file owns exactly one idea):

  money.py        Decimal arithmetic — a RE-EXPORT of `portfolio/money.py`
  models.py       typed contracts + the closed vocabularies
  errors.py       structured, named refusals
  accounts.py     chart-of-accounts templates (data) + account validation
  journal.py      posting rules: balance, sides, FX, no negative amounts
  periods.py      the monthly fiscal calendar and the OPEN/CLOSED/LOCKED lock
  statements.py   trial balance, balance sheet, P&L, cash flow, close check
  store.py        persistence on the ONE `agent-memory.db` (append-only)
  service.py      the facade the tools and routes share
  tools.py        agent tools (flat `ledger_*` names)
  authorizers.py  the `ledger_write` single-use approval layer
  bootstrap.py    boot wiring, called once from `AgenticService.__init__`

Invariants this package treats as non-negotiable:

  1. A posting balances exactly, or it does not happen.
  2. A posted entry is never mutated — corrections are reversing entries.
  3. Statements are derived from postings on every read; nothing is cached.
  4. A number that cannot be computed is reported as unavailable, never invented.
"""

from __future__ import annotations

__all__ = ["LedgerService", "LedgerStore"]


def __getattr__(name: str):  # lazy, so importing the package stays cheap
    if name == "LedgerService":
        from .service import LedgerService

        return LedgerService
    if name == "LedgerStore":
        from .store import LedgerStore

        return LedgerStore
    raise AttributeError(name)

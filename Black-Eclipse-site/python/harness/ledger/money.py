"""Decimal arithmetic for the General Ledger — the portfolio helpers, reused.

The Portfolio Accounting Engine already settled the money policy for this
runtime: `Decimal` everywhere, 34 significant digits in the working context,
quantization only at the output boundary. A general ledger that invented a
second money type would be a second source of truth for what "1.00" means.

This module is a deliberate re-export, not a fork. If the policy changes it
changes ONCE, in `portfolio/money.py`.
"""

from __future__ import annotations

from ..portfolio.money import (  # noqa: F401 - re-exported on purpose
    MONEY_PLACES,
    ONE,
    RATE_PLACES,
    ZERO,
    D,
    D_or_none,
    localcontext,
    money_str,
    q_money,
    q_rate,
    to_float,
)

__all__ = [
    "D",
    "D_or_none",
    "ZERO",
    "ONE",
    "MONEY_PLACES",
    "RATE_PLACES",
    "q_money",
    "q_rate",
    "money_str",
    "to_float",
    "localcontext",
]

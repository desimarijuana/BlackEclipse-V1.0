"""Portfolio Accounting Engine.

The transaction ledger is the source of truth: transactions → tax lots →
positions → valuation → P&L → exposure → allocation → performance → risk →
rebalancing. Money/quantity are Decimal; every price carries provenance and a
freshness class; a missing input is reported as UNAVAILABLE, never fabricated.

Consumed by the agent tools (`tools.py`), the HTTP router
(`routers/portfolio.py`) and — by design — the future Backtesting Engine, which
reuses the SAME accounting core with simulated transactions.
"""

from __future__ import annotations

from .accounting import AccountingResult, compute_accounting
from .models import CostBasisMethod, Transaction, TransactionType
from .service import PortfolioService

__all__ = [
    "AccountingResult",
    "compute_accounting",
    "CostBasisMethod",
    "Transaction",
    "TransactionType",
    "PortfolioService",
]

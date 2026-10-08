"""Additive migration: an old portfolio table gains the new columns safely.

Simulates a database created BEFORE `basisAdjustment`/`lotSelection` existed,
then proves `PortfolioStore` adds the columns on open (non-destructively) and a
transaction using them round-trips.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from harness.persistence import AgentMemoryStore
from harness.portfolio.models import Transaction, TransactionType
from harness.portfolio.store import PortfolioStore

_OLD_DDL = """
CREATE TABLE Portfolio (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, baseCurrency TEXT NOT NULL DEFAULT 'USD',
  ownerId TEXT, description TEXT, costBasisMethod TEXT NOT NULL DEFAULT 'FIFO',
  currency TEXT NOT NULL DEFAULT 'USD', status TEXT NOT NULL DEFAULT 'ACTIVE',
  createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL
);
CREATE TABLE PortfolioTransaction (
  id TEXT PRIMARY KEY, portfolioId TEXT NOT NULL, accountId TEXT, instrumentId TEXT,
  symbol TEXT, assetType TEXT, txnType TEXT NOT NULL, quantity TEXT NOT NULL DEFAULT '0',
  price TEXT, grossAmount TEXT, fees TEXT NOT NULL DEFAULT '0', taxes TEXT NOT NULL DEFAULT '0',
  netAmount TEXT, currency TEXT NOT NULL DEFAULT 'USD', fxRate TEXT, tradeDate TEXT,
  settlementDate TEXT, timestamp TEXT, externalId TEXT, source TEXT NOT NULL DEFAULT 'manual',
  notes TEXT, correctionOf TEXT, createdBy TEXT, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL
);
INSERT INTO Portfolio (id, name, createdAt, updatedAt) VALUES ('pf-old', 'Legacy', '2020-01-01', '2020-01-01');
INSERT INTO PortfolioTransaction (id, portfolioId, txnType, quantity, createdAt, updatedAt)
VALUES ('tx-old', 'pf-old', 'BUY', '5', '2020-01-01', '2020-01-01');
"""


def test_migration_adds_columns_and_preserves_rows(tmp_path):
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(str(path))
    con.executescript(_OLD_DDL)
    con.commit()
    con.close()

    store = AgentMemoryStore(str(path))
    portfolio = PortfolioStore(store)  # runs the additive migration

    cols = {r["name"] for r in store._db.execute("PRAGMA table_info(PortfolioTransaction)").fetchall()}
    assert "basisAdjustment" in cols
    assert "lotSelection" in cols
    # the pre-existing row is intact
    legacy = portfolio.list_transactions("pf-old")
    assert len(legacy) == 1
    assert legacy[0].id == "tx-old"

    # a new transaction using the added columns round-trips
    tx = Transaction(
        portfolio_id="pf-old", transaction_type=TransactionType.COST_BASIS_ADJUSTMENT,
        symbol="X", quantity=Decimal("0"), basis_adjustment=Decimal("-10"),
    )
    portfolio.append_transaction(tx)
    fetched = portfolio.get_transaction(tx.id)
    assert fetched is not None
    assert fetched.basis_adjustment == Decimal("-10")

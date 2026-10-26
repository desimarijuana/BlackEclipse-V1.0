"""Durable PAPER trading account for the Graph Studio execution adapter.

A paper fill is a simulation, but a SCHEDULED paper graph must remember what it
already holds. This store keeps one cash/positions row per account plus an
append-only fill log on the SAME `agent-memory.db` connection. It never contacts a
broker and never records a live order.

Accounting is deliberately simple and honest: cash and the cost basis of open
positions. It is not a mark-to-market valuation, and the fill price is always
the one the graph supplied.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..persistence import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS GraphPaperAccount (
  accountId   TEXT PRIMARY KEY,
  cash        REAL NOT NULL,
  positions   TEXT NOT NULL DEFAULT '{}',
  realizedPnl REAL NOT NULL DEFAULT 0,
  createdAt   TEXT NOT NULL,
  updatedAt   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS GraphPaperFill (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  accountId   TEXT NOT NULL,
  runId       TEXT,
  nodeId      TEXT,
  symbol      TEXT NOT NULL,
  side        TEXT NOT NULL,
  quantity    REAL NOT NULL,
  price       REAL NOT NULL,
  notional    REAL NOT NULL,
  commission  REAL NOT NULL DEFAULT 0,
  createdAt   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_paper_fill_account ON GraphPaperFill(accountId, id);
"""


def _loads(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class PaperAccountError(ValueError):
    """A paper-account operation the caller must see (bad state, missing store)."""


class PaperAccountStore:
    """Cash + positions + realized PnL for PAPER accounts."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def _row(self, account_id: str) -> Optional[Any]:
        return self._db.execute(
            "SELECT * FROM GraphPaperAccount WHERE accountId=?", (account_id,)
        ).fetchone()

    def snapshot(self, account_id: str, *, initial_cash: float = 100_000.0) -> dict[str, Any]:
        row = self._row(account_id)
        if row is None:
            return {
                "accountId": account_id,
                "cash": float(initial_cash),
                "positions": {},
                "realizedPnl": 0.0,
                "bookValue": float(initial_cash),
                "createdAt": None,
                "updatedAt": None,
            }
        return self._snapshot(row)

    def _snapshot(self, row: Any) -> dict[str, Any]:
        positions = _loads(row["positions"], {})
        book = float(row["cash"]) + sum(
            float(item.get("quantity") or 0) * float(item.get("averagePrice") or 0)
            for item in positions.values()
            if isinstance(item, dict)
        )
        return {
            "accountId": row["accountId"],
            "cash": round(float(row["cash"]), 8),
            "positions": positions,
            "realizedPnl": round(float(row["realizedPnl"]), 8),
            "bookValue": round(book, 8),
            "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
        }

    def apply_fill(
        self,
        account_id: str,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        commission: float = 0.0,
        initial_cash: float = 100_000.0,
        run_id: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Apply ONE fill atomically and return the post-fill account snapshot."""
        if side not in ("buy", "sell"):
            raise PaperAccountError("side must be buy or sell")
        if quantity <= 0 or price <= 0:
            raise PaperAccountError("quantity and price must be positive")
        now = now_iso()
        # BEGIN IMMEDIATE takes the write lock up front; busy_timeout makes a
        # second process wait instead of failing on a read->write upgrade.
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._row(account_id)
            if row is None:
                cash = float(initial_cash)
                positions: dict[str, Any] = {}
                realized = 0.0
                created = now
                self._db.execute(
                    "INSERT INTO GraphPaperAccount (accountId, cash, positions, realizedPnl, createdAt, updatedAt)"
                    " VALUES (?, ?, '{}', 0, ?, ?)",
                    (account_id, cash, now, now),
                )
            else:
                cash = float(row["cash"])
                positions = _loads(row["positions"], {})
                realized = float(row["realizedPnl"])
                created = row["createdAt"]

            delta = quantity if side == "buy" else -quantity
            notional = price * quantity
            current = positions.get(symbol) or {"quantity": 0.0, "averagePrice": 0.0}
            held = float(current.get("quantity") or 0.0)
            average = float(current.get("averagePrice") or 0.0)
            closing = min(abs(delta), abs(held)) if held and delta * held < 0 else 0.0
            if closing:
                realized += (price - average) * closing * (1.0 if held > 0 else -1.0)

            new_qty = held + delta
            if abs(new_qty) < 1e-12:
                positions.pop(symbol, None)
            elif held == 0 or held * new_qty < 0:
                positions[symbol] = {"quantity": round(new_qty, 8), "averagePrice": round(price, 8)}
            elif held * delta > 0:
                total = abs(held) + abs(delta)
                positions[symbol] = {
                    "quantity": round(new_qty, 8),
                    "averagePrice": round((abs(held) * average + abs(delta) * price) / total, 8),
                }
            else:
                positions[symbol] = {"quantity": round(new_qty, 8), "averagePrice": average}

            cash += -notional - commission if side == "buy" else notional - commission
            self._db.execute(
                "UPDATE GraphPaperAccount SET cash=?, positions=?, realizedPnl=?, updatedAt=?"
                " WHERE accountId=?",
                (cash, json.dumps(positions, sort_keys=True), realized, now, account_id),
            )
            self._db.execute(
                "INSERT INTO GraphPaperFill"
                " (accountId, runId, nodeId, symbol, side, quantity, price, notional, commission, createdAt)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (account_id, run_id, node_id, symbol, side, quantity, price, notional, commission, now),
            )
            self._db.execute("COMMIT")
        except Exception:
            try:
                self._db.execute("ROLLBACK")
            except Exception:  # noqa: BLE001 - preserve the original error
                pass
            raise

        row = self._row(account_id)
        if row is None:  # pragma: no cover - the transaction above created it
            raise PaperAccountError("the paper account row disappeared")
        snapshot = self._snapshot(row)
        snapshot["createdAt"] = created
        return snapshot


__all__ = ["PaperAccountError", "PaperAccountStore"]

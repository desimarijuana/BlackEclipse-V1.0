"""Local SQLite store for Brazilian official datasets.

Tables and their natural keys:

| Table | Key | Written by |
|---|---|---|
| ``b3_quotes`` | ``(trade_date, ticker)`` | `sync_archive` |
| ``cvm_funds`` | ``(cnpj, trade_date)`` | `sync_dataset("cvm_inf_diario", …)` |
| ``bcb_series`` | ``(series, trade_date)`` | `sync_dataset("bcb_sgs", …, code=…)` |
| ``tesouro_bonds`` | ``(bond, trade_date)`` | `sync_dataset("tesouro_direto_preco_taxa", …)` |

A re-run of the same file updates the same rows instead of duplicating them, which
is what makes every sync idempotent and safe to schedule. The three dataset tables
live in `dataset_store.py` (their own module, because their keys differ); this
class is the one handle a caller needs.

Prices are stored exactly as parsed (already divided by 100 for B3), and the lot
factor is kept beside them, so a reader can always recover the raw quoted value.
The table never stores a derived "unit price" — that is a presentation decision and
would go stale if the factor changed. The same rule drops the CVM ``netFlow``: it
is `contributions - redemptions` over stored columns.

Every sync writes a row to ``sync_runs`` with counts and a status. A failed run
is recorded with its error: a store that silently knows nothing about the last
failure is worse than no store.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from . import dataset_store

SCHEMA = """
CREATE TABLE IF NOT EXISTS b3_quotes (
    trade_date       TEXT NOT NULL,
    ticker           TEXT NOT NULL,
    bdi              TEXT,
    market_type      INTEGER,
    short_name       TEXT,
    spec             TEXT,
    open             REAL,
    high             REAL,
    low              REAL,
    average          REAL,
    close            REAL,
    best_bid         REAL,
    best_ask         REAL,
    trades           INTEGER,
    quantity         INTEGER,
    volume           REAL,
    exercise_price   REAL,
    expiration_date  TEXT,
    factor           INTEGER,
    isin             TEXT,
    PRIMARY KEY (trade_date, ticker)
);
CREATE INDEX IF NOT EXISTS idx_b3_quotes_ticker ON b3_quotes(ticker);
CREATE INDEX IF NOT EXISTS idx_b3_quotes_date ON b3_quotes(trade_date);

CREATE TABLE IF NOT EXISTS sync_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    rows         INTEGER NOT NULL DEFAULT 0,
    inserted     INTEGER NOT NULL DEFAULT 0,
    updated      INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'running',
    error        TEXT
);
"""

_COLUMNS = (
    "trade_date", "ticker", "bdi", "market_type", "short_name", "spec",
    "open", "high", "low", "average", "close", "best_bid", "best_ask",
    "trades", "quantity", "volume", "exercise_price", "expiration_date",
    "factor", "isin",
)

#: Parsed row key -> column. The parser is camelCase; the table is snake_case.
_FROM_ROW = {
    "trade_date": "tradeDate", "ticker": "ticker", "bdi": "bdi",
    "market_type": "marketType", "short_name": "shortName", "spec": "spec",
    "open": "open", "high": "high", "low": "low", "average": "average",
    "close": "close", "best_bid": "bestBid", "best_ask": "bestAsk",
    "trades": "trades", "quantity": "quantity", "volume": "volume",
    "exercise_price": "exercisePrice", "expiration_date": "expirationDate",
    "factor": "factor", "isin": "isin",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class BrStore:
    """A small wrapper over one SQLite file (created on open)."""

    path: str | Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.executescript(dataset_store.SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    # -- writes ---------------------------------------------------------

    def upsert(self, rows: Iterable[dict[str, Any]]) -> tuple[int, int, int]:
        """Insert/update parsed rows. Returns `(inserted, updated, skipped)`.

        A row without a `tradeDate` or `ticker` cannot be keyed and is skipped
        (and counted) rather than being written under an empty key.
        """
        inserted = updated = skipped = 0
        placeholders = ", ".join("?" for _ in _COLUMNS)
        update_clause = ", ".join(f"{c}=excluded.{c}" for c in _COLUMNS[2:])
        sql = (
            f"INSERT INTO b3_quotes ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(trade_date, ticker) DO UPDATE SET {update_clause}"
        )
        with self._connect() as conn:
            for row in rows:
                values = [row.get(_FROM_ROW[c]) for c in _COLUMNS]
                if not values[0] or not values[1]:
                    skipped += 1
                    continue
                exists = conn.execute(
                    "SELECT 1 FROM b3_quotes WHERE trade_date=? AND ticker=?",
                    (values[0], values[1]),
                ).fetchone()
                conn.execute(sql, values)
                if exists:
                    updated += 1
                else:
                    inserted += 1
            conn.commit()
        return inserted, updated, skipped

    # -- datasets (CVM / BCB / Tesouro) ----------------------------------

    def upsert_dataset(self, name: str, rows: Iterable[dict[str, Any]]) -> tuple[int, int, int]:
        """Insert/update one dataset's rows. Same contract as `upsert`."""
        with self._connect() as conn:
            result = dataset_store.upsert(conn, name, rows)
            conn.commit()
        return result

    def dataset_rows(self, name: str, *, key: Optional[str] = None,
                     limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return dataset_store.read(conn, name, key=key, limit=limit)

    def dataset_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            return dataset_store.counts(conn)

    def start_run(self, source: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO sync_runs (source, started_at, status) VALUES (?, ?, 'running')",
                (source, _now()),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, *, rows: int, inserted: int, updated: int,
                   status: str = "ok", error: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sync_runs SET finished_at=?, rows=?, inserted=?, updated=?,"
                " status=?, error=? WHERE id=?",
                (_now(), rows, inserted, updated, status, error or None, run_id),
            )
            conn.commit()

    # -- reads ----------------------------------------------------------

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM b3_quotes").fetchone()[0])

    def quotes(self, *, ticker: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if ticker:
                rows = conn.execute(
                    "SELECT * FROM b3_quotes WHERE ticker=? ORDER BY trade_date DESC LIMIT ?",
                    (ticker, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM b3_quotes ORDER BY trade_date DESC, ticker LIMIT ?",
                    (int(limit),),
                ).fetchall()
            return [dict(row) for row in rows]

    def status(self) -> dict[str, Any]:
        with self._connect() as conn:
            quotes = int(conn.execute("SELECT COUNT(*) FROM b3_quotes").fetchone()[0])
            dates = conn.execute(
                "SELECT MIN(trade_date), MAX(trade_date) FROM b3_quotes").fetchone()
            last = conn.execute(
                "SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
            datasets = dataset_store.counts(conn)
        return {
            "quotes": quotes,
            "firstTradeDate": dates[0],
            "lastTradeDate": dates[1],
            "datasets": datasets,
            "lastRun": dict(last) if last is not None else None,
        }


__all__ = ["BrStore", "SCHEMA"]

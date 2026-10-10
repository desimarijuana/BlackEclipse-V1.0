"""Persistent normalized bar series.

The gateway caches history in-process only; a research dataset is otherwise the
sole durable copy. This store keeps normalized OHLCV bars keyed by
(symbol, interval, provider, adjusted, eventTime) on the ONE `agent-memory.db`
connection so a dataset can be inspected, exported and refreshed without
re-fetching every bar, and so coverage is queryable.

It owns only its own table and never touches `jdds.db`.
"""

from __future__ import annotations

from typing import Any, Optional

from ..persistence import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS MarketBarSeries (
  symbol      TEXT NOT NULL,
  interval    TEXT NOT NULL,
  provider    TEXT NOT NULL,
  adjusted    INTEGER NOT NULL DEFAULT 1,
  eventTime   TEXT NOT NULL,
  retrievedAt TEXT,
  open        REAL, high REAL, low REAL, close REAL, volume REAL, vwap REAL,
  PRIMARY KEY (symbol, interval, provider, adjusted, eventTime)
);
CREATE INDEX IF NOT EXISTS idx_mbs_lookup ON MarketBarSeries(symbol, interval, adjusted, eventTime);
"""


class SeriesStore:
    """Durable normalized bars, bound to the market store's sqlite connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        try:
            self._db.executescript(_SCHEMA)
            self._db.commit()
        except Exception:  # noqa: BLE001 - persistence is best-effort
            pass

    def save_bars(self, symbol: str, interval: str, provider: str, adjusted: bool,
                  bars: list[dict[str, Any]]) -> int:
        clean = (symbol or "").upper()
        if not clean or not bars:
            return 0
        retrieved = now_iso()
        rows = []
        for bar in bars:
            ts = bar.get("timestamp")
            if ts is None:
                continue
            rows.append((
                clean, interval or "1d", provider or "unknown", 1 if adjusted else 0,
                str(ts), retrieved, bar.get("open"), bar.get("high"), bar.get("low"),
                bar.get("close"), bar.get("volume"), bar.get("vwap"),
            ))
        if not rows:
            return 0
        self._db.executemany(
            """INSERT OR REPLACE INTO MarketBarSeries
               (symbol, interval, provider, adjusted, eventTime, retrievedAt,
                open, high, low, close, volume, vwap)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self._db.commit()
        return len(rows)

    def get_bars(self, symbol: str, interval: str = "1d", *, adjusted: bool = True,
                 start: Optional[str] = None, end: Optional[str] = None,
                 provider: Optional[str] = None, limit: int = 100_000) -> list[dict[str, Any]]:
        where = ["symbol = ?", "interval = ?", "adjusted = ?"]
        params: list[Any] = [(symbol or "").upper(), interval or "1d", 1 if adjusted else 0]
        if provider:
            where.append("provider = ?")
            params.append(provider)
        if start:
            where.append("eventTime >= ?")
            params.append(str(start))
        if end:
            where.append("eventTime <= ?")
            params.append(str(end))
        params.append(max(1, int(limit)))
        rows = self._db.execute(
            f"SELECT eventTime, open, high, low, close, volume, vwap, provider "
            f"FROM MarketBarSeries WHERE {' AND '.join(where)} "
            f"ORDER BY eventTime ASC LIMIT ?",
            params,
        ).fetchall()
        return [
            {"timestamp": r["eventTime"], "open": r["open"], "high": r["high"],
             "low": r["low"], "close": r["close"], "volume": r["volume"],
             "vwap": r["vwap"], "knownAt": None}
            for r in rows
        ]

    def coverage(self, symbol: str, interval: str = "1d", *, adjusted: bool = True) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT COUNT(*) AS n, MIN(eventTime) AS start, MAX(eventTime) AS end "
            "FROM MarketBarSeries WHERE symbol=? AND interval=? AND adjusted=?",
            ((symbol or "").upper(), interval or "1d", 1 if adjusted else 0),
        ).fetchone()
        return {"symbol": (symbol or "").upper(), "interval": interval,
                "barCount": int(row["n"]) if row else 0,
                "start": row["start"] if row else None, "end": row["end"] if row else None}

    def list_series(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT symbol, interval, adjusted, provider, COUNT(*) AS n, "
            "MIN(eventTime) AS start, MAX(eventTime) AS end "
            "FROM MarketBarSeries GROUP BY symbol, interval, adjusted, provider "
            "ORDER BY symbol, interval LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [dict(r) for r in rows]


__all__ = ["SeriesStore"]

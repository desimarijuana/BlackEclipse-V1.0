"""Read-only JDdS inventory and cross-store series resolution.

JDdS (`jdds.db`) and the provider cache (`MarketBarSeries` in `agent-memory.db`)
are different stores with different owners, rights and counts. This module makes
that distinction explicit:

  * `jdds_inventory()` reads `jdds.db` in SQLite **read-only** mode and reports
    its candle/price/asset counts with `store="jdds"`;
  * `resolve_series()` returns one labelled record per store that actually holds
    the series — it never merges or averages them, and a count disagreement is
    surfaced as `quality.status="conflict"`.

No write, no schema change, no seeding. Licensing is the caller's decision; this
module only reports what is already stored.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Optional


def jdds_path() -> Path:
    override = (os.environ.get("BE_JDDS_PATH") or "").strip()
    if override:
        return Path(override)
    # .../Black-Eclipse-site/python/harness/market/vault.py -> site/jdds.db
    return Path(__file__).resolve().parents[3] / "jdds.db"


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=3.0)
    db.row_factory = sqlite3.Row
    return db


def jdds_inventory(*, symbol: Optional[str] = None, interval: str = "1d") -> dict[str, Any]:
    """Counts and coverage from JDdS only. UNAVAILABLE when the file is absent."""
    path = jdds_path()
    if not path.exists():
        return {
            "status": "UNAVAILABLE", "store": "jdds",
            "reason": f"jdds.db not found at {path}", "series": [],
        }
    try:
        db = _connect_readonly(path)
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNAVAILABLE", "store": "jdds", "reason": str(exc), "series": []}
    try:
        where = ["timeframe = ?"]
        params: list[Any] = [interval or "1d"]
        if symbol:
            where.append("symbol = ?")
            params.append(symbol.strip().upper())
        rows = db.execute(
            "SELECT symbol, COUNT(*) AS n, MIN(ts) AS start, MAX(ts) AS end "
            f"FROM Candles WHERE {' AND '.join(where)} "
            "GROUP BY symbol ORDER BY symbol",
            params,
        ).fetchall()
        series = [
            {
                "store": "jdds", "symbol": r["symbol"], "interval": interval or "1d",
                "barCount": int(r["n"] or 0), "start": r["start"], "end": r["end"],
            }
            for r in rows
        ]
        counts = {
            "candles": db.execute("SELECT COUNT(*) AS n FROM Candles").fetchone()["n"],
            "prices": db.execute("SELECT COUNT(*) AS n FROM Price").fetchone()["n"],
            "assets": db.execute("SELECT COUNT(*) AS n FROM Asset").fetchone()["n"],
        }
        return {
            "status": "ok", "store": "jdds", "path": str(path),
            "interval": interval or "1d", "series": series,
            "symbols": len(series), "counts": counts,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNAVAILABLE", "store": "jdds", "reason": str(exc), "series": []}
    finally:
        db.close()


def resolve_series(
    symbol: str,
    interval: str = "1d",
    *,
    series_store: Any = None,
    adjusted: bool = True,
) -> dict[str, Any]:
    """Return every store that holds `symbol`/`interval`, labelled, never merged."""
    clean = (symbol or "").strip().upper()
    records: list[dict[str, Any]] = []
    jdds = jdds_inventory(symbol=clean, interval=interval)
    for row in jdds.get("series") or []:
        if row.get("symbol") == clean:
            records.append({**row, "quality": {"status": "ok", "issues": []}})
    if series_store is not None:
        try:
            coverage = series_store.coverage(clean, interval, adjusted=adjusted)
            if int(coverage.get("barCount") or 0) > 0:
                records.append({
                    **coverage, "store": "history_cache",
                    "quality": {"status": "ok", "issues": []},
                })
        except Exception:  # noqa: BLE001 - a cache read failure is not a record
            pass
    if len(records) > 1:
        counts = {r.get("barCount") for r in records}
        if len(counts) > 1:
            for record in records:
                record["quality"] = {
                    "status": "conflict",
                    "issues": [f"bar counts differ across stores: {sorted(counts)}"],
                }
    return {
        "status": "ok" if records else "UNAVAILABLE",
        "symbol": clean, "interval": interval,
        "records": records,
        "reason": None if records else "no store holds this series",
    }


__all__ = ["jdds_inventory", "jdds_path", "resolve_series"]

"""Market-data persistence — instruments cache, snapshots and quality events.

Bound to the ONE `AgentMemoryStore` sqlite connection (`agent-memory.db`), the
same pattern as `research/web_store.py`, `browser/store.py` and `code/store.py`.
It owns only its own tables and the DDL is idempotent. It NEVER touches `jdds.db`
or `eclipse-memory.db`.

What is persisted:
  * `MarketInstrument`   — resolved canonical identities + provider symbol maps,
  * `MarketSnapshot`     — the latest canonical record per (capability, symbol),
  * `MarketQualityEvent` — data-quality findings + provider conflicts,
  * `MarketProviderHealth` — a durable mirror of the in-process breaker counters.

Large raw time-series are NOT duplicated here: history comes from the provider
and is cached in-process; a dedicated time-series backend can be added later
without changing the tool layer (directive §27).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS MarketInstrument (
  instrumentId TEXT PRIMARY KEY,
  symbol       TEXT NOT NULL,
  assetType    TEXT,
  market       TEXT,
  exchange     TEXT,
  currency     TEXT,
  name         TEXT,
  payload      TEXT,
  resolvedAt   TEXT,
  updatedAt    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mkt_inst_symbol ON MarketInstrument(symbol);

CREATE TABLE IF NOT EXISTS MarketSnapshot (
  capability   TEXT NOT NULL,
  symbol       TEXT NOT NULL,
  instrumentId TEXT,
  assetType    TEXT,
  provider     TEXT,
  eventTime    TEXT,
  retrievedAt  TEXT,
  quality      TEXT,
  payload      TEXT,
  updatedAt    TEXT NOT NULL,
  PRIMARY KEY (capability, symbol)
);
CREATE INDEX IF NOT EXISTS idx_mkt_snap_symbol ON MarketSnapshot(symbol);

CREATE TABLE IF NOT EXISTS MarketQualityEvent (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  capability   TEXT,
  symbol       TEXT,
  provider     TEXT,
  kind         TEXT,
  severity     TEXT,
  detail       TEXT,
  createdAt    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mkt_quality_symbol ON MarketQualityEvent(symbol);

CREATE TABLE IF NOT EXISTS MarketProviderHealth (
  provider     TEXT PRIMARY KEY,
  successes    INTEGER NOT NULL DEFAULT 0,
  failures     INTEGER NOT NULL DEFAULT 0,
  breakerState TEXT,
  lastError    TEXT,
  updatedAt    TEXT NOT NULL
);
"""


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return None


def _loads(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


class MarketStore:
    """Persistence for market instruments, snapshots and quality events."""

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
        except Exception:  # noqa: BLE001 - a schema failure makes persistence a no-op, never fatal
            pass

    # ── Instruments ──────────────────────────────────────────────────────────
    def save_instrument(self, instrument: Any) -> None:
        now = now_iso()
        self._db.execute(
            """INSERT INTO MarketInstrument
               (instrumentId, symbol, assetType, market, exchange, currency, name, payload, resolvedAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(instrumentId) DO UPDATE SET
                 symbol=excluded.symbol, assetType=excluded.assetType, market=excluded.market,
                 exchange=excluded.exchange, currency=excluded.currency, name=excluded.name,
                 payload=excluded.payload, resolvedAt=excluded.resolvedAt, updatedAt=excluded.updatedAt""",
            (
                instrument.instrument_id, instrument.symbol, instrument.asset_type,
                instrument.market, instrument.exchange, instrument.currency, instrument.name,
                _json(instrument.to_dict()), now, now,
            ),
        )
        self._db.commit()

    def get_instrument(self, instrument_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM MarketInstrument WHERE instrumentId = ?", (instrument_id,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["payload"] = _loads(data.get("payload"))
        return data

    # ── Snapshots ────────────────────────────────────────────────────────────
    def save_snapshot(self, capability: str, record: Any) -> None:
        meta = record.meta
        self._db.execute(
            """INSERT INTO MarketSnapshot
               (capability, symbol, instrumentId, assetType, provider, eventTime, retrievedAt, quality, payload, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(capability, symbol) DO UPDATE SET
                 instrumentId=excluded.instrumentId, assetType=excluded.assetType,
                 provider=excluded.provider, eventTime=excluded.eventTime,
                 retrievedAt=excluded.retrievedAt, quality=excluded.quality,
                 payload=excluded.payload, updatedAt=excluded.updatedAt""",
            (
                capability, meta.symbol or "", meta.instrument_id, meta.asset_type,
                meta.provider, meta.event_time, meta.retrieved_at, meta.quality,
                _json(record.to_dict()), now_iso(),
            ),
        )
        self._db.commit()

    def get_snapshot(self, capability: str, symbol: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM MarketSnapshot WHERE capability = ? AND symbol = ?",
            (capability, symbol.upper()),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["payload"] = _loads(data.get("payload"))
        return data

    # ── Quality events ───────────────────────────────────────────────────────
    def record_quality(
        self, capability: str, symbol: Optional[str], provider: Optional[str],
        findings: list[dict[str, Any]], conflict: Optional[dict[str, Any]] = None,
    ) -> None:
        now = now_iso()
        for finding in findings:
            self._db.execute(
                """INSERT INTO MarketQualityEvent
                   (capability, symbol, provider, kind, severity, detail, createdAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (capability, symbol, provider, finding.get("kind"), finding.get("severity"),
                 finding.get("detail"), now),
            )
        if conflict:
            self._db.execute(
                """INSERT INTO MarketQualityEvent
                   (capability, symbol, provider, kind, severity, detail, createdAt)
                   VALUES (?, ?, ?, 'conflict', 'warning', ?, ?)""",
                (capability, symbol, provider, _json(conflict), now),
            )
        self._db.commit()

    def recent_quality(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM MarketQualityEvent ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Provider health mirror ───────────────────────────────────────────────
    def save_provider_health(self, provider: str, successes: int, failures: int,
                             breaker_state: Optional[str], last_error: Optional[str]) -> None:
        self._db.execute(
            """INSERT INTO MarketProviderHealth
               (provider, successes, failures, breakerState, lastError, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(provider) DO UPDATE SET
                 successes=excluded.successes, failures=excluded.failures,
                 breakerState=excluded.breakerState, lastError=excluded.lastError,
                 updatedAt=excluded.updatedAt""",
            (provider, successes, failures, breaker_state, last_error, now_iso()),
        )
        self._db.commit()

    def provider_health(self) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT * FROM MarketProviderHealth").fetchall()
        return [dict(r) for r in rows]


__all__ = ["MarketStore"]

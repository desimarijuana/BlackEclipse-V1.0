"""Intel persistence on the ONE `agent-memory.db` connection.

No second database, mirroring the decision/advisory stores. Two kinds of row:

  * `IntelObservation` — an immutable measurement, keyed deterministically so a
    re-scan replaces the point instead of duplicating it;
  * `IntelWatch` — what the operator asked us to keep an eye on.

`IntelScan` stores the assembled card as a snapshot so a later review can see
what the evidence looked like *at decision time*, even after the series moves.
That snapshot is the only honest way to grade a signal later.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Iterable, Optional

from ..persistence import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS IntelObservation (
  id            TEXT PRIMARY KEY,
  ownerId       TEXT NOT NULL,
  entity        TEXT NOT NULL,
  signal        TEXT NOT NULL,
  asOf          TEXT NOT NULL,
  value         REAL NOT NULL DEFAULT 0,
  unit          TEXT NOT NULL DEFAULT '',
  windowDays    INTEGER NOT NULL DEFAULT 0,
  confidence    REAL NOT NULL DEFAULT 0,
  source        TEXT NOT NULL DEFAULT '',
  method        TEXT NOT NULL DEFAULT '',
  detail        TEXT NOT NULL DEFAULT '{}',
  provenance    TEXT NOT NULL DEFAULT '{}',
  directionHint TEXT NOT NULL DEFAULT 'watch',
  note          TEXT NOT NULL DEFAULT '',
  createdAt     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intel_obs_entity
  ON IntelObservation(ownerId, entity, signal, asOf);
CREATE INDEX IF NOT EXISTS idx_intel_obs_created
  ON IntelObservation(ownerId, createdAt);

CREATE TABLE IF NOT EXISTS IntelWatch (
  ownerId   TEXT NOT NULL,
  entity    TEXT NOT NULL,
  createdAt TEXT NOT NULL,
  PRIMARY KEY (ownerId, entity)
);

CREATE TABLE IF NOT EXISTS IntelScan (
  id         TEXT NOT NULL,
  ownerId    TEXT NOT NULL,
  createdAt  TEXT NOT NULL,
  asOf       TEXT NOT NULL,
  entity     TEXT NOT NULL,
  direction  TEXT NOT NULL,
  priority   REAL NOT NULL DEFAULT 0,
  conviction TEXT NOT NULL DEFAULT 'low',
  payload    TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (ownerId, id)
);
CREATE INDEX IF NOT EXISTS idx_intel_scan_created
  ON IntelScan(ownerId, createdAt);

CREATE TABLE IF NOT EXISTS IntelEntityRef (
  ownerId   TEXT NOT NULL,
  ticker    TEXT NOT NULL,
  cik       TEXT,
  name      TEXT,
  article   TEXT,
  updatedAt TEXT NOT NULL,
  PRIMARY KEY (ownerId, ticker)
);
"""


def observation_id(owner_id: str, entity: str, signal: str, as_of: str, window_days: int) -> str:
    raw = f"{owner_id}|{entity.upper()}|{signal}|{as_of}|{int(window_days)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def scan_id(owner_id: str, entity: str, as_of: str, created_at: str) -> str:
    raw = f"{owner_id}|{entity.upper()}|{as_of}|{created_at}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class IntelStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self) -> sqlite3.Connection:
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ── Observations ────────────────────────────────────────────────────────
    def write_observations(self, owner_id: str, observations: Iterable[dict[str, Any]]) -> int:
        written = 0
        created = now_iso()
        for raw in observations:
            entity = str(raw.get("entity") or "").upper()
            signal = str(raw.get("signal") or "")
            as_of = str(raw.get("asOf") or "")
            if not entity or not signal or not as_of:
                continue
            window = int(raw.get("windowDays") or 0)
            self._db.execute(
                """INSERT OR REPLACE INTO IntelObservation
                   (id, ownerId, entity, signal, asOf, value, unit, windowDays,
                    confidence, source, method, detail, provenance,
                    directionHint, note, createdAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    observation_id(owner_id, entity, signal, as_of, window),
                    owner_id, entity, signal, as_of,
                    float(raw.get("value") or 0.0),
                    str(raw.get("unit") or ""),
                    window,
                    float(raw.get("confidence") or 0.0),
                    str(raw.get("source") or ""),
                    str(raw.get("method") or ""),
                    json.dumps(raw.get("detail") or {}),
                    json.dumps(raw.get("provenance") or {}),
                    str(raw.get("directionHint") or "watch"),
                    str(raw.get("note") or ""),
                    created,
                ),
            )
            written += 1
        self._db.commit()
        return written

    def list_observations(
        self,
        owner_id: str,
        *,
        entity: Optional[str] = None,
        signal: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses = ["ownerId = ?"]
        params: list[Any] = [owner_id]
        if entity:
            clauses.append("entity = ?")
            params.append(entity.upper())
        if signal:
            clauses.append("signal = ?")
            params.append(signal)
        rows = self._db.execute(
            f"SELECT * FROM IntelObservation WHERE {' AND '.join(clauses)} "
            "ORDER BY asOf DESC, signal ASC LIMIT ?",
            (*params, max(1, min(int(limit), 1000))),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def latest_per_signal(self, owner_id: str, entity: str) -> list[dict[str, Any]]:
        """The newest row for each signal on one entity."""
        rows = self._db.execute(
            """SELECT o.* FROM IntelObservation o
               JOIN (SELECT signal, MAX(asOf) AS latest FROM IntelObservation
                     WHERE ownerId = ? AND entity = ? GROUP BY signal) m
                 ON o.signal = m.signal AND o.asOf = m.latest
               WHERE o.ownerId = ? AND o.entity = ?
               ORDER BY o.signal ASC""",
            (owner_id, entity.upper(), owner_id, entity.upper()),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def latest_entities(self, owner_id: str, limit: int = 50) -> list[str]:
        rows = self._db.execute(
            "SELECT entity, MAX(createdAt) AS seen FROM IntelObservation "
            "WHERE ownerId = ? GROUP BY entity ORDER BY seen DESC LIMIT ?",
            (owner_id, max(1, min(int(limit), 200))),
        ).fetchall()
        return [str(row["entity"]) for row in rows]

    def series(self, owner_id: str, entity: str, signal: str, limit: int = 120) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT asOf, value, unit, confidence FROM IntelObservation "
            "WHERE ownerId = ? AND entity = ? AND signal = ? "
            "ORDER BY asOf ASC LIMIT ?",
            (owner_id, entity.upper(), signal, max(1, min(int(limit), 500))),
        ).fetchall()
        return [dict(row) for row in rows]

    # ── Watchlist ───────────────────────────────────────────────────────────
    def add_watch(self, owner_id: str, entities: Iterable[str]) -> list[str]:
        created = now_iso()
        added: list[str] = []
        for raw in entities:
            entity = str(raw or "").strip().upper()
            if not entity:
                continue
            self._db.execute(
                "INSERT OR IGNORE INTO IntelWatch (ownerId, entity, createdAt) VALUES (?, ?, ?)",
                (owner_id, entity, created),
            )
            added.append(entity)
        self._db.commit()
        return added

    def remove_watch(self, owner_id: str, entities: Iterable[str]) -> int:
        removed = 0
        for raw in entities:
            entity = str(raw or "").strip().upper()
            if not entity:
                continue
            cursor = self._db.execute(
                "DELETE FROM IntelWatch WHERE ownerId = ? AND entity = ?", (owner_id, entity)
            )
            removed += int(cursor.rowcount or 0)
        self._db.commit()
        return removed

    def list_watch(self, owner_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT entity FROM IntelWatch WHERE ownerId = ? ORDER BY entity ASC", (owner_id,)
        ).fetchall()
        return [str(row["entity"]) for row in rows]

    # ── Cards ───────────────────────────────────────────────────────────────
    def write_scan(self, owner_id: str, card: dict[str, Any], *, as_of: str, created_at: str) -> None:
        entity = str(card.get("entity") or "").upper()
        self._db.execute(
            """INSERT OR REPLACE INTO IntelScan
               (id, ownerId, createdAt, asOf, entity, direction, priority, conviction, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scan_id(owner_id, entity, as_of, created_at),
                owner_id, created_at, as_of, entity,
                str(card.get("direction") or "watch"),
                float(card.get("priority") or 0.0),
                str(card.get("conviction") or "low"),
                json.dumps(card),
            ),
        )
        self._db.commit()

    def list_scans(self, owner_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM IntelScan WHERE ownerId = ? ORDER BY createdAt DESC, priority DESC LIMIT ?",
            (owner_id, max(1, min(int(limit), 200))),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.get("payload") or "{}")
            except (TypeError, ValueError):
                item["payload"] = {}
            out.append(item)
        return out

    # ── Entity ref cache (ticker → CIK/name/article) ────────────────────────
    def get_ref(self, owner_id: str, ticker: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM IntelEntityRef WHERE ownerId = ? AND ticker = ?",
            (owner_id, ticker.upper()),
        ).fetchone()
        return dict(row) if row else None

    def put_ref(self, owner_id: str, ticker: str, *, cik: str = "", name: str = "", article: str = "") -> None:
        self._db.execute(
            """INSERT INTO IntelEntityRef (ownerId, ticker, cik, name, article, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(ownerId, ticker) DO UPDATE SET
                 cik = excluded.cik, name = excluded.name,
                 article = COALESCE(NULLIF(excluded.article, ''), IntelEntityRef.article),
                 updatedAt = excluded.updatedAt""",
            (owner_id, ticker.upper(), cik, name, article, now_iso()),
        )
        self._db.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for field in ("detail", "provenance"):
            try:
                item[field] = json.loads(item.get(field) or "{}")
            except (TypeError, ValueError):
                item[field] = {}
        return item


__all__ = ["IntelStore", "observation_id", "scan_id"]

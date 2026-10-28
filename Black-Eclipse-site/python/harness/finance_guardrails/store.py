"""Durable money-guardrail state on the ONE `agent-memory.db` connection.

Two tables:

  * `MoneyGuardrailConfig` — the operator's settings, one singleton row;
  * `MoneyIntent` — every evaluated money intent and the verdict, so limits are
    aggregate (not per-call) and every decision is explainable after the fact.

It reuses `AgentMemoryStore` exactly like the portfolio/advisory stores: no
second database, no migration step, idempotent DDL. Nothing here is secret.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..persistence import now_iso
from .models import GuardrailVerdict, MoneyIntent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS MoneyGuardrailConfig (
  id               TEXT PRIMARY KEY,
  mode             TEXT NOT NULL DEFAULT 'guard',
  perTxnCap        REAL NOT NULL DEFAULT 0,
  dailyCap         REAL NOT NULL DEFAULT 0,
  velocityPerHour  INTEGER NOT NULL DEFAULT 0,
  baselineMultiplier REAL NOT NULL DEFAULT 3,
  coolingSeconds   INTEGER NOT NULL DEFAULT 120,
  highValue        REAL NOT NULL DEFAULT 0,
  impairedMode     INTEGER NOT NULL DEFAULT 0,
  crisisMode       INTEGER NOT NULL DEFAULT 0,
  panicPaused      INTEGER NOT NULL DEFAULT 0,
  trustedContact   TEXT,
  allowlist        TEXT NOT NULL DEFAULT '[]',
  blocklist        TEXT NOT NULL DEFAULT '[]',
  updatedAt        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MoneyIntent (
  id          TEXT PRIMARY KEY,
  runId       TEXT,
  tool        TEXT,
  channel     TEXT,
  action      TEXT NOT NULL,
  amount      REAL,
  currency    TEXT,
  counterparty TEXT,
  instrument  TEXT,
  account     TEXT,
  decision    TEXT NOT NULL,
  reasons     TEXT NOT NULL DEFAULT '[]',
  rules       TEXT NOT NULL DEFAULT '[]',
  risk        TEXT,
  digest      TEXT,
  createdAt   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_money_intent_created ON MoneyIntent(createdAt);
CREATE INDEX IF NOT EXISTS idx_money_intent_counterparty ON MoneyIntent(counterparty);
"""

_DEFAULT_ID = "default"

_BOOL_KEYS = ("impairedMode", "crisisMode", "panicPaused")
_NUM_KEYS = ("perTxnCap", "dailyCap", "velocityPerHour", "baselineMultiplier", "coolingSeconds", "highValue")
_LIST_KEYS = ("allowlist", "blocklist")

_PATCHABLE = {
    "mode",
    *_BOOL_KEYS,
    *_NUM_KEYS,
    *_LIST_KEYS,
    "trustedContact",
}


def _parse_iso(value: Any) -> Optional[datetime]:
    raw = str(value or "")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class MoneyGuardrailStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self) -> sqlite3.Connection:
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        existing = self._db.execute(
            "SELECT id FROM MoneyGuardrailConfig WHERE id=?", (_DEFAULT_ID,)
        ).fetchone()
        if existing is None:
            self._db.execute(
                "INSERT INTO MoneyGuardrailConfig (id, updatedAt) VALUES (?, ?)",
                (_DEFAULT_ID, now_iso()),
            )
        self._db.commit()

    # ── config ───────────────────────────────────────────────────────────────
    def get_config(self) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM MoneyGuardrailConfig WHERE id=?", (_DEFAULT_ID,)
        ).fetchone()
        if row is None:
            return self._defaults()
        record = dict(row)
        for key in _BOOL_KEYS:
            record[key] = bool(record.get(key))
        for key in _LIST_KEYS:
            try:
                record[key] = json.loads(record.get(key) or "[]")
            except (TypeError, ValueError):
                record[key] = []
        record.pop("id", None)
        return record

    def _defaults(self) -> dict[str, Any]:
        return {
            "mode": "guard",
            "perTxnCap": 0.0,
            "dailyCap": 0.0,
            "velocityPerHour": 0,
            "baselineMultiplier": 3.0,
            "coolingSeconds": 120,
            "highValue": 0.0,
            "impairedMode": False,
            "crisisMode": False,
            "panicPaused": False,
            "trustedContact": "",
            "allowlist": [],
            "blocklist": [],
            "updatedAt": now_iso(),
        }

    def update_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        for key, value in (patch or {}).items():
            if key not in _PATCHABLE:
                continue
            if key in _BOOL_KEYS:
                updates[key] = 1 if bool(value) else 0
            elif key in _NUM_KEYS:
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                if number < 0:
                    continue
                updates[key] = int(number) if key in ("velocityPerHour", "coolingSeconds") else number
            elif key in _LIST_KEYS:
                if isinstance(value, str):
                    value = [v.strip() for v in value.split(",") if v.strip()]
                updates[key] = json.dumps([str(v).strip() for v in (value or []) if str(v).strip()])
            elif key == "mode":
                updates[key] = str(value) if str(value) in ("off", "guard", "strict") else "guard"
            elif key == "trustedContact":
                updates[key] = str(value or "")[:200]
        if not updates:
            return self.get_config()
        updates["updatedAt"] = now_iso()
        assignments = ", ".join(f"{k}=?" for k in updates)
        self._db.execute(
            f"UPDATE MoneyGuardrailConfig SET {assignments} WHERE id=?",
            (*updates.values(), _DEFAULT_ID),
        )
        self._db.commit()
        return self.get_config()

    # ── ledger ───────────────────────────────────────────────────────────────
    def record(self, intent: MoneyIntent, verdict: GuardrailVerdict) -> str:
        record_id = f"mi_{uuid.uuid4().hex[:20]}"
        self._db.execute(
            """INSERT INTO MoneyIntent
               (id, runId, tool, channel, action, amount, currency, counterparty,
                instrument, account, decision, reasons, rules, risk, digest, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id, intent.run_id or None, intent.tool or None, intent.channel,
                intent.action, intent.amount, intent.currency, intent.counterparty,
                intent.instrument, intent.account, verdict.decision,
                json.dumps(verdict.reasons), json.dumps(verdict.rules),
                verdict.risk, intent.digest, now_iso(),
            ),
        )
        self._db.commit()
        return record_id

    def list_intents(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        rows = self._db.execute(
            "SELECT * FROM MoneyIntent ORDER BY createdAt DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for row in rows:
            record = dict(row)
            for key in ("reasons", "rules"):
                try:
                    record[key] = json.loads(record.get(key) or "[]")
                except (TypeError, ValueError):
                    record[key] = []
            result.append(record)
        return result

    def aggregates(self, *, now: Optional[datetime] = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        hour_ago = now - timedelta(hours=1)
        thirty_days = now - timedelta(days=30)
        ninety_days = now - timedelta(days=90)

        rows = self._db.execute(
            "SELECT amount, createdAt FROM MoneyIntent "
            "WHERE decision != 'deny' AND amount IS NOT NULL AND createdAt >= ?",
            (ninety_days.strftime("%Y-%m-%dT%H:%M:%S"),),
        ).fetchall()
        amounts: list[tuple[float, datetime]] = []
        for row in rows:
            parsed = _parse_iso(row["createdAt"])
            if parsed is None:
                continue
            try:
                amounts.append((float(row["amount"]), parsed))
            except (TypeError, ValueError):
                continue

        spend_today = sum(a for a, ts in amounts if ts >= midnight)
        spend_30d = sum(a for a, ts in amounts if ts >= thirty_days)
        count_last_hour = sum(1 for _, ts in amounts if ts >= hour_ago)
        values = sorted(a for a, _ in amounts)
        baseline_p95 = None
        if len(values) >= 5:
            index = min(len(values) - 1, int(round(0.95 * (len(values) - 1))))
            baseline_p95 = values[index]

        recent_rows = self._db.execute(
            "SELECT amount FROM MoneyIntent "
            "WHERE decision != 'deny' AND amount IS NOT NULL "
            "ORDER BY createdAt DESC LIMIT 5"
        ).fetchall()
        recent = [float(r["amount"]) for r in recent_rows if r["amount"] is not None]

        return {
            "spendToday": round(spend_today, 2),
            "spend30d": round(spend_30d, 2),
            "countLastHour": count_last_hour,
            "baselineP95": baseline_p95,
            "recentAmounts": recent,
        }

    def counterparty_seen(self, counterparty: Optional[str]) -> bool:
        value = str(counterparty or "").strip()
        if not value:
            return False
        row = self._db.execute(
            "SELECT 1 FROM MoneyIntent WHERE counterparty=? AND decision != 'deny' LIMIT 1",
            (value,),
        ).fetchone()
        return row is not None


__all__ = ["MoneyGuardrailStore"]

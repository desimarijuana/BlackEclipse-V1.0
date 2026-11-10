"""Durable daily monitoring snapshots.

A dashboard cannot show drift if the numbers are not stored. This is a small
append-only table of the daily signal parity, drift and attribution state.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .monitor import attribution, drift, signal_parity
from .store import QuantStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS QuantMonitorSnapshot (
  id TEXT PRIMARY KEY,
  trialId TEXT NOT NULL,
  day TEXT NOT NULL,
  parityJson TEXT,
  driftJson TEXT,
  attributionJson TEXT,
  brokerJson TEXT,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qmon_trial ON QuantMonitorSnapshot(trialId, day);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class MonitorStore:
    def __init__(self, store: QuantStore) -> None:
        self.store = store
        self._db = store._db
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def record(
        self, *, trial_id: str,
        backtest_signals: list[dict[str, Any]] | None = None,
        live_signals: list[dict[str, Any]] | None = None,
        baseline: dict[str, Any] | None = None,
        recent: dict[str, Any] | None = None,
        trades: list[dict[str, Any]] | None = None,
        broker: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot_id = f"mon_{uuid.uuid4().hex[:16]}"
        parity = signal_parity(backtest_signals or [], live_signals or [])
        drift_report = drift(baseline or {}, recent or {})
        attribution_report = attribution(trades or [])
        self._db.execute(
            "INSERT INTO QuantMonitorSnapshot "
            "(id,trialId,day,parityJson,driftJson,attributionJson,brokerJson,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (snapshot_id, trial_id, _day(),
             json.dumps(parity, sort_keys=True, default=str),
             json.dumps(drift_report, sort_keys=True, default=str),
             json.dumps(attribution_report, sort_keys=True, default=str),
             json.dumps(broker or {}, sort_keys=True, default=str), _now()),
        )
        self._db.commit()
        return self.get(snapshot_id)

    def get(self, snapshot_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM QuantMonitorSnapshot WHERE id=?", (snapshot_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"snapshot {snapshot_id!r} not found")
        return {
            "id": row["id"], "trialId": row["trialId"], "day": row["day"],
            "parity": json.loads(row["parityJson"] or "{}"),
            "drift": json.loads(row["driftJson"] or "{}"),
            "attribution": json.loads(row["attributionJson"] or "{}"),
            "broker": json.loads(row["brokerJson"] or "{}"),
            "createdAt": row["createdAt"],
        }

    def list(self, *, trial_id: str | None = None,
             limit: int = 100) -> list[dict[str, Any]]:
        if trial_id:
            rows = self._db.execute(
                "SELECT id FROM QuantMonitorSnapshot WHERE trialId=? "
                "ORDER BY day DESC, createdAt DESC LIMIT ?", (trial_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT id FROM QuantMonitorSnapshot ORDER BY createdAt DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self.get(r["id"]) for r in rows]


__all__ = ["MonitorStore"]

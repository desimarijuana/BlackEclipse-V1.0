"""Durable bar-close runner keys and pause/resume control.

The runner is the piece that makes live execution repeatable. A run is claimed
for one strategy, version, timeframe and closed bar. The unique key prevents a
restart, retry or double click from sending the same order twice.

It stores state only. The caller evaluates the signal and submits the order.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .oms import order_key
from .store import QuantStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS QuantLiveRun (
  id TEXT PRIMARY KEY,
  runKey TEXT NOT NULL UNIQUE,
  strategyId TEXT NOT NULL,
  version TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  barTs TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'claimed',
  attempts INTEGER NOT NULL DEFAULT 1,
  error TEXT,
  createdAt TEXT NOT NULL,
  updatedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qlrun_strategy ON QuantLiveRun(strategyId);
CREATE TABLE IF NOT EXISTS QuantLiveControl (
  strategyId TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',
  updatedAt TEXT NOT NULL,
  PRIMARY KEY (strategyId, version)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LiveRunner:
    def __init__(self, store: QuantStore) -> None:
        self.store = store
        self._db = store._db
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def control(self, strategy_id: str, version: str) -> str:
        row = self._db.execute(
            "SELECT status FROM QuantLiveControl WHERE strategyId=? AND version=?",
            (strategy_id, version),
        ).fetchone()
        return row["status"] if row else "running"

    def set_control(self, strategy_id: str, version: str, status: str) -> dict[str, Any]:
        if status not in ("running", "paused"):
            raise ValueError("status must be running or paused")
        self._db.execute(
            "INSERT INTO QuantLiveControl (strategyId,version,status,updatedAt) "
            "VALUES (?,?,?,?) ON CONFLICT(strategyId,version) DO UPDATE SET "
            "status=excluded.status, updatedAt=excluded.updatedAt",
            (strategy_id, version, status, _now()),
        )
        self._db.commit()
        return {"strategyId": strategy_id, "version": version, "status": status}

    def claim(self, *, strategy_id: str, version: str, timeframe: str,
              bar_ts: str) -> dict[str, Any]:
        if self.control(strategy_id, version) == "paused":
            return {"claimed": False, "reason": "paused"}
        key = order_key(strategy_id, version, timeframe, bar_ts)
        existing = self._db.execute(
            "SELECT * FROM QuantLiveRun WHERE runKey=?", (key,)
        ).fetchone()
        if existing:
            return {"claimed": False, "reason": "already_claimed",
                    "run": self._row(existing)}
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        now = _now()
        self._db.execute(
            "INSERT INTO QuantLiveRun "
            "(id,runKey,strategyId,version,timeframe,barTs,state,attempts,error,"
            "createdAt,updatedAt) VALUES (?,?,?,?,?,?,'claimed',1,NULL,?,?)",
            (run_id, key, strategy_id, version, timeframe, bar_ts, now, now),
        )
        self._db.commit()
        return {"claimed": True, "run": self.get(run_id)}

    def get(self, run_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM QuantLiveRun WHERE id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"run {run_id!r} not found")
        return self._row(row)

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"], "runKey": row["runKey"],
            "strategyId": row["strategyId"], "version": row["version"],
            "timeframe": row["timeframe"], "barTs": row["barTs"],
            "state": row["state"], "attempts": row["attempts"],
            "error": row["error"], "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
        }

    def finish(self, run_id: str, *, state: str, error: str = "") -> dict[str, Any]:
        if state not in ("done", "failed", "skipped"):
            raise ValueError("state must be done, failed or skipped")
        self._db.execute(
            "UPDATE QuantLiveRun SET state=?, error=?, updatedAt=? WHERE id=?",
            (state, error or None, _now(), run_id),
        )
        self._db.commit()
        return self.get(run_id)

    def reopen(self, run_id: str) -> dict[str, Any]:
        """Allow a retry of a failed run only. A done run stays closed."""
        run = self.get(run_id)
        if run["state"] != "failed":
            return {"reopened": False, "reason": f"run is {run['state']}"}
        self._db.execute(
            "UPDATE QuantLiveRun SET state='claimed', attempts=attempts+1, "
            "error=NULL, updatedAt=? WHERE id=?", (_now(), run_id),
        )
        self._db.commit()
        return {"reopened": True, "run": self.get(run_id)}

    def runs(self, *, strategy_id: str | None = None,
             limit: int = 100) -> list[dict[str, Any]]:
        if strategy_id:
            rows = self._db.execute(
                "SELECT * FROM QuantLiveRun WHERE strategyId=? "
                "ORDER BY createdAt DESC LIMIT ?", (strategy_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM QuantLiveRun ORDER BY createdAt DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(r) for r in rows]


__all__ = ["LiveRunner"]

"""Persisted compression cooldown (W2).

A failed summary must not be retried every turn. The cooldown is per session,
with the 60 -> 300 -> 900 second ladder. The deterministic skeleton is always
allowed; only the model narrative obeys the cooldown.
"""

from __future__ import annotations

import time
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS ContextCompressionState (
  sessionId      TEXT PRIMARY KEY,
  failures       INTEGER NOT NULL DEFAULT 0,
  nextAttemptAt  REAL NOT NULL DEFAULT 0,
  failureClass   TEXT,
  updatedAt      TEXT NOT NULL
);
"""

_LADDER = (60.0, 300.0, 900.0)


class CompressionStateStore:
    def __init__(self, store: Any) -> None:
        self._db = getattr(store, "_db", None)
        if self._db is not None:
            try:
                self._db.executescript(SCHEMA)
                self._db.commit()
            except Exception:  # noqa: BLE001
                pass

    def allow(self, session_id: str, *, now: Optional[float] = None) -> bool:
        if self._db is None or not session_id:
            return True
        try:
            row = self._db.execute(
                "SELECT nextAttemptAt FROM ContextCompressionState WHERE sessionId=?",
                (session_id,),
            ).fetchone()
        except Exception:  # noqa: BLE001
            return True
        return row is None or float(row["nextAttemptAt"] or 0) <= (now if now is not None else time.time())

    def record_failure(self, session_id: str, failure_class: str, *, now: Optional[float] = None) -> None:
        if self._db is None or not session_id:
            return
        from ..persistence import now_iso  # noqa: PLC0415

        current = now if now is not None else time.time()
        try:
            row = self._db.execute(
                "SELECT failures FROM ContextCompressionState WHERE sessionId=?",
                (session_id,),
            ).fetchone()
            failures = int(row["failures"] or 0) + 1 if row is not None else 1
            delay = _LADDER[min(max(0, failures - 1), len(_LADDER) - 1)]
            self._db.execute(
                """INSERT INTO ContextCompressionState
                   (sessionId, failures, nextAttemptAt, failureClass, updatedAt)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(sessionId) DO UPDATE SET
                     failures=excluded.failures,
                     nextAttemptAt=excluded.nextAttemptAt,
                     failureClass=excluded.failureClass,
                     updatedAt=excluded.updatedAt""",
                (session_id, failures, current + delay, failure_class, now_iso()),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001
            pass

    def clear(self, session_id: str) -> None:
        if self._db is None or not session_id:
            return
        try:
            self._db.execute("DELETE FROM ContextCompressionState WHERE sessionId=?", (session_id,))
            self._db.commit()
        except Exception:  # noqa: BLE001
            pass


__all__ = ["CompressionStateStore", "SCHEMA"]

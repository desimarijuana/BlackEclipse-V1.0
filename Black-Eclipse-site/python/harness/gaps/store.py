"""Durable capability gaps on the ONE agent-memory database.

A gap outlives the run: a bot or a scheduled task has no chat card to click, so
the gap is the durable "needs your decision" record. Fail-open: a store error
never breaks a run.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from ..persistence import now_iso

log = logging.getLogger("harness.gaps.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS CapabilityGap (
  id         TEXT PRIMARY KEY,
  runId      TEXT NOT NULL,
  signature  TEXT NOT NULL,
  need       TEXT NOT NULL,
  kind       TEXT NOT NULL,
  code       TEXT NOT NULL,
  tool       TEXT NOT NULL DEFAULT '',
  reason     TEXT NOT NULL DEFAULT '',
  taskId     TEXT NOT NULL DEFAULT '',
  state      TEXT NOT NULL,
  createdAt  TEXT NOT NULL,
  updatedAt  TEXT NOT NULL,
  UNIQUE(runId, signature)
);
CREATE INDEX IF NOT EXISTS idx_cap_gap_run ON CapabilityGap(runId, state);
CREATE INDEX IF NOT EXISTS idx_cap_gap_state ON CapabilityGap(state, updatedAt);
CREATE INDEX IF NOT EXISTS idx_cap_gap_sig ON CapabilityGap(signature, state);
"""

_ACTIVE_STATES = ("open", "offered")
_TERMINAL_STATES = ("accepted", "declined", "suppressed", "resolved")


class GapStore:
    def __init__(self, store: Any = None) -> None:
        self._store = store
        self._db = getattr(store, "_db", None) if store is not None else None
        if self._db is not None:
            try:
                self._db.executescript(_SCHEMA)
                self._db.commit()
            except Exception:  # noqa: BLE001 - the gap ledger is additive
                log.debug("capability gap schema failed", exc_info=True)
                self._db = None

    @property
    def durable(self) -> bool:
        return self._db is not None

    def _row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        return {
            "gapId": data.get("id"),
            "runId": data.get("runId"),
            "signature": data.get("signature"),
            "need": data.get("need") or "",
            "kind": data.get("kind") or "",
            "code": data.get("code") or "",
            "tool": data.get("tool") or "",
            "reason": data.get("reason") or "",
            "taskId": data.get("taskId") or "",
            "state": data.get("state") or "",
            "createdAt": data.get("createdAt"),
            "updatedAt": data.get("updatedAt"),
        }

    def _is_suppressed(self, signature: str) -> bool:
        if self._db is None:
            return False
        try:
            row = self._db.execute(
                "SELECT 1 FROM CapabilityGap WHERE signature=? AND state='suppressed' LIMIT 1",
                (signature,),
            ).fetchone()
            return row is not None
        except Exception:  # noqa: BLE001
            return False

    def create(
        self,
        *,
        run_id: str,
        signature: str,
        need: str,
        kind: str,
        code: str,
        tool: str = "",
        reason: str = "",
        task_id: str = "",
    ) -> Optional[dict[str, Any]]:
        if self._db is None or not run_id or not signature:
            return None
        now = now_iso()
        state = "suppressed" if self._is_suppressed(signature) else "open"
        gap_id = "gap_" + uuid.uuid4().hex[:16]
        try:
            self._db.execute(
                """
                INSERT INTO CapabilityGap
                  (id, runId, signature, need, kind, code, tool, reason, taskId,
                   state, createdAt, updatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(runId, signature) DO UPDATE SET
                  need=excluded.need, kind=excluded.kind, code=excluded.code,
                  tool=excluded.tool, reason=excluded.reason, taskId=excluded.taskId,
                  state=CASE WHEN CapabilityGap.state IN ('accepted','declined','suppressed')
                             THEN CapabilityGap.state ELSE excluded.state END,
                  updatedAt=excluded.updatedAt
                """,
                (
                    gap_id, str(run_id), str(signature), str(need)[:300],
                    str(kind), str(code)[:120], str(tool)[:120], str(reason)[:500],
                    str(task_id or ""), state, now, now,
                ),
            )
            self._db.commit()
            row = self._db.execute(
                "SELECT * FROM CapabilityGap WHERE runId=? AND signature=?",
                (str(run_id), str(signature)),
            ).fetchone()
            return self._row(row) if row is not None else None
        except Exception:  # noqa: BLE001 - never break the run
            log.debug("capability gap write failed", exc_info=True)
            return None

    def get(self, gap_id: str) -> Optional[dict[str, Any]]:
        if self._db is None:
            return None
        try:
            row = self._db.execute(
                "SELECT * FROM CapabilityGap WHERE id=?", (str(gap_id),),
            ).fetchone()
            return self._row(row) if row is not None else None
        except Exception:  # noqa: BLE001
            return None

    def records(
        self,
        *,
        run_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if self._db is None:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if run_id:
            clauses.append("runId = ?")
            params.append(str(run_id))
        if state:
            clauses.append("state = ?")
            params.append(str(state))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(max(1, int(limit)))
        try:
            rows = self._db.execute(
                f"SELECT * FROM CapabilityGap{where} ORDER BY updatedAt DESC LIMIT ?",
                tuple(params),
            ).fetchall()
            return [self._row(row) for row in rows]
        except Exception:  # noqa: BLE001
            return []

    def pending(self, run_id: str) -> list[dict[str, Any]]:
        if self._db is None:
            return []
        try:
            rows = self._db.execute(
                "SELECT * FROM CapabilityGap WHERE runId=? AND state IN ('open','offered') "
                "ORDER BY createdAt ASC LIMIT 20",
                (str(run_id),),
            ).fetchall()
            return [self._row(row) for row in rows]
        except Exception:  # noqa: BLE001
            return []

    def set_state(self, gap_id: str, state: str) -> Optional[dict[str, Any]]:
        if self._db is None or state not in (*_ACTIVE_STATES, *_TERMINAL_STATES):
            return None
        try:
            self._db.execute(
                "UPDATE CapabilityGap SET state=?, updatedAt=? WHERE id=?",
                (str(state), now_iso(), str(gap_id)),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001
            return None
        return self.get(gap_id)

    def resolve_tool(self, run_id: str, tool: str) -> int:
        """A later success on the same tool closes its open gaps for this run."""
        if self._db is None or not tool:
            return 0
        try:
            cur = self._db.execute(
                "UPDATE CapabilityGap SET state='resolved', updatedAt=? "
                "WHERE runId=? AND tool=? AND state IN ('open','offered')",
                (now_iso(), str(run_id), str(tool)),
            )
            self._db.commit()
            return int(cur.rowcount or 0)
        except Exception:  # noqa: BLE001
            return 0

    def summary(self) -> dict[str, Any]:
        if self._db is None:
            return {"total": 0, "byState": {}, "byClass": {}, "durable": False}
        try:
            by_state = {
                str(row[0]): int(row[1])
                for row in self._db.execute(
                    "SELECT state, COUNT(*) FROM CapabilityGap GROUP BY state"
                ).fetchall()
            }
            by_class = {
                str(row[0]): int(row[1])
                for row in self._db.execute(
                    "SELECT kind, COUNT(*) FROM CapabilityGap GROUP BY kind"
                ).fetchall()
            }
            total = sum(by_state.values())
            return {
                "total": total,
                "byState": by_state,
                "byClass": by_class,
                "durable": True,
            }
        except Exception:  # noqa: BLE001
            return {"total": 0, "byState": {}, "byClass": {}, "durable": True}


__all__ = ["GapStore"]

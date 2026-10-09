"""Durable operation ledger — idempotency + compensation for side effects.

A repair that mutates the world (installs a dependency, edits a repo, calls an
external API) must not run twice because a worker crashed between the effect and
the record, and it must be undoable when the repair turns out wrong. This module
is the durable ledger that makes both possible:

  * `begin(key, …)` is idempotent on the key: a second call returns the existing
    row with `created=False`, so a resumed worker can see "already done" instead
    of repeating the side effect (spec §5.2 durability, §9.3 repair lifecycle).
  * `complete` / `fail` / `compensate` record the terminal state.
  * `pending_compensations()` lists operations that declared a compensating
    action but did not finish, so a crash can be reconciled on boot.

It records intent and outcome; it does NOT itself perform a compensation (that is
the caller's action, run inside the normal security boundary). Rides the ONE
`eclipse-memory.db` connection the recovery store already holds.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..eclipse_memory.db import new_id, now_iso

BEGIN = "begun"
COMPLETED = "completed"
FAILED = "failed"
COMPENSATED = "compensated"


class OperationLedger:
    def __init__(self, store: Any) -> None:
        # `store` is the RecoveryStore (which owns the eclipse-memory connection).
        self._db = store._db

    def begin(
        self,
        idempotency_key: str,
        kind: str,
        *,
        incident_id: Optional[str] = None,
        request: Optional[dict[str, Any]] = None,
        compensating_action: Optional[str] = None,
    ) -> dict[str, Any]:
        existing = self.get_by_key(idempotency_key)
        if existing is not None:
            return {**existing, "created": False}
        op_id = new_id("op")
        now = now_iso()
        self._db.execute(
            """INSERT INTO RecoveryOperation
               (id, idempotencyKey, kind, status, incidentId, request, result,
                compensatingAction, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
            (
                op_id, idempotency_key, kind, BEGIN, incident_id,
                json.dumps(request) if request is not None else None,
                compensating_action, now, now,
            ),
        )
        self._db.commit()
        return {**(self.get(op_id) or {}), "created": True}

    def _set(self, op_id: str, status: str, result: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        self._db.execute(
            "UPDATE RecoveryOperation SET status = ?, result = ?, updatedAt = ? WHERE id = ?",
            (status, json.dumps(result) if result is not None else None, now_iso(), op_id),
        )
        self._db.commit()
        return self.get(op_id)

    def complete(self, op_id: str, *, result: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        return self._set(op_id, COMPLETED, result)

    def fail(self, op_id: str, *, result: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        return self._set(op_id, FAILED, result)

    def compensate(self, op_id: str, *, result: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        return self._set(op_id, COMPENSATED, result)

    def get(self, op_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM RecoveryOperation WHERE id = ?", (op_id,)).fetchone()
        return self._row(row) if row is not None else None

    def get_by_key(self, idempotency_key: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM RecoveryOperation WHERE idempotencyKey = ?", (idempotency_key,)
        ).fetchone()
        return self._row(row) if row is not None else None

    def list_by_incident(self, incident_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM RecoveryOperation WHERE incidentId = ? ORDER BY createdAt DESC LIMIT ?",
            (incident_id, max(1, min(int(limit), 200))),
        ).fetchall()
        return [self._row(r) for r in rows]

    def pending_compensations(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Operations that declared a compensating action but are not compensated."""
        rows = self._db.execute(
            """SELECT * FROM RecoveryOperation
               WHERE compensatingAction IS NOT NULL AND status IN (?, ?)
               ORDER BY createdAt ASC LIMIT ?""",
            (BEGIN, FAILED, max(1, min(int(limit), 200))),
        ).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        request = row["request"]
        result = row["result"]
        return {
            "id": row["id"],
            "idempotencyKey": row["idempotencyKey"],
            "kind": row["kind"],
            "status": row["status"],
            "incidentId": row["incidentId"],
            "request": json.loads(request) if request else None,
            "result": json.loads(result) if result else None,
            "compensatingAction": row["compensatingAction"],
            "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
        }


__all__ = [
    "BEGIN",
    "COMPENSATED",
    "COMPLETED",
    "FAILED",
    "OperationLedger",
]
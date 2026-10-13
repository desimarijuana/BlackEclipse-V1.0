"""Durable persistence for failure incidents and recovery attempts.

This is the recovery engine's slice of **`eclipse-memory.db`** — Eclipse's own
memory about its failures and what it did about them. It is deliberately NOT
`jdds.db` (market data) and NOT `agent-memory.db` (run/event/tool traces): what
Eclipse learned while repairing itself is agent memory, and it is bounded and
queryable as such (spec §12, §18).

The store accepts the ONE `EclipseMemoryStore` the runtime already holds and
rides its connection — it never opens a second connection to the file.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from ..eclipse_memory.db import new_id, now_iso
from .controller import RecoveryDecision
from .taxonomy import NormalizedFailure

OPEN = "open"
RESOLVED = "resolved"
FAILED = "failed"


class RecoveryStore:
    def __init__(self, memory_store: Any) -> None:
        # `EclipseMemoryStore` exposes `.connection`; `EclipseMemoryDb` exposes
        # it too. Accept either so tests can pass the raw db.
        self.memory_store = memory_store
        db = getattr(memory_store, "db", memory_store)
        self._db = db.connection

    # ── incidents ────────────────────────────────────────────────────────────

    def _find(self, signature: str, task_id: Optional[str]) -> Optional[Any]:
        return self._db.execute(
            "SELECT id, occurrenceCount FROM RecoveryIncident "
            "WHERE signature = ? AND IFNULL(taskId, '') = ?",
            (signature, task_id or ""),
        ).fetchone()

    def record_failure(
        self,
        failure: NormalizedFailure,
        *,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        decision: Optional[RecoveryDecision] = None,
        metadata: Optional[dict[str, Any]] = None,
        status: str = OPEN,
    ) -> dict[str, Any]:
        """Upsert the incident for this (signature, task) and bump its count."""
        now = now_iso()
        decision_json = json.dumps(decision.to_dict()) if decision is not None else None
        existing = self._find(failure.signature, task_id)
        if existing is not None:
            incident_id = existing["id"]
            self._db.execute(
                """UPDATE RecoveryIncident
                   SET occurrenceCount = occurrenceCount + 1, lastSeenAt = ?,
                       status = ?, kind = ?, retryability = ?, code = ?, message = ?,
                       source = ?, subsystem = ?, decision = ?,
                       runId = COALESCE(?, runId),
                       metadata = COALESCE(?, metadata)
                   WHERE id = ?""",
                (
                    now, status, failure.kind.value, failure.retryability.value,
                    failure.code, failure.message, failure.source, failure.subsystem,
                    decision_json, run_id,
                    json.dumps(metadata) if metadata is not None else None,
                    incident_id,
                ),
            )
        else:
            incident_id = new_id("inc")
            self._db.execute(
                """INSERT INTO RecoveryIncident
                   (id, signature, kind, retryability, code, subsystem, source, message,
                    taskId, runId, status, occurrenceCount, attempts, decision, metadata,
                    firstSeenAt, lastSeenAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?)""",
                (
                    incident_id, failure.signature, failure.kind.value,
                    failure.retryability.value, failure.code, failure.subsystem,
                    failure.source, failure.message, task_id, run_id, status,
                    decision_json,
                    json.dumps(metadata) if metadata is not None else None,
                    now, now,
                ),
            )
        self._db.commit()
        return self.get_incident(incident_id)  # type: ignore[return-value]

    def get_incident(self, incident_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            """SELECT i.*, d.diagnosis AS diagnosis
               FROM RecoveryIncident i
               LEFT JOIN RecoveryDiagnosis d ON d.incidentId = i.id
               WHERE i.id = ?""",
            (incident_id,),
        ).fetchone()
        return self._row(row) if row is not None else None

    def find_incident(
        self, signature: str, *, task_id: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        row = self._find(signature, task_id)
        if row is None:
            return None
        return self.get_incident(row["id"])

    def occurrence_count(self, signature: str, *, task_id: Optional[str] = None) -> int:
        row = self._find(signature, task_id)
        return int(row["occurrenceCount"]) if row is not None else 0

    def list_incidents(
        self,
        *,
        status: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("i.status = ?")
            params.append(status)
        if task_id:
            clauses.append("i.taskId = ?")
            params.append(task_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        rows = self._db.execute(
            f"""SELECT i.*, d.diagnosis AS diagnosis
                FROM RecoveryIncident i
                LEFT JOIN RecoveryDiagnosis d ON d.incidentId = i.id
                {where}
                ORDER BY i.lastSeenAt DESC LIMIT ?""",
            tuple(params),
        ).fetchall()
        return [self._row(r) for r in rows]

    def set_status(self, incident_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE RecoveryIncident SET status = ?, lastSeenAt = ? WHERE id = ?",
            (status, now_iso(), incident_id),
        )
        self._db.commit()

    def set_diagnosis(self, incident_id: str, diagnosis: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO RecoveryDiagnosis (incidentId, diagnosis, updatedAt)
               VALUES (?, ?, ?)
               ON CONFLICT(incidentId) DO UPDATE SET diagnosis = excluded.diagnosis,
                                                     updatedAt = excluded.updatedAt""",
            (incident_id, json.dumps(diagnosis), now_iso()),
        )
        self._db.commit()

    # ── attempts ─────────────────────────────────────────────────────────────

    def record_attempt(
        self,
        incident_id: str,
        *,
        attempt_no: int,
        action: str,
        strategy: Optional[str] = None,
        reason: str = "",
        backoff_ms: int = 0,
        outcome: str = "planned",
        detail: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        attempt_id = new_id("rat")
        now = now_iso()
        self._db.execute(
            """INSERT INTO RecoveryAttempt
               (id, incidentId, attemptNo, action, strategy, reason, backoffMs, outcome, detail, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                attempt_id, incident_id, int(attempt_no), action, strategy, reason,
                int(backoff_ms), outcome,
                json.dumps(detail) if detail is not None else None, now,
            ),
        )
        self._db.execute(
            "UPDATE RecoveryIncident SET attempts = attempts + 1, lastSeenAt = ? WHERE id = ?",
            (now, incident_id),
        )
        self._db.commit()
        return {
            "id": attempt_id, "incidentId": incident_id, "attemptNo": int(attempt_no),
            "action": action, "strategy": strategy, "reason": reason,
            "backoffMs": int(backoff_ms), "outcome": outcome, "detail": detail or {},
            "createdAt": now,
        }

    def list_attempts(self, incident_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM RecoveryAttempt WHERE incidentId = ? ORDER BY attemptNo ASC LIMIT ?",
            (incident_id, max(1, min(int(limit), 500))),
        ).fetchall()
        return [self._attempt_row(r) for r in rows]

    # ── roll-up ──────────────────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        total = self._db.execute("SELECT COUNT(*) AS c FROM RecoveryIncident").fetchone()["c"]
        by_status = {
            row["status"]: row["c"]
            for row in self._db.execute(
                "SELECT status, COUNT(*) AS c FROM RecoveryIncident GROUP BY status"
            ).fetchall()
        }
        by_kind = {
            row["kind"]: row["c"]
            for row in self._db.execute(
                "SELECT kind, COUNT(*) AS c FROM RecoveryIncident GROUP BY kind ORDER BY c DESC LIMIT 20"
            ).fetchall()
        }
        attempts = self._db.execute("SELECT COUNT(*) AS c FROM RecoveryAttempt").fetchone()["c"]
        return {
            "incidents": int(total),
            "byStatus": by_status,
            "byKind": by_kind,
            "attempts": int(attempts),
        }

    # ── autonomy envelope persistence ────────────────────────────────────────

    def save_envelope(self, payload: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO AutonomyEnvelope (id, payload, updatedAt) VALUES (1, ?, ?)
               ON CONFLICT(id) DO UPDATE SET payload = excluded.payload,
                                             updatedAt = excluded.updatedAt""",
            (json.dumps(payload), now_iso()),
        )
        self._db.commit()

    def load_envelope_dict(self) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT payload FROM AutonomyEnvelope WHERE id = 1").fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["payload"])
        except Exception:  # noqa: BLE001 - a corrupt row falls back to config/default
            return None

    # ── per-signature repair lease ───────────────────────────────────────────

    def acquire_lease(self, signature: str, holder: str, *, ttl_s: int = 120) -> bool:
        """Claim the repair lease for a signature. False if another holder holds it.

        Advisory via SQLite row locking; an expired lease is reclaimable.
        """
        now = now_iso()
        future_ts = time.time() + int(ttl_s)
        future = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(future_ts)) + ".000Z"
        cursor = self._db.execute(
            """INSERT INTO RecoveryLease (signature, holder, expiresAt) VALUES (?, ?, ?)
               ON CONFLICT(signature) DO UPDATE SET holder = excluded.holder,
                                                    expiresAt = excluded.expiresAt
               WHERE RecoveryLease.expiresAt <= ?""",
            (signature, holder, future, now),
        )
        self._db.commit()
        return cursor.rowcount >= 1

    def release_lease(self, signature: str, holder: str) -> None:
        self._db.execute(
            "DELETE FROM RecoveryLease WHERE signature = ? AND holder = ?",
            (signature, holder),
        )
        self._db.commit()

    # ── one-off operator approvals ───────────────────────────────────────────

    def add_approval(self, incident_id: str, strategy: str, *, approved_by: Optional[str] = None) -> dict[str, Any]:
        self._db.execute(
            """INSERT INTO RecoveryApproval (id, incidentId, strategy, approvedBy, approvedAt)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(incidentId, strategy) DO UPDATE SET
                 approvedBy = excluded.approvedBy, approvedAt = excluded.approvedAt""",
            (new_id("appr"), incident_id, strategy, approved_by, now_iso()),
        )
        self._db.commit()
        return {"incidentId": incident_id, "strategy": strategy, "approvedBy": approved_by}

    def has_approval(self, incident_id: str, strategy: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM RecoveryApproval WHERE incidentId = ? AND strategy = ? LIMIT 1",
            (incident_id, strategy),
        ).fetchone()
        return row is not None

    def consume_approval(self, incident_id: str, strategy: str) -> bool:
        """Claim a one-off operator approval EXACTLY once, then delete it.

        Reports whether a row was consumed, so the same approval can never
        authorize a second recovery action — the same single-use discipline every
        other approval store in the harness uses.
        """
        cursor = self._db.execute(
            "DELETE FROM RecoveryApproval WHERE incidentId = ? AND strategy = ?",
            (incident_id, strategy),
        )
        self._db.commit()
        return int(cursor.rowcount or 0) == 1

    def list_approvals(self, incident_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT incidentId, strategy, approvedBy, approvedAt FROM RecoveryApproval WHERE incidentId = ?",
            (incident_id,),
        ).fetchall()
        return [
            {
                "incidentId": r["incidentId"], "strategy": r["strategy"],
                "approvedBy": r["approvedBy"], "approvedAt": r["approvedAt"],
            }
            for r in rows
        ]

    # ── row mapping ──────────────────────────────────────────────────────────

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        decision = row["decision"]
        metadata = row["metadata"]
        diagnosis = row["diagnosis"] if "diagnosis" in row.keys() else None
        return {
            "id": row["id"],
            "signature": row["signature"],
            "kind": row["kind"],
            "retryability": row["retryability"],
            "code": row["code"],
            "subsystem": row["subsystem"],
            "source": row["source"],
            "message": row["message"],
            "taskId": row["taskId"],
            "runId": row["runId"],
            "status": row["status"],
            "occurrenceCount": int(row["occurrenceCount"]),
            "attempts": int(row["attempts"]),
            "decision": json.loads(decision) if decision else None,
            "diagnosis": json.loads(diagnosis) if diagnosis else None,
            "metadata": json.loads(metadata) if metadata else {},
            "firstSeenAt": row["firstSeenAt"],
            "lastSeenAt": row["lastSeenAt"],
        }

    @staticmethod
    def _attempt_row(row: Any) -> dict[str, Any]:
        detail = row["detail"]
        return {
            "id": row["id"],
            "incidentId": row["incidentId"],
            "attemptNo": int(row["attemptNo"]),
            "action": row["action"],
            "strategy": row["strategy"],
            "reason": row["reason"],
            "backoffMs": int(row["backoffMs"]),
            "outcome": row["outcome"],
            "detail": json.loads(detail) if detail else {},
            "createdAt": row["createdAt"],
        }


__all__ = ["FAILED", "OPEN", "RESOLVED", "RecoveryStore"]

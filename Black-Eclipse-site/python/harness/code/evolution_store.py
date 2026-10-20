"""Evolution persistence (Phase 10), bound to the ONE agent-memory connection.

Owns the `EvolutionCandidate` and `EvolutionAttempt` tables and their helpers.
Mirrors `run_lineage.py` / `code/store.py`: bound to the single `AgentMemoryStore`
sqlite connection, additive + idempotent DDL, old-row-safe. Never a second
database, never a second recurrence counter.

`costMicros` / `tokensUsed` are NULLABLE on purpose: a metric whose inputs do not
exist renders UNKNOWN, and a stored `0` would be a lie the report could not detect.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..persistence import now_iso

# Candidate lifecycle states.
STATUSES = (
    "inert", "proposed", "refused", "evaluating",
    "evaluated_ok", "evaluated_bad", "canaried", "activated", "rolled_back",
    "dismissed",
)
# Attempt outcomes.
OUTCOMES = ("success", "failure", "rolled_back", "refused")


def new_candidate_id() -> str:
    return "evo_" + uuid.uuid4().hex[:16]


def new_attempt_id() -> str:
    return "evat_" + uuid.uuid4().hex[:16]


def _candidate_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "signature": row["signature"],
        "sourceCategory": row["sourceCategory"],
        "observedCount": row["observedCount"],
        "problemStatement": row["problemStatement"],
        "targetPath": row["targetPath"],
        "proposedOps": json.loads(row["proposedOpsJson"]) if row["proposedOpsJson"] else None,
        "subjectType": row["subjectType"] if "subjectType" in row.keys() else "code",
        "surfaceConfig": (
            json.loads(row["surfaceConfigJson"]) if row["surfaceConfigJson"] else None
        ),
        "status": row["status"],
        "refusalCode": row["refusalCode"],
        "activatedVersion": row["activatedVersion"],
        "previousVersion": row["previousVersion"],
        "createdByRunId": row["createdByRunId"],
        "createdAt": row["createdAt"],
        "updatedAt": row["updatedAt"],
    }


def _attempt_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "candidateId": row["candidateId"],
        "attemptIndex": row["attemptIndex"],
        "targetPath": row["targetPath"],
        "baseDigest": row["baseDigest"],
        "diffDigest": row["diffDigest"],
        "proposedOps": json.loads(row["proposedOpsJson"]) if row["proposedOpsJson"] else [],
        "evaluation": json.loads(row["evaluationJson"]) if row["evaluationJson"] else None,
        "outcome": row["outcome"],
        "outcomeReason": row["outcomeReason"],
        "costMicros": row["costMicros"],          # None ⇒ UNKNOWN, never 0
        "tokensUsed": row["tokensUsed"],          # None ⇒ UNKNOWN, never 0
        "startedAt": row["startedAt"],
        "finishedAt": row["finishedAt"],
    }


class EvolutionStore:
    """EvolutionCandidate + EvolutionAttempt over the ONE agent-memory store."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS EvolutionCandidate (
              id                TEXT PRIMARY KEY,
              signature         TEXT NOT NULL UNIQUE,
              sourceCategory    TEXT NOT NULL,
              observedCount     INTEGER NOT NULL,
              problemStatement  TEXT NOT NULL,
              targetPath        TEXT,
              proposedOpsJson   TEXT,
              subjectType       TEXT NOT NULL DEFAULT 'code',
              surfaceConfigJson TEXT,
              status            TEXT NOT NULL DEFAULT 'inert',
              refusalCode       TEXT,
              activatedVersion  TEXT,
              previousVersion   TEXT,
              createdByRunId    TEXT,
              createdAt         TEXT NOT NULL,
              updatedAt         TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_evolution_candidate_status "
            "ON EvolutionCandidate(status, observedCount)"
        )
        # Additive, idempotent columns: an existing store keeps its rows and the
        # old `code` subject semantics. A surface candidate carries its validated
        # snapshot + benchmark config in `surfaceConfigJson`; no second table.
        self._ensure_column(
            "EvolutionCandidate", "subjectType",
            "subjectType TEXT NOT NULL DEFAULT 'code'",
        )
        self._ensure_column(
            "EvolutionCandidate", "surfaceConfigJson", "surfaceConfigJson TEXT",
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS EvolutionAttempt (
              id              TEXT PRIMARY KEY,
              candidateId     TEXT NOT NULL,
              attemptIndex    INTEGER NOT NULL,
              targetPath      TEXT NOT NULL,
              baseDigest      TEXT NOT NULL,
              diffDigest      TEXT NOT NULL,
              proposedOpsJson TEXT NOT NULL,
              evaluationJson  TEXT,
              outcome         TEXT NOT NULL,
              outcomeReason   TEXT,
              costMicros      INTEGER,
              tokensUsed      INTEGER,
              startedAt       TEXT NOT NULL,
              finishedAt      TEXT
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_evolution_attempt_candidate "
            "ON EvolutionAttempt(candidateId, startedAt)"
        )
        self._db.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        """Add a column once; old stores keep working without a table rebuild."""
        columns = {
            str(row["name"])
            for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    # ── Candidates ────────────────────────────────────────────────────────────
    def save_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        record = {
            **candidate,
            "id": candidate.get("id") or new_candidate_id(),
            "createdAt": candidate.get("createdAt") or now_iso(),
            "updatedAt": now_iso(),
        }
        self._db.execute(
            """INSERT OR REPLACE INTO EvolutionCandidate
               (id, signature, sourceCategory, observedCount, problemStatement, targetPath,
                proposedOpsJson, subjectType, surfaceConfigJson, status, refusalCode,
                activatedVersion, previousVersion, createdByRunId, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"], record["signature"], record["sourceCategory"],
                int(record["observedCount"]), record["problemStatement"], record.get("targetPath"),
                json.dumps(record["proposedOps"]) if record.get("proposedOps") is not None else None,
                record.get("subjectType", "code"),
                json.dumps(record["surfaceConfig"]) if record.get("surfaceConfig") is not None else None,
                record.get("status", "inert"), record.get("refusalCode"),
                record.get("activatedVersion"), record.get("previousVersion"),
                record.get("createdByRunId"), record["createdAt"], record["updatedAt"],
            ),
        )
        self._db.commit()
        return self.get_candidate(record["id"]) or record

    def get_candidate(self, candidate_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM EvolutionCandidate WHERE id=?", (candidate_id,)
        ).fetchone()
        return _candidate_row(row) if row else None

    def get_by_signature(self, signature: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM EvolutionCandidate WHERE signature=?", (signature,)
        ).fetchone()
        return _candidate_row(row) if row else None

    def list_candidates(
        self, *, status: Optional[str] = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if status:
            rows = self._db.execute(
                "SELECT * FROM EvolutionCandidate WHERE status=? "
                "ORDER BY createdAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM EvolutionCandidate ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_candidate_row(r) for r in rows]

    def update_candidate(self, candidate_id: str, **fields: Any) -> Optional[dict[str, Any]]:
        # Public field name → column name. `proposedOps` lives in `proposedOpsJson`.
        columns = {
            "status": "status", "refusalCode": "refusalCode", "targetPath": "targetPath",
            "proposedOps": "proposedOpsJson", "activatedVersion": "activatedVersion",
            "previousVersion": "previousVersion", "observedCount": "observedCount",
            "problemStatement": "problemStatement", "subjectType": "subjectType",
            "surfaceConfig": "surfaceConfigJson",
        }
        sets: list[str] = []
        params: list[Any] = []
        for key, value in fields.items():
            column = columns.get(key)
            if column is None:
                continue
            sets.append(f"{column}=?")
            params.append(
                json.dumps(value)
                if key in {"proposedOps", "surfaceConfig"} and value is not None
                else value
            )
        if not sets:
            return self.get_candidate(candidate_id)
        sets.append("updatedAt=?")
        params.append(now_iso())
        params.append(candidate_id)
        self._db.execute(f"UPDATE EvolutionCandidate SET {', '.join(sets)} WHERE id=?", params)
        self._db.commit()
        return self.get_candidate(candidate_id)

    # ── Attempts ──────────────────────────────────────────────────────────────
    def claim(
        self, candidate_id: str, *, statuses: tuple[str, ...] = ("inert", "proposed"),
    ) -> Optional[dict[str, Any]]:
        """Atomically move a candidate to `evaluating`; return it only on success.

        The conditional UPDATE is the single-flight lease: a second conductor (or
        a second process) sees rowcount 0 and must not run the same candidate.
        """
        allowed = tuple(status for status in statuses if status in STATUSES)
        if not allowed:
            return None
        placeholders = ",".join("?" for _ in allowed)
        cursor = self._db.execute(
            "UPDATE EvolutionCandidate SET status='evaluating', updatedAt=? "
            f"WHERE id=? AND status IN ({placeholders})",
            (now_iso(), candidate_id, *allowed),
        )
        self._db.commit()
        return self.get_candidate(candidate_id) if cursor.rowcount == 1 else None

    def reclaim_stale(
        self, lease_seconds: int, *, now: Optional[str] = None,
    ) -> list[str]:
        """Move stale `evaluating` rows back to `proposed`; return their ids."""
        import datetime as _dt  # noqa: PLC0415

        current = now or now_iso()
        cutoff = (
            _dt.datetime.now(_dt.timezone.utc)
            - _dt.timedelta(seconds=max(1, int(lease_seconds)))
        ).strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"
        rows = self._db.execute(
            "SELECT id FROM EvolutionCandidate "
            "WHERE status='evaluating' AND updatedAt < ?",
            (cutoff,),
        ).fetchall()
        ids = [str(row["id"]) for row in rows]
        for candidate_id in ids:
            self._db.execute(
                "UPDATE EvolutionCandidate SET status='proposed', updatedAt=? "
                "WHERE id=? AND status='evaluating'",
                (current, candidate_id),
            )
        if ids:
            self._db.commit()
        return ids

    def experiments_started_since(self, since_iso: str) -> int:
        """Count non-refused attempts started at/after `since_iso` (daily budget)."""
        row = self._db.execute(
            "SELECT COUNT(*) AS n FROM EvolutionAttempt "
            "WHERE startedAt >= ? AND outcome != 'refused'",
            (since_iso,),
        ).fetchone()
        return int(row["n"]) if row else 0

    def save_attempt(self, attempt: dict[str, Any]) -> dict[str, Any]:
        candidate_id = attempt["candidateId"]
        index_row = self._db.execute(
            "SELECT COALESCE(MAX(attemptIndex), -1) AS m FROM EvolutionAttempt WHERE candidateId=?",
            (candidate_id,),
        ).fetchone()
        attempt_index = int(index_row["m"]) + 1 if attempt.get("attemptIndex") is None else int(attempt["attemptIndex"])
        record = {
            **attempt,
            "id": attempt.get("id") or new_attempt_id(),
            "attemptIndex": attempt_index,
            "startedAt": attempt.get("startedAt") or now_iso(),
        }
        self._db.execute(
            """INSERT INTO EvolutionAttempt
               (id, candidateId, attemptIndex, targetPath, baseDigest, diffDigest,
                proposedOpsJson, evaluationJson, outcome, outcomeReason, costMicros,
                tokensUsed, startedAt, finishedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"], candidate_id, record["attemptIndex"],
                record.get("targetPath", ""), record.get("baseDigest", ""),
                record.get("diffDigest", ""),
                json.dumps(record.get("proposedOps") or []),
                json.dumps(record["evaluation"]) if record.get("evaluation") is not None else None,
                record.get("outcome", "failure"), record.get("outcomeReason"),
                record.get("costMicros"), record.get("tokensUsed"),
                record["startedAt"], record.get("finishedAt"),
            ),
        )
        self._db.commit()
        return self.get_attempt(record["id"]) or record

    def get_attempt(self, attempt_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM EvolutionAttempt WHERE id=?", (attempt_id,)
        ).fetchone()
        return _attempt_row(row) if row else None

    def list_attempts(self, candidate_id: str, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        rows = self._db.execute(
            "SELECT * FROM EvolutionAttempt WHERE candidateId=? ORDER BY attemptIndex ASC LIMIT ?",
            (candidate_id, limit),
        ).fetchall()
        return [_attempt_row(r) for r in rows]


__all__ = [
    "EvolutionStore",
    "OUTCOMES",
    "STATUSES",
    "new_attempt_id",
    "new_candidate_id",
]

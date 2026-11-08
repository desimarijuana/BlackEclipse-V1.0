"""Decision audit persistence on the ONE `agent-memory.db` connection.

Every decision request is a durable record: what was asked (by template hash),
against what state (content hash), which provider/model answered, the typed
answers with their probabilities and confidence, the policy verdict, and how long
it took. That record is the audit trail and the calibration substrate.

Two invariants, copied from the Advisory Ledger:

  * **No second database.** It wraps the shared `AgentMemoryStore` connection and
    creates its tables idempotently.
  * **Records are immutable.** A record is written once; a re-run of the same
    request is a no-op (deterministic id). An OUTCOME is appended later and never
    rewrites the original answer.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Optional

from ..persistence import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS DecisionRecord (
  id             TEXT PRIMARY KEY,
  runId          TEXT,
  ownerId        TEXT,
  conversationId TEXT,
  createdAt      TEXT NOT NULL,
  provider       TEXT NOT NULL,
  model          TEXT NOT NULL DEFAULT '',
  questionHash   TEXT NOT NULL,
  stateHash      TEXT,
  status         TEXT NOT NULL,
  policy         TEXT NOT NULL DEFAULT '{}',
  answers        TEXT NOT NULL DEFAULT '{}',
  usage          TEXT NOT NULL DEFAULT '{}',
  latencyMs      INTEGER NOT NULL DEFAULT 0,
  tool           TEXT,
  reason         TEXT
);
CREATE INDEX IF NOT EXISTS idx_decision_record_created ON DecisionRecord(createdAt);
CREATE INDEX IF NOT EXISTS idx_decision_record_run ON DecisionRecord(runId);
CREATE INDEX IF NOT EXISTS idx_decision_record_owner ON DecisionRecord(ownerId);
CREATE INDEX IF NOT EXISTS idx_decision_record_question ON DecisionRecord(questionHash);

CREATE TABLE IF NOT EXISTS DecisionOutcome (
  recordId    TEXT PRIMARY KEY,
  evaluatedAt TEXT NOT NULL,
  questionId  TEXT,
  expected    TEXT,
  observed    TEXT,
  verdict     TEXT NOT NULL,
  note        TEXT,
  FOREIGN KEY (recordId) REFERENCES DecisionRecord(id) ON DELETE CASCADE
);
"""

# The closed outcome vocabulary. `unscored` is the absence of a row, not a value.
OUTCOME_VERDICTS: tuple[str, ...] = ("correct", "incorrect", "partial", "unknown")


def record_id(
    *,
    run_id: Optional[str],
    provider: str,
    question_hash: str,
    state_hash: str,
    tool: Optional[str] = None,
) -> str:
    """Deterministic id: a resumed run never double-counts the same decision."""
    raw = "|".join(
        [
            str(run_id or ""),
            str(provider or ""),
            str(question_hash or ""),
            str(state_hash or ""),
            str(tool or ""),
        ]
    )
    return "dec_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class DecisionStore:
    """CRUD over the decision tables on the shared agent-memory connection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self) -> sqlite3.Connection:
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ── Records ──────────────────────────────────────────────────────────────
    def write_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Insert once. An existing id is returned unchanged (immutable)."""
        existing = self.get_record(str(record["id"]))
        if existing is not None:
            return existing
        self._db.execute(
            """INSERT INTO DecisionRecord
               (id, runId, ownerId, conversationId, createdAt, provider, model,
                questionHash, stateHash, status, policy, answers, usage,
                latencyMs, tool, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"],
                record.get("runId"),
                record.get("ownerId"),
                record.get("conversationId"),
                record.get("createdAt") or now_iso(),
                record.get("provider") or "",
                record.get("model") or "",
                record.get("questionHash") or "",
                record.get("stateHash"),
                record.get("status") or "unavailable",
                json.dumps(record.get("policy") or {}),
                json.dumps(record.get("answers") or {}),
                json.dumps(record.get("usage") or {}),
                int(record.get("latencyMs") or 0),
                record.get("tool"),
                record.get("reason"),
            ),
        )
        self._db.commit()
        return self.get_record(record["id"]) or dict(record)

    def get_record(self, decision_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM DecisionRecord WHERE id = ?", (decision_id,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_records(
        self,
        *,
        owner_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if owner_id:
            clauses.append("ownerId = ?")
            params.append(owner_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            f"SELECT * FROM DecisionRecord{where} ORDER BY createdAt DESC LIMIT ?",
            (*params, max(1, min(int(limit), 200))),
        ).fetchall()
        records = [self._row_to_dict(row) for row in rows]
        for record in records:
            record["outcome"] = self.get_outcome(record["id"])
        return records

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        for key in ("policy", "answers", "usage"):
            raw = record.get(key)
            try:
                record[key] = json.loads(raw) if raw else ({} if key != "answers" else {})
            except (TypeError, ValueError):
                # A corrupt row must not break the whole listing; keep it visible
                # as an explicit marker instead of pretending it parsed.
                record[key] = {"_unparsed": True}
        return record

    # ── Outcomes (appended later; never rewrite the answer) ─────────────────
    def record_outcome(
        self,
        *,
        record_id: str,
        verdict: str,
        question_id: Optional[str] = None,
        expected: Any = None,
        observed: Any = None,
        note: Optional[str] = None,
    ) -> dict[str, Any]:
        if verdict not in OUTCOME_VERDICTS:
            raise ValueError(f"unknown outcome verdict {verdict!r}")
        self._db.execute(
            """INSERT INTO DecisionOutcome
               (recordId, evaluatedAt, questionId, expected, observed, verdict, note)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(recordId) DO UPDATE SET
                 evaluatedAt=excluded.evaluatedAt,
                 questionId=excluded.questionId,
                 expected=excluded.expected,
                 observed=excluded.observed,
                 verdict=excluded.verdict,
                 note=excluded.note""",
            (
                record_id,
                now_iso(),
                question_id,
                json.dumps(expected) if expected is not None else None,
                json.dumps(observed) if observed is not None else None,
                verdict,
                note,
            ),
        )
        self._db.commit()
        return self.get_outcome(record_id) or {}

    def get_outcome(self, record_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM DecisionOutcome WHERE recordId = ?", (record_id,)
        ).fetchone()
        return dict(row) if row else None

    def scorecard(self, *, owner_id: Optional[str] = None) -> dict[str, Any]:
        clause = " WHERE ownerId = ?" if owner_id else ""
        params: tuple[Any, ...] = (owner_id,) if owner_id else ()
        by_status = {
            row["status"]: int(row["n"])
            for row in self._db.execute(
                f"SELECT status, COUNT(*) AS n FROM DecisionRecord{clause} GROUP BY status",
                params,
            ).fetchall()
        }
        by_provider = {
            row["provider"]: int(row["n"])
            for row in self._db.execute(
                f"SELECT provider, COUNT(*) AS n FROM DecisionRecord{clause} "
                "GROUP BY provider ORDER BY n DESC",
                params,
            ).fetchall()
        }
        join_clause = (
            "JOIN DecisionRecord r ON r.id = o.recordId AND r.ownerId = ?"
            if owner_id
            else "JOIN DecisionRecord r ON r.id = o.recordId"
        )
        by_outcome = {
            row["verdict"]: int(row["n"])
            for row in self._db.execute(
                f"SELECT o.verdict, COUNT(*) AS n FROM DecisionOutcome o {join_clause} "
                "GROUP BY o.verdict",
                params,
            ).fetchall()
        }
        total = sum(by_status.values())
        evaluated = sum(by_outcome.values())
        correct = by_outcome.get("correct", 0)
        return {
            "total": total,
            "byStatus": {
                "answered": by_status.get("answered", 0),
                "review": by_status.get("review", 0),
                "unavailable": by_status.get("unavailable", 0),
            },
            "byProvider": by_provider,
            "evaluated": evaluated,
            "byOutcome": by_outcome,
            "accuracy": (correct / evaluated) if evaluated else None,
        }


__all__ = ["DecisionStore", "OUTCOME_VERDICTS", "record_id"]

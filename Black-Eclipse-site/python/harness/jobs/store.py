"""Job persistence, bound to the ONE agent-memory connection (Phase 6).

Owns the `HarnessJob` and `HarnessJobRun` tables and their helpers. Mirrors
`run_lineage.py`, `code/store.py` and `mcp/approvals.py`: the module is bound to
the single `AgentMemoryStore` sqlite connection and owns only its own tables, so
`persistence.py` — pinned at its size ratchet — does not grow.

The database is `agent-memory.db` (the runtime's own). NEVER `eclipse-memory.db`
and NEVER `jdds.db`. The DDL is idempotent (`CREATE TABLE IF NOT EXISTS`) and is
applied on first use.

`runId` links a job run to the existing `HarnessRun` row — a job run IS a normal
run with a trace, events, tool executions and (for code jobs) a verification
ledger. Never a second execution record.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..persistence import now_iso
from .model import JobDefinition, JobDelivery, JobTarget

# A job run status is one of the model's `RUN_STATUSES`.
_TERMINAL = ("ok", "failed", "skipped", "timed_out", "refused")


def new_job_id() -> str:
    return uuid.uuid4().hex


def new_job_run_id() -> str:
    return "jobrun_" + uuid.uuid4().hex[:20]


def _job_row(row: Any) -> dict[str, Any]:
    """Reassemble a JobDefinition from a row (secret hash + JSON blobs)."""
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "cron": row["cron"],
        "interval_seconds": row["intervalSeconds"],
        "watch_path": row["watchPath"],
        "webhook_token_hash": row["webhookTokenHash"],
        "timezone": row["timezone"],
        "on_missed": row["onMissed"],
        "target": json.loads(row["targetJson"]) if row["targetJson"] else {},
        "delivery": json.loads(row["deliveryJson"]) if row["deliveryJson"] else {},
        # Phase 11 (additive, old-row-safe): the scope FILTER label.
        "scope_id": row["scopeId"] if "scopeId" in row.keys() else None,
        "enabled": bool(row["enabled"]),
        "max_runtime_s": row["maxRuntimeS"],
        "created_at": row["createdAt"],
        "updated_at": row["updatedAt"],
        "last_run_at": row["lastRunAt"] if "lastRunAt" in row.keys() else None,
        "consecutive_failures": row["consecutiveFailures"],
        "breaker": row["breaker"],
        "breaker_opened_at": row["breakerOpenedAt"],
        "breaker_reset_by": row["breakerResetBy"],
    }


def _run_row(row: Any) -> dict[str, Any]:
    raw = json.loads(row["deliveryJson"]) if row["deliveryJson"] else None
    # Phase 11: a run records ONE OUTCOME PER TARGET (a list). A row written before
    # this phase stored a single dict; normalize it to a one-element list without
    # rewriting the row (old-row-safe). `delivery` stays the first outcome so the
    # older front door keeps working.
    if isinstance(raw, list):
        deliveries = raw
    elif isinstance(raw, dict):
        deliveries = [raw]
    else:
        deliveries = None
    return {
        "id": row["id"],
        "jobId": row["jobId"],
        "runId": row["runId"],
        "scopeId": row["scopeId"] if "scopeId" in row.keys() else None,
        "triggeredBy": row["triggeredBy"],
        "scheduledFor": row["scheduledFor"],
        "startedAt": row["startedAt"],
        "finishedAt": row["finishedAt"],
        "status": row["status"],
        "outcomeReason": row["outcomeReason"],
        "delivery": deliveries[0] if deliveries else None,
        "deliveries": deliveries,
        "missed": bool(row["missed"]),
    }


class JobStore:
    """Jobs + job-run history over the ONE agent-memory store."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessJob (
              id                   TEXT PRIMARY KEY,
              name                 TEXT NOT NULL,
              kind                 TEXT NOT NULL,
              cron                 TEXT,
              intervalSeconds      INTEGER,
              watchPath            TEXT,
              webhookTokenHash     TEXT,
              timezone             TEXT NOT NULL DEFAULT 'local',
              onMissed             TEXT NOT NULL DEFAULT 'skip',
              targetJson           TEXT NOT NULL,
              deliveryJson         TEXT NOT NULL,
              enabled              INTEGER NOT NULL DEFAULT 0,
              maxRuntimeS          INTEGER NOT NULL DEFAULT 900,
              createdAt            TEXT NOT NULL,
              updatedAt            TEXT NOT NULL,
              consecutiveFailures  INTEGER NOT NULL DEFAULT 0,
              breaker              TEXT NOT NULL DEFAULT 'closed',
              breakerOpenedAt      TEXT,
              breakerResetBy       TEXT
            )
            """
        )
        # Additive column: the resolved last-run time, so the scheduler can order
        # due jobs without scanning the run table. Idempotent ALTER.
        existing = {r["name"] for r in self._db.execute("PRAGMA table_info(HarnessJob)").fetchall()}
        if "lastRunAt" not in existing:
            self._db.execute("ALTER TABLE HarnessJob ADD COLUMN lastRunAt TEXT")
        # Phase 11 (additive): the scope FILTER label. A job saved before this
        # phase reads NULL and behaves exactly as before.
        if "scopeId" not in existing:
            self._db.execute("ALTER TABLE HarnessJob ADD COLUMN scopeId TEXT")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessJobRun (
              id            TEXT PRIMARY KEY,
              jobId         TEXT NOT NULL,
              runId         TEXT,
              triggeredBy   TEXT NOT NULL,
              scheduledFor  TEXT NOT NULL,
              startedAt     TEXT NOT NULL,
              finishedAt    TEXT,
              status        TEXT NOT NULL,
              outcomeReason TEXT,
              deliveryJson  TEXT,
              missed        INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Phase 11 (additive): the run's scope FILTER label, so an artifact read can
        # be refused for another scope without opening the file. Old rows read NULL.
        run_cols = {r["name"] for r in self._db.execute("PRAGMA table_info(HarnessJobRun)").fetchall()}
        if "scopeId" not in run_cols:
            self._db.execute("ALTER TABLE HarnessJobRun ADD COLUMN scopeId TEXT")
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobrun_job ON HarnessJobRun(jobId, startedAt)"
        )
        self._db.commit()

    # ── Jobs ─────────────────────────────────────────────────────────────────
    def save_job(self, job: JobDefinition) -> JobDefinition:
        """Insert or replace a job definition (JSON blobs + queryable columns)."""
        self._db.execute(
            """INSERT OR REPLACE INTO HarnessJob
               (id, name, kind, cron, intervalSeconds, watchPath, webhookTokenHash,
                timezone, onMissed, targetJson, deliveryJson, scopeId, enabled, maxRuntimeS,
                createdAt, updatedAt, consecutiveFailures, breaker, breakerOpenedAt,
                breakerResetBy, lastRunAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job.id, job.name, job.kind, job.cron, job.interval_seconds,
                job.watch_path, job.webhook_token_hash, job.timezone, job.on_missed,
                job.target.model_dump_json(), job.delivery.model_dump_json(),
                job.scope_id, 1 if job.enabled else 0, job.max_runtime_s, job.created_at,
                job.updated_at, job.consecutive_failures, job.breaker,
                job.breaker_opened_at, job.breaker_reset_by, job.last_run_at,
            ),
        )
        self._db.commit()
        return job

    def get_job(self, job_id: str) -> Optional[JobDefinition]:
        row = self._db.execute("SELECT * FROM HarnessJob WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        return JobDefinition(**_job_row(row))

    def list_jobs(self, limit: int = 100, *, scope_id: Optional[str] = None) -> list[JobDefinition]:
        """List jobs, optionally narrowed by a caller-supplied scope FILTER label.

        A `scope_id` narrows what is returned; it NEVER authorizes a mutation.
        Absent ⇒ every job (the single-user-local default).
        """
        limit = max(1, min(int(limit), 500))
        if scope_id is None:
            rows = self._db.execute(
                "SELECT * FROM HarnessJob ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM HarnessJob WHERE scopeId=? ORDER BY createdAt DESC LIMIT ?",
                (scope_id, limit),
            ).fetchall()
        return [JobDefinition(**_job_row(r)) for r in rows]

    def delete_job(self, job_id: str) -> bool:
        """Delete a job definition. Run history is RETAINED (audit)."""
        cur = self._db.execute("DELETE FROM HarnessJob WHERE id=?", (job_id,))
        self._db.commit()
        return cur.rowcount > 0

    def set_enabled(self, job_id: str, enabled: bool) -> Optional[JobDefinition]:
        self._db.execute(
            "UPDATE HarnessJob SET enabled=?, updatedAt=? WHERE id=?",
            (1 if enabled else 0, now_iso(), job_id),
        )
        self._db.commit()
        return self.get_job(job_id)

    def record_outcome(
        self, job_id: str, *, status: str, ran_at: str,
        consecutive_failures: int, breaker: str, breaker_opened_at: Optional[str],
    ) -> None:
        self._db.execute(
            """UPDATE HarnessJob
               SET lastRunAt=?, updatedAt=?, consecutiveFailures=?, breaker=?, breakerOpenedAt=?
               WHERE id=?""",
            (ran_at, now_iso(), consecutive_failures, breaker, breaker_opened_at, job_id),
        )
        self._db.commit()

    def touch_last_run(self, job_id: str, *, ran_at: str) -> None:
        """Advance the due-computation anchor without changing counters.

        Used when a tick or a startup reconciliation records a `skipped`
        decision, so the SAME decision is not recorded again on the next tick.
        """
        self._db.execute(
            "UPDATE HarnessJob SET lastRunAt=?, updatedAt=? WHERE id=?",
            (ran_at, now_iso(), job_id),
        )
        self._db.commit()

    def reset_breaker(self, job_id: str, *, reset_by: str) -> Optional[JobDefinition]:
        self._db.execute(
            """UPDATE HarnessJob
               SET consecutiveFailures=0, breaker='closed', breakerOpenedAt=NULL,
                   breakerResetBy=?, updatedAt=?
               WHERE id=?""",
            (reset_by, now_iso(), job_id),
        )
        self._db.commit()
        return self.get_job(job_id)

    # ── Job runs ─────────────────────────────────────────────────────────────
    def start_run(
        self, job_id: str, *, triggered_by: str, scheduled_for: str, run_id: Optional[str] = None,
        missed: bool = False, scope_id: Optional[str] = None,
    ) -> dict[str, Any]:
        row = {
            "id": new_job_run_id(),
            "jobId": job_id,
            "runId": run_id,
            "scopeId": scope_id,
            "triggeredBy": triggered_by,
            "scheduledFor": scheduled_for,
            "startedAt": now_iso(),
            "finishedAt": None,
            "status": "running",
            "outcomeReason": None,
            "deliveryJson": None,
            "missed": 1 if missed else 0,
        }
        self._db.execute(
            """INSERT INTO HarnessJobRun
               (id, jobId, runId, scopeId, triggeredBy, scheduledFor, startedAt, finishedAt,
                status, outcomeReason, deliveryJson, missed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["id"], row["jobId"], row["runId"], row["scopeId"], row["triggeredBy"],
                row["scheduledFor"], row["startedAt"], row["finishedAt"], row["status"],
                row["outcomeReason"], row["deliveryJson"], row["missed"],
            ),
        )
        self._db.commit()
        return row

    def finish_run(
        self, job_run_id: str, *, status: str, outcome_reason: Optional[str] = None,
        run_id: Optional[str] = None,
        delivery: Optional[list[dict[str, Any]] | dict[str, Any]] = None,
    ) -> None:
        """Finish a run. `delivery` is a LIST of per-target outcomes (Phase 11)."""
        self._db.execute(
            """UPDATE HarnessJobRun
               SET status=?, outcomeReason=?, finishedAt=?, runId=COALESCE(?, runId),
                   deliveryJson=?
               WHERE id=?""",
            (
                status, outcome_reason, now_iso(), run_id,
                json.dumps(delivery) if delivery is not None else None, job_run_id,
            ),
        )
        self._db.commit()

    def get_run(self, job_run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM HarnessJobRun WHERE id=?", (job_run_id,)
        ).fetchone()
        return _run_row(row) if row else None

    def list_runs(
        self, job_id: str, limit: int = 50, *, scope_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if scope_id is None:
            rows = self._db.execute(
                "SELECT * FROM HarnessJobRun WHERE jobId=? ORDER BY startedAt DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM HarnessJobRun WHERE jobId=? AND scopeId=? "
                "ORDER BY startedAt DESC LIMIT ?",
                (job_id, scope_id, limit),
            ).fetchall()
        return [_run_row(r) for r in rows]

    def last_run(self, job_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM HarnessJobRun WHERE jobId=? ORDER BY startedAt DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        return _run_row(row) if row else None

    def running_count(self) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS n FROM HarnessJobRun WHERE status='running'"
        ).fetchone()
        return int(row["n"]) if row else 0

    def has_running(self, job_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM HarnessJobRun WHERE jobId=? AND status='running' LIMIT 1",
            (job_id,),
        ).fetchone()
        return row is not None


__all__ = ["JobStore", "new_job_id", "new_job_run_id"]

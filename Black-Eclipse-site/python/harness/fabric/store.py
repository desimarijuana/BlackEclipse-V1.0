"""Durable Execution-Fabric state on the ONE agent-memory connection.

Jobs, attempts, events, workers, distributed locks and idempotency keys are all
persisted here — bound to `AgentMemoryStore._db`, exactly like
`orchestration/store.py`, `tasks/store.py` and `terminal/store.py`. No second
database is introduced, and no dependency is added.

Writes are bounded (a runaway job payload cannot grow the database without
limit) and idempotent on stable ids, so recovery can replay safely. Times are
stored as REAL epoch seconds so ordering and comparison are exact.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from .models import (
    Job,
    JobAttempt,
    JobState,
    WorkerInfo,
    new_attempt_id,
    new_event_id,
    now,
)
from .state import InvalidJobTransition, require_transition

MAX_STORED_JSON = 200_000

_JOB_COLUMNS = {
    "type", "queue", "status", "priority", "workerKind", "taskId", "parentJobId",
    "rootJobId", "agentId", "sessionId", "userId", "workspaceId", "input", "output",
    "error", "errorClass", "progress", "attempts", "maxAttempts", "timeoutMs",
    "idempotencyKey", "correlationId", "traceId", "workerId", "durable",
    "availableAt", "leaseExpiresAt", "startedAt", "completedAt", "cancelledAt", "metadata",
}

# The terminal transitions spell these fields in snake_case; without
# normalization they were silently dropped and the job row lost its
# errorClass/timestamps (only the events carried them).
_JOB_COLUMN_ALIASES = {
    "worker_kind": "workerKind", "task_id": "taskId", "parent_job_id": "parentJobId",
    "root_job_id": "rootJobId", "agent_id": "agentId", "session_id": "sessionId",
    "user_id": "userId", "workspace_id": "workspaceId", "error_class": "errorClass",
    "max_attempts": "maxAttempts", "timeout_ms": "timeoutMs",
    "idempotency_key": "idempotencyKey", "correlation_id": "correlationId",
    "trace_id": "traceId", "worker_id": "workerId", "available_at": "availableAt",
    "lease_expires_at": "leaseExpiresAt", "started_at": "startedAt",
    "completed_at": "completedAt", "cancelled_at": "cancelledAt",
}


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None
    if len(text) > MAX_STORED_JSON:
        return text[:MAX_STORED_JSON] + "\n[TRUNCATED]"
    return text


def _load(text: Any, default: Any) -> Any:
    if text in (None, ""):
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


class FabricStore:
    """Persist jobs, attempts, events, workers, locks and idempotency keys."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    # ── schema ───────────────────────────────────────────────────────────────
    def _ensure_schema(self) -> None:
        db = self._db
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS FabricJob (
              id            TEXT PRIMARY KEY,
              type          TEXT NOT NULL,
              queue         TEXT NOT NULL,
              status        TEXT NOT NULL,
              priority      INTEGER NOT NULL DEFAULT 500,
              workerKind    TEXT,
              taskId        TEXT,
              parentJobId   TEXT,
              rootJobId     TEXT,
              agentId       TEXT,
              sessionId     TEXT,
              userId        TEXT,
              workspaceId   TEXT,
              input         TEXT,
              output        TEXT,
              error         TEXT,
              errorClass    TEXT,
              progress      REAL NOT NULL DEFAULT 0,
              attempts      INTEGER NOT NULL DEFAULT 0,
              maxAttempts   INTEGER NOT NULL DEFAULT 1,
              timeoutMs     INTEGER NOT NULL DEFAULT 120000,
              idempotencyKey TEXT,
              correlationId TEXT,
              traceId       TEXT,
              workerId      TEXT,
              durable       INTEGER NOT NULL DEFAULT 0,
              availableAt   REAL,
              leaseExpiresAt REAL,
              createdAt     REAL NOT NULL,
              startedAt     REAL,
              completedAt   REAL,
              cancelledAt   REAL,
              updatedAt     REAL NOT NULL,
              metadata      TEXT
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_fabric_job_queue ON FabricJob(queue, status, availableAt)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_fabric_job_status ON FabricJob(status, updatedAt)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_fabric_job_root ON FabricJob(rootJobId)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_fabric_job_parent ON FabricJob(parentJobId)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_fabric_job_user ON FabricJob(userId)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_fabric_job_idem ON FabricJob(idempotencyKey)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_fabric_job_lease ON FabricJob(status, leaseExpiresAt)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS FabricJobAttempt (
              id          TEXT PRIMARY KEY,
              jobId       TEXT NOT NULL,
              attempt     INTEGER NOT NULL,
              workerId    TEXT,
              status      TEXT NOT NULL,
              error       TEXT,
              errorClass  TEXT,
              startedAt   REAL NOT NULL,
              finishedAt  REAL,
              durationMs  INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_fabric_attempt_job ON FabricJobAttempt(jobId, attempt)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS FabricJobEvent (
              id     TEXT PRIMARY KEY,
              jobId  TEXT NOT NULL,
              seq    INTEGER NOT NULL,
              type   TEXT NOT NULL,
              at     REAL NOT NULL,
              data   TEXT
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_fabric_event_job ON FabricJobEvent(jobId, seq)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS FabricWorker (
              id             TEXT PRIMARY KEY,
              kind           TEXT NOT NULL,
              queue          TEXT NOT NULL,
              status         TEXT NOT NULL,
              concurrency    INTEGER NOT NULL DEFAULT 1,
              activeJobs     INTEGER NOT NULL DEFAULT 0,
              pid            INTEGER,
              startedAt      REAL NOT NULL,
              lastHeartbeat  REAL NOT NULL,
              metadata       TEXT
            )
            """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_fabric_worker_queue ON FabricWorker(queue, status)")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS FabricLock (
              name        TEXT PRIMARY KEY,
              owner       TEXT NOT NULL,
              token       TEXT NOT NULL,
              ttlMs       INTEGER NOT NULL,
              acquiredAt  REAL NOT NULL,
              expiresAt   REAL NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS FabricIdempotency (
              key        TEXT PRIMARY KEY,
              jobId      TEXT NOT NULL,
              createdAt  REAL NOT NULL
            )
            """
        )
        db.commit()

    # ── jobs ─────────────────────────────────────────────────────────────────
    def create_job(self, job: Job) -> Job:
        self._db.execute(
            """INSERT INTO FabricJob
               (id, type, queue, status, priority, workerKind, taskId, parentJobId,
                rootJobId, agentId, sessionId, userId, workspaceId, input, output,
                error, errorClass, progress, attempts, maxAttempts, timeoutMs,
                idempotencyKey, correlationId, traceId, workerId, durable,
                availableAt, leaseExpiresAt, createdAt, startedAt, completedAt,
                cancelledAt, updatedAt, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job.id, job.type, job.queue, job.status, int(job.priority),
                job.worker_kind, job.task_id, job.parent_job_id, job.root_job_id,
                job.agent_id, job.session_id, job.user_id, job.workspace_id,
                _json(job.input), _json(job.output), job.error, job.error_class,
                float(job.progress), int(job.attempts), int(job.max_attempts),
                int(job.timeout_ms), job.idempotency_key, job.correlation_id,
                job.trace_id, job.worker_id, 1 if job.durable else 0,
                job.available_at, None, float(job.created_at), job.started_at,
                job.completed_at, job.cancelled_at, float(job.updated_at),
                _json(job.metadata),
            ),
        )
        self._db.commit()
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        row = self._db.execute("SELECT * FROM FabricJob WHERE id = ?", (job_id,)).fetchone()
        return self._to_job(row) if row else None

    def list_jobs(
        self,
        *,
        queue: Optional[str] = None,
        status: Optional[str] = None,
        statuses: Optional[list[str]] = None,
        type: Optional[str] = None,
        root_job_id: Optional[str] = None,
        parent_job_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order: str = "recent",
    ) -> list[Job]:
        where: list[str] = []
        params: list[Any] = []
        if queue:
            where.append("queue = ?"); params.append(queue)
        if status:
            where.append("status = ?"); params.append(status)
        if statuses:
            where.append("status IN (" + ",".join("?" for _ in statuses) + ")"); params.extend(statuses)
        if type:
            where.append("type = ?"); params.append(type)
        if root_job_id:
            where.append("rootJobId = ?"); params.append(root_job_id)
        if parent_job_id:
            where.append("parentJobId = ?"); params.append(parent_job_id)
        if user_id:
            where.append("userId = ?"); params.append(user_id)
        if agent_id:
            where.append("agentId = ?"); params.append(agent_id)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        order_clause = (
            "ORDER BY priority DESC, createdAt ASC" if order == "queue"
            else "ORDER BY createdAt DESC"
        )
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        rows = self._db.execute(
            f"SELECT * FROM FabricJob{clause} {order_clause} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [self._to_job(r) for r in rows]

    def update_job(self, job_id: str, **patch: Any) -> Optional[Job]:
        sets: list[str] = []
        params: list[Any] = []
        for key, value in patch.items():
            key = _JOB_COLUMN_ALIASES.get(key, key)
            if key not in _JOB_COLUMNS:
                continue
            sets.append(f"{key} = ?")
            if key in ("input", "output", "metadata"):
                params.append(_json(value))
            elif key == "durable":
                params.append(1 if value else 0)
            elif key == "progress":
                params.append(float(value))
            else:
                params.append(value)
        if not sets:
            return self.get_job(job_id)
        sets.append("updatedAt = ?")
        params.append(now())
        params.append(job_id)
        self._db.execute(f"UPDATE FabricJob SET {', '.join(sets)} WHERE id = ?", params)
        self._db.commit()
        return self.get_job(job_id)

    def set_state(self, job_id: str, target: JobState | str, **patch: Any) -> Job:
        """Transition a job through the validated state machine, then patch it."""
        target_state = target if isinstance(target, JobState) else JobState(str(target))
        current = self.get_job(job_id)
        if current is None:
            raise KeyError(f"no such job {job_id!r}")
        try:
            require_transition(current.state, target_state)
        except InvalidJobTransition:
            raise
        fields = {"status": target_state.value, **patch}
        updated = self.update_job(job_id, **fields)
        assert updated is not None
        return updated

    def append_event(self, job_id: str, event_type: str, data: Optional[dict[str, Any]] = None) -> int:
        row = self._db.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM FabricJobEvent WHERE jobId = ?", (job_id,)
        ).fetchone()
        seq = int(row["m"]) + 1
        self._db.execute(
            "INSERT INTO FabricJobEvent (id, jobId, seq, type, at, data) VALUES (?, ?, ?, ?, ?, ?)",
            (new_event_id(), job_id, seq, event_type, now(), _json(data or {})),
        )
        self._db.commit()
        return seq

    def list_events(self, job_id: str, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM FabricJobEvent WHERE jobId = ? ORDER BY seq ASC LIMIT ?",
            (job_id, max(1, min(int(limit), 2000))),
        ).fetchall()
        return [
            {"id": r["id"], "jobId": r["jobId"], "seq": r["seq"], "type": r["type"],
             "at": r["at"], "data": _load(r["data"], {})}
            for r in rows
        ]

    def start_attempt(self, job_id: str, *, attempt: int, worker_id: Optional[str]) -> str:
        attempt_id = new_attempt_id()
        self._db.execute(
            "INSERT INTO FabricJobAttempt (id, jobId, attempt, workerId, status, startedAt)"
            " VALUES (?, ?, ?, ?, 'RUNNING', ?)",
            (attempt_id, job_id, int(attempt), worker_id, now()),
        )
        self._db.commit()
        return attempt_id

    def finish_attempt(
        self, attempt_id: str, *, status: str, error: Optional[str] = None,
        error_class: Optional[str] = None, duration_ms: int = 0,
    ) -> None:
        self._db.execute(
            "UPDATE FabricJobAttempt SET status = ?, error = ?, errorClass = ?,"
            " finishedAt = ?, durationMs = ? WHERE id = ?",
            (status, error, error_class, now(), int(duration_ms), attempt_id),
        )
        self._db.commit()

    def list_attempts(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM FabricJobAttempt WHERE jobId = ? ORDER BY attempt ASC", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── queue claim / release ────────────────────────────────────────────────
    def claim_job(
        self, queues: list[str], *, worker_id: str, worker_kind: Optional[str] = None,
        lease_seconds: int = 120, moment: Optional[float] = None,
    ) -> Optional[Job]:
        moment = now() if moment is None else moment
        if not queues:
            return None
        placeholders = ",".join("?" for _ in queues)
        row = self._db.execute(
            f"""SELECT * FROM FabricJob
                WHERE queue IN ({placeholders}) AND status = 'QUEUED'
                  AND (availableAt IS NULL OR availableAt <= ?)
                  AND (? IS NULL OR workerKind IS NULL OR workerKind = ?)
                ORDER BY priority DESC, availableAt ASC, createdAt ASC
                LIMIT 1""",
            [*queues, moment, worker_kind, worker_kind],
        ).fetchone()
        if row is None:
            return None
        job_id = row["id"]
        attempt = int(row["attempts"]) + 1
        self._db.execute(
            """UPDATE FabricJob
               SET status = 'RUNNING', workerId = ?, startedAt = ?,
                   leaseExpiresAt = ?, attempts = ?, updatedAt = ?
               WHERE id = ? AND status = 'QUEUED'""",
            (worker_id, moment, moment + max(5, lease_seconds), attempt, moment, job_id),
        )
        self._db.commit()
        return self.get_job(job_id)

    def renew_lease(self, job_id: str, *, worker_id: str, lease_seconds: int) -> bool:
        moment = now()
        cur = self._db.execute(
            "UPDATE FabricJob SET leaseExpiresAt = ?, updatedAt = ?"
            " WHERE id = ? AND status = 'RUNNING' AND workerId = ?",
            (moment + max(5, lease_seconds), moment, job_id, worker_id),
        )
        self._db.commit()
        return cur.rowcount > 0

    def expired_running_jobs(self, *, moment: Optional[float] = None, limit: int = 100) -> list[Job]:
        moment = now() if moment is None else moment
        rows = self._db.execute(
            "SELECT * FROM FabricJob WHERE status = 'RUNNING' AND leaseExpiresAt IS NOT NULL"
            " AND leaseExpiresAt < ? ORDER BY startedAt ASC LIMIT ?",
            (moment, max(1, min(int(limit), 500))),
        ).fetchall()
        return [self._to_job(r) for r in rows]

    # ── terminal transitions ─────────────────────────────────────────────────
    def complete_job(self, job_id: str, *, output: Any = None, progress: float = 1.0) -> Job:
        return self.set_state(
            job_id, JobState.SUCCEEDED, output=output, error=None, error_class=None,
            progress=float(progress), completed_at=now(), leaseExpiresAt=None,
            availableAt=None,
        )

    def fail_job(self, job_id: str, *, error: str, error_class: Optional[str] = None) -> Job:
        return self.set_state(
            job_id, JobState.FAILED, error=error[:2000], error_class=error_class,
            completed_at=now(), leaseExpiresAt=None, availableAt=None,
        )

    def timed_out_job(self, job_id: str, *, error: str = "job timed out") -> Job:
        return self.set_state(
            job_id, JobState.TIMED_OUT, error=error[:2000], error_class="TIMEOUT",
            completed_at=now(), leaseExpiresAt=None, availableAt=None,
        )

    def requeue_for_retry(self, job_id: str, *, available_at: float, error: str,
                          error_class: Optional[str] = None) -> Job:
        self.set_state(
            job_id, JobState.RETRYING, error=error[:2000], error_class=error_class,
            completed_at=None, availableAt=available_at, leaseExpiresAt=None,
        )
        return self.set_state(job_id, JobState.QUEUED, availableAt=available_at)

    def to_dead_letter(self, job_id: str, *, error: str, error_class: Optional[str] = None) -> Job:
        return self.set_state(
            job_id, JobState.DEAD_LETTER, error=error[:2000], error_class=error_class,
            completed_at=now(), leaseExpiresAt=None, availableAt=None,
        )

    def request_cancel(self, job_id: str) -> Optional[Job]:
        current = self.get_job(job_id)
        if current is None or current.state in (
            JobState.SUCCEEDED, JobState.CANCELLED, JobState.TIMED_OUT, JobState.DEAD_LETTER,
        ):
            return current
        if current.state == JobState.RUNNING:
            return self.set_state(job_id, JobState.CANCEL_REQUESTED)
        return self.set_state(job_id, JobState.CANCELLED, cancelled_at=now(), completed_at=now())

    def mark_cancelled(self, job_id: str) -> Job:
        return self.set_state(
            job_id, JobState.CANCELLED, cancelled_at=now(), completed_at=now(),
            leaseExpiresAt=None, availableAt=None,
        )

    # ── aggregate views ──────────────────────────────────────────────────────
    def queue_stats(self) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT queue, status, COUNT(*) AS c FROM FabricJob GROUP BY queue, status"
        ).fetchall()
        queues: dict[str, dict[str, Any]] = {}
        for row in rows:
            bucket = queues.setdefault(
                row["queue"],
                {"queue": row["queue"], "waiting": 0, "active": 0, "delayed": 0,
                 "completed": 0, "failed": 0, "dlq": 0, "total": 0},
            )
            count = int(row["c"])
            bucket["total"] += count
            status = row["status"]
            if status == JobState.QUEUED.value:
                bucket["waiting"] += count
            elif status in (JobState.RUNNING.value, JobState.CANCEL_REQUESTED.value):
                bucket["active"] += count
            elif status in (JobState.RETRYING.value, JobState.PAUSED.value):
                bucket["delayed"] += count
            elif status == JobState.SUCCEEDED.value:
                bucket["completed"] += count
            elif status in (JobState.FAILED.value, JobState.TIMED_OUT.value):
                bucket["failed"] += count
            elif status == JobState.DEAD_LETTER.value:
                bucket["dlq"] += count
        return [queues[k] for k in sorted(queues)]

    def status_counts(self) -> dict[str, int]:
        rows = self._db.execute(
            "SELECT status, COUNT(*) AS c FROM FabricJob GROUP BY status"
        ).fetchall()
        return {r["status"]: int(r["c"]) for r in rows}

    def dlq_jobs(self, limit: int = 100) -> list[Job]:
        return self.list_jobs(status=JobState.DEAD_LETTER.value, limit=limit)

    def total_jobs(self) -> int:
        row = self._db.execute("SELECT COUNT(*) AS c FROM FabricJob").fetchone()
        return int(row["c"]) if row else 0

    # ── idempotency ──────────────────────────────────────────────────────────
    def idempotency_get(self, key: str) -> Optional[str]:
        row = self._db.execute(
            "SELECT jobId FROM FabricIdempotency WHERE key = ?", (key,)
        ).fetchone()
        return row["jobId"] if row else None

    def idempotency_put(self, key: str, job_id: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO FabricIdempotency (key, jobId, createdAt) VALUES (?, ?, ?)",
            (key, job_id, now()),
        )
        self._db.commit()

    # ── workers ──────────────────────────────────────────────────────────────
    def upsert_worker(self, info: WorkerInfo) -> None:
        self._db.execute(
            """INSERT INTO FabricWorker
               (id, kind, queue, status, concurrency, activeJobs, pid, startedAt, lastHeartbeat, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 status = excluded.status, concurrency = excluded.concurrency,
                 activeJobs = excluded.activeJobs, lastHeartbeat = excluded.lastHeartbeat,
                 metadata = excluded.metadata""",
            (info.id, info.kind, info.queue, info.status, int(info.concurrency),
             int(info.active_jobs), info.pid, info.started_at, info.last_heartbeat_at,
             _json(info.metadata)),
        )
        self._db.commit()

    def heartbeat_worker(self, worker_id: str, *, status: str, active_jobs: int) -> None:
        self._db.execute(
            "UPDATE FabricWorker SET status = ?, activeJobs = ?, lastHeartbeat = ? WHERE id = ?",
            (status, int(active_jobs), now(), worker_id),
        )
        self._db.commit()

    def list_workers(self) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT * FROM FabricWorker ORDER BY kind, queue").fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            data = dict(r)
            data["metadata"] = _load(data.get("metadata"), {})
            out.append(data)
        return out

    def remove_worker(self, worker_id: str) -> None:
        self._db.execute("DELETE FROM FabricWorker WHERE id = ?", (worker_id,))
        self._db.commit()

    def stale_workers(self, *, timeout_seconds: int, moment: Optional[float] = None) -> list[dict[str, Any]]:
        moment = now() if moment is None else moment
        rows = self._db.execute(
            "SELECT * FROM FabricWorker WHERE lastHeartbeat < ?",
            (moment - max(1, timeout_seconds),),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── distributed locks ────────────────────────────────────────────────────
    def try_acquire_lock(
        self, name: str, *, owner: str, token: str, ttl_ms: int,
        moment: Optional[float] = None,
    ) -> bool:
        moment = now() if moment is None else moment
        existing = self._db.execute("SELECT * FROM FabricLock WHERE name = ?", (name,)).fetchone()
        if existing is not None and float(existing["expiresAt"]) > moment:
            return False
        self._db.execute(
            """INSERT INTO FabricLock (name, owner, token, ttlMs, acquiredAt, expiresAt)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 owner = excluded.owner, token = excluded.token, ttlMs = excluded.ttlMs,
                 acquiredAt = excluded.acquiredAt, expiresAt = excluded.expiresAt""",
            (name, owner, token, int(ttl_ms), moment, moment + max(1, ttl_ms) / 1000.0),
        )
        self._db.commit()
        return True

    def release_lock(self, name: str, *, token: str) -> bool:
        cur = self._db.execute(
            "DELETE FROM FabricLock WHERE name = ? AND token = ?", (name, token)
        )
        self._db.commit()
        return cur.rowcount > 0

    def renew_lock(self, name: str, *, token: str, ttl_ms: int) -> bool:
        moment = now()
        cur = self._db.execute(
            "UPDATE FabricLock SET expiresAt = ? WHERE name = ? AND token = ?",
            (moment + max(1, ttl_ms) / 1000.0, name, token),
        )
        self._db.commit()
        return cur.rowcount > 0

    def get_lock(self, name: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM FabricLock WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def purge_expired_locks(self, *, moment: Optional[float] = None) -> int:
        moment = now() if moment is None else moment
        cur = self._db.execute("DELETE FROM FabricLock WHERE expiresAt < ?", (moment,))
        self._db.commit()
        return cur.rowcount

    # ── helpers ──────────────────────────────────────────────────────────────
    def _to_job(self, row: Any) -> Job:
        return Job(
            id=row["id"], type=row["type"], queue=row["queue"], status=row["status"],
            priority=int(row["priority"]), worker_kind=row["workerKind"],
            task_id=row["taskId"], parent_job_id=row["parentJobId"],
            root_job_id=row["rootJobId"], agent_id=row["agentId"],
            session_id=row["sessionId"], user_id=row["userId"],
            workspace_id=row["workspaceId"], input=_load(row["input"], {}),
            output=_load(row["output"], None), error=row["error"],
            error_class=row["errorClass"], progress=float(row["progress"] or 0.0),
            attempts=int(row["attempts"] or 0), max_attempts=int(row["maxAttempts"] or 1),
            timeout_ms=int(row["timeoutMs"] or 120_000),
            idempotency_key=row["idempotencyKey"], correlation_id=row["correlationId"],
            trace_id=row["traceId"], worker_id=row["workerId"],
            durable=bool(row["durable"]), available_at=row["availableAt"],
            created_at=float(row["createdAt"] or time.time()),
            started_at=row["startedAt"], completed_at=row["completedAt"],
            cancelled_at=row["cancelledAt"], updated_at=float(row["updatedAt"] or time.time()),
            metadata=_load(row["metadata"], {}),
        )


# A convenience for callers that want an attempt row object.
__all__ = ["FabricStore", "JobAttempt"]

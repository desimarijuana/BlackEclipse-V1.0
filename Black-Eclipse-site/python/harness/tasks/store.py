"""Durable task/plan persistence, bound to the ONE agent-memory connection.

Mirrors `run_lineage.py`, `jobs/store.py` and `code/store.py`: this module is
bound to the single `AgentMemoryStore` sqlite connection and owns only its own
tables, so `persistence.py` — pinned at its size ratchet — does not grow. The
database is `agent-memory.db` (the runtime's own), NEVER `eclipse-memory.db` and
NEVER `jdds.db`.

Tables (the logical entities of §4/§37):
  * `HarnessPlan`             — a named, durable intent.
  * `HarnessTask`             — one task; arbitrary parent/child nesting.
  * `HarnessTaskDependency`   — a directed edge between two tasks.
  * `HarnessTaskCriterion`    — one verifiable acceptance condition.
  * `HarnessTaskEvent`        — an immutable history row.
  * `HarnessTaskExecution`    — one execution attempt of a task.
  * `HarnessTaskCheckpoint`   — a durable resume boundary.
  * `HarnessTaskArtifact`     — a reference (never the bytes) to an artifact.

Atomicity: `claim_task` is a single conditional UPDATE, so two workers can never
both claim the same task. The store NEVER changes a task's status on its own
unless the caller supplies the transition — the state machine lives in
`state.py` and is enforced by `manager.py`.
"""

from __future__ import annotations

import json
import uuid
from enum import Enum
from typing import Any, Optional

from ..persistence import now_iso
from .model import (
    BlockedReason,
    CriterionState,
    DependencyKind,
    ExecutionStatus,
    FailurePolicy,
    Plan,
    PlanStatus,
    Task,
    TaskAcceptanceCriterion,
    TaskArtifact,
    TaskCheckpoint,
    TaskDependency,
    TaskEvent,
    TaskExecution,
    TaskPriority,
    TaskStatus,
    WaitingReason,
)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


# ── Row → model ───────────────────────────────────────────────────────────────


def _plan_row(row: Any) -> Plan:
    return Plan(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        objective=row["objective"] or "",
        root_task_id=row["rootTaskId"],
        status=PlanStatus(row["status"]),
        priority=TaskPriority(row["priority"]),
        agent_id=row["agentId"] or "eclipse-agent",
        metadata=_loads(row["metadata"], {}),
        created_at=row["createdAt"],
        updated_at=row["updatedAt"],
    )


def _task_row(row: Any) -> Task:
    return Task(
        id=row["id"],
        plan_id=row["planId"],
        parent_task_id=row["parentTaskId"],
        title=row["title"],
        description=row["description"] or "",
        objective=row["objective"] or "",
        status=TaskStatus(row["status"]),
        priority=TaskPriority(row["priority"]),
        progress=int(row["progress"] or 0),
        assigned_agent_id=row["assignedAgentId"],
        assigned_run_id=row["assignedRunId"],
        delegated_by=row["delegatedBy"],
        delegation_id=row["delegationId"],
        retry_count=int(row["retryCount"] or 0),
        max_retries=int(row["maxRetries"] or 0),
        backoff_ms=int(row["backoffMs"] or 0),
        available_at=row["availableAt"],
        claimed_by=row["claimedBy"],
        claim_token=row["claimToken"],
        claimed_at=row["claimedAt"],
        lease_expires_at=row["leaseExpiresAt"],
        required=bool(row["required"]),
        failure_policy=FailurePolicy(row["failurePolicy"]),
        weight=float(row["weight"] or 1.0),
        waiting_reason=WaitingReason(row["waitingReason"]) if row["waitingReason"] else None,
        blocked_reason=BlockedReason(row["blockedReason"]) if row["blockedReason"] else None,
        blocked_by=_loads(row["blockedBy"], []),
        output_reference=row["outputReference"],
        error=row["error"],
        error_class=row["errorClass"],
        metadata=_loads(row["metadata"], {}),
        created_at=row["createdAt"],
        updated_at=row["updatedAt"],
        started_at=row["startedAt"],
        completed_at=row["completedAt"],
        deadline=row["deadline"],
    )


class TaskStore:
    """Plans + tasks + edges + criteria + events + executions + checkpoints."""

    #: Every allowed update key is also the real column name; these sets pick the
    #: value encoding. A plain "absent" None is skipped; a NULLABLE column may be
    #: cleared on purpose.
    _JSON_COLUMNS = frozenset({"metadata", "blockedBy"})
    _BOOL_COLUMNS = frozenset({"required"})
    _NULLABLE = frozenset({
        "planId", "parentTaskId", "assignedAgentId", "assignedRunId", "delegatedBy",
        "delegationId", "availableAt", "claimedBy", "claimToken", "claimedAt",
        "leaseExpiresAt", "waitingReason", "blockedReason", "outputReference",
        "error", "errorClass", "startedAt", "completedAt", "deadline", "rootTaskId",
    })

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    # ── Schema ───────────────────────────────────────────────────────────────
    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessPlan (
              id          TEXT PRIMARY KEY,
              name        TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              objective   TEXT NOT NULL DEFAULT '',
              rootTaskId  TEXT,
              status      TEXT NOT NULL,
              priority    TEXT NOT NULL DEFAULT 'NORMAL',
              agentId     TEXT NOT NULL DEFAULT 'eclipse-agent',
              metadata    TEXT NOT NULL DEFAULT '{}',
              createdAt   TEXT NOT NULL,
              updatedAt   TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_plan_status ON HarnessPlan(status)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessTask (
              id             TEXT PRIMARY KEY,
              planId         TEXT,
              parentTaskId   TEXT,
              title          TEXT NOT NULL,
              description    TEXT NOT NULL DEFAULT '',
              objective      TEXT NOT NULL DEFAULT '',
              status         TEXT NOT NULL,
              priority       TEXT NOT NULL DEFAULT 'NORMAL',
              progress       INTEGER NOT NULL DEFAULT 0,
              assignedAgentId TEXT,
              assignedRunId  TEXT,
              delegatedBy    TEXT,
              delegationId   TEXT,
              retryCount     INTEGER NOT NULL DEFAULT 0,
              maxRetries     INTEGER NOT NULL DEFAULT 2,
              backoffMs      INTEGER NOT NULL DEFAULT 1000,
              availableAt    TEXT,
              claimedBy      TEXT,
              claimToken     TEXT,
              claimedAt      TEXT,
              leaseExpiresAt TEXT,
              required       INTEGER NOT NULL DEFAULT 1,
              failurePolicy  TEXT NOT NULL DEFAULT 'FAIL_FAST',
              weight         REAL NOT NULL DEFAULT 1.0,
              waitingReason  TEXT,
              blockedReason  TEXT,
              blockedBy      TEXT NOT NULL DEFAULT '[]',
              outputReference TEXT,
              error          TEXT,
              errorClass     TEXT,
              metadata       TEXT NOT NULL DEFAULT '{}',
              createdAt      TEXT NOT NULL,
              updatedAt      TEXT NOT NULL,
              startedAt      TEXT,
              completedAt    TEXT,
              deadline       TEXT,
              FOREIGN KEY (planId) REFERENCES HarnessPlan(id) ON DELETE CASCADE,
              FOREIGN KEY (parentTaskId) REFERENCES HarnessTask(id) ON DELETE CASCADE
            )
            """
        )
        for idx, cols in (
            ("idx_task_plan", "planId"),
            ("idx_task_parent", "parentTaskId"),
            ("idx_task_status", "status"),
            ("idx_task_agent", "assignedAgentId"),
            ("idx_task_claim", "claimToken"),
            ("idx_task_lease", "leaseExpiresAt"),
            ("idx_task_created", "createdAt"),
        ):
            self._db.execute(f"CREATE INDEX IF NOT EXISTS {idx} ON HarnessTask({cols})")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessTaskDependency (
              id               TEXT PRIMARY KEY,
              taskId           TEXT NOT NULL,
              dependsOnTaskId  TEXT NOT NULL,
              kind             TEXT NOT NULL DEFAULT 'REQUIRES',
              createdAt        TEXT NOT NULL,
              UNIQUE (taskId, dependsOnTaskId),
              FOREIGN KEY (taskId) REFERENCES HarnessTask(id) ON DELETE CASCADE,
              FOREIGN KEY (dependsOnTaskId) REFERENCES HarnessTask(id) ON DELETE CASCADE
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_taskdep_dependent ON HarnessTaskDependency(dependsOnTaskId)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessTaskCriterion (
              id        TEXT PRIMARY KEY,
              taskId    TEXT NOT NULL,
              text      TEXT NOT NULL,
              state     TEXT NOT NULL DEFAULT 'PENDING',
              evidence  TEXT,
              required  INTEGER NOT NULL DEFAULT 1,
              ordinal   INTEGER NOT NULL DEFAULT 0,
              createdAt TEXT NOT NULL,
              updatedAt TEXT NOT NULL,
              FOREIGN KEY (taskId) REFERENCES HarnessTask(id) ON DELETE CASCADE
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_taskcrit_task ON HarnessTaskCriterion(taskId)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessTaskEvent (
              id        TEXT PRIMARY KEY,
              planId    TEXT,
              taskId    TEXT,
              type      TEXT NOT NULL,
              seq       INTEGER NOT NULL,
              data      TEXT NOT NULL DEFAULT '{}',
              createdAt TEXT NOT NULL,
              FOREIGN KEY (taskId) REFERENCES HarnessTask(id) ON DELETE CASCADE,
              FOREIGN KEY (planId) REFERENCES HarnessPlan(id) ON DELETE CASCADE
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_taskevent_task ON HarnessTaskEvent(taskId, seq)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_taskevent_plan ON HarnessTaskEvent(planId, seq)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessTaskExecution (
              id          TEXT PRIMARY KEY,
              taskId      TEXT NOT NULL,
              attempt     INTEGER NOT NULL,
              agentId     TEXT,
              runId       TEXT,
              status      TEXT NOT NULL,
              error       TEXT,
              errorClass  TEXT,
              metrics     TEXT NOT NULL DEFAULT '{}',
              startedAt   TEXT NOT NULL,
              completedAt TEXT,
              FOREIGN KEY (taskId) REFERENCES HarnessTask(id) ON DELETE CASCADE
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_taskexec_task ON HarnessTaskExecution(taskId, attempt)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessTaskCheckpoint (
              id          TEXT PRIMARY KEY,
              taskId      TEXT NOT NULL,
              executionId TEXT,
              seq         INTEGER NOT NULL,
              label       TEXT NOT NULL DEFAULT 'checkpoint',
              payload     TEXT NOT NULL DEFAULT '{}',
              createdAt   TEXT NOT NULL,
              FOREIGN KEY (taskId) REFERENCES HarnessTask(id) ON DELETE CASCADE
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_taskckpt_task ON HarnessTaskCheckpoint(taskId, seq)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessTaskArtifact (
              id          TEXT PRIMARY KEY,
              taskId      TEXT NOT NULL,
              executionId TEXT,
              kind        TEXT NOT NULL DEFAULT 'file',
              uri         TEXT NOT NULL,
              digest      TEXT,
              sizeBytes   INTEGER,
              label       TEXT,
              metadata    TEXT NOT NULL DEFAULT '{}',
              createdAt   TEXT NOT NULL,
              FOREIGN KEY (taskId) REFERENCES HarnessTask(id) ON DELETE CASCADE
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_taskartifact_task ON HarnessTaskArtifact(taskId)"
        )
        self._db.commit()

    # ── Plans ────────────────────────────────────────────────────────────────
    def save_plan(self, plan: Plan) -> Plan:
        self._db.execute(
            """INSERT OR REPLACE INTO HarnessPlan
               (id, name, description, objective, rootTaskId, status, priority, agentId,
                metadata, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                plan.id, plan.name, plan.description, plan.objective, plan.root_task_id,
                plan.status.value, plan.priority.value, plan.agent_id,
                _json(plan.metadata), plan.created_at, plan.updated_at,
            ),
        )
        self._db.commit()
        return plan

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        row = self._db.execute("SELECT * FROM HarnessPlan WHERE id=?", (plan_id,)).fetchone()
        return _plan_row(row) if row else None

    def list_plans(self, limit: int = 100, *, status: Optional[str] = None) -> list[Plan]:
        limit = max(1, min(int(limit), 500))
        if status:
            rows = self._db.execute(
                "SELECT * FROM HarnessPlan WHERE status=? ORDER BY createdAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM HarnessPlan ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_plan_row(r) for r in rows]

    def update_plan_fields(self, plan_id: str, fields: dict[str, Any]) -> Optional[Plan]:
        allowed = {
            "name", "description", "objective", "rootTaskId", "status", "priority",
            "agentId", "metadata",
        }
        sets, params = self._update_clause(fields, allowed)
        if not sets:
            return self.get_plan(plan_id)
        sets.append("updatedAt = ?")
        params.append(now_iso())
        params.append(plan_id)
        self._db.execute(f"UPDATE HarnessPlan SET {', '.join(sets)} WHERE id=?", params)
        self._db.commit()
        return self.get_plan(plan_id)

    # ── Tasks ────────────────────────────────────────────────────────────────
    def insert_task(self, task: Task) -> Task:
        self._db.execute(
            """INSERT INTO HarnessTask
               (id, planId, parentTaskId, title, description, objective, status, priority,
                progress, assignedAgentId, assignedRunId, delegatedBy, delegationId,
                retryCount, maxRetries, backoffMs, availableAt, claimedBy, claimToken,
                claimedAt, leaseExpiresAt, required, failurePolicy, weight, waitingReason,
                blockedReason, blockedBy, outputReference, error, errorClass, metadata,
                createdAt, updatedAt, startedAt, completedAt, deadline)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id, task.plan_id, task.parent_task_id, task.title, task.description,
                task.objective, task.status.value, task.priority.value, int(task.progress),
                task.assigned_agent_id, task.assigned_run_id, task.delegated_by,
                task.delegation_id, int(task.retry_count), int(task.max_retries),
                int(task.backoff_ms), task.available_at, task.claimed_by, task.claim_token,
                task.claimed_at, task.lease_expires_at, 1 if task.required else 0,
                task.failure_policy.value, float(task.weight),
                task.waiting_reason.value if task.waiting_reason else None,
                task.blocked_reason.value if task.blocked_reason else None,
                _json(task.blocked_by), task.output_reference, task.error, task.error_class,
                _json(task.metadata), task.created_at, task.updated_at, task.started_at,
                task.completed_at, task.deadline,
            ),
        )
        self._db.commit()
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        row = self._db.execute("SELECT * FROM HarnessTask WHERE id=?", (task_id,)).fetchone()
        return _task_row(row) if row else None

    def list_tasks(
        self,
        *,
        plan_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 500,
    ) -> list[Task]:
        limit = max(1, min(int(limit), 2000))
        clauses: list[str] = []
        params: list[Any] = []
        if plan_id is not None:
            clauses.append("planId = ?")
            params.append(plan_id)
        if parent_task_id is not None:
            clauses.append("parentTaskId = ?")
            params.append(parent_task_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._db.execute(
            f"SELECT * FROM HarnessTask{where} ORDER BY createdAt ASC LIMIT ?", tuple(params)
        ).fetchall()
        return [_task_row(r) for r in rows]

    def list_children(self, parent_task_id: str) -> list[Task]:
        return self.list_tasks(parent_task_id=parent_task_id, limit=2000)

    def count_children(self, parent_task_id: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS n FROM HarnessTask WHERE parentTaskId=?", (parent_task_id,)
        ).fetchone()
        return int(row["n"]) if row else 0

    def update_task_fields(
        self, task_id: str, fields: dict[str, Any], *, expected_claim_token: Optional[str] = None
    ) -> Optional[Task]:
        """Update whitelisted columns. When a claim token is expected, the update
        only lands for the worker that still holds the claim (concurrency safe)."""
        allowed = {
            "planId", "parentTaskId", "title", "description", "objective", "status",
            "priority", "progress", "assignedAgentId", "assignedRunId", "delegatedBy",
            "delegationId", "retryCount", "maxRetries", "backoffMs", "availableAt",
            "claimedBy", "claimToken", "claimedAt", "leaseExpiresAt", "required",
            "failurePolicy", "weight", "waitingReason", "blockedReason", "blockedBy",
            "outputReference", "error", "errorClass", "metadata", "startedAt",
            "completedAt", "deadline",
        }
        sets, params = self._update_clause(fields, allowed)
        if not sets:
            return self.get_task(task_id)
        sets.append("updatedAt = ?")
        params.append(now_iso())
        params.append(task_id)
        clause = "UPDATE HarnessTask SET " + ", ".join(sets) + " WHERE id=?"
        if expected_claim_token is not None:
            clause += " AND claimToken=?"
            params.append(expected_claim_token)
        cur = self._db.execute(clause, params)
        self._db.commit()
        if expected_claim_token is not None and cur.rowcount == 0:
            return None
        return self.get_task(task_id)

    # ── Atomic claiming / leases ─────────────────────────────────────────────
    def claim_task(
        self, task_id: str, *, worker_id: str, claim_token: str, lease_seconds: int,
        now: Optional[str] = None,
    ) -> bool:
        """Atomically move a TODO task to IN_PROGRESS under a lease.

        A single conditional UPDATE means two workers racing for the same task
        cannot both succeed: SQLite serializes writes and `rowcount` reports
        whether THIS worker got it. A task under an unexpired lease is not claimable
        because `claimToken` is not NULL.
        """
        moment = now or now_iso()
        lease_expiry = _plus_seconds(moment, lease_seconds)
        cur = self._db.execute(
            """UPDATE HarnessTask
               SET status='IN_PROGRESS', claimedBy=?, claimToken=?, claimedAt=?,
                   leaseExpiresAt=?, startedAt=COALESCE(startedAt, ?), updatedAt=?,
                   error=NULL, errorClass=NULL, waitingReason=NULL
               WHERE id=? AND status='TODO' AND claimToken IS NULL
                 AND (availableAt IS NULL OR availableAt <= ?)""",
            (worker_id, claim_token, moment, lease_expiry, moment, moment, task_id, moment),
        )
        self._db.commit()
        return cur.rowcount == 1

    def heartbeat_task(
        self, task_id: str, *, claim_token: str, lease_seconds: int, now: Optional[str] = None
    ) -> bool:
        moment = now or now_iso()
        lease_expiry = _plus_seconds(moment, lease_seconds)
        cur = self._db.execute(
            "UPDATE HarnessTask SET leaseExpiresAt=?, updatedAt=? WHERE id=? AND claimToken=?",
            (lease_expiry, moment, task_id, claim_token),
        )
        self._db.commit()
        return cur.rowcount == 1

    def release_claim(self, task_id: str, *, claim_token: Optional[str] = None) -> None:
        clause = (
            "UPDATE HarnessTask SET claimedBy=NULL, claimToken=NULL, claimedAt=NULL, "
            "leaseExpiresAt=NULL, updatedAt=? WHERE id=?"
        )
        params: list[Any] = [now_iso(), task_id]
        if claim_token is not None:
            clause += " AND claimToken=?"
            params.append(claim_token)
        self._db.execute(clause, params)
        self._db.commit()

    def expired_leases(self, now: Optional[str] = None, limit: int = 100) -> list[Task]:
        moment = now or now_iso()
        rows = self._db.execute(
            """SELECT * FROM HarnessTask
               WHERE status='IN_PROGRESS' AND leaseExpiresAt IS NOT NULL
                 AND leaseExpiresAt < ? ORDER BY leaseExpiresAt ASC LIMIT ?""",
            (moment, max(1, min(int(limit), 500))),
        ).fetchall()
        return [_task_row(r) for r in rows]

    # ── Dependencies ─────────────────────────────────────────────────────────
    def add_dependency(
        self, *, task_id: str, depends_on_task_id: str, kind: DependencyKind
    ) -> TaskDependency:
        dep = TaskDependency(
            id=new_id("dep"), task_id=task_id, depends_on_task_id=depends_on_task_id,
            kind=kind, created_at=now_iso(),
        )
        self._db.execute(
            """INSERT OR IGNORE INTO HarnessTaskDependency
               (id, taskId, dependsOnTaskId, kind, createdAt) VALUES (?, ?, ?, ?, ?)""",
            (dep.id, dep.task_id, dep.depends_on_task_id, dep.kind.value, dep.created_at),
        )
        self._db.commit()
        return dep

    def remove_dependency(self, *, task_id: str, depends_on_task_id: str) -> bool:
        cur = self._db.execute(
            "DELETE FROM HarnessTaskDependency WHERE taskId=? AND dependsOnTaskId=?",
            (task_id, depends_on_task_id),
        )
        self._db.commit()
        return cur.rowcount > 0

    def list_dependencies(self, task_id: str) -> list[TaskDependency]:
        rows = self._db.execute(
            "SELECT * FROM HarnessTaskDependency WHERE taskId=? ORDER BY createdAt ASC",
            (task_id,),
        ).fetchall()
        return [_dep_row(r) for r in rows]

    def list_dependents(self, task_id: str) -> list[TaskDependency]:
        rows = self._db.execute(
            "SELECT * FROM HarnessTaskDependency WHERE dependsOnTaskId=? ORDER BY createdAt ASC",
            (task_id,),
        ).fetchall()
        return [_dep_row(r) for r in rows]

    def list_plan_edges(self, plan_id: str) -> list[TaskDependency]:
        rows = self._db.execute(
            """SELECT d.* FROM HarnessTaskDependency d
               JOIN HarnessTask t ON t.id = d.taskId
               WHERE t.planId=? ORDER BY d.createdAt ASC""",
            (plan_id,),
        ).fetchall()
        return [_dep_row(r) for r in rows]

    # ── Acceptance criteria ──────────────────────────────────────────────────
    def add_criterion(
        self, *, task_id: str, text: str, required: bool, ordinal: int
    ) -> TaskAcceptanceCriterion:
        moment = now_iso()
        criterion = TaskAcceptanceCriterion(
            id=new_id("crit"), task_id=task_id, text=text, state=CriterionState.PENDING,
            required=required, ordinal=ordinal, created_at=moment, updated_at=moment,
        )
        self._db.execute(
            """INSERT INTO HarnessTaskCriterion
               (id, taskId, text, state, evidence, required, ordinal, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                criterion.id, criterion.task_id, criterion.text, criterion.state.value,
                criterion.evidence, 1 if criterion.required else 0, criterion.ordinal,
                criterion.created_at, criterion.updated_at,
            ),
        )
        self._db.commit()
        return criterion

    def update_criterion_state(
        self, criterion_id: str, *, state: CriterionState, evidence: Optional[str] = None
    ) -> Optional[TaskAcceptanceCriterion]:
        self._db.execute(
            "UPDATE HarnessTaskCriterion SET state=?, evidence=?, updatedAt=? WHERE id=?",
            (state.value, evidence, now_iso(), criterion_id),
        )
        self._db.commit()
        row = self._db.execute(
            "SELECT * FROM HarnessTaskCriterion WHERE id=?", (criterion_id,)
        ).fetchone()
        return _criterion_row(row) if row else None

    def list_criteria(self, task_id: str) -> list[TaskAcceptanceCriterion]:
        rows = self._db.execute(
            "SELECT * FROM HarnessTaskCriterion WHERE taskId=? ORDER BY ordinal ASC",
            (task_id,),
        ).fetchall()
        return [_criterion_row(r) for r in rows]

    # ── Events (immutable history) ───────────────────────────────────────────
    def append_event(
        self, *, event_type: str, plan_id: Optional[str] = None,
        task_id: Optional[str] = None, data: Optional[dict[str, Any]] = None,
    ) -> TaskEvent:
        anchor_col = "taskId" if task_id else "planId"
        anchor_val = task_id if task_id else plan_id
        seq = 0
        if anchor_val is not None:
            row = self._db.execute(
                f"SELECT COALESCE(MAX(seq), -1) AS m FROM HarnessTaskEvent WHERE {anchor_col}=?",
                (anchor_val,),
            ).fetchone()
            seq = int(row["m"]) + 1
        event = TaskEvent(
            id=new_id("tevt"), plan_id=plan_id, task_id=task_id, type=event_type, seq=seq,
            data=data or {}, created_at=now_iso(),
        )
        self._db.execute(
            """INSERT INTO HarnessTaskEvent (id, planId, taskId, type, seq, data, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event.id, event.plan_id, event.task_id, event.type, event.seq,
             _json(event.data), event.created_at),
        )
        self._db.commit()
        return event

    def list_task_events(self, task_id: str, limit: int = 500) -> list[TaskEvent]:
        rows = self._db.execute(
            "SELECT * FROM HarnessTaskEvent WHERE taskId=? ORDER BY seq ASC LIMIT ?",
            (task_id, max(1, min(int(limit), 2000))),
        ).fetchall()
        return [_event_row(r) for r in rows]

    def list_plan_events(self, plan_id: str, limit: int = 1000) -> list[TaskEvent]:
        rows = self._db.execute(
            "SELECT * FROM HarnessTaskEvent WHERE planId=? ORDER BY createdAt ASC, seq ASC LIMIT ?",
            (plan_id, max(1, min(int(limit), 5000))),
        ).fetchall()
        return [_event_row(r) for r in rows]

    # ── Executions ───────────────────────────────────────────────────────────
    def next_attempt(self, task_id: str) -> int:
        row = self._db.execute(
            "SELECT COALESCE(MAX(attempt), 0) AS m FROM HarnessTaskExecution WHERE taskId=?",
            (task_id,),
        ).fetchone()
        return int(row["m"]) + 1

    def start_execution(
        self, *, task_id: str, agent_id: Optional[str], run_id: Optional[str]
    ) -> TaskExecution:
        execution = TaskExecution(
            id=new_id("exec"), task_id=task_id, attempt=self.next_attempt(task_id),
            agent_id=agent_id, run_id=run_id, status=ExecutionStatus.RUNNING,
            started_at=now_iso(),
        )
        self._db.execute(
            """INSERT INTO HarnessTaskExecution
               (id, taskId, attempt, agentId, runId, status, error, errorClass, metrics,
                startedAt, completedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                execution.id, execution.task_id, execution.attempt, execution.agent_id,
                execution.run_id, execution.status.value, execution.error,
                execution.error_class, _json(execution.metrics), execution.started_at,
                execution.completed_at,
            ),
        )
        self._db.commit()
        return execution

    def finish_execution(
        self, execution_id: str, *, status: ExecutionStatus, error: Optional[str] = None,
        error_class: Optional[str] = None, metrics: Optional[dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Optional[TaskExecution]:
        self._db.execute(
            """UPDATE HarnessTaskExecution
               SET status=?, error=?, errorClass=?, metrics=?, completedAt=?,
                   runId=COALESCE(?, runId)
               WHERE id=?""",
            (status.value, error, error_class, _json(metrics or {}), now_iso(),
             run_id, execution_id),
        )
        self._db.commit()
        row = self._db.execute(
            "SELECT * FROM HarnessTaskExecution WHERE id=?", (execution_id,)
        ).fetchone()
        return _execution_row(row) if row else None

    def list_executions(self, task_id: str, limit: int = 100) -> list[TaskExecution]:
        rows = self._db.execute(
            "SELECT * FROM HarnessTaskExecution WHERE taskId=? ORDER BY attempt ASC LIMIT ?",
            (task_id, max(1, min(int(limit), 500))),
        ).fetchall()
        return [_execution_row(r) for r in rows]

    # ── Checkpoints ──────────────────────────────────────────────────────────
    def save_checkpoint(
        self, *, task_id: str, label: str, payload: Optional[dict[str, Any]],
        execution_id: Optional[str] = None,
    ) -> TaskCheckpoint:
        row = self._db.execute(
            "SELECT COALESCE(MAX(seq), -1) AS m FROM HarnessTaskCheckpoint WHERE taskId=?",
            (task_id,),
        ).fetchone()
        checkpoint = TaskCheckpoint(
            id=new_id("tckpt"), task_id=task_id, execution_id=execution_id,
            seq=int(row["m"]) + 1, label=label, payload=payload or {}, created_at=now_iso(),
        )
        self._db.execute(
            """INSERT INTO HarnessTaskCheckpoint
               (id, taskId, executionId, seq, label, payload, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (checkpoint.id, checkpoint.task_id, checkpoint.execution_id, checkpoint.seq,
             checkpoint.label, _json(checkpoint.payload), checkpoint.created_at),
        )
        self._db.commit()
        return checkpoint

    def list_checkpoints(self, task_id: str) -> list[TaskCheckpoint]:
        rows = self._db.execute(
            "SELECT * FROM HarnessTaskCheckpoint WHERE taskId=? ORDER BY seq ASC", (task_id,)
        ).fetchall()
        return [_checkpoint_row(r) for r in rows]

    def latest_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        row = self._db.execute(
            "SELECT * FROM HarnessTaskCheckpoint WHERE taskId=? ORDER BY seq DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return _checkpoint_row(row) if row else None

    def prune(self, *, retention_days: int = 90, now: Optional[str] = None) -> dict[str, int]:
        """Delete aged execution/trace rows, keeping the durable plans and tasks.

        Retention applies to the high-volume append-only trails (checkpoints,
        execution attempts, events) — never to the plans/tasks/criteria/artifacts,
        which are the durable record. Rows younger than the cutoff are untouched.
        """
        import datetime as _dt  # noqa: PLC0415

        if retention_days <= 0:
            return {}
        moment = now or now_iso()
        try:
            base = _dt.datetime.fromisoformat(moment.replace("Z", "+00:00"))
        except ValueError:
            base = _dt.datetime.now(_dt.timezone.utc)
        cutoff = (base - _dt.timedelta(days=int(retention_days))).isoformat()
        counts: dict[str, int] = {}
        for table, column in (
            ("HarnessTaskCheckpoint", "createdAt"),
            ("HarnessTaskExecution", "startedAt"),
            ("HarnessTaskEvent", "createdAt"),
        ):
            cur = self._db.execute(f"DELETE FROM {table} WHERE {column} < ?", (cutoff,))
            counts[table] = cur.rowcount
        self._db.commit()
        return counts

    def count_rows(self) -> dict[str, int]:
        """A small size snapshot for operators/tests."""
        out: dict[str, int] = {}
        for table in ("HarnessPlan", "HarnessTask", "HarnessTaskEvent",
                      "HarnessTaskExecution", "HarnessTaskCheckpoint"):
            row = self._db.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
            out[table] = int(row["c"]) if row else 0
        return out

    # ── Artifacts ────────────────────────────────────────────────────────────
    def add_artifact(
        self, *, task_id: str, uri: str, kind: str = "file", digest: Optional[str] = None,
        size_bytes: Optional[int] = None, label: Optional[str] = None,
        execution_id: Optional[str] = None, metadata: Optional[dict[str, Any]] = None,
    ) -> TaskArtifact:
        artifact = TaskArtifact(
            id=new_id("tart"), task_id=task_id, execution_id=execution_id, kind=kind,
            uri=uri, digest=digest, size_bytes=size_bytes, label=label,
            metadata=metadata or {}, created_at=now_iso(),
        )
        self._db.execute(
            """INSERT INTO HarnessTaskArtifact
               (id, taskId, executionId, kind, uri, digest, sizeBytes, label, metadata, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact.id, artifact.task_id, artifact.execution_id, artifact.kind,
                artifact.uri, artifact.digest, artifact.size_bytes, artifact.label,
                _json(artifact.metadata), artifact.created_at,
            ),
        )
        self._db.commit()
        return artifact

    def list_artifacts(self, task_id: str) -> list[TaskArtifact]:
        rows = self._db.execute(
            "SELECT * FROM HarnessTaskArtifact WHERE taskId=? ORDER BY createdAt ASC", (task_id,)
        ).fetchall()
        return [_artifact_row(r) for r in rows]

    # ── Delete ───────────────────────────────────────────────────────────────
    def delete_task(self, task_id: str) -> bool:
        cur = self._db.execute("DELETE FROM HarnessTask WHERE id=?", (task_id,))
        self._db.commit()
        return cur.rowcount > 0

    # ── Internal ─────────────────────────────────────────────────────────────
    def _update_clause(
        self, fields: dict[str, Any], allowed: set[str]
    ) -> tuple[list[str], list[Any]]:
        sets: list[str] = []
        params: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if value is None and key not in self._NULLABLE:
                continue
            if key in self._JSON_COLUMNS:
                sets.append(f"{key} = ?")
                params.append(_json(value))
            elif key in self._BOOL_COLUMNS:
                sets.append(f"{key} = ?")
                params.append(1 if value else 0)
            else:
                raw = value.value if isinstance(value, Enum) else value
                sets.append(f"{key} = ?")
                params.append(raw)
        return sets, params


# ── Row helpers ───────────────────────────────────────────────────────────────


def _dep_row(row: Any) -> TaskDependency:
    return TaskDependency(
        id=row["id"], task_id=row["taskId"], depends_on_task_id=row["dependsOnTaskId"],
        kind=DependencyKind(row["kind"]), created_at=row["createdAt"],
    )


def _criterion_row(row: Any) -> TaskAcceptanceCriterion:
    return TaskAcceptanceCriterion(
        id=row["id"], task_id=row["taskId"], text=row["text"],
        state=CriterionState(row["state"]), evidence=row["evidence"],
        required=bool(row["required"]), ordinal=int(row["ordinal"]),
        created_at=row["createdAt"], updated_at=row["updatedAt"],
    )


def _event_row(row: Any) -> TaskEvent:
    return TaskEvent(
        id=row["id"], plan_id=row["planId"], task_id=row["taskId"], type=row["type"],
        seq=int(row["seq"]), data=_loads(row["data"], {}), created_at=row["createdAt"],
    )


def _execution_row(row: Any) -> TaskExecution:
    return TaskExecution(
        id=row["id"], task_id=row["taskId"], attempt=int(row["attempt"]),
        agent_id=row["agentId"], run_id=row["runId"],
        status=ExecutionStatus(row["status"]), error=row["error"],
        error_class=row["errorClass"], metrics=_loads(row["metrics"], {}),
        started_at=row["startedAt"], completed_at=row["completedAt"],
    )


def _checkpoint_row(row: Any) -> TaskCheckpoint:
    return TaskCheckpoint(
        id=row["id"], task_id=row["taskId"], execution_id=row["executionId"],
        seq=int(row["seq"]), label=row["label"], payload=_loads(row["payload"], {}),
        created_at=row["createdAt"],
    )


def _artifact_row(row: Any) -> TaskArtifact:
    return TaskArtifact(
        id=row["id"], task_id=row["taskId"], execution_id=row["executionId"],
        kind=row["kind"], uri=row["uri"], digest=row["digest"],
        size_bytes=row["sizeBytes"], label=row["label"],
        metadata=_loads(row["metadata"], {}), created_at=row["createdAt"],
    )


def _plus_seconds(moment_iso: str, seconds: int) -> str:
    import datetime as _dt

    try:
        base = _dt.datetime.fromisoformat(moment_iso.replace("Z", "+00:00"))
    except ValueError:
        base = _dt.datetime.now(_dt.timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=_dt.timezone.utc)
    return (base + _dt.timedelta(seconds=int(seconds))).isoformat()


__all__ = ["TaskStore", "new_id"]

"""Durable records for W7 asynchronous delegation.

The Execution Fabric owns the job (lease, retry, cancel). This store owns the
*delegation* contract on top of it: which parent asked for which child, the
output schema, the terminal result, whether the parent consumed it, and the
steer mailbox. It is deliberately small and additive; it never schedules.

Tables live on the ONE `agent-memory.db` and are created idempotently, exactly
like `run_lineage._ensure_schema`. A migration id is registered so diagnostics
can answer "is this database current?".
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from .delegation import DelegationChild
from .migrations import Migration, MigrationRunner
from .persistence import now_iso

TERMINAL = frozenset({"completed", "failed", "timed_out", "cancelled", "refused"})
_SCHEMA_READY: set[str] = set()

DELEGATION_MIGRATIONS = (
    Migration(
        id="2026-11-12-w7-delegation",
        description="W7 durable delegation + steer mailbox",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS HarnessDelegation (
              id              TEXT NOT NULL,
              parentRunId     TEXT NOT NULL,
              parentAgentId   TEXT,
              childIndex      INTEGER NOT NULL,
              fabricJobId     TEXT,
              childRunId      TEXT,
              status          TEXT NOT NULL,
              attempt         INTEGER NOT NULL DEFAULT 0,
              strategy        TEXT,
              aggregate       TEXT,
              title           TEXT,
              tokenBudget     INTEGER NOT NULL DEFAULT 0,
              childJson       TEXT NOT NULL,
              schemaJson      TEXT,
              schemaValid     INTEGER,
              schemaErrors    TEXT,
              rawSummary      TEXT,
              summary         TEXT,
              resultJson      TEXT,
              tokens          INTEGER NOT NULL DEFAULT 0,
              reason          TEXT,
              consumedAt      TEXT,
              createdAt       TEXT NOT NULL,
              updatedAt       TEXT NOT NULL,
              PRIMARY KEY (id, childIndex)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_delegation_parent "
            "ON HarnessDelegation(parentRunId, status)",
            "CREATE INDEX IF NOT EXISTS idx_delegation_job "
            "ON HarnessDelegation(fabricJobId)",
            """
            CREATE TABLE IF NOT EXISTS HarnessDelegationSteer (
              delegationId TEXT NOT NULL,
              seq          INTEGER NOT NULL,
              message      TEXT NOT NULL,
              consumedAt   TEXT,
              createdAt    TEXT NOT NULL,
              PRIMARY KEY (delegationId, seq)
            )
            """,
        ),
    ),
)


def new_delegation_id() -> str:
    return "dlg_" + uuid.uuid4().hex[:16]


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str)


def _loads(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class DelegationStore:
    """Read/write access to the two W7 tables. Never raises on a read."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db  # noqa: SLF001 - the one shared connection

    def _ensure_schema(self) -> None:
        key = str(getattr(self._store, "path", "") or id(self._store))
        if key in _SCHEMA_READY:
            return
        db = self._db
        for statement in DELEGATION_MIGRATIONS[0].statements:
            db.execute(statement)
        # Additive columns for an older table created by a previous build.
        cols = {row["name"] for row in db.execute("PRAGMA table_info(HarnessDelegation)").fetchall()}
        for name, ddl in (
            ("consumedAt", "TEXT"), ("schemaValid", "INTEGER"),
            ("schemaErrors", "TEXT"), ("rawSummary", "TEXT"), ("summary", "TEXT"),
        ):
            if name not in cols:
                db.execute(f"ALTER TABLE HarnessDelegation ADD COLUMN {name} {ddl}")
        db.commit()
        try:
            MigrationRunner(db, "agent-memory").apply(DELEGATION_MIGRATIONS)
        except Exception:  # noqa: BLE001 - the ledger is diagnostics, not the schema
            pass
        _SCHEMA_READY.add(key)

    # ── creation ──────────────────────────────────────────────────────────────

    def create_batch(
        self,
        *,
        delegation_id: str,
        parent_run_id: str,
        parent_agent_id: Optional[str],
        children: list[DelegationChild],
        strategy: str,
        aggregate: str,
        title: Optional[str],
        token_budget: int,
    ) -> str:
        now = now_iso()
        for index, child in enumerate(children):
            self._db.execute(
                """
                INSERT INTO HarnessDelegation
                  (id, parentRunId, parentAgentId, childIndex, status, strategy,
                   aggregate, title, tokenBudget, childJson, createdAt, updatedAt)
                VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delegation_id, parent_run_id, parent_agent_id, index, strategy,
                    aggregate, title, int(token_budget),
                    _dumps(child.model_dump(by_alias=True)), now, now,
                ),
            )
        self._db.commit()
        return delegation_id

    def attach_job(
        self, delegation_id: str, child_index: int, *, job_id: str,
        child_run_id: Optional[str] = None,
    ) -> None:
        self._db.execute(
            "UPDATE HarnessDelegation SET fabricJobId=?, childRunId=COALESCE(?, childRunId), "
            "updatedAt=? WHERE id=? AND childIndex=?",
            (job_id, child_run_id, now_iso(), delegation_id, child_index),
        )
        self._db.commit()

    def mark_running(self, delegation_id: str, child_index: int, *, child_run_id: str) -> None:
        self._db.execute(
            "UPDATE HarnessDelegation SET status='running', childRunId=?, updatedAt=? "
            "WHERE id=? AND childIndex=? AND status IN ('queued','running')",
            (child_run_id, now_iso(), delegation_id, child_index),
        )
        self._db.commit()

    # ── completion ────────────────────────────────────────────────────────────

    def complete(
        self,
        delegation_id: str,
        child_index: int,
        *,
        status: str,
        child_run_id: Optional[str] = None,
        raw_summary: str = "",
        summary: Optional[str] = None,
        schema_valid: Optional[bool] = None,
        schema_errors: Optional[list[str]] = None,
        tokens: int = 0,
        reason: Optional[str] = None,
        result: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Write a terminal state once. Returns False when already terminal.

        The conditional UPDATE is the idempotency boundary: a Fabric retry or a
        cancel race cannot overwrite a terminal row.
        """
        now = now_iso()
        cursor = self._db.execute(
            """
            UPDATE HarnessDelegation SET
              status=?, childRunId=COALESCE(?, childRunId), rawSummary=?,
              summary=COALESCE(?, rawSummary), schemaValid=?, schemaErrors=?,
              tokens=?, reason=?, resultJson=?, updatedAt=?
            WHERE id=? AND childIndex=? AND status NOT IN
              ('completed','failed','timed_out','cancelled','refused')
            """,
            (
                status, child_run_id, raw_summary[:16_000], summary,
                None if schema_valid is None else (1 if schema_valid else 0),
                _dumps(schema_errors or []), max(0, int(tokens)), reason,
                _dumps(result or {}), now, delegation_id, child_index,
            ),
        )
        self._db.commit()
        return cursor.rowcount > 0

    def fail_open_rows(self, reason: str = "delegation worker did not finish") -> list[dict[str, Any]]:
        """A boot diagnostic: rows left running with no terminal write."""
        rows = self._rows("SELECT * FROM HarnessDelegation WHERE status='running'")
        return rows

    # ── reads ────────────────────────────────────────────────────────────────

    def _rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            rows = self._db.execute(sql, params).fetchall()
        except Exception:  # noqa: BLE001 - a read failure is empty, never fatal
            return []
        return [self._row(row) for row in rows]

    def get(self, delegation_id: str) -> dict[str, Any]:
        rows = self._rows(
            "SELECT * FROM HarnessDelegation WHERE id=? ORDER BY childIndex ASC",
            (delegation_id,),
        )
        return self._batch(delegation_id, rows)

    def find_by_job(self, job_id: str) -> Optional[dict[str, Any]]:
        rows = self._rows(
            "SELECT * FROM HarnessDelegation WHERE fabricJobId=? ORDER BY childIndex ASC",
            (job_id,),
        )
        if not rows:
            return None
        return self._batch(str(rows[0].get("id")), rows)

    def list_for_parent(self, parent_run_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._rows(
            "SELECT * FROM HarnessDelegation WHERE parentRunId=? "
            "ORDER BY createdAt DESC, childIndex ASC LIMIT ?",
            (parent_run_id, max(1, min(int(limit), 500))),
        )
        return self._batches(rows)

    def inbox(self, parent_run_id: str) -> list[dict[str, Any]]:
        """Terminal children the parent has not consumed, oldest first."""
        rows = self._rows(
            "SELECT * FROM HarnessDelegation WHERE parentRunId=? "
            "AND consumedAt IS NULL AND status IN "
            "('completed','failed','timed_out','cancelled','refused') "
            "ORDER BY createdAt ASC, childIndex ASC",
            (parent_run_id,),
        )
        return rows

    def mark_consumed(self, delegation_id: str, child_indexes: list[int]) -> None:
        if not child_indexes:
            return
        now = now_iso()
        for index in child_indexes:
            self._db.execute(
                "UPDATE HarnessDelegation SET consumedAt=?, updatedAt=? "
                "WHERE id=? AND childIndex=? AND consumedAt IS NULL",
                (now, now, delegation_id, index),
            )
        self._db.commit()

    # ── steering ─────────────────────────────────────────────────────────────

    def append_steer(self, delegation_id: str, message: str, *, max_pending: int = 4) -> int:
        text = str(message or "").strip()
        if not text:
            raise ValueError("a steer message must not be empty")
        pending = self._db.execute(
            "SELECT COUNT(*) AS n FROM HarnessDelegationSteer "
            "WHERE delegationId=? AND consumedAt IS NULL",
            (delegation_id,),
        ).fetchone()
        if pending is not None and int(pending["n"]) >= max_pending:
            raise ValueError(f"at most {max_pending} pending steer message(s) per child")
        row = self._db.execute(
            "SELECT COALESCE(MAX(seq), 0) AS seq FROM HarnessDelegationSteer WHERE delegationId=?",
            (delegation_id,),
        ).fetchone()
        seq = int(row["seq"] if row is not None else 0) + 1
        self._db.execute(
            "INSERT INTO HarnessDelegationSteer (delegationId, seq, message, createdAt) "
            "VALUES (?, ?, ?, ?)",
            (delegation_id, seq, text[:4_000], now_iso()),
        )
        self._db.commit()
        return seq

    def peek_steers(self, delegation_id: str) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT seq, message, createdAt FROM HarnessDelegationSteer "
            "WHERE delegationId=? AND consumedAt IS NULL ORDER BY seq ASC",
            (delegation_id,),
        )

    def consume_steers(self, delegation_id: str, seqs: list[int]) -> None:
        if not seqs:
            return
        now = now_iso()
        for seq in seqs:
            self._db.execute(
                "UPDATE HarnessDelegationSteer SET consumedAt=? "
                "WHERE delegationId=? AND seq=? AND consumedAt IS NULL",
                (now, delegation_id, int(seq)),
            )
        self._db.commit()

    # ── shaping ──────────────────────────────────────────────────────────────

    def _row(self, row: Any) -> dict[str, Any]:
        data = dict(row) if not isinstance(row, dict) else dict(row)
        for key in ("childJson", "schemaJson", "schemaErrors", "resultJson"):
            if key in data:
                data[key] = _loads(data[key], {} if key == "childJson" else [])
        if data.get("schemaValid") is not None:
            data["schemaValid"] = bool(data["schemaValid"])
        return data

    def _batch(self, delegation_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"delegationId": delegation_id, "found": False, "children": []}
        first = rows[0]
        children = [
            {
                "childIndex": row.get("childIndex"),
                "status": row.get("status"),
                "fabricJobId": row.get("fabricJobId"),
                "childRunId": row.get("childRunId"),
                "goal": (row.get("childJson") or {}).get("goal", ""),
                "approach": (row.get("childJson") or {}).get("approach"),
                "agentId": (row.get("childJson") or {}).get("agentId"),
                "model": (row.get("childJson") or {}).get("model"),
                "summary": row.get("summary") or "",
                "rawSummary": row.get("rawSummary") or "",
                "schemaValid": row.get("schemaValid"),
                "schemaErrors": row.get("schemaErrors") or [],
                "tokens": row.get("tokens") or 0,
                "reason": row.get("reason"),
                "result": row.get("resultJson") or {},
                "consumedAt": row.get("consumedAt"),
            }
            for row in rows
        ]
        return {
            "delegationId": delegation_id,
            "found": True,
            "parentRunId": first.get("parentRunId"),
            "parentAgentId": first.get("parentAgentId"),
            "strategy": first.get("strategy"),
            "aggregate": first.get("aggregate"),
            "title": first.get("title"),
            "tokenBudget": first.get("tokenBudget") or 0,
            "children": children,
            "status": _batch_status([c["status"] for c in children]),
        }

    def _batches(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        for row in rows:
            did = str(row.get("id"))
            if did not in grouped:
                grouped[did] = []
                order.append(did)
            grouped[did].append(row)
        return [self._batch(did, grouped[did]) for did in order]


def _batch_status(statuses: list[str]) -> str:
    if not statuses:
        return "queued"
    if any(s not in TERMINAL and s != "running" for s in statuses):
        return "queued"
    if any(s == "running" for s in statuses):
        return "running"
    if all(s == "completed" for s in statuses):
        return "completed"
    if any(s == "failed" for s in statuses) or any(s == "timed_out" for s in statuses):
        return "failed"
    if all(s == "cancelled" for s in statuses):
        return "cancelled"
    if all(s == "refused" for s in statuses):
        return "refused"
    return "partial"


__all__ = [
    "DELEGATION_MIGRATIONS",
    "DelegationStore",
    "TERMINAL",
    "new_delegation_id",
]

"""Graph-run persistence on the ONE `agent-memory.db`.

Owns its own tables and never reads another subsystem's rows. Rows are written
twice per run: once when the run STARTS (status ``running``, so a crash leaves
an inspectable record) and once when it FINISHES (status + full result JSON).

Node runs and events are stored inside the run's result document for now; Phase
4 normalizes them into queryable tables alongside durable orchestration.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import new_id, now_iso
from .model import GraphRun

_SCHEMA = """
CREATE TABLE IF NOT EXISTS HarnessGraphRun (
  id              TEXT PRIMARY KEY,
  workflowId      TEXT NOT NULL,
  workflowVersion INTEGER,
  irVersion       INTEGER NOT NULL,
  mode            TEXT NOT NULL,
  testRun         INTEGER NOT NULL DEFAULT 1,
  status          TEXT NOT NULL,
  ownerId         TEXT NOT NULL DEFAULT 'local',
  startedAt       TEXT NOT NULL,
  finishedAt      TEXT,
  durationMs      INTEGER,
  error           TEXT,
  plan            TEXT,
  result          TEXT,
  createdAt       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_graph_run_workflow ON HarnessGraphRun(workflowId, startedAt);
CREATE INDEX IF NOT EXISTS idx_graph_run_status ON HarnessGraphRun(status);
"""


class GraphRunStore:
    """Durable rows for graph runs over the shared agent-memory store."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)

    def create_run(self, run: GraphRun) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO HarnessGraphRun
               (id, workflowId, workflowVersion, irVersion, mode, testRun, status,
                ownerId, startedAt, finishedAt, durationMs, error, plan, result, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.id, run.workflow_id, run.workflow_version, run.ir_version,
                run.mode.value, 1 if run.test_run else 0, run.status.value,
                run.owner_id, run.started_at, run.finished_at, run.duration_ms,
                run.error,
                json.dumps(run.plan.model_dump(by_alias=True)) if run.plan else None,
                None,
                now_iso(),
            ),
        )

    def finish_run(self, run: GraphRun) -> None:
        self._db.execute(
            """UPDATE HarnessGraphRun
               SET status=?, finishedAt=?, durationMs=?, error=?, result=?
               WHERE id=?""",
            (
                run.status.value, run.finished_at, run.duration_ms, run.error,
                json.dumps(run.model_dump(by_alias=True)), run.id,
            ),
        )

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM HarnessGraphRun WHERE id=?", (run_id,)
        ).fetchone()
        return self._row_to_dict(row) if row is not None else None

    def list_runs(self, workflow_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        if workflow_id:
            rows = self._db.execute(
                "SELECT * FROM HarnessGraphRun WHERE workflowId=? ORDER BY startedAt DESC LIMIT ?",
                (workflow_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM HarnessGraphRun ORDER BY startedAt DESC LIMIT ?", (limit,),
            ).fetchall()
        return [self._row_to_dict(row, summary=True) for row in rows]

    def delete_run(self, run_id: str) -> int:
        cursor = self._db.execute("DELETE FROM HarnessGraphRun WHERE id=?", (run_id,))
        return cursor.rowcount

    def reconcile_orphans(self, note: str = "interrupted by a restart") -> int:
        """A run left `running` by a previous process can never finish — mark it
        failed at boot instead of leaving a phantom in-flight row forever."""
        cursor = self._db.execute(
            "UPDATE HarnessGraphRun SET status=?, error=?, finishedAt=? WHERE status=?",
            ("failed", note, now_iso(), "running"),
        )
        return cursor.rowcount

    @staticmethod
    def new_run_id() -> str:
        return new_id("grun")

    @staticmethod
    def _row_to_dict(row: Any, summary: bool = False) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": row["id"],
            "workflowId": row["workflowId"],
            "workflowVersion": row["workflowVersion"],
            "irVersion": row["irVersion"],
            "mode": row["mode"],
            "testRun": bool(row["testRun"]),
            "status": row["status"],
            "ownerId": row["ownerId"],
            "startedAt": row["startedAt"],
            "finishedAt": row["finishedAt"],
            "durationMs": row["durationMs"],
            "error": row["error"],
        }
        if summary:
            return record
        plan = json.loads(row["plan"]) if row["plan"] else None
        result = json.loads(row["result"]) if row["result"] else None
        if result:
            # The completed run document is authoritative on read.
            record.update(result)
        record["plan"] = plan
        return record


__all__ = ["GraphRunStore"]

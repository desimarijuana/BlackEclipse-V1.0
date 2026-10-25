"""Graph-run persistence on the ONE `agent-memory.db`.

Owns its own tables and never reads another subsystem's rows.

Layout:

* `HarnessGraphRun` — one row per run; written at start and finalized at finish.
* `HarnessGraphNodeRun` — one row per node, UPSERTed as the node settles. It
  carries the bounded preview shown in the UI AND a full-output checkpoint used
  to resume a crashed/interrupted run.
* `HarnessGraphEvent` — the append-only run log, queryable per run.

A run started through the Fabric has a `jobId`; the worker can therefore be
recovered/replayed by the existing Fabric. A legacy/thread run has no jobId and
is reconciled to `failed` at boot (it can never finish).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import new_id, now_iso
from .model import GraphRun, NodeRun, NodeStatus, RunEvent

# A node checkpoint survives a restart, but it is not an unlimited dataset.
# Larger outputs stay visible as previews but make the run non-resumable.
MAX_CHECKPOINT_BYTES = 2_000_000

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
  jobId           TEXT,
  irHash          TEXT,
  createdAt       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_graph_run_workflow ON HarnessGraphRun(workflowId, startedAt);
CREATE INDEX IF NOT EXISTS idx_graph_run_status ON HarnessGraphRun(status);
CREATE INDEX IF NOT EXISTS idx_graph_run_job ON HarnessGraphRun(jobId);

CREATE TABLE IF NOT EXISTS HarnessGraphNodeRun (
  runId        TEXT NOT NULL,
  nodeId       TEXT NOT NULL,
  nodeType     TEXT NOT NULL,
  label        TEXT NOT NULL DEFAULT '',
  status       TEXT NOT NULL,
  layer        INTEGER NOT NULL DEFAULT 0,
  attempt      INTEGER NOT NULL DEFAULT 1,
  startedAt    TEXT,
  finishedAt   TEXT,
  durationMs   INTEGER,
  error        TEXT,
  errorCode    TEXT,
  inputs       TEXT,
  outputs      TEXT,
  fired        TEXT,
  checkpoint   TEXT,
  terminalDone INTEGER NOT NULL DEFAULT 0,
  terminalValue TEXT,
  resumable    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (runId, nodeId)
);
CREATE INDEX IF NOT EXISTS idx_graph_node_run_status ON HarnessGraphNodeRun(runId, status);

CREATE TABLE IF NOT EXISTS HarnessGraphEvent (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  runId   TEXT NOT NULL,
  at      TEXT NOT NULL,
  kind    TEXT NOT NULL,
  nodeId  TEXT,
  message TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_graph_event_run ON HarnessGraphEvent(runId, id);
"""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _loads(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


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
        self._ensure_columns("HarnessGraphRun", [("jobId", "TEXT"), ("irHash", "TEXT")])
        self._db.commit()

    def _ensure_columns(self, table: str, columns: list[tuple[str, str]]) -> None:
        existing = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, ddl in columns:
            if name not in existing:
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    # ── run rows ─────────────────────────────────────────────────────────────

    def create_run(self, run: GraphRun) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO HarnessGraphRun
               (id, workflowId, workflowVersion, irVersion, mode, testRun, status,
                ownerId, startedAt, finishedAt, durationMs, error, plan, result,
                jobId, irHash, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.id, run.workflow_id, run.workflow_version, run.ir_version,
                run.mode.value, 1 if run.test_run else 0, run.status.value,
                run.owner_id, run.started_at, run.finished_at, run.duration_ms,
                run.error,
                _json(run.plan.model_dump(by_alias=True)) if run.plan else None,
                None,
                getattr(run, "job_id", None),
                None,
                now_iso(),
            ),
        )
        self._db.commit()

    def set_job_id(self, run_id: str, job_id: Optional[str]) -> None:
        self._db.execute("UPDATE HarnessGraphRun SET jobId=? WHERE id=?", (job_id, run_id))
        self._db.commit()

    def mark_running(self, run_id: str) -> None:
        self._db.execute(
            "UPDATE HarnessGraphRun SET status=?, startedAt=COALESCE(startedAt, ?) WHERE id=?",
            ("running", now_iso(), run_id),
        )
        self._db.commit()

    def finish_run(self, run: GraphRun) -> None:
        self._db.execute(
            """UPDATE HarnessGraphRun
               SET status=?, finishedAt=?, durationMs=?, error=?, result=?
               WHERE id=?""",
            (
                run.status.value, run.finished_at, run.duration_ms, run.error,
                _json(run.model_dump(by_alias=True)), run.id,
            ),
        )
        self._db.commit()

    def mark_cancelled(self, run_id: str, reason: str = "cancelled by user") -> None:
        self._db.execute(
            "UPDATE HarnessGraphRun SET status=?, finishedAt=?, error=? WHERE id=?",
            ("cancelled", now_iso(), reason, run_id),
        )
        self._db.commit()

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM HarnessGraphRun WHERE id=?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        record = self._row_to_dict(row)
        result = _loads(row["result"], None)
        if isinstance(result, dict):
            # The completed run document is authoritative on read, but the
            # normalized tables below are more current for live runs.
            record.update(result)
            record["jobId"] = row["jobId"]
        node_runs = self.list_node_runs(run_id)
        if node_runs:
            record["nodeRuns"] = node_runs
            record["nodeStatus"] = {item["nodeId"]: item["status"] for item in node_runs}
        events = self.list_events(run_id)
        if events:
            record["events"] = events
        return record

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
        self._db.execute("DELETE FROM HarnessGraphNodeRun WHERE runId=?", (run_id,))
        self._db.execute("DELETE FROM HarnessGraphEvent WHERE runId=?", (run_id,))
        self._db.commit()
        return cursor.rowcount

    def reconcile_orphans(self, note: str = "interrupted by a restart") -> int:
        """A LEGACY (un-queued) run left `running` can never finish. Durable
        Fabric runs are deliberately left alone: the Fabric requeues them and
        the worker resumes from node checkpoints."""
        cursor = self._db.execute(
            """UPDATE HarnessGraphRun SET status=?, error=?, finishedAt=?
               WHERE status=? AND (jobId IS NULL OR jobId='')""",
            ("failed", note, now_iso(), "running"),
        )
        self._db.commit()
        return cursor.rowcount

    # ── node rows / checkpoints ──────────────────────────────────────────────

    def save_node_run(
        self,
        run_id: str,
        record: NodeRun,
        *,
        outputs: Optional[dict[str, Any]] = None,
        fired: Optional[list[str]] = None,
        terminal_done: bool = False,
        terminal_value: Any = None,
    ) -> None:
        checkpoint = _json(outputs or {}) if record.status == NodeStatus.SUCCEEDED else None
        resumable = bool(checkpoint is not None and len(checkpoint.encode("utf-8")) <= MAX_CHECKPOINT_BYTES)
        if checkpoint is not None and not resumable:
            checkpoint = None
        terminal_json = _json(terminal_value) if terminal_done else None
        if terminal_json is not None and len(terminal_json.encode("utf-8")) > MAX_CHECKPOINT_BYTES:
            # A huge terminal value is preview-only; do not pretend the run can
            # resume from a truncated value.
            terminal_json = None
            terminal_done = False
            resumable = False
        self._db.execute(
            """INSERT INTO HarnessGraphNodeRun
               (runId, nodeId, nodeType, label, status, layer, attempt, startedAt,
                finishedAt, durationMs, error, errorCode, inputs, outputs, fired,
                checkpoint, terminalDone, terminalValue, resumable)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(runId, nodeId) DO UPDATE SET
                 nodeType=excluded.nodeType, label=excluded.label, status=excluded.status,
                 layer=excluded.layer, attempt=excluded.attempt,
                 startedAt=excluded.startedAt, finishedAt=excluded.finishedAt,
                 durationMs=excluded.durationMs, error=excluded.error,
                 errorCode=excluded.errorCode, inputs=excluded.inputs,
                 outputs=excluded.outputs, fired=excluded.fired,
                 checkpoint=excluded.checkpoint, terminalDone=excluded.terminalDone,
                 terminalValue=excluded.terminalValue, resumable=excluded.resumable""",
            (
                run_id, record.node_id, record.node_type, record.label,
                record.status.value, record.layer, record.attempt,
                record.started_at, record.finished_at, record.duration_ms,
                record.error, record.error_code,
                _json(record.inputs), _json(record.outputs), _json(fired or []),
                checkpoint, 1 if terminal_done else 0, terminal_json,
                1 if resumable else 0,
            ),
        )
        self._db.commit()

    def load_resume(self, run_id: str) -> dict[str, Any]:
        """The successful node checkpoints for a run. `complete` is False when a
        successful node has no checkpoint (too large), in which case the caller
        must NOT pretend it can resume."""
        rows = self._db.execute(
            "SELECT * FROM HarnessGraphNodeRun WHERE runId=? AND status='succeeded'",
            (run_id,),
        ).fetchall()
        nodes: dict[str, NodeRun] = {}
        outputs: dict[str, dict[str, Any]] = {}
        fired: dict[str, list[str]] = {}
        terminal: dict[str, Any] = {}
        complete = True
        for row in rows:
            if not row["resumable"] or not row["checkpoint"]:
                complete = False
                continue
            node_id = row["nodeId"]
            nodes[node_id] = NodeRun(
                nodeId=node_id,
                nodeType=row["nodeType"],
                label=row["label"] or "",
                status=NodeStatus.SUCCEEDED,
                layer=row["layer"] or 0,
                attempt=row["attempt"] or 1,
                startedAt=row["startedAt"],
                finishedAt=row["finishedAt"],
                durationMs=row["durationMs"],
                inputs=_loads(row["inputs"], {}),
                outputs=_loads(row["outputs"], {}),
                error=row["error"],
                errorCode=row["errorCode"],
            )
            outputs[node_id] = _loads(row["checkpoint"], {})
            fired[node_id] = _loads(row["fired"], [])
            if row["terminalDone"]:
                terminal[node_id] = _loads(row["terminalValue"], None)
        return {
            "complete": complete,
            "nodes": nodes,
            "outputs": outputs,
            "fired": fired,
            "terminal": terminal,
        }

    def list_node_runs(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM HarnessGraphNodeRun WHERE runId=? ORDER BY layer, nodeId",
            (run_id,),
        ).fetchall()
        return [
            {
                "nodeId": row["nodeId"],
                "nodeType": row["nodeType"],
                "label": row["label"],
                "status": row["status"],
                "layer": row["layer"],
                "attempt": row["attempt"],
                "startedAt": row["startedAt"],
                "finishedAt": row["finishedAt"],
                "durationMs": row["durationMs"],
                "inputs": _loads(row["inputs"], {}),
                "outputs": _loads(row["outputs"], {}),
                "error": row["error"],
                "errorCode": row["errorCode"],
                "resumable": bool(row["resumable"]),
            }
            for row in rows
        ]

    # ── events ───────────────────────────────────────────────────────────────

    def save_event(self, run_id: str, event: RunEvent) -> None:
        self._db.execute(
            "INSERT INTO HarnessGraphEvent (runId, at, kind, nodeId, message) VALUES (?, ?, ?, ?, ?)",
            (run_id, event.at, event.kind, event.node_id, event.message),
        )
        self._db.commit()

    def list_events(self, run_id: str, limit: int = 1_000) -> list[dict[str, Any]]:
        return self.events_since(run_id, 0, limit=limit)

    def events_since(self, run_id: str, after_id: int = 0, limit: int = 1_000) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM HarnessGraphEvent WHERE runId=? AND id>? ORDER BY id LIMIT ?",
            (run_id, max(0, int(after_id)), max(1, min(int(limit), 5_000))),
        ).fetchall()
        return [
            {
                "id": row["id"], "at": row["at"], "kind": row["kind"],
                "nodeId": row["nodeId"], "message": row["message"],
            }
            for row in rows
        ]

    # ── helpers ──────────────────────────────────────────────────────────────

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
            "jobId": row["jobId"],
        }
        if summary:
            return record
        plan = _loads(row["plan"], None)
        record["plan"] = plan
        return record


__all__ = ["GraphRunStore", "MAX_CHECKPOINT_BYTES"]

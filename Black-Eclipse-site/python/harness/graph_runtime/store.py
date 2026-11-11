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

import datetime as _dt
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from ..persistence import new_id, now_iso
from .model import GraphRun, NodeRun, NodeStatus, RunEvent

# A node checkpoint survives a restart, but it is not an unlimited dataset.
# Larger outputs stay visible as previews but make the run non-resumable.
MAX_CHECKPOINT_BYTES = 2_000_000
HARD_CHECKPOINT_BYTES = 16_000_000
# Above the DB checkpoint limit, a payload spills to a confined file instead of
# making the run non-resumable. The file cap is deliberately generous but finite.
CHECKPOINT_FILE_LIMIT_BYTES = 256_000_000
_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _checkpoint_limit() -> int:
    """Operator override for the per-node checkpoint size (bounded)."""
    raw = os.environ.get("HARNESS_GRAPH_CHECKPOINT_MAX_BYTES")
    if raw is not None and str(raw).strip():
        try:
            return max(1_000, min(int(float(raw)), HARD_CHECKPOINT_BYTES))
        except (TypeError, ValueError):
            pass
    return MAX_CHECKPOINT_BYTES

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

CREATE TABLE IF NOT EXISTS GraphHealthWatchState (
  scope     TEXT PRIMARY KEY,
  status    TEXT NOT NULL,
  reasons   TEXT NOT NULL DEFAULT '[]',
  updatedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS GraphHealthAlert (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  status    TEXT NOT NULL,
  reasons   TEXT NOT NULL DEFAULT '[]',
  createdAt TEXT NOT NULL
);
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


def _percentile(values: list[float], fraction: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def _utc(value: Optional[str]) -> Optional[_dt.datetime]:
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.timezone.utc)


class GraphRunStore:
    """Durable rows for graph runs over the shared agent-memory store."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()
        from ..execution_log import ExecutionEventLog  # noqa: PLC0415

        self._events = ExecutionEventLog(self._db)

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._ensure_columns("HarnessGraphRun", [("jobId", "TEXT"), ("irHash", "TEXT")])
        # The jobId index must be created AFTER the upgrade: on a legacy table
        # (one created before jobId existed) an index in _SCHEMA fails with
        # "no such column: jobId" and blocks the graph runtime at boot.
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_graph_run_job ON HarnessGraphRun(jobId)"
        )
        self._db.commit()

    # ── checkpoint spill ───────────────────────────────────────────────────
    def _checkpoint_root(self) -> Path:
        path = str(getattr(self._store, "path", "") or "")
        base = Path(path).resolve().parent if path and path != ":memory:" else Path.cwd()
        return base / "graph-checkpoints"

    @staticmethod
    def _safe(value: str) -> str:
        return _SAFE.sub("_", str(value))[:120] or "_"

    def _spill_checkpoint(self, run_id: str, node_id: str, kind: str, text: str) -> str:
        """Write one oversized payload to a confined file; return its relative path."""
        root = self._checkpoint_root()
        target = root / self._safe(run_id) / f"{self._safe(node_id)}.{kind}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(target)
        return str(target.relative_to(root)).replace("\\", "/")

    def _read_checkpoint(self, value: Optional[str]) -> tuple[bool, Any]:
        """Read a checkpoint value, following a spilled-file reference safely."""
        if not value:
            return True, None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return False, None
        if not (isinstance(parsed, dict) and set(parsed) == {"$file"}):
            return True, parsed
        root = self._checkpoint_root().resolve()
        try:
            path = (root / str(parsed["$file"])).resolve()
        except Exception:  # noqa: BLE001 - a malformed ref is unreadable
            return False, None
        if not path.is_relative_to(root):
            return False, None
        try:
            return True, json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False, None

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

    def health(
        self,
        *,
        window_hours: int = 24,
        run_limit: int = 1_000,
        node_limit: int = 5_000,
    ) -> dict[str, Any]:
        """Bounded operator telemetry from the persisted run tables.

        Honest by construction: counts and percentiles are computed only from
        rows inside the window, `truncated` is true when a hard read cap was hit,
        and a missing duration is excluded rather than counted as zero.
        """
        hours = max(1, min(int(window_hours), 168))
        limit = max(1, min(int(run_limit), 2_000))
        node_cap = max(1, min(int(node_limit), 20_000))
        cutoff_dt = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)
        cutoff = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        run_rows = self._db.execute(
            "SELECT * FROM HarnessGraphRun WHERE startedAt>=? ORDER BY startedAt DESC LIMIT ?",
            (cutoff, limit + 1),
        ).fetchall()
        truncated_runs = len(run_rows) > limit
        run_rows = run_rows[:limit]

        node_rows = self._db.execute(
            """SELECT n.nodeType, n.status, n.durationMs, n.errorCode, n.resumable
                 FROM HarnessGraphNodeRun n
                 JOIN HarnessGraphRun r ON r.id = n.runId
                WHERE r.startedAt>=? LIMIT ?""",
            (cutoff, node_cap + 1),
        ).fetchall()
        truncated_nodes = len(node_rows) > node_cap
        node_rows = node_rows[:node_cap]

        by_status: dict[str, int] = {}
        durations: list[float] = []
        queue_waits: list[float] = []
        for row in run_rows:
            status = str(row["status"])
            by_status[status] = by_status.get(status, 0) + 1
            if isinstance(row["durationMs"], (int, float)):
                durations.append(float(row["durationMs"]))
            started = _utc(row["startedAt"])
            created = _utc(row["createdAt"])
            if started is not None and created is not None:
                queue_waits.append(max(0.0, (started - created).total_seconds() * 1000.0))

        terminal = sum(by_status.get(name, 0) for name in ("succeeded", "failed", "cancelled"))
        succeeded = by_status.get("succeeded", 0)
        failure_codes: dict[str, int] = {}
        node_by_type: dict[str, dict[str, Any]] = {}
        failed_nodes = 0
        skipped_nodes = 0
        resumable_nodes = 0
        for row in node_rows:
            status = str(row["status"])
            failed_nodes += int(status == "failed")
            skipped_nodes += int(status == "skipped")
            resumable_nodes += int(status == "succeeded" and bool(row["resumable"]))
            if status == "failed":
                code = str(row["errorCode"] or "UNKNOWN")
                failure_codes[code] = failure_codes.get(code, 0) + 1
            stats = node_by_type.setdefault(
                str(row["nodeType"]),
                {"nodeType": str(row["nodeType"]), "runs": 0, "failures": 0, "durations": []},
            )
            stats["runs"] += 1
            stats["failures"] += int(status == "failed")
            if isinstance(row["durationMs"], (int, float)):
                stats["durations"].append(float(row["durationMs"]))

        slowest = []
        for stats in node_by_type.values():
            values = stats.pop("durations")
            if not values:
                continue
            slowest.append({
                **stats,
                "avgMs": round(sum(values) / len(values), 2),
                "p95Ms": round(_percentile(values, 0.95) or 0.0, 2),
            })
        slowest.sort(key=lambda item: (item["avgMs"], item["runs"]), reverse=True)

        return {
            "windowHours": hours,
            "generatedAt": now_iso(),
            "runs": {
                "total": len(run_rows),
                "terminal": terminal,
                "byStatus": by_status,
                "successRate": round(succeeded / terminal, 4) if terminal else None,
                "failureRate": round(by_status.get("failed", 0) / terminal, 4) if terminal else None,
                "throughputPerHour": round(len(run_rows) / hours, 3),
            },
            "durationMs": {
                "avg": round(sum(durations) / len(durations), 2) if durations else None,
                "p50": _percentile(durations, 0.50),
                "p95": _percentile(durations, 0.95),
            },
            "queueWaitMs": {
                "avg": round(sum(queue_waits) / len(queue_waits), 2) if queue_waits else None,
                "p95": _percentile(queue_waits, 0.95),
            },
            "nodeRuns": {
                "total": len(node_rows),
                "failed": failed_nodes,
                "skipped": skipped_nodes,
                "checkpointRate": (
                    round(resumable_nodes / len(node_rows), 4) if node_rows else None
                ),
            },
            "failures": [
                {"code": code, "count": count}
                for code, count in sorted(failure_codes.items(), key=lambda item: (-item[1], item[0]))[:10]
            ],
            "slowestNodes": slowest[:10],
            "truncated": {"runs": truncated_runs, "nodeRuns": truncated_nodes},
            "watch": self.watch_state(),
            "alerts": self.health_alerts(20),
        }

    def watch_state(self) -> dict[str, Any]:
        """The last health-watch verdict (persisted; survives a restart)."""
        row = self._db.execute(
            "SELECT * FROM GraphHealthWatchState WHERE scope='graph'"
        ).fetchone()
        if row is None:
            return {"status": "unmeasured", "reasons": [], "checkedAt": None}
        return {
            "status": str(row["status"]),
            "reasons": _loads(row["reasons"], []),
            "checkedAt": row["updatedAt"],
        }

    def save_watch_state(self, status: str, reasons: list[str]) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO GraphHealthWatchState (scope, status, reasons, updatedAt) "
            "VALUES ('graph', ?, ?, ?)",
            (status, _json(reasons), now_iso()),
        )
        self._db.commit()

    def save_alert(self, status: str, reasons: list[str]) -> None:
        """Append one TRANSITION to the bounded alert history."""
        self._db.execute(
            "INSERT INTO GraphHealthAlert (status, reasons, createdAt) VALUES (?, ?, ?)",
            (status, _json(reasons), now_iso()),
        )
        self._db.commit()

    def health_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM GraphHealthAlert ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "status": row["status"],
                "reasons": _loads(row["reasons"], []),
                "createdAt": row["createdAt"],
            }
            for row in rows
        ]

    def delete_run(self, run_id: str) -> int:
        cursor = self._db.execute("DELETE FROM HarnessGraphRun WHERE id=?", (run_id,))
        self._db.execute("DELETE FROM HarnessGraphNodeRun WHERE runId=?", (run_id,))
        self._db.execute("DELETE FROM HarnessGraphEvent WHERE runId=?", (run_id,))
        self._db.commit()
        shutil.rmtree(self._checkpoint_root() / self._safe(run_id), ignore_errors=True)
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
        limit = _checkpoint_limit()
        resumable = False
        if checkpoint is not None:
            size = len(checkpoint.encode("utf-8"))
            if size <= limit:
                resumable = True
            elif size <= CHECKPOINT_FILE_LIMIT_BYTES:
                ref = self._spill_checkpoint(run_id, record.node_id, "checkpoint", checkpoint)
                checkpoint = _json({"$file": ref})
                resumable = True
            else:
                checkpoint = None
        terminal_json = _json(terminal_value) if terminal_done else None
        if terminal_json is not None:
            term_size = len(terminal_json.encode("utf-8"))
            if term_size > limit:
                if term_size <= CHECKPOINT_FILE_LIMIT_BYTES:
                    ref = self._spill_checkpoint(run_id, record.node_id, "terminal", terminal_json)
                    terminal_json = _json({"$file": ref})
                else:
                    # A huge terminal value is preview-only; do not pretend the run
                    # can resume from a truncated value.
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
            ok, data = self._read_checkpoint(row["checkpoint"])
            if not ok:
                complete = False
                continue
            outputs[node_id] = data if isinstance(data, dict) else {}
            fired[node_id] = _loads(row["fired"], [])
            if row["terminalDone"]:
                term_ok, term = self._read_checkpoint(row["terminalValue"])
                if not term_ok:
                    complete = False
                    continue
                terminal[node_id] = term
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
        # Round 5 / C2: one canonical log, this table as the graph projection.
        self._events.append(
            "graph", run_id, event.kind,
            {"nodeId": event.node_id, "message": event.message, "at": event.at},
        )

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

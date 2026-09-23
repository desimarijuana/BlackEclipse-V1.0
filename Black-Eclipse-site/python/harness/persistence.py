"""Agent-memory persistence — owned by the Python runtime.

The SEPARATE SQLite database `agent-memory.db` holds runs, events, tool
executions, long-lived agent memory (user/agent/market facts) and skills. It is
deliberately NOT JDdS (`jdds.db`), which stays the committed market-data vault.

Uses the stdlib `sqlite3`, so there is no dependency and no migration step: the
idempotent DDL is applied on first use. The schema mirrors the TS
`src/lib/harness/persistence/schema.ts`.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import time
import uuid
from typing import Any, Optional

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS HarnessRun (
  id          TEXT PRIMARY KEY,
  agentId     TEXT NOT NULL,
  userId      TEXT,
  status      TEXT NOT NULL,
  input       TEXT NOT NULL,
  output      TEXT,
  error       TEXT,
  modelSteps  INTEGER NOT NULL DEFAULT 0,
  toolCalls   INTEGER NOT NULL DEFAULT 0,
  toolErrors  INTEGER NOT NULL DEFAULT 0,
  promptTokens     INTEGER NOT NULL DEFAULT 0,
  completionTokens INTEGER NOT NULL DEFAULT 0,
  totalTokens      INTEGER NOT NULL DEFAULT 0,
  provider    TEXT,
  model       TEXT,
  createdAt   TEXT NOT NULL,
  updatedAt   TEXT NOT NULL,
  startedAt   TEXT,
  finishedAt  TEXT
);
CREATE INDEX IF NOT EXISTS idx_harness_run_status  ON HarnessRun(status);
CREATE INDEX IF NOT EXISTS idx_harness_run_user    ON HarnessRun(userId);
CREATE INDEX IF NOT EXISTS idx_harness_run_created ON HarnessRun(createdAt);

CREATE TABLE IF NOT EXISTS HarnessEvent (
  id     TEXT PRIMARY KEY,
  runId  TEXT NOT NULL,
  type   TEXT NOT NULL,
  seq    INTEGER NOT NULL,
  at     TEXT NOT NULL,
  data   TEXT,
  FOREIGN KEY (runId) REFERENCES HarnessRun(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_harness_event_run ON HarnessEvent(runId, seq);

CREATE TABLE IF NOT EXISTS HarnessToolExecution (
  id          TEXT PRIMARY KEY,
  runId       TEXT NOT NULL,
  toolCallId  TEXT NOT NULL,
  name        TEXT NOT NULL,
  ok          INTEGER NOT NULL,
  durationMs  INTEGER NOT NULL,
  args        TEXT NOT NULL,
  text        TEXT NOT NULL,
  error       TEXT,
  createdAt   TEXT NOT NULL,
  FOREIGN KEY (runId) REFERENCES HarnessRun(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_harness_tool_run  ON HarnessToolExecution(runId);
CREATE INDEX IF NOT EXISTS idx_harness_tool_name ON HarnessToolExecution(name);

CREATE TABLE IF NOT EXISTS AgentMemory (
  id         TEXT PRIMARY KEY,
  scope      TEXT NOT NULL,
  userId     TEXT,
  agentId    TEXT,
  subject    TEXT,
  kind       TEXT NOT NULL,
  content    TEXT NOT NULL,
  source     TEXT,
  confidence REAL NOT NULL DEFAULT 0.5,
  createdAt  TEXT NOT NULL,
  updatedAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_scope   ON AgentMemory(scope, userId);
CREATE INDEX IF NOT EXISTS idx_memory_subject ON AgentMemory(subject);
CREATE INDEX IF NOT EXISTS idx_memory_agent   ON AgentMemory(agentId);

CREATE TABLE IF NOT EXISTS AgentSkill (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL,
  definition  TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'proposed',
  originRunId TEXT,
  successCount INTEGER NOT NULL DEFAULT 0,
  failCount    INTEGER NOT NULL DEFAULT 0,
  createdAt   TEXT NOT NULL,
  updatedAt   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_status ON AgentSkill(status);

-- D1: durable retrieval records. A retrieval result is parsed once and persisted
-- here keyed by the request key, so re-running an identical query returns the
-- SAME figures and citations instead of re-scraping (which could drift).
CREATE TABLE IF NOT EXISTS RetrievalRecord (
  key          TEXT PRIMARY KEY,
  dataType     TEXT NOT NULL,
  instrument   TEXT,
  market       TEXT,
  result       TEXT NOT NULL,   -- the full FinancialRetrievalResult JSON
  provenance   TEXT NOT NULL,   -- source + retrieval timestamp, for audit
  retrievedAt  TEXT NOT NULL,
  dataTimestamp TEXT
);
CREATE INDEX IF NOT EXISTS idx_retrieval_type ON RetrievalRecord(dataType);

-- Phase 4: durable research receipts. One bounded, queryable record per research
-- run explaining request → coverage → claims → validation → final status.
-- Lives in agent-memory.db (the harness store); never in eclipse-memory.db or
-- JDdS. Bounded: evidence references carry hashes/summaries, not full documents.
CREATE TABLE IF NOT EXISTS ResearchReceipt (
  runId        TEXT PRIMARY KEY,
  schemaVersion TEXT NOT NULL,
  taskType     TEXT NOT NULL,
  objective    TEXT NOT NULL,
  finalStatus  TEXT NOT NULL,
  receipt      TEXT NOT NULL,   -- the full ResearchReceipt JSON
  createdAt    TEXT NOT NULL,
  FOREIGN KEY (runId) REFERENCES HarnessRun(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_research_receipt_status ON ResearchReceipt(finalStatus);
CREATE INDEX IF NOT EXISTS idx_research_receipt_created ON ResearchReceipt(createdAt);
"""

DB_FILENAME = "agent-memory.db"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() % 1 * 1000):03d}Z"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def _iso_days_ago(days: int) -> str:
    """UTC ISO timestamp `days` ago, matching the `now_iso` format so string
    comparison against `createdAt` is chronological."""
    then = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    return then.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def default_db_path() -> str:
    override = os.environ.get("AGENT_MEMORY_DB_PATH")
    if override:
        return os.path.abspath(override)
    return os.path.join(os.getcwd(), DB_FILENAME)


# Columns added after the first release. `CREATE TABLE IF NOT EXISTS` does not
# alter an existing table, so an older `agent-memory.db` needs an explicit
# idempotent ADD COLUMN — otherwise upgrades would silently lose token data.
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "HarnessRun": [
        ("promptTokens", "INTEGER NOT NULL DEFAULT 0"),
        ("completionTokens", "INTEGER NOT NULL DEFAULT 0"),
        ("totalTokens", "INTEGER NOT NULL DEFAULT 0"),
    ],
}


class AgentMemoryStore:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or default_db_path()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._migrate()
        self._db.commit()

    def _migrate(self) -> None:
        """Add any post-release columns to an existing database (idempotent)."""
        for table, columns in _ADDED_COLUMNS.items():
            existing = {
                row["name"]
                for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for name, ddl in columns:
                if name not in existing:
                    self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    # ── Runs ────────────────────────────────────────────────────────────────
    def create_run(
        self,
        run_id: str,
        agent_id: str,
        input_data: dict[str, Any],
        user_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        now = now_iso()
        self._db.execute(
            """INSERT INTO HarnessRun
               (id, agentId, userId, status, input, modelSteps, toolCalls, toolErrors,
                provider, model, createdAt, updatedAt)
               VALUES (?, ?, ?, 'created', ?, 0, 0, 0, ?, ?, ?, ?)""",
            (run_id, agent_id, user_id, json.dumps(input_data), provider, model, now, now),
        )
        self._db.commit()

    def update_run(self, run_id: str, **patch: Any) -> None:
        allowed = {
            "status", "output", "error", "modelSteps", "toolCalls", "toolErrors",
            "promptTokens", "completionTokens", "totalTokens",
            "provider", "model", "startedAt", "finishedAt",
        }
        sets, params = [], []
        for key, value in patch.items():
            if key not in allowed:
                continue
            sets.append(f"{key} = ?")
            params.append(json.dumps(value) if key == "error" and value is not None else value)
        if not sets:
            return
        sets.append("updatedAt = ?")
        params.append(now_iso())
        params.append(run_id)
        self._db.execute(f"UPDATE HarnessRun SET {', '.join(sets)} WHERE id = ?", params)
        self._db.commit()

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM HarnessRun WHERE id = ?", (run_id,)).fetchone()
        return _run_row(row) if row else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        rows = self._db.execute(
            "SELECT * FROM HarnessRun ORDER BY createdAt DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_run_row(r) for r in rows]

    # ── Usage analytics ─────────────────────────────────────────────────────
    # Token consumption is real, persisted data. `totalTokens` can legitimately
    # be 0 when a provider (e.g. a local Ollama server) omits a usage block — the
    # UI must render that honestly as "not reported", never as a fabricated
    # number. Hence `runsWithUsage` alongside the totals.
    def usage_summary(self, days: int = 30) -> dict[str, Any]:
        days = max(1, min(int(days), 365))
        since = _iso_days_ago(days)

        totals = self._db.execute(
            """SELECT
                 COUNT(*)                        AS runs,
                 COALESCE(SUM(promptTokens), 0)     AS promptTokens,
                 COALESCE(SUM(completionTokens), 0) AS completionTokens,
                 COALESCE(SUM(totalTokens), 0)      AS totalTokens,
                 COALESCE(SUM(modelSteps), 0)       AS modelSteps,
                 COALESCE(SUM(toolCalls), 0)        AS toolCalls,
                 COALESCE(SUM(toolErrors), 0)       AS toolErrors,
                 COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) AS completed,
                 COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0)    AS failed,
                 COALESCE(SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled,
                 COALESCE(SUM(CASE WHEN totalTokens > 0 THEN 1 ELSE 0 END), 0)      AS runsWithUsage
               FROM HarnessRun WHERE createdAt >= ?""",
            (since,),
        ).fetchone()

        by_model = self._db.execute(
            """SELECT COALESCE(provider, 'unknown') AS provider,
                      COALESCE(model, 'unknown')    AS model,
                      COUNT(*)                      AS runs,
                      COALESCE(SUM(promptTokens), 0)     AS promptTokens,
                      COALESCE(SUM(completionTokens), 0) AS completionTokens,
                      COALESCE(SUM(totalTokens), 0)      AS totalTokens
               FROM HarnessRun WHERE createdAt >= ?
               GROUP BY provider, model
               ORDER BY totalTokens DESC, runs DESC""",
            (since,),
        ).fetchall()

        by_day = self._db.execute(
            """SELECT substr(createdAt, 1, 10) AS date,
                      COUNT(*)                 AS runs,
                      COALESCE(SUM(promptTokens), 0)     AS promptTokens,
                      COALESCE(SUM(completionTokens), 0) AS completionTokens,
                      COALESCE(SUM(totalTokens), 0)      AS totalTokens
               FROM HarnessRun WHERE createdAt >= ?
               GROUP BY date ORDER BY date ASC""",
            (since,),
        ).fetchall()

        recent = self._db.execute(
            """SELECT id, agentId, status, provider, model, modelSteps, toolCalls,
                      toolErrors, promptTokens, completionTokens, totalTokens, createdAt
               FROM HarnessRun ORDER BY createdAt DESC LIMIT 20"""
        ).fetchall()

        return {
            "windowDays": days,
            "since": since,
            "totals": {
                "runs": totals["runs"],
                "promptTokens": totals["promptTokens"],
                "completionTokens": totals["completionTokens"],
                "totalTokens": totals["totalTokens"],
                "modelSteps": totals["modelSteps"],
                "toolCalls": totals["toolCalls"],
                "toolErrors": totals["toolErrors"],
                "completed": totals["completed"],
                "failed": totals["failed"],
                "cancelled": totals["cancelled"],
                "runsWithUsage": totals["runsWithUsage"],
            },
            "byModel": [
                {
                    "provider": r["provider"],
                    "model": r["model"],
                    "runs": r["runs"],
                    "promptTokens": r["promptTokens"],
                    "completionTokens": r["completionTokens"],
                    "totalTokens": r["totalTokens"],
                }
                for r in by_model
            ],
            "byDay": [
                {
                    "date": r["date"],
                    "runs": r["runs"],
                    "promptTokens": r["promptTokens"],
                    "completionTokens": r["completionTokens"],
                    "totalTokens": r["totalTokens"],
                }
                for r in by_day
            ],
            "recent": [dict(r) for r in recent],
        }

    # ── Events ──────────────────────────────────────────────────────────────
    def append_event(self, run_id: str, event_type: str, seq: int, data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        event = {
            "id": new_id("evt"),
            "runId": run_id,
            "type": event_type,
            "seq": seq,
            "at": now_iso(),
            "data": data or {},
        }
        self._db.execute(
            "INSERT INTO HarnessEvent (id, runId, type, seq, at, data) VALUES (?, ?, ?, ?, ?, ?)",
            (event["id"], run_id, event_type, seq, event["at"], json.dumps(event["data"])),
        )
        self._db.commit()
        return event

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM HarnessEvent WHERE runId = ? ORDER BY seq ASC", (run_id,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "runId": r["runId"],
                "type": r["type"],
                "seq": r["seq"],
                "at": r["at"],
                "data": json.loads(r["data"]) if r["data"] else {},
            }
            for r in rows
        ]

    # ── Tool executions ─────────────────────────────────────────────────────
    def record_tool_execution(self, run_id: str, result: Any) -> None:
        self._db.execute(
            """INSERT INTO HarnessToolExecution
               (id, runId, toolCallId, name, ok, durationMs, args, text, error, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id("tex"),
                run_id,
                result.tool_call_id,
                result.name,
                1 if result.ok else 0,
                result.duration_ms,
                json.dumps(getattr(result, "args", {}) or {}),
                result.text[:4000],
                result.error.model_dump_json() if result.error else None,
                now_iso(),
            ),
        )
        self._db.commit()

    def list_tool_executions(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM HarnessToolExecution WHERE runId = ? ORDER BY createdAt ASC", (run_id,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "runId": r["runId"],
                "toolCallId": r["toolCallId"],
                "name": r["name"],
                "ok": bool(r["ok"]),
                "durationMs": r["durationMs"],
                "args": json.loads(r["args"]) if r["args"] else {},
                "text": r["text"],
                "error": json.loads(r["error"]) if r["error"] else None,
                "createdAt": r["createdAt"],
            }
            for r in rows
        ]

    # ── Durable retrieval records (D1) ──────────────────────────────────────
    def save_retrieval(
        self,
        key: str,
        data_type: str,
        instrument: Optional[str],
        market: Optional[str],
        result_json: dict[str, Any],
        provenance: dict[str, Any],
        data_timestamp: Optional[str] = None,
    ) -> None:
        self._db.execute(
            """INSERT INTO RetrievalRecord
               (key, dataType, instrument, market, result, provenance, retrievedAt, dataTimestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                 result = excluded.result,
                 provenance = excluded.provenance,
                 retrievedAt = excluded.retrievedAt,
                 dataTimestamp = excluded.dataTimestamp""",
            (
                key,
                data_type,
                instrument,
                market,
                json.dumps(result_json),
                json.dumps(provenance),
                now_iso(),
                data_timestamp,
            ),
        )
        self._db.commit()

    def get_retrieval(self, key: str) -> Optional[dict[str, Any]]:
        r = self._db.execute("SELECT * FROM RetrievalRecord WHERE key = ?", (key,)).fetchone()
        if r is None:
            return None
        return {
            "key": r["key"],
            "dataType": r["dataType"],
            "instrument": r["instrument"],
            "market": r["market"],
            "result": json.loads(r["result"]),
            "provenance": json.loads(r["provenance"]) if r["provenance"] else {},
            "retrievedAt": r["retrievedAt"],
            "dataTimestamp": r["dataTimestamp"],
        }

    # ── Research receipts (Phase 4) ─────────────────────────────────────────
    def save_receipt(self, receipt: dict[str, Any]) -> None:
        """Persist a bounded research receipt (idempotent per run).

        `receipt` is a `ResearchReceipt.model_dump()`. Persistence failures are
        raised to the caller so a save is never falsely claimed successful.
        """
        run_id = str(receipt.get("runId") or "")
        if not run_id:
            raise ValueError("receipt is missing a runId")
        self._db.execute(
            """INSERT INTO ResearchReceipt
               (runId, schemaVersion, taskType, objective, finalStatus, receipt, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(runId) DO UPDATE SET
                 schemaVersion = excluded.schemaVersion,
                 taskType = excluded.taskType,
                 objective = excluded.objective,
                 finalStatus = excluded.finalStatus,
                 receipt = excluded.receipt,
                 createdAt = excluded.createdAt""",
            (
                run_id,
                str(receipt.get("schemaVersion") or "1.0.0"),
                str(receipt.get("taskType") or "general"),
                str(receipt.get("objective") or ""),
                str(receipt.get("finalStatus") or "rejected"),
                json.dumps(receipt),
                now_iso(),
            ),
        )
        self._db.commit()

    def get_receipt(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM ResearchReceipt WHERE runId = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["receipt"]) if row["receipt"] else None

    def list_receipts(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        rows = self._db.execute(
            "SELECT * FROM ResearchReceipt ORDER BY createdAt DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "runId": r["runId"],
                "schemaVersion": r["schemaVersion"],
                "taskType": r["taskType"],
                "objective": r["objective"],
                "finalStatus": r["finalStatus"],
                "createdAt": r["createdAt"],
            }
            for r in rows
        ]

    # ── Agent memory ────────────────────────────────────────────────────────
    def remember(
        self,
        scope: str,
        kind: str,
        content: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        subject: Optional[str] = None,
        source: Optional[str] = None,
        confidence: float = 0.5,
    ) -> dict[str, Any]:
        record = {
            "id": new_id("mem"),
            "scope": scope,
            "userId": user_id,
            "agentId": agent_id,
            "subject": subject,
            "kind": kind,
            "content": content,
            "source": source,
            "confidence": max(0.0, min(float(confidence), 1.0)),
            "createdAt": now_iso(),
        }
        record["updatedAt"] = record["createdAt"]
        self._db.execute(
            """INSERT INTO AgentMemory
               (id, scope, userId, agentId, subject, kind, content, source, confidence, createdAt, updatedAt)
               VALUES (:id, :scope, :userId, :agentId, :subject, :kind, :content, :source, :confidence, :createdAt, :updatedAt)""",
            record,
        )
        self._db.commit()
        return record

    def recall(
        self,
        scope: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        subject: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        where, params = [], []
        for column, value in (("scope", scope), ("userId", user_id), ("agentId", agent_id), ("subject", subject)):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        limit = max(1, min(int(limit), 100))
        rows = self._db.execute(
            f"SELECT * FROM AgentMemory {clause} ORDER BY updatedAt DESC LIMIT ?", [*params, limit]
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Skills ──────────────────────────────────────────────────────────────
    def propose_skill(
        self,
        name: str,
        description: str,
        definition: dict[str, Any],
        origin_run_id: Optional[str] = None,
        status: str = "proposed",
    ) -> dict[str, Any]:
        existing = self._db.execute("SELECT * FROM AgentSkill WHERE name = ?", (name,)).fetchone()
        if existing:
            self._db.execute(
                "UPDATE AgentSkill SET description = ?, definition = ?, updatedAt = ? WHERE name = ?",
                (description, json.dumps(definition), now_iso(), name),
            )
            self._db.commit()
            return self.get_skill(name)  # type: ignore[return-value]
        now = now_iso()
        self._db.execute(
            """INSERT INTO AgentSkill
               (id, name, description, definition, status, originRunId, successCount, failCount, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?)""",
            (new_id("skill"), name, description, json.dumps(definition), status, origin_run_id, now, now),
        )
        self._db.commit()
        return self.get_skill(name)  # type: ignore[return-value]

    def get_skill(self, name: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM AgentSkill WHERE name = ?", (name,)).fetchone()
        if not row:
            return None
        record = dict(row)
        record["definition"] = json.loads(record["definition"])
        return record

    def list_skills(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        if status:
            rows = self._db.execute("SELECT * FROM AgentSkill WHERE status = ? ORDER BY updatedAt DESC", (status,)).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM AgentSkill ORDER BY updatedAt DESC").fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["definition"] = json.loads(record["definition"])
            out.append(record)
        return out

    def record_skill_outcome(self, name: str, ok: bool) -> None:
        column = "successCount" if ok else "failCount"
        self._db.execute(
            f"UPDATE AgentSkill SET {column} = {column} + 1, updatedAt = ? WHERE name = ?", (now_iso(), name)
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()


def _run_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "agentId": row["agentId"],
        "userId": row["userId"],
        "status": row["status"],
        "input": json.loads(row["input"]) if row["input"] else {},
        "output": row["output"],
        "error": json.loads(row["error"]) if row["error"] else None,
        "modelSteps": row["modelSteps"],
        "toolCalls": row["toolCalls"],
        "toolErrors": row["toolErrors"],
        "promptTokens": row["promptTokens"],
        "completionTokens": row["completionTokens"],
        "totalTokens": row["totalTokens"],
        "provider": row["provider"],
        "model": row["model"],
        "createdAt": row["createdAt"],
        "updatedAt": row["updatedAt"],
        "startedAt": row["startedAt"],
        "finishedAt": row["finishedAt"],
    }


__all__ = ["AgentMemoryStore", "SCHEMA", "DB_FILENAME", "default_db_path", "now_iso", "new_id"]

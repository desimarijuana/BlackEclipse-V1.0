"""Computer Use persistence, bound to the ONE agent-memory connection.

Owns the Computer Use metadata tables and their helpers. Mirrors `browser/store.py`
and `code/store.py`: the module is bound to the single `AgentMemoryStore` sqlite
connection and owns only its own tables, so `persistence.py` does not grow.

The database is `agent-memory.db` (the runtime's own). NEVER `eclipse-memory.db`
and NEVER `jdds.db`. The DDL is idempotent. NO secret and NO screenshot pixel
data is stored here — only content-free metadata and artifact PATHS.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..persistence import now_iso


def _row(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def new_session_id() -> str:
    return "csess_" + uuid.uuid4().hex[:16]


def new_trace_id() -> str:
    return "ctrace_" + uuid.uuid4().hex[:16]


class ComputerStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS ComputerSession (
              id           TEXT PRIMARY KEY,
              agentId      TEXT,
              taskId       TEXT,
              runId        TEXT,
              userId       TEXT,
              machineId    TEXT,
              driver       TEXT NOT NULL,
              displayState TEXT,
              activeApp    TEXT,
              windowCount  INTEGER NOT NULL DEFAULT 0,
              riskMode     TEXT,
              status       TEXT NOT NULL,
              state        TEXT,
              createdAt    TEXT NOT NULL,
              lastActivity TEXT,
              terminatedAt TEXT,
              metadataJson TEXT
            )
            """
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_computer_session_created ON ComputerSession(createdAt)")
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_computer_session_status ON ComputerSession(status, lastActivity)")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS ComputerAction (
              id           TEXT PRIMARY KEY,
              sessionId    TEXT,
              runId        TEXT,
              action       TEXT NOT NULL,
              application  TEXT,
              window       TEXT,
              target       TEXT,
              method       TEXT,
              confidence   REAL,
              deliveryMode TEXT,
              risk         TEXT,
              result       TEXT,
              verification TEXT,
              verdict      TEXT,
              createdAt    TEXT NOT NULL
            )
            """
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_computer_action_session ON ComputerAction(sessionId, createdAt)")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS ComputerTrace (
              id           TEXT PRIMARY KEY,
              sessionId    TEXT,
              runId        TEXT,
              status       TEXT NOT NULL,
              createdAt    TEXT NOT NULL,
              finishedAt   TEXT,
              stepsJson    TEXT,
              summaryJson  TEXT
            )
            """
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_computer_trace_session ON ComputerTrace(sessionId, createdAt)")
        self._db.commit()

    # -- sessions ------------------------------------------------------------

    def save_session(self, record: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO ComputerSession
               (id, agentId, taskId, runId, userId, machineId, driver, displayState,
                activeApp, windowCount, riskMode, status, state, createdAt,
                lastActivity, terminatedAt, metadataJson)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 displayState=excluded.displayState, activeApp=excluded.activeApp,
                 windowCount=excluded.windowCount, riskMode=excluded.riskMode,
                 status=excluded.status, state=excluded.state,
                 lastActivity=excluded.lastActivity, terminatedAt=excluded.terminatedAt,
                 metadataJson=excluded.metadataJson""",
            (
                record.get("id"), record.get("agentId"), record.get("taskId"),
                record.get("runId"), record.get("userId"), record.get("machineId"),
                record.get("driver", ""), record.get("displayState"), record.get("activeApp"),
                int(record.get("windowCount", 0)), record.get("riskMode"),
                record.get("status", "READY"), record.get("state"),
                record.get("createdAt", now_iso()), record.get("lastActivity"),
                record.get("terminatedAt"),
                json.dumps(record.get("metadata") or {}, default=str),
            ),
        )
        self._db.commit()

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM ComputerSession WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return None
        data = _row(row)
        data["metadata"] = json.loads(data.get("metadataJson") or "{}")
        return data

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM ComputerSession ORDER BY createdAt DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
        result = []
        for row in rows:
            data = _row(row)
            data["metadata"] = json.loads(data.get("metadataJson") or "{}")
            result.append(data)
        return result

    # -- actions (the audit journal) -----------------------------------------

    def save_action(self, record: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO ComputerAction
               (id, sessionId, runId, action, application, window, target, method,
                confidence, deliveryMode, risk, result, verification, verdict, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("id", uuid.uuid4().hex), record.get("sessionId"), record.get("runId"),
                record.get("action", ""), record.get("application"), record.get("window"),
                record.get("target"), record.get("method"), record.get("confidence"),
                record.get("deliveryMode"), record.get("risk"), record.get("result"),
                record.get("verification"), record.get("verdict"),
                record.get("createdAt", now_iso()),
            ),
        )
        self._db.commit()

    def list_actions(self, session_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if session_id:
            rows = self._db.execute(
                "SELECT * FROM ComputerAction WHERE sessionId=? ORDER BY createdAt DESC LIMIT ?",
                (session_id, max(1, min(limit, 1000))),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM ComputerAction ORDER BY createdAt DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- traces --------------------------------------------------------------

    def save_trace(self, record: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO ComputerTrace
               (id, sessionId, runId, status, createdAt, finishedAt, stepsJson, summaryJson)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 status=excluded.status, finishedAt=excluded.finishedAt,
                 stepsJson=excluded.stepsJson, summaryJson=excluded.summaryJson""",
            (
                record.get("id", new_trace_id()), record.get("sessionId"), record.get("runId"),
                record.get("status", "open"), record.get("createdAt", now_iso()),
                record.get("finishedAt"),
                json.dumps(record.get("steps") or [], default=str),
                json.dumps(record.get("summary") or {}, default=str),
            ),
        )
        self._db.commit()

    def get_trace(self, trace_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM ComputerTrace WHERE id=?", (trace_id,)).fetchone()
        if row is None:
            return None
        data = _row(row)
        data["steps"] = json.loads(data.pop("stepsJson") or "[]")
        data["summary"] = json.loads(data.pop("summaryJson") or "{}")
        return data

    def list_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT id, sessionId, runId, status, createdAt, finishedAt FROM ComputerTrace "
            "ORDER BY createdAt DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
        return [dict(r) for r in rows]


__all__ = ["ComputerStore", "new_session_id", "new_trace_id"]

"""Terminal persistence — bound to the ONE agent-memory connection.

Owns the `TerminalSession`, `ProcessRecord` and `TerminalCommand` tables, exactly
as `run_lineage.py` and `code/store.py` own theirs: same database
(`agent-memory.db`), same connection, idempotent DDL, never the ratcheted
`persistence.py`. NEVER `eclipse-memory.db` and NEVER `jdds.db`.

Only metadata and cursors are persisted. Process OUTPUT is not written here — it
lives in the bounded in-memory ring buffer; only the last-N tail needed for a
post-crash inspection is captured at exit by the caller. This keeps the relational
tables small, which §66 requires.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import now_iso


def _row(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _loads(value: Any) -> Any:
    try:
        return json.loads(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


class TerminalStore:
    """Rows describing terminal sessions, processes and command history."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS TerminalSession (
              id          TEXT PRIMARY KEY,
              runtime     TEXT NOT NULL,
              shell       TEXT NOT NULL,
              pid         INTEGER,
              cwd         TEXT NOT NULL,
              status      TEXT NOT NULL,
              rows        INTEGER NOT NULL DEFAULT 24,
              columns     INTEGER NOT NULL DEFAULT 80,
              envProfile  TEXT NOT NULL DEFAULT '{}',
              workspaceId TEXT,
              agentId     TEXT,
              owner       TEXT,
              pty         INTEGER NOT NULL DEFAULT 0,
              createdAt   TEXT NOT NULL,
              updatedAt   TEXT NOT NULL,
              closedAt    TEXT
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_term_session_written ON TerminalSession(updatedAt)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS ProcessRecord (
              id          TEXT PRIMARY KEY,
              pid         INTEGER,
              parentPid   INTEGER,
              command     TEXT NOT NULL,
              cwd         TEXT NOT NULL,
              runtime     TEXT NOT NULL,
              shell       TEXT NOT NULL,
              state       TEXT NOT NULL,
              exitCode    INTEGER,
              ports       TEXT NOT NULL DEFAULT '[]',
              workspaceId TEXT,
              agentId     TEXT,
              runId       TEXT,
              taskId      TEXT,
              purpose     TEXT,
              createdAt   TEXT NOT NULL,
              updatedAt   TEXT NOT NULL,
              startedAt   TEXT,
              exitAt      TEXT
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_term_process_written ON ProcessRecord(updatedAt)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_term_process_run ON ProcessRecord(runId)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS TerminalCommand (
              id          TEXT PRIMARY KEY,
              sessionId   TEXT,
              processId   TEXT,
              command     TEXT NOT NULL,
              cwd         TEXT NOT NULL,
              runtime     TEXT NOT NULL,
              shell       TEXT,
              exitCode    INTEGER,
              status      TEXT NOT NULL,
              durationMs  INTEGER NOT NULL DEFAULT 0,
              agentId     TEXT,
              runId       TEXT,
              taskId      TEXT,
              purpose     TEXT,
              createdAt   TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_term_command_written ON TerminalCommand(createdAt)"
        )
        self._db.commit()

    # ── Sessions ───────────────────────────────────────────────────────────────

    def save_session(self, row: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO TerminalSession
               (id, runtime, shell, pid, cwd, status, rows, columns, envProfile,
                workspaceId, agentId, owner, pty, createdAt, updatedAt, closedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["sessionId"], row["runtime"], row["shell"], row.get("pid"),
                row["cwd"], row["status"], int(row.get("rows", 24)), int(row.get("columns", 80)),
                json.dumps(row.get("envProfile", {})),
                row.get("workspaceId"), row.get("agentId"), row.get("owner"),
                1 if row.get("pty") else 0, row["createdAt"], row["updatedAt"], row.get("closedAt"),
            ),
        )
        self._db.commit()

    def update_session(self, session_id: str, **fields: Any) -> None:
        sets, params = _assignments(fields)
        if not sets:
            return
        params.append(session_id)
        self._db.execute(f"UPDATE TerminalSession SET {', '.join(sets)} WHERE id = ?", tuple(params))
        self._db.commit()

    def mark_session_closed(self, session_id: str) -> None:
        self.update_session(session_id, status="closed", closedAt=now_iso(), updatedAt=now_iso())

    def list_sessions(self, *, workspace_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if workspace_id is not None:
            rows = self._db.execute(
                "SELECT * FROM TerminalSession WHERE workspaceId=? ORDER BY updatedAt DESC LIMIT ?",
                (workspace_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM TerminalSession ORDER BY updatedAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_session_row(r) for r in rows]

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM TerminalSession WHERE id=?", (session_id,)).fetchone()
        return _session_row(row) if row else None

    # ── Processes ──────────────────────────────────────────────────────────────

    def upsert_process(self, row: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO ProcessRecord
               (id, pid, parentPid, command, cwd, runtime, shell, state, exitCode,
                ports, workspaceId, agentId, runId, taskId, purpose, createdAt,
                updatedAt, startedAt, exitAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["processId"], row.get("pid"), row.get("parentPid"), row["command"],
                row["cwd"], row["runtime"], row["shell"], row["state"], row.get("exitCode"),
                json.dumps(row.get("ports", [])), row.get("workspaceId"), row.get("agentId"),
                row.get("runId"), row.get("taskId"), row.get("purpose"), row["createdAt"],
                row["updatedAt"], row.get("startedAt"), row.get("exitAt"),
            ),
        )
        self._db.commit()

    def list_processes(self, *, run_id: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        if run_id is not None:
            rows = self._db.execute(
                "SELECT * FROM ProcessRecord WHERE runId=? ORDER BY createdAt DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM ProcessRecord ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_process_row(r) for r in rows]

    def get_process(self, process_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM ProcessRecord WHERE id=?", (process_id,)).fetchone()
        return _process_row(row) if row else None

    def list_alive_processes(self) -> list[dict[str, Any]]:
        """Processes last seen RUNNING/STARTING/STOPPING — the recovery candidates."""
        rows = self._db.execute(
            "SELECT * FROM ProcessRecord WHERE state IN ('CREATED','STARTING','RUNNING','STOPPING','PAUSED')"
        ).fetchall()
        return [_process_row(r) for r in rows]

    def mark_process_reconciled(self, process_id: str, state: str, *, exit_code: Optional[int] = None) -> None:
        self._db.execute(
            "UPDATE ProcessRecord SET state=?, exitCode=?, exitAt=?, updatedAt=? WHERE id=?",
            (state, exit_code, now_iso(), now_iso(), process_id),
        )
        self._db.commit()

    # ── Command history ───────────────────────────────────────────────────────

    def record_command(self, row: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO TerminalCommand
               (id, sessionId, processId, command, cwd, runtime, shell, exitCode,
                status, durationMs, agentId, runId, taskId, purpose, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["id"], row.get("sessionId"), row.get("processId"), row["command"],
                row["cwd"], row["runtime"], row.get("shell"), row.get("exitCode"),
                row["status"], int(row.get("durationMs", 0)), row.get("agentId"),
                row.get("runId"), row.get("taskId"), row.get("purpose"), row["createdAt"],
            ),
        )
        self._db.commit()

    def list_commands(
        self, *, run_id: Optional[str] = None, session_id: Optional[str] = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        clauses: list[str] = []
        params: list[Any] = []
        if run_id is not None:
            clauses.append("runId = ?")
            params.append(run_id)
        if session_id is not None:
            clauses.append("sessionId = ?")
            params.append(session_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._db.execute(
            f"SELECT * FROM TerminalCommand{where} ORDER BY createdAt DESC LIMIT ?", tuple(params)
        ).fetchall()
        return [_command_row(r) for r in rows]


def _assignments(fields: dict[str, Any]) -> tuple[list[str], list[Any]]:
    sets: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if value is None:
            continue
        sets.append(f"{key} = ?")
        params.append(value)
    return sets, params


def _session_row(row: Any) -> dict[str, Any]:
    data = _row(row)
    data["envProfile"] = _loads(data.get("envProfile")) or {}
    data["pty"] = bool(data.get("pty"))
    return data


def _process_row(row: Any) -> dict[str, Any]:
    data = _row(row)
    data["ports"] = _loads(data.get("ports")) or []
    return data


def _command_row(row: Any) -> dict[str, Any]:
    return _row(row)


__all__ = ["TerminalStore"]

"""Execution history — bounded rows on the ONE agent-memory connection.

Owns the execution tables the capability contract names (executions, logs,
artifacts, tests, diagnostics, metrics). It mirrors `terminal/store.py` and
`code/store.py`: idempotent `CREATE TABLE IF NOT EXISTS`, bound to the shared
`AgentMemoryStore._db`, and it NEVER touches `eclipse-memory.db` or `jdds.db`.

Output is stored bounded (a single cap per stream) so a runaway program cannot
grow the database without limit. The structured evidence — exit code, status,
tests, diagnostics, artifacts, metrics — is what an agent reads back.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import now_iso

MAX_STORED_OUTPUT = 100_000


def _row(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


class ExecutionStore:
    """Rows describing executions and their evidence."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS Execution (
              id             TEXT PRIMARY KEY,
              runId          TEXT,
              agentId        TEXT,
              workspaceId    TEXT,
              language       TEXT NOT NULL,
              runtime        TEXT,
              mode           TEXT NOT NULL,
              status         TEXT NOT NULL,
              exitCode       INTEGER,
              durationMs     INTEGER NOT NULL DEFAULT 0,
              errorClass     TEXT,
              errorCode      TEXT,
              networkPolicy  TEXT,
              filesystemPolicy TEXT,
              risk           TEXT,
              stdout         TEXT NOT NULL DEFAULT '',
              stderr         TEXT NOT NULL DEFAULT '',
              truncated      INTEGER NOT NULL DEFAULT 0,
              context        TEXT,
              reproducible   TEXT,
              createdAt      TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_run ON Execution(runId, createdAt)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_execution_written ON Execution(createdAt)"
        )
        for table, ddl in (
            ("ExecutionArtifact",
             """CREATE TABLE IF NOT EXISTS ExecutionArtifact (
                  id TEXT PRIMARY KEY, executionId TEXT NOT NULL, path TEXT NOT NULL,
                  type TEXT, size INTEGER DEFAULT 0, hash TEXT, createdAt TEXT NOT NULL)"""),
            ("ExecutionTest",
             """CREATE TABLE IF NOT EXISTS ExecutionTest (
                  id TEXT PRIMARY KEY, executionId TEXT NOT NULL, suite TEXT, test TEXT,
                  status TEXT NOT NULL, durationMs INTEGER DEFAULT 0, error TEXT,
                  file TEXT, line INTEGER DEFAULT 0, createdAt TEXT NOT NULL)"""),
            ("ExecutionDiagnostic",
             """CREATE TABLE IF NOT EXISTS ExecutionDiagnostic (
                  id TEXT PRIMARY KEY, executionId TEXT NOT NULL, file TEXT, line INTEGER DEFAULT 0,
                  column INTEGER DEFAULT 0, severity TEXT, category TEXT, message TEXT,
                  source TEXT, createdAt TEXT NOT NULL)"""),
            ("ExecutionMetric",
             """CREATE TABLE IF NOT EXISTS ExecutionMetric (
                  id TEXT PRIMARY KEY, executionId TEXT NOT NULL, name TEXT NOT NULL,
                  value REAL, unit TEXT, createdAt TEXT NOT NULL)"""),
        ):
            self._db.execute(ddl)
            self._db.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table.lower()}_exec ON {table}(executionId)"
            )
        self._db.commit()

    # ── Writes ───────────────────────────────────────────────────────────────

    def save_execution(self, result: Any, *, run_id: str = "", agent_id: Optional[str] = None) -> dict[str, Any]:
        """Persist one `ExecutionResult` and its evidence. Returns the row dict."""
        context = result.context or {}
        record = {
            "id": result.execution_id,
            "runId": run_id or context.get("runId"),
            "agentId": agent_id or context.get("agentId"),
            "workspaceId": context.get("workspaceId"),
            "language": result.language,
            "runtime": result.runtime,
            "mode": (result.metadata or {}).get("mode") or context.get("mode") or "RUN",
            "status": result.status,
            "exitCode": result.exit_code,
            "durationMs": int(result.duration_ms or 0),
            "errorClass": result.error_class,
            "errorCode": (result.error or {}).get("code"),
            "networkPolicy": context.get("networkPolicy"),
            "filesystemPolicy": context.get("filesystemPolicy"),
            "risk": (result.metadata or {}).get("risk"),
            "stdout": _bound(result.stdout),
            "stderr": _bound(result.stderr),
            "truncated": 1 if result.truncated else 0,
            "context": _json(context),
            "reproducible": _json(context.get("reproducible")),
            "createdAt": now_iso(),
        }
        self._db.execute(
            """INSERT OR REPLACE INTO Execution
               (id, runId, agentId, workspaceId, language, runtime, mode, status, exitCode,
                durationMs, errorClass, errorCode, networkPolicy, filesystemPolicy, risk,
                stdout, stderr, truncated, context, reproducible, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(record.values()),
        )
        self._db.commit()
        self._save_children(result)
        return record

    def _save_children(self, result: Any) -> None:
        created = now_iso()
        import uuid

        try:
            self._db.execute("DELETE FROM ExecutionArtifact WHERE executionId=?", (result.execution_id,))
            for artifact in result.artifacts:
                self._db.execute(
                    "INSERT INTO ExecutionArtifact (id, executionId, path, type, size, hash, createdAt) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("art_" + uuid.uuid4().hex[:12], result.execution_id, artifact.path,
                     artifact.type, artifact.size, artifact.hash, created),
                )
            self._db.execute("DELETE FROM ExecutionTest WHERE executionId=?", (result.execution_id,))
            for test in result.tests:
                self._db.execute(
                    "INSERT INTO ExecutionTest (id, executionId, suite, test, status, durationMs, error, file, line, createdAt) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("tst_" + uuid.uuid4().hex[:12], result.execution_id, test.suite, test.test,
                     test.status, test.duration_ms, test.error[:2000], test.file, test.line, created),
                )
            self._db.execute("DELETE FROM ExecutionDiagnostic WHERE executionId=?", (result.execution_id,))
            for diag in result.diagnostics:
                self._db.execute(
                    "INSERT INTO ExecutionDiagnostic (id, executionId, file, line, column, severity, category, message, source, createdAt) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("dg_" + uuid.uuid4().hex[:12], result.execution_id, diag.file, diag.line,
                     diag.column, diag.severity, diag.category, diag.message[:2000], diag.source, created),
                )
            usage = result.resource_usage
            for name, value, unit in (
                ("cpuMs", usage.cpu_ms, "ms"), ("memoryPeakMb", usage.memory_peak_mb, "mb"),
                ("processCount", usage.process_count, "count"),
                ("stdoutBytes", usage.stdout_bytes, "bytes"),
            ):
                if value is not None:
                    self._db.execute(
                        "INSERT INTO ExecutionMetric (id, executionId, name, value, unit, createdAt) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        ("met_" + uuid.uuid4().hex[:12], result.execution_id, name, float(value), unit, created),
                    )
            self._db.commit()
        except Exception:  # noqa: BLE001 - child rows are additive; never break the call
            pass

    # ── Reads ────────────────────────────────────────────────────────────────

    def get_execution(self, execution_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM Execution WHERE id=?", (execution_id,)).fetchone()
        if row is None:
            return None
        data = _row(row)
        data["artifacts"] = [_row(r) for r in self._db.execute(
            "SELECT * FROM ExecutionArtifact WHERE executionId=?", (execution_id,)).fetchall()]
        data["tests"] = [_row(r) for r in self._db.execute(
            "SELECT * FROM ExecutionTest WHERE executionId=?", (execution_id,)).fetchall()]
        data["diagnostics"] = [_row(r) for r in self._db.execute(
            "SELECT * FROM ExecutionDiagnostic WHERE executionId=?", (execution_id,)).fetchall()]
        data["metrics"] = [_row(r) for r in self._db.execute(
            "SELECT * FROM ExecutionMetric WHERE executionId=?", (execution_id,)).fetchall()]
        return _decode(data)

    def list_executions(self, *, run_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if run_id:
            rows = self._db.execute(
                "SELECT * FROM Execution WHERE runId=? ORDER BY createdAt DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM Execution ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_decode(_row(r)) for r in rows]


def _bound(text: str) -> str:
    text = str(text or "")
    return text if len(text) <= MAX_STORED_OUTPUT else text[:MAX_STORED_OUTPUT] + "\n[TRUNCATED]"


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None


def _decode(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("context", "reproducible"):
        raw = data.get(key)
        if isinstance(raw, str) and raw:
            try:
                data[key] = json.loads(raw)
            except json.JSONDecodeError:
                pass
    return data


__all__ = ["ExecutionStore", "MAX_STORED_OUTPUT"]

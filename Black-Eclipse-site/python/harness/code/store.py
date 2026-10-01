"""Code persistence, bound to the ONE agent-memory connection (Phases 2–3).

Owns the `CodeWorkspace` and `HarnessCommandExecution` tables and their helpers.
Mirrors `run_lineage.py` and `mcp/approvals.py`: the module is bound to the single
`AgentMemoryStore` sqlite connection and owns only its own tables, so
`persistence.py` — pinned at its size ratchet — does not grow.

The database is `agent-memory.db` (the runtime's own). NEVER `eclipse-memory.db`
and NEVER `jdds.db`. The DDL is idempotent (`CREATE TABLE IF NOT EXISTS`) and is
applied on first use, exactly like `run_lineage.py`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..persistence import now_iso


def _row(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


class CodeWorkspaceStore:
    """Rows describing disposable code workspaces (allocation → release)."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        # Phase 4: the additive `HarnessRun.codeVerification` column. It is added
        # HERE (not in the ratcheted persistence.py) exactly as run_lineage.py owns
        # its own additive columns — same database, same connection, idempotent.
        try:
            existing = {
                row["name"] for row in self._db.execute("PRAGMA table_info(HarnessRun)").fetchall()
            }
            if "codeVerification" not in existing:
                self._db.execute("ALTER TABLE HarnessRun ADD COLUMN codeVerification TEXT")
        except Exception:  # noqa: BLE001 - a missing table just means no column to add
            pass
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS CodeWorkspace (
              id           TEXT PRIMARY KEY,
              root         TEXT NOT NULL,
              baseRevision TEXT NOT NULL,
              strategy     TEXT NOT NULL,
              createdAt    TEXT NOT NULL,
              releasedAt   TEXT,
              diffDigest   TEXT,
              runId        TEXT,
              fileCount    INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Phase 11 (additive, old-row-safe): the caller-supplied scope FILTER label.
        # A workspace is not enumerable across scopes. It NEVER authorizes anything.
        ws_cols = {r["name"] for r in self._db.execute("PRAGMA table_info(CodeWorkspace)").fetchall()}
        if "scopeId" not in ws_cols:
            self._db.execute("ALTER TABLE CodeWorkspace ADD COLUMN scopeId TEXT")
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_code_workspace_created ON CodeWorkspace(createdAt)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_code_workspace_run ON CodeWorkspace(runId)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS HarnessCommandExecution (
              id             TEXT PRIMARY KEY,
              runId          TEXT NOT NULL,
              stepIndex      INTEGER,
              toolCallId     TEXT,
              commandClass   TEXT NOT NULL,
              argv           TEXT NOT NULL,
              cwd            TEXT NOT NULL,
              exitCode       INTEGER,
              durationMs     INTEGER NOT NULL,
              timedOut       INTEGER NOT NULL DEFAULT 0,
              output         TEXT NOT NULL,
              truncated      INTEGER NOT NULL DEFAULT 0,
              totalChars     INTEGER NOT NULL,
              sandboxBackend TEXT NOT NULL,
              network        INTEGER NOT NULL DEFAULT 0,
              policyDecision TEXT NOT NULL,
              createdAt      TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_cmd_run ON HarnessCommandExecution(runId, createdAt)"
        )
        self._db.commit()

    # ── Writes ───────────────────────────────────────────────────────────────
    def save_workspace(
        self,
        workspace_id: str,
        root: str,
        base_revision: str,
        strategy: str,
        *,
        run_id: Optional[str] = None,
        file_count: int = 0,
        created_at: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> dict[str, Any]:
        record = {
            "id": workspace_id,
            "root": root,
            "baseRevision": base_revision,
            "strategy": strategy,
            "createdAt": created_at or now_iso(),
            "releasedAt": None,
            "diffDigest": None,
            "runId": run_id,
            "fileCount": int(file_count),
            "scopeId": scope_id,
        }
        self._db.execute(
            """INSERT OR REPLACE INTO CodeWorkspace
               (id, root, baseRevision, strategy, createdAt, releasedAt, diffDigest, runId,
                fileCount, scopeId)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"], record["root"], record["baseRevision"], record["strategy"],
                record["createdAt"], record["releasedAt"], record["diffDigest"],
                record["runId"], record["fileCount"], record["scopeId"],
            ),
        )
        self._db.commit()
        return record

    def mark_released(self, workspace_id: str) -> None:
        self._db.execute(
            "UPDATE CodeWorkspace SET releasedAt=? WHERE id=?",
            (now_iso(), workspace_id),
        )
        self._db.commit()

    def set_diff_digest(self, workspace_id: str, digest: str) -> None:
        self._db.execute(
            "UPDATE CodeWorkspace SET diffDigest=? WHERE id=?",
            (digest, workspace_id),
        )
        self._db.commit()

    # ── Reads ────────────────────────────────────────────────────────────────
    def get_workspace(
        self, workspace_id: str, *, scope_id: Optional[str] = None
    ) -> Optional[dict[str, Any]]:
        """One workspace, or None. A `scope_id` mismatch reads as not found.

        The scope label is a FILTER: a read of another scope's workspace returns
        nothing (and the route refuses it) — it never escalates access.
        """
        if scope_id is None:
            row = self._db.execute(
                "SELECT * FROM CodeWorkspace WHERE id=?", (workspace_id,)
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT * FROM CodeWorkspace WHERE id=? AND scopeId=?",
                (workspace_id, scope_id),
            ).fetchone()
        return _row(row) if row else None

    def list_workspaces(
        self, *, run_id: Optional[str] = None, limit: int = 100,
        scope_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List workspaces, optionally narrowed by a caller-supplied scope label.

        A `scope_id` narrows what is returned; it NEVER authorizes a mutation.
        """
        limit = max(1, min(int(limit), 500))
        clauses: list[str] = []
        params: list[Any] = []
        if run_id:
            clauses.append("runId = ?")
            params.append(run_id)
        if scope_id is not None:
            clauses.append("scopeId = ?")
            params.append(scope_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._db.execute(
            f"SELECT * FROM CodeWorkspace{where} ORDER BY createdAt DESC LIMIT ?", tuple(params)
        ).fetchall()
        return [_row(r) for r in rows]

    # ── Command executions (Phase 3) ─────────────────────────────────────────
    def record_command_execution(
        self,
        *,
        run_id: str,
        command_class: str,
        argv: list[str],
        cwd: str,
        exit_code: Optional[int],
        duration_ms: int,
        output: str,
        total_chars: int,
        sandbox_backend: str,
        policy_decision: dict[str, Any],
        timed_out: bool = False,
        truncated: bool = False,
        network: bool = False,
        step_index: Optional[int] = None,
        tool_call_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record one command execution. `argv` carries NO secret (env is scrubbed)."""
        record = {
            "id": "cmd_" + uuid.uuid4().hex[:16],
            "runId": run_id,
            "stepIndex": step_index,
            "toolCallId": tool_call_id,
            "commandClass": command_class,
            "argv": json.dumps(list(argv), ensure_ascii=False),
            "cwd": str(cwd),
            "exitCode": exit_code,
            "durationMs": int(duration_ms),
            "timedOut": 1 if timed_out else 0,
            "output": str(output)[:60_000],
            "truncated": 1 if truncated else 0,
            "totalChars": int(total_chars),
            "sandboxBackend": sandbox_backend,
            "network": 1 if network else 0,
            "policyDecision": json.dumps(policy_decision or {}, ensure_ascii=False),
            "createdAt": now_iso(),
        }
        self._db.execute(
            """INSERT INTO HarnessCommandExecution
               (id, runId, stepIndex, toolCallId, commandClass, argv, cwd, exitCode,
                durationMs, timedOut, output, truncated, totalChars, sandboxBackend,
                network, policyDecision, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"], record["runId"], record["stepIndex"], record["toolCallId"],
                record["commandClass"], record["argv"], record["cwd"], record["exitCode"],
                record["durationMs"], record["timedOut"], record["output"], record["truncated"],
                record["totalChars"], record["sandboxBackend"], record["network"],
                record["policyDecision"], record["createdAt"],
            ),
        )
        self._db.commit()
        return record

    def list_command_executions(self, run_id: str, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        rows = self._db.execute(
            "SELECT * FROM HarnessCommandExecution WHERE runId=? ORDER BY createdAt ASC LIMIT ?",
            (run_id, limit),
        ).fetchall()
        return [_row(r) for r in rows]


__all__ = ["CodeWorkspaceStore"]

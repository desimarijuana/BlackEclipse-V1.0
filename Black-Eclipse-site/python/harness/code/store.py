"""Code-workspace persistence, bound to the ONE agent-memory connection (Phase 2).

Owns the `CodeWorkspace` table and its helpers. Mirrors `run_lineage.py` and
`mcp/approvals.py`: the module is bound to the single `AgentMemoryStore` sqlite
connection and owns only its own table, so `persistence.py` — pinned at its size
ratchet — does not grow.

The database is `agent-memory.db` (the runtime's own). NEVER `eclipse-memory.db`
and NEVER `jdds.db`. The DDL is idempotent (`CREATE TABLE IF NOT EXISTS`) and is
applied on first use, exactly like `run_lineage.py`.
"""

from __future__ import annotations

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
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_code_workspace_created ON CodeWorkspace(createdAt)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_code_workspace_run ON CodeWorkspace(runId)"
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
        }
        self._db.execute(
            """INSERT OR REPLACE INTO CodeWorkspace
               (id, root, baseRevision, strategy, createdAt, releasedAt, diffDigest, runId, fileCount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["id"], record["root"], record["baseRevision"], record["strategy"],
                record["createdAt"], record["releasedAt"], record["diffDigest"],
                record["runId"], record["fileCount"],
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
    def get_workspace(self, workspace_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM CodeWorkspace WHERE id=?", (workspace_id,)
        ).fetchone()
        return _row(row) if row else None

    def list_workspaces(self, *, run_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if run_id:
            rows = self._db.execute(
                "SELECT * FROM CodeWorkspace WHERE runId=? ORDER BY createdAt DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM CodeWorkspace ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row(r) for r in rows]


__all__ = ["CodeWorkspaceStore"]

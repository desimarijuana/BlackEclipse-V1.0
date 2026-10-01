"""Workflow definition persistence (Harness closeout Phase 5).

Workflows + their versions are persisted in `agent-memory.db` (the runtime's own
database), bound to the ONE store connection — same pattern as
`mcp/approvals.py`. Definitions are stored as bounded JSON; a definition is
validated BEFORE it is stored.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .model import Workflow
from .validate import validate_workflow

log = logging.getLogger("harness.workflows.store")


class WorkflowStore:
    """Persist workflow definitions + versions over the ONE agent-memory store."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS WorkflowDefinition (
              id          TEXT NOT NULL,
              version     TEXT NOT NULL,
              name        TEXT,
              description TEXT,
              definition  TEXT NOT NULL,
              createdAt   TEXT NOT NULL,
              PRIMARY KEY (id, version)
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_def_id ON WorkflowDefinition(id, createdAt)"
        )
        self._db.commit()

    def save(self, workflow: Workflow, *, known_tools: Optional[list[str]] = None) -> dict[str, Any]:
        """Validate then persist a workflow. Invalid definitions are refused."""
        validate_workflow(workflow, known_tools=known_tools)
        from ..persistence import now_iso

        now = now_iso()
        self._db.execute(
            """INSERT OR REPLACE INTO WorkflowDefinition
               (id, version, name, description, definition, createdAt)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                workflow.id, workflow.version, workflow.name, workflow.description,
                json.dumps(workflow.model_dump()), now,
            ),
        )
        self._db.commit()
        return {"id": workflow.id, "version": workflow.version, "createdAt": now}

    def get(self, workflow_id: str, version: Optional[str] = None) -> Optional[Workflow]:
        if version:
            row = self._db.execute(
                "SELECT definition FROM WorkflowDefinition WHERE id=? AND version=?",
                (workflow_id, version),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT definition FROM WorkflowDefinition WHERE id=? ORDER BY createdAt DESC LIMIT 1",
                (workflow_id,),
            ).fetchone()
        if row is None:
            return None
        return Workflow(**json.loads(row["definition"]))

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        rows = self._db.execute(
            "SELECT id, version, name, description, createdAt FROM WorkflowDefinition "
            "ORDER BY createdAt DESC LIMIT ?", (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, workflow_id: str, version: Optional[str] = None) -> int:
        if version:
            cur = self._db.execute(
                "DELETE FROM WorkflowDefinition WHERE id=? AND version=?", (workflow_id, version)
            )
        else:
            cur = self._db.execute("DELETE FROM WorkflowDefinition WHERE id=?", (workflow_id,))
        self._db.commit()
        return cur.rowcount


__all__ = ["WorkflowStore"]

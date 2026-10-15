"""Durable team-run state on the ONE agent-memory connection.

Team runs are stored as a JSON blob plus queryable columns, exactly like the
automation and A2A stores. No second database, no second connection.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import now_iso
from .model import TeamRun, TeamRunStatus


class TeamStore:
    def __init__(self, memory_store: Any) -> None:
        self._store = memory_store
        self._db = memory_store._db  # noqa: SLF001 - the ONE shared connection
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS TeamRun (
                id          TEXT PRIMARY KEY,
                teamId      TEXT NOT NULL,
                name        TEXT NOT NULL,
                rootRunId   TEXT NOT NULL,
                planId      TEXT,
                status      TEXT NOT NULL,
                record      TEXT NOT NULL,
                createdAt   TEXT NOT NULL,
                updatedAt   TEXT NOT NULL,
                finishedAt  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_teamrun_root ON TeamRun(rootRunId);
            CREATE INDEX IF NOT EXISTS idx_teamrun_status ON TeamRun(status);
            """
        )
        self._db.commit()

    def save_run(self, run: TeamRun) -> TeamRun:
        run.updated_at = now_iso()
        payload = run.model_dump(by_alias=True)
        self._db.execute(
            """
            INSERT INTO TeamRun (id, teamId, name, rootRunId, planId, status, record,
                                 createdAt, updatedAt, finishedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status, planId=excluded.planId, record=excluded.record,
                updatedAt=excluded.updatedAt, finishedAt=excluded.finishedAt
            """,
            (
                run.id, run.team_id, run.name, run.root_run_id, run.plan_id,
                run.status.value if isinstance(run.status, TeamRunStatus) else str(run.status),
                json.dumps(payload), run.created_at, run.updated_at, run.finished_at,
            ),
        )
        self._db.commit()
        return run

    def _row_to_run(self, row: Any) -> Optional[TeamRun]:
        if row is None:
            return None
        try:
            record = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None
        try:
            return TeamRun(**record)
        except Exception:  # noqa: BLE001 - an unreadable row is skipped, never guessed
            return None

    def get_run(self, run_id: str) -> Optional[TeamRun]:
        row = self._db.execute(
            "SELECT record FROM TeamRun WHERE id=?", (run_id,)
        ).fetchone()
        return self._row_to_run(row)

    def list_runs(self, *, limit: int = 100, status: Optional[str] = None) -> list[TeamRun]:
        if status:
            rows = self._db.execute(
                "SELECT record FROM TeamRun WHERE status=? ORDER BY createdAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT record FROM TeamRun ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        out: list[TeamRun] = []
        for row in rows:
            parsed = self._row_to_run(row)
            if parsed is not None:
                out.append(parsed)
        return out


__all__ = ["TeamStore"]

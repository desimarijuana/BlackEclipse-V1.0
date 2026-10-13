"""Durable persistence for learning paths and per-node progress.

Rides the ONE `EclipseMemoryStore` connection to **`eclipse-memory.db`** — the
same rule as the recovery store. A learner's roadmap, node progress and durable
learning preferences are agent memory about the user's learning, so they belong
here, never in `jdds.db` (market data) or `agent-memory.db` (run/event traces).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..eclipse_memory.db import new_id, now_iso

NODE_STATUSES = frozenset({"pending", "in_progress", "completed", "skipped"})
PATH_STATUSES = frozenset({"active", "archived"})


class LearningStore:
    def __init__(self, memory_store: Any) -> None:
        self.memory_store = memory_store
        db = getattr(memory_store, "db", memory_store)
        self._db = db.connection

    # ── paths ──────────────────────────────────────────────────────────────

    def save_path(
        self,
        path_id: str,
        *,
        goal: str,
        payload: dict[str, Any],
        start_level: Optional[str] = None,
        target_competency: Optional[str] = None,
        version: int = 1,
        status: str = "active",
    ) -> dict[str, Any]:
        now = now_iso()
        self._db.execute(
            "INSERT INTO LearningPath "
            "(id, goal, startLevel, targetCompetency, version, status, payload, createdAt, updatedAt, lastAccessedAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (path_id, goal, start_level, target_competency, int(version), status,
             json.dumps(payload, default=str), now, now, now),
        )
        self._db.commit()
        return self.get_path(path_id)  # type: ignore[return-value]

    def update_path(
        self,
        path_id: str,
        *,
        payload: dict[str, Any],
        version: int,
        status: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        now = now_iso()
        if status is not None:
            self._db.execute(
                "UPDATE LearningPath SET payload = ?, version = ?, status = ?, updatedAt = ? WHERE id = ?",
                (json.dumps(payload, default=str), int(version), status, now, path_id),
            )
        else:
            self._db.execute(
                "UPDATE LearningPath SET payload = ?, version = ?, updatedAt = ? WHERE id = ?",
                (json.dumps(payload, default=str), int(version), now, path_id),
            )
        self._db.commit()
        return self.get_path(path_id)

    def get_path(self, path_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT id, goal, startLevel, targetCompetency, version, status, payload, "
            "createdAt, updatedAt, lastAccessedAt FROM LearningPath WHERE id = ?",
            (path_id,),
        ).fetchone()
        return _row(row) if row else None

    def list_paths(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT id, goal, startLevel, targetCompetency, version, status, createdAt, updatedAt, lastAccessedAt "
            "FROM LearningPath ORDER BY updatedAt DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [_row(r) for r in rows]

    def find_active_by_goal(self, goal: str) -> Optional[dict[str, Any]]:
        """Resume lookup: the most recently touched active path for a goal.

        Matching is a normalized substring test in BOTH directions so a returning
        request ("I want to keep learning quant trading") finds the earlier
        roadmap without the user restating it exactly.
        """
        target = (goal or "").strip().lower()
        if not target:
            return None
        row = self._db.execute(
            "SELECT id, goal, startLevel, targetCompetency, version, status, payload "
            "FROM LearningPath WHERE status = 'active' AND (LOWER(goal) LIKE ? OR ? LIKE '%' || LOWER(goal) || '%') "
            "ORDER BY updatedAt DESC LIMIT 1",
            (f"%{target}%", target),
        ).fetchone()
        return _row(row) if row else None

    def touch(self, path_id: str) -> None:
        self._db.execute("UPDATE LearningPath SET lastAccessedAt = ? WHERE id = ?", (now_iso(), path_id))
        self._db.commit()

    def delete_path(self, path_id: str) -> bool:
        cur = self._db.execute("DELETE FROM LearningPath WHERE id = ?", (path_id,))
        self._db.execute("DELETE FROM LearningNodeProgress WHERE pathId = ?", (path_id,))
        self._db.commit()
        return cur.rowcount > 0

    # ── node progress ────────────────────────────────────────────────────────

    def set_node_status(
        self,
        path_id: str,
        node_id: str,
        status: str,
        assessment: Optional[str] = None,
    ) -> dict[str, Any]:
        st = status if status in NODE_STATUSES else "pending"
        now = now_iso()
        row_id = f"{path_id}:{node_id}"
        self._db.execute(
            "INSERT INTO LearningNodeProgress (id, pathId, nodeId, status, assessment, updatedAt) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(pathId, nodeId) DO UPDATE SET status = excluded.status, "
            "assessment = excluded.assessment, updatedAt = excluded.updatedAt",
            (row_id, path_id, node_id, st, assessment, now),
        )
        self._db.commit()
        return {"pathId": path_id, "nodeId": node_id, "status": st, "assessment": assessment, "updatedAt": now}

    def list_node_progress(self, path_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT pathId, nodeId, status, assessment, updatedAt FROM LearningNodeProgress WHERE pathId = ?",
            (path_id,),
        ).fetchall()
        return [_row(r) for r in rows]

    # ── durable preferences ──────────────────────────────────────────────────

    def set_preference(self, key: str, value: str) -> dict[str, Any]:
        now = now_iso()
        self._db.execute(
            "INSERT INTO LearningPreference (key, value, updatedAt) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updatedAt = excluded.updatedAt",
            (key, value, now),
        )
        self._db.commit()
        return {"key": key, "value": value, "updatedAt": now}

    def get_preference(self, key: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT key, value, updatedAt FROM LearningPreference WHERE key = ?", (key,)
        ).fetchone()
        return _row(row) if row else None

    def list_preferences(self) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT key, value, updatedAt FROM LearningPreference ORDER BY key").fetchall()
        return [_row(r) for r in rows]


def _row(row: Any) -> dict[str, Any]:
    out = dict(row)
    payload = out.get("payload")
    if isinstance(payload, str):
        try:
            out["payload"] = json.loads(payload)
        except (ValueError, TypeError):
            out["payload"] = None
    return out


__all__ = ["LearningStore", "NODE_STATUSES", "PATH_STATUSES"]

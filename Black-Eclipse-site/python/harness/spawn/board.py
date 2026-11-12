"""The shared blackboard: durable facts a spawned tree can read (C5).

One board per ROOT run. A child reaches it by walking its `parentRunId` chain, so
no child can read another tree's board. Writes are bounded (entries + chars);
an over-full board refuses the write instead of silently dropping history.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from ..migrations import Migration, MigrationRunner
from ..persistence import now_iso

MAX_BOARD_ENTRIES = 200
MAX_BOARD_CHARS = 200_000
MAX_ENTRY_TEXT = 8_000
BOARD_KINDS = frozenset({"fact", "artifact", "evidence", "question", "decision", "note"})

BOARD_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        id="2026-11-11-006-blackboard",
        description="Shared spawn blackboard (one board per root run)",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS Board (
              id         TEXT PRIMARY KEY,
              rootRunId  TEXT NOT NULL UNIQUE,
              scope      TEXT NOT NULL,
              maxEntries INTEGER NOT NULL,
              maxChars   INTEGER NOT NULL,
              createdAt  TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS BoardEntry (
              id        TEXT PRIMARY KEY,
              boardId   TEXT NOT NULL,
              runId     TEXT NOT NULL,
              kind      TEXT NOT NULL,
              text      TEXT NOT NULL,
              handles   TEXT,
              digest    TEXT NOT NULL,
              status    TEXT NOT NULL,
              author    TEXT,
              createdAt TEXT NOT NULL,
              FOREIGN KEY (boardId) REFERENCES Board(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_board_entry_board ON BoardEntry(boardId, createdAt)",
        ),
    ),
)


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _json(value: Any) -> str:
    return json.dumps(value or [], ensure_ascii=False, default=str)


def _load(value: Any) -> list[Any]:
    try:
        loaded = json.loads(value) if value else []
        return loaded if isinstance(loaded, list) else []
    except (TypeError, ValueError):
        return []


class BoardStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._db = getattr(store, "_db", store)
        MigrationRunner(self._db, "agent-memory").apply(BOARD_MIGRATIONS)

    def root_of(self, run_id: str, *, max_depth: int = 20) -> str:
        current = str(run_id or "")
        visited: set[str] = set()
        for _ in range(max_depth):
            if not current or current in visited:
                break
            visited.add(current)
            row = self._db.execute(
                "SELECT parentRunId FROM HarnessRun WHERE id=?", (current,),
            ).fetchone()
            if row is None or not row["parentRunId"]:
                break
            current = row["parentRunId"]
        return current

    def ensure_board(
        self, root_run_id: str, *, scope: str = "shared",
    ) -> dict[str, Any]:
        root = self.root_of(root_run_id)
        row = self._db.execute(
            "SELECT * FROM Board WHERE rootRunId=?", (root,),
        ).fetchone()
        if row is not None:
            return dict(row)
        board_id = _uid("board")
        self._db.execute(
            "INSERT INTO Board (id, rootRunId, scope, maxEntries, maxChars, createdAt) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (board_id, root, scope, MAX_BOARD_ENTRIES, MAX_BOARD_CHARS, now_iso()),
        )
        return {
            "id": board_id, "rootRunId": root, "scope": scope,
            "maxEntries": MAX_BOARD_ENTRIES, "maxChars": MAX_BOARD_CHARS,
        }

    def write(
        self, *, run_id: str, kind: str, text: str,
        handles: Optional[list[dict[str, Any]]] = None,
        status: str = "supported", author: str = "",
    ) -> dict[str, Any]:
        if kind not in BOARD_KINDS:
            raise ValueError(f"unknown board kind {kind!r}")
        clean = " ".join(str(text or "").split())[:MAX_ENTRY_TEXT]
        if not clean:
            raise ValueError("empty board entry")
        board = self.ensure_board(run_id)
        count_row = self._db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(text)), 0) AS c "
            "FROM BoardEntry WHERE boardId=?",
            (board["id"],),
        ).fetchone()
        if int(count_row["n"]) >= int(board["maxEntries"]):
            raise ValueError("the board is full (entry cap)")
        if int(count_row["c"]) + len(clean) > int(board["maxChars"]):
            raise ValueError("the board is full (character cap)")
        digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        entry = {
            "id": _uid("bentry"), "boardId": board["id"], "runId": run_id,
            "kind": kind, "text": clean, "handles": list(handles or [])[:16],
            "digest": digest, "status": status, "author": author,
            "createdAt": now_iso(),
        }
        self._db.execute(
            "INSERT INTO BoardEntry "
            "(id, boardId, runId, kind, text, handles, digest, status, author, createdAt) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry["id"], board["id"], run_id, kind, clean,
                _json(entry["handles"]), digest, status, author, entry["createdAt"],
            ),
        )
        return entry

    def _rows(self, run_id: str, *, kind: Optional[str], limit: int) -> list[Any]:
        board = self.ensure_board(run_id)
        sql = "SELECT * FROM BoardEntry WHERE boardId=?"
        params: list[Any] = [board["id"]]
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY createdAt ASC LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        return self._db.execute(sql, params).fetchall()

    def read(self, run_id: str, *, kind: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        return [self._entry(row) for row in self._rows(run_id, kind=kind, limit=limit)]

    def search(self, run_id: str, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        needle = str(query or "").strip().lower()
        if not needle:
            return []
        rows = self._rows(run_id, kind=None, limit=200)
        return [
            self._entry(row) for row in rows
            if needle in str(row["text"]).lower()
        ][:max(1, min(int(limit), 50))]

    def summary(self, run_id: str) -> dict[str, Any]:
        board = self.ensure_board(run_id)
        row = self._db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(text)), 0) AS c "
            "FROM BoardEntry WHERE boardId=?",
            (board["id"],),
        ).fetchone()
        return {"boardId": board["id"], "rootRunId": board["rootRunId"],
                "entries": int(row["n"]), "chars": int(row["c"])}

    @staticmethod
    def _entry(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"], "runId": row["runId"], "kind": row["kind"],
            "text": row["text"], "handles": _load(row["handles"]),
            "digest": row["digest"], "status": row["status"],
            "author": row["author"], "createdAt": row["createdAt"],
        }


__all__ = [
    "BOARD_KINDS",
    "MAX_BOARD_CHARS",
    "MAX_BOARD_ENTRIES",
    "MAX_ENTRY_TEXT",
    "BoardStore",
]

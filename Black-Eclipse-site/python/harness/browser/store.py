"""Browser persistence, bound to the ONE agent-memory connection.

Owns the browser metadata tables and their helpers. Mirrors `run_lineage.py`,
`code/store.py`, `jobs/store.py` and `mcp/approvals.py`: the module is bound to
the single `AgentMemoryStore` sqlite connection and owns only its own tables, so
`persistence.py` — pinned at its size ratchet — does not grow.

The database is `agent-memory.db` (the runtime's own). NEVER `eclipse-memory.db`
and NEVER `jdds.db`. The DDL is idempotent (`CREATE TABLE IF NOT EXISTS`).

NO plaintext secret is ever stored here. The vault table holds credential
REFERENCES and content-free metadata only.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..persistence import now_iso


def _row(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def new_session_id() -> str:
    return "bsess_" + uuid.uuid4().hex[:16]


def new_trace_id() -> str:
    return "btrace_" + uuid.uuid4().hex[:16]


def new_profile_id() -> str:
    return "bprof_" + uuid.uuid4().hex[:12]


class BrowserStore:
    """Rows describing browser sessions, profiles, traces, downloads and vault
    metadata (all content-free)."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS BrowserSession (
              id           TEXT PRIMARY KEY,
              agentId      TEXT,
              taskId       TEXT,
              runId        TEXT,
              profileId    TEXT,
              provider     TEXT NOT NULL,
              backend      TEXT,
              browserType  TEXT,
              contextId    TEXT,
              status       TEXT NOT NULL,
              state        TEXT,
              createdAt    TEXT NOT NULL,
              lastActivity TEXT,
              terminatedAt TEXT,
              tabCount     INTEGER NOT NULL DEFAULT 0,
              metadataJson TEXT
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_browser_session_created ON BrowserSession(createdAt)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_browser_session_status ON BrowserSession(status, lastActivity)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS BrowserProfile (
              id           TEXT PRIMARY KEY,
              name         TEXT NOT NULL,
              path         TEXT NOT NULL,
              persistent   INTEGER NOT NULL DEFAULT 1,
              createdAt    TEXT NOT NULL,
              lastUsedAt   TEXT,
              metadataJson TEXT
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS BrowserTrace (
              id           TEXT PRIMARY KEY,
              sessionId    TEXT,
              runId        TEXT,
              taskId       TEXT,
              provider     TEXT,
              status       TEXT NOT NULL,
              createdAt    TEXT NOT NULL,
              finishedAt   TEXT,
              stepsJson    TEXT,
              summaryJson  TEXT
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_browser_trace_session ON BrowserTrace(sessionId, createdAt)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS BrowserDownload (
              id           TEXT PRIMARY KEY,
              sessionId    TEXT,
              filename     TEXT,
              sourceUrl    TEXT,
              mimeType     TEXT,
              size         INTEGER,
              path         TEXT,
              startedAt    TEXT,
              completedAt  TEXT,
              checksum     TEXT,
              status       TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS BrowserVaultEntry (
              reference   TEXT PRIMARY KEY,
              scope       TEXT NOT NULL,
              name        TEXT NOT NULL,
              kind        TEXT NOT NULL,
              username    TEXT,
              profileId   TEXT,
              origin      TEXT,
              createdAt   TEXT NOT NULL
            )
            """
        )
        self._db.commit()

    # -- sessions ------------------------------------------------------------

    def save_session(self, record: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO BrowserSession
               (id, agentId, taskId, runId, profileId, provider, backend, browserType,
                contextId, status, state, createdAt, lastActivity, terminatedAt,
                tabCount, metadataJson)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 status=excluded.status, state=excluded.state,
                 lastActivity=excluded.lastActivity, terminatedAt=excluded.terminatedAt,
                 tabCount=excluded.tabCount, metadataJson=excluded.metadataJson""",
            (
                record.get("id"), record.get("agentId"), record.get("taskId"),
                record.get("runId"), record.get("profileId"), record.get("provider", ""),
                record.get("backend"), record.get("browserType"), record.get("contextId"),
                record.get("status", "READY"), record.get("state"), record.get("createdAt", now_iso()),
                record.get("lastActivity"), record.get("terminatedAt"),
                int(record.get("tabCount", 0)),
                json.dumps(record.get("metadata") or {}, default=str),
            ),
        )
        self._db.commit()

    def update_session_status(self, session_id: str, status: str, *, state: Optional[str] = None) -> None:
        self._db.execute(
            "UPDATE BrowserSession SET status=?, state=COALESCE(?, state), lastActivity=? WHERE id=?",
            (status, state, now_iso(), session_id),
        )
        self._db.commit()

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM BrowserSession WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return None
        data = _row(row)
        data["metadata"] = json.loads(data.get("metadataJson") or "{}")
        return data

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM BrowserSession ORDER BY createdAt DESC LIMIT ?", (max(1, min(limit, 500)),)
        ).fetchall()
        result = []
        for row in rows:
            data = _row(row)
            data["metadata"] = json.loads(data.get("metadataJson") or "{}")
            result.append(data)
        return result

    # -- profiles ------------------------------------------------------------

    def save_profile(self, record: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO BrowserProfile (id, name, path, persistent, createdAt, lastUsedAt, metadataJson)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, path=excluded.path, persistent=excluded.persistent,
                 lastUsedAt=excluded.lastUsedAt, metadataJson=excluded.metadataJson""",
            (
                record.get("id", new_profile_id()), record.get("name", ""), record.get("path", ""),
                1 if record.get("persistent", True) else 0, record.get("createdAt", now_iso()),
                record.get("lastUsedAt"), json.dumps(record.get("metadata") or {}, default=str),
            ),
        )
        self._db.commit()

    def list_profiles(self) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT * FROM BrowserProfile ORDER BY createdAt DESC").fetchall()
        return [dict(r) for r in rows]

    def delete_profile(self, profile_id: str) -> bool:
        cursor = self._db.execute("DELETE FROM BrowserProfile WHERE id=?", (profile_id,))
        self._db.commit()
        return cursor.rowcount > 0

    # -- traces --------------------------------------------------------------

    def save_trace(self, record: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO BrowserTrace
               (id, sessionId, runId, taskId, provider, status, createdAt, finishedAt, stepsJson, summaryJson)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 status=excluded.status, finishedAt=excluded.finishedAt,
                 stepsJson=excluded.stepsJson, summaryJson=excluded.summaryJson""",
            (
                record.get("id", new_trace_id()), record.get("sessionId"), record.get("runId"),
                record.get("taskId"), record.get("provider"), record.get("status", "open"),
                record.get("createdAt", now_iso()), record.get("finishedAt"),
                json.dumps(record.get("steps") or [], default=str),
                json.dumps(record.get("summary") or {}, default=str),
            ),
        )
        self._db.commit()

    def get_trace(self, trace_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM BrowserTrace WHERE id=?", (trace_id,)).fetchone()
        if row is None:
            return None
        data = _row(row)
        data["steps"] = json.loads(data.pop("stepsJson") or "[]")
        data["summary"] = json.loads(data.pop("summaryJson") or "{}")
        return data

    def list_traces(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT id, sessionId, runId, taskId, provider, status, createdAt, finishedAt "
            "FROM BrowserTrace ORDER BY createdAt DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- downloads -----------------------------------------------------------

    def save_download(self, record: dict[str, Any]) -> None:
        self._db.execute(
            """INSERT INTO BrowserDownload
               (id, sessionId, filename, sourceUrl, mimeType, size, path, startedAt, completedAt, checksum, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 size=excluded.size, completedAt=excluded.completedAt,
                 checksum=excluded.checksum, status=excluded.status""",
            (
                record.get("id", uuid.uuid4().hex), record.get("sessionId"), record.get("filename"),
                record.get("sourceUrl"), record.get("mimeType"), record.get("size"),
                record.get("path"), record.get("startedAt", now_iso()), record.get("completedAt"),
                record.get("checksum"), record.get("status", "pending"),
            ),
        )
        self._db.commit()

    def list_downloads(self, session_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        if session_id:
            rows = self._db.execute(
                "SELECT * FROM BrowserDownload WHERE sessionId=? ORDER BY startedAt DESC LIMIT ?",
                (session_id, max(1, min(limit, 500))),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM BrowserDownload ORDER BY startedAt DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- vault metadata (NEVER a value) --------------------------------------

    def save_vault_entry(self, entry: Any) -> None:
        self._db.execute(
            """INSERT INTO BrowserVaultEntry (reference, scope, name, kind, username, profileId, origin, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(reference) DO UPDATE SET
                 kind=excluded.kind, username=excluded.username, profileId=excluded.profileId, origin=excluded.origin""",
            (
                entry.reference, entry.scope, entry.name, entry.kind,
                entry.username, entry.profile_id, entry.origin, entry.created_at or now_iso(),
            ),
        )
        self._db.commit()

    def list_vault_entries(self, profile_id: Optional[str] = None) -> list[dict[str, Any]]:
        if profile_id:
            rows = self._db.execute(
                "SELECT * FROM BrowserVaultEntry WHERE profileId=? ORDER BY createdAt DESC",
                (profile_id,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM BrowserVaultEntry ORDER BY createdAt DESC"
            ).fetchall()
        # The DDL holds no secrets; map to the public (model-facing) shape.
        return [
            {
                "reference": r["reference"], "scope": r["scope"], "name": r["name"],
                "kind": r["kind"], "origin": r["origin"], "profileId": r["profileId"],
                "createdAt": r["createdAt"],
            }
            for r in rows
        ]


__all__ = ["BrowserStore", "new_profile_id", "new_session_id", "new_trace_id"]

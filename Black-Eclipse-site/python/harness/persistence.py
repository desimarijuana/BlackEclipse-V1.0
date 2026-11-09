"""Agent-memory persistence — owned by the Python runtime.

The SEPARATE SQLite database `agent-memory.db` holds runs, events, tool
executions, long-lived agent memory (user/agent/market facts) and skills. It is
deliberately NOT JDdS (`jdds.db`), which stays the committed market-data vault.

Uses the stdlib `sqlite3`, so there is no dependency and no migration step: the
idempotent DDL is applied on first use. The schema mirrors the TS
`src/lib/harness/persistence/schema.ts`.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sqlite3
import time
import uuid
from typing import Any, Optional

from .sqlite_pool import ThreadLocalConnections

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS HarnessRun (
  id          TEXT PRIMARY KEY,
  agentId     TEXT NOT NULL,
  userId      TEXT,
  status      TEXT NOT NULL,
  input       TEXT NOT NULL,
  output      TEXT,
  error       TEXT,
  modelSteps  INTEGER NOT NULL DEFAULT 0,
  toolCalls   INTEGER NOT NULL DEFAULT 0,
  toolErrors  INTEGER NOT NULL DEFAULT 0,
  promptTokens     INTEGER NOT NULL DEFAULT 0,
  completionTokens INTEGER NOT NULL DEFAULT 0,
  totalTokens      INTEGER NOT NULL DEFAULT 0,
  provider    TEXT,
  model       TEXT,
  createdAt   TEXT NOT NULL,
  updatedAt   TEXT NOT NULL,
  startedAt   TEXT,
  finishedAt  TEXT
);CREATE INDEX IF NOT EXISTS idx_harness_run_status  ON HarnessRun(status);
CREATE INDEX IF NOT EXISTS idx_harness_run_user    ON HarnessRun(userId);
CREATE INDEX IF NOT EXISTS idx_harness_run_created ON HarnessRun(createdAt);

CREATE TABLE IF NOT EXISTS HarnessEvent (
  id     TEXT PRIMARY KEY,
  runId  TEXT NOT NULL,
  type   TEXT NOT NULL,
  seq    INTEGER NOT NULL,
  at     TEXT NOT NULL,
  data   TEXT,
  FOREIGN KEY (runId) REFERENCES HarnessRun(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_harness_event_run ON HarnessEvent(runId, seq);

CREATE TABLE IF NOT EXISTS HarnessToolExecution (
  id          TEXT PRIMARY KEY,
  runId       TEXT NOT NULL,
  toolCallId  TEXT NOT NULL,
  name        TEXT NOT NULL,
  ok          INTEGER NOT NULL,
  durationMs  INTEGER NOT NULL,
  args        TEXT NOT NULL,
  text        TEXT NOT NULL,
  error       TEXT,
  createdAt   TEXT NOT NULL,
  FOREIGN KEY (runId) REFERENCES HarnessRun(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_harness_tool_run  ON HarnessToolExecution(runId);
CREATE INDEX IF NOT EXISTS idx_harness_tool_name ON HarnessToolExecution(name);

CREATE TABLE IF NOT EXISTS AgentMemory (
  id         TEXT PRIMARY KEY,
  scope      TEXT NOT NULL,
  userId     TEXT,
  agentId    TEXT,
  subject    TEXT,
  kind       TEXT NOT NULL,
  content    TEXT NOT NULL,
  source     TEXT,
  confidence REAL NOT NULL DEFAULT 0.5,
  createdAt  TEXT NOT NULL,
  updatedAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_scope   ON AgentMemory(scope, userId);
CREATE INDEX IF NOT EXISTS idx_memory_subject ON AgentMemory(subject);
CREATE INDEX IF NOT EXISTS idx_memory_agent   ON AgentMemory(agentId);

CREATE TABLE IF NOT EXISTS AgentSkill (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL,
  definition  TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'proposed',
  originRunId TEXT,
  successCount INTEGER NOT NULL DEFAULT 0,
  failCount    INTEGER NOT NULL DEFAULT 0,
  createdAt   TEXT NOT NULL,
  updatedAt   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_status ON AgentSkill(status);

-- D1: durable retrieval records. A retrieval result is parsed once and persisted
-- here keyed by the request key, so re-running an identical query returns the
-- SAME figures and citations instead of re-scraping (which could drift).
CREATE TABLE IF NOT EXISTS RetrievalRecord (
  key          TEXT PRIMARY KEY,
  dataType     TEXT NOT NULL,
  instrument   TEXT,
  market       TEXT,
  result       TEXT NOT NULL,   -- the full FinancialRetrievalResult JSON
  provenance   TEXT NOT NULL,   -- source + retrieval timestamp, for audit
  retrievedAt  TEXT NOT NULL,
  dataTimestamp TEXT
);
CREATE INDEX IF NOT EXISTS idx_retrieval_type ON RetrievalRecord(dataType);

-- Phase 4: durable research receipts. One bounded, queryable record per research
-- run explaining request → coverage → claims → validation → final status.
-- Lives in agent-memory.db (the harness store); never in eclipse-memory.db or
-- JDdS. Bounded: evidence references carry hashes/summaries, not full documents.
CREATE TABLE IF NOT EXISTS ResearchReceipt (
  runId        TEXT PRIMARY KEY,
  schemaVersion TEXT NOT NULL,
  taskType     TEXT NOT NULL,
  objective    TEXT NOT NULL,
  finalStatus  TEXT NOT NULL,
  receipt      TEXT NOT NULL,   -- the full ResearchReceipt JSON
  createdAt    TEXT NOT NULL,
  FOREIGN KEY (runId) REFERENCES HarnessRun(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_research_receipt_status ON ResearchReceipt(finalStatus);
CREATE INDEX IF NOT EXISTS idx_research_receipt_created ON ResearchReceipt(createdAt);

-- Learning recurrence ledger. An implicit skill candidate (a reusable procedure)
-- requires recurrence evidence: the same successful workflow observed before.
-- Counting this by scanning recent runs was O(runs) and missed recurrence beyond
-- the scan window. This table records one bounded row per deterministic evidence
-- signature (see `skills.learning._candidate_recurrence_key`) so recurrence is a
-- single indexed lookup that survives restarts. The signature is a digest of
-- tool names, never raw content.
CREATE TABLE IF NOT EXISTS LearningRecurrence (
  signature   TEXT PRIMARY KEY,
  seenCount   INTEGER NOT NULL DEFAULT 1,
  firstRunId  TEXT,
  firstSeenAt TEXT NOT NULL,
  lastSeenAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learning_recurrence_last ON LearningRecurrence(lastSeenAt);

-- Which run contributed which recurrence signature, so recording the same run
-- twice (e.g. an operator re-runs analysis) does NOT inflate the count.
CREATE TABLE IF NOT EXISTS LearningRecurrenceRun (
  runId     TEXT NOT NULL,
  signature TEXT NOT NULL,
  at        TEXT NOT NULL,
  PRIMARY KEY (runId, signature)
);

-- Full-session historical recall (Phase 3-M Memory Expansion, M2). One
-- normalized, searchable row per meaningful message: the user turn, the
-- assistant's final answer, bounded tool/retrieval summaries, corrections,
-- memory actions and skill-learning outcomes. The FULL run trace stays in
-- HarnessRun/HarnessEvent — this is a bounded *search index*, not a second copy
-- of everything. Secrets/credentials/raw provider payloads are never indexed.
CREATE TABLE IF NOT EXISTS SessionMessage (
  id        TEXT PRIMARY KEY,
  runId     TEXT NOT NULL,
  userId    TEXT,
  role      TEXT NOT NULL,
  kind      TEXT NOT NULL DEFAULT 'message',
  content   TEXT NOT NULL,
  createdAt TEXT NOT NULL,
  ordinal   INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (runId) REFERENCES HarnessRun(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_session_msg_run ON SessionMessage(runId, ordinal);
CREATE INDEX IF NOT EXISTS idx_session_msg_created ON SessionMessage(createdAt);
CREATE INDEX IF NOT EXISTS idx_session_msg_user ON SessionMessage(userId);

-- Long-lived named sessions (M3). A run belongs to a session; a session belongs
-- to one profile/user. The session is metadata + a bounded summary; the full
-- trace stays in HarnessRun/HarnessEvent. `summary` is a bounded, searchable
-- JSON blob (objective/decisions/unresolved/corrections/skills/memories/files/
-- next actions) — never injected into every prompt.
CREATE TABLE IF NOT EXISTS ChatSession (
  id             TEXT PRIMARY KEY,
  profileId      TEXT,
  userId         TEXT,
  title          TEXT,
  status         TEXT NOT NULL DEFAULT 'active',
  summary        TEXT,
  sourceSessionId TEXT,
  createdAt      TEXT NOT NULL,
  updatedAt      TEXT NOT NULL,
  lastActivityAt TEXT,
  archivedAt     TEXT
);
CREATE INDEX IF NOT EXISTS idx_chat_session_profile ON ChatSession(profileId);
CREATE INDEX IF NOT EXISTS idx_chat_session_user ON ChatSession(userId);
CREATE INDEX IF NOT EXISTS idx_chat_session_status ON ChatSession(status, updatedAt);
CREATE INDEX IF NOT EXISTS idx_chat_session_activity ON ChatSession(lastActivityAt);

-- Learning review audit (Phase 3-M Memory Expansion, M3). One row per bounded
-- post-run review attempt: status, mode, model, input digest and a BOUNDED
-- result JSON. The review itself never writes durable memory or activates a
-- skill — it proposes outcomes that pass through the shared decision gate.
CREATE TABLE IF NOT EXISTS LearningReview (
  id          TEXT PRIMARY KEY,
  runId       TEXT NOT NULL,
  status      TEXT NOT NULL,
  mode        TEXT NOT NULL DEFAULT 'deterministic',
  startedAt   TEXT,
  finishedAt  TEXT,
  model       TEXT,
  inputDigest TEXT,
  result      TEXT,
  error       TEXT,
  attempts    INTEGER NOT NULL DEFAULT 0,
  createdAt   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learning_review_run ON LearningReview(runId);
CREATE INDEX IF NOT EXISTS idx_learning_review_status ON LearningReview(status, createdAt);
"""

DB_FILENAME = "agent-memory.db"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() % 1 * 1000):03d}Z"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def _iso_days_ago(days: int) -> str:
    """UTC ISO timestamp `days` ago, matching the `now_iso` format so string
    comparison against `createdAt` is chronological."""
    then = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    return then.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


def _harness_root() -> str:
    """The application root that owns the runtime databases, independent of the
    process working directory. `BE_DATA_DIR` (the encrypted vault) overrides it.
    Matches `eclipse_memory.config.repo_root()` so the DBs live side by side."""
    return os.path.abspath(os.environ.get("BE_DATA_DIR") or os.path.join(os.path.dirname(__file__), "..", ".."))


def default_db_path() -> str:
    override = os.environ.get("AGENT_MEMORY_DB_PATH")
    if override:
        return os.path.abspath(override)
    return os.path.join(_harness_root(), DB_FILENAME)


# Columns added after the first release. `CREATE TABLE IF NOT EXISTS` does not
# alter an existing table, so an older `agent-memory.db` needs an explicit
# idempotent ADD COLUMN — otherwise upgrades would silently lose token data.
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "HarnessRun": [
        ("documents", "TEXT"),
        # Internet image search: a bounded JSON blob of the run's validated,
        # normalized image results for the chat's inline gallery. NULL when the
        # run used no image tool, so existing clients stay compatible.
        ("images", "TEXT"),
        # Native video: a bounded JSON blob of the video jobs this run QUEUED
        # (job/project ids) for the chat's live job card. NULL when the run used
        # no video tool, so existing clients stay compatible.
        ("video", "TEXT"),
        ("promptTokens", "INTEGER NOT NULL DEFAULT 0"),
        ("completionTokens", "INTEGER NOT NULL DEFAULT 0"),
        ("totalTokens", "INTEGER NOT NULL DEFAULT 0"),
        # Phase 4: a bounded JSON blob of the run's research metadata (status,
        # citations, coverage, gaps, receipt availability). NULL for ordinary
        # chat and for older rows, so existing clients stay compatible.
        ("research", "TEXT"),
        # Phase 3-M Reliability: the deterministic outcome of explicit user
        # memory intent for this run (saved/forgotten/corrected/refused) plus
        # learning eligibility. Additive and NULL for older rows.
        ("memory", "TEXT"),
        # Context budgeting (how the model window bounded history) + vision results.
        ("context", "TEXT"), ("vision", "TEXT"),
        # M3/M4: a run belongs to a session, profile and project. Additive and
        # NULL for older rows, so existing clients stay compatible.
        ("sessionId", "TEXT"),
        ("profileId", "TEXT"),
        ("projectId", "TEXT"),
        # The run's code-verification ledger + repair outcome (Phase 4). This
        # column was WRITTEN by the answer seam (`graph.py`: `update_run(...,
        # codeVerification=...)`) but was never in the CREATE TABLE and never in
        # this migration list, so on a FRESH `agent-memory.db` - which every new
        # clone gets, because the file is gitignored - the write raised
        # `no such column: codeVerification` and every run crashed at the answer
        # seam, AFTER the model had already produced its answer. The live
        # repository masked it because its database predates the column rename.
        # Additive and NULL for older rows, so existing clients stay compatible.
        ("codeVerification", "TEXT"),
        # The run's resolved autonomy profile and the workspace it was bound to
        # (Phase 5). These were in `RunResult` from the start and read back from
        # the run row, but the write was silently dropped by `update_run`'s
        # allowlist, so the field was ALWAYS None. Additive and NULL for older
        # rows.
        ("autonomy", "TEXT"),
        ("workspaceId", "TEXT"),
        # Round 3 / W2 (ADR-H280): the run's tool surface resolution - what the
        # surface added, what the autonomy profile removed, what a disabled store
        # removed, and the measured bound size. Additive and NULL for runs that
        # resolved no surface, so existing clients stay compatible.
        ("surface", "TEXT"),
    ],
    # Learning-review scheduling metadata (M1/M3). Priority ordering, the
    # coalescing session key, the profile scope and the review mode are additive
    # columns so an older database opens cleanly (NULL = not recorded).
    "LearningReview": [
        ("sessionId", "TEXT"),
        ("profileId", "TEXT"),
        ("priority", "TEXT NOT NULL DEFAULT 'normal'"),
        ("scheduling", "TEXT"),
        # Reviews written before the justified-null contract are history, not
        # current defects. Marked once; never rewritten.
        ("legacyUnscored", "INTEGER NOT NULL DEFAULT 0"),
    ],
    # Session-search index scope + filter columns (M3). Additive; NULL = unknown.
    "SessionMessage": [
        ("sessionId", "TEXT"),
        ("profileId", "TEXT"),
        ("projectId", "TEXT"),
        ("market", "TEXT"),
        ("skillId", "TEXT"),
        ("memoryAction", "TEXT"),
    ],
}


class AgentMemoryStore:
    """SQLite-backed agent-memory store.

    The store is shared across FastAPI's worker threads and async tasks, so it
    hands each thread its **own** connection via `ThreadLocalConnections` (see
    `harness/sqlite_pool.py`) rather than sharing one connection concurrently.
    Connections are autocommit + `busy_timeout` so WAL readers and the single
    writer coexist; the one multi-statement atomic op (`reset_memory`) issues an
    explicit transaction.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or default_db_path()
        self._pool = ThreadLocalConnections(self.path)
        db = self._db  # establishes the calling thread's connection
        db.executescript(SCHEMA)
        self._migrate()
        db.commit()

    @property
    def _db(self) -> sqlite3.Connection:
        return self._pool.db

    def close(self) -> None:
        """Close this store's connections (idempotent; safe to call at shutdown)."""
        self._pool.close()

    def _migrate(self) -> None:
        """Add any post-release columns to an existing database (idempotent)."""
        for table, columns in _ADDED_COLUMNS.items():
            existing = {
                row["name"]
                for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for name, ddl in columns:
                if name not in existing:
                    self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    # ── Runs ────────────────────────────────────────────────────────────────
    def create_run(
        self,
        run_id: str,
        agent_id: str,
        input_data: dict[str, Any],
        user_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        *,
        session_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        now = now_iso()
        self._db.execute(
            """INSERT INTO HarnessRun
               (id, agentId, userId, status, input, modelSteps, toolCalls, toolErrors,
                provider, model, createdAt, updatedAt, sessionId, profileId, projectId)
               VALUES (?, ?, ?, 'created', ?, 0, 0, 0, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, agent_id, user_id, json.dumps(input_data), provider, model, now, now,
             session_id, profile_id, project_id),
        )
        self._db.commit()
        # A run belongs to a session; create one lazily when the caller did not.
        if session_id and self.get_chat_session(session_id) is None:
            self.create_chat_session(
                session_id, profile_id=profile_id, user_id=user_id,
                title=(input_data or {}).get("query", "")[:80] or None,
            )
        if session_id:
            self.touch_chat_session(session_id)

    def update_run(self, run_id: str, **patch: Any) -> None:
        allowed = {
            "status", "output", "error", "modelSteps", "toolCalls", "toolErrors",
            "promptTokens", "completionTokens", "totalTokens",
            "provider", "model", "startedAt", "finishedAt", "research", "memory",
            "context", "codeVerification", "vision", "documents", "images", "video",
            "sessionId", "profileId", "projectId",
            # Round 3 / W2: the run's autonomy profile, its bound workspace and
            # its tool-surface resolution. `autonomy` and `workspaceId` were in
            # `RunResult` from the start but the write was silently dropped here,
            # so the field was always None; `surface` is new in ADR-H280.
            "autonomy", "workspaceId", "surface",
        }
        sets, params = [], []
        for key in patch:
            if key not in allowed:
                continue
            value = patch[key]
            sets.append(f"{key} = ?")
            if key in ("error", "research", "memory", "context", "codeVerification", "vision", "documents", "images", "video", "surface") and value is not None:
                params.append(json.dumps(value))
            else:
                params.append(value)
        if not sets:
            return
        sets.append("updatedAt = ?")
        params.append(now_iso())
        params.append(run_id)
        self._db.execute(f"UPDATE HarnessRun SET {', '.join(sets)} WHERE id = ?", params)
        self._db.commit()

    # ── Chat sessions (M3) ──────────────────────────────────────────────────
    def create_chat_session(
        self, session_id: str, *, profile_id: Optional[str] = None,
        user_id: Optional[str] = None, title: Optional[str] = None,
        status: str = "active", summary: Optional[dict[str, Any]] = None,
        source_session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        now = now_iso()
        self._db.execute(
            """INSERT INTO ChatSession
               (id, profileId, userId, title, status, summary, sourceSessionId,
                createdAt, updatedAt, lastActivityAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO NOTHING""",
            (session_id, profile_id, user_id, title, status,
             json.dumps(summary) if summary is not None else None,
             source_session_id, now, now, now),
        )
        self._db.commit()
        return self.get_chat_session(session_id) or {}

    def get_chat_session(self, session_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM ChatSession WHERE id=?", (session_id,)).fetchone()
        return _chat_session_row(row) if row else None

    def list_chat_sessions(
        self, *, profile_id: Optional[str] = None, user_id: Optional[str] = None,
        status: Optional[str] = None, limit: int = 50, offset: int = 0,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if profile_id is not None:
            where.append("profileId = ?"); params.append(profile_id)
        if user_id is not None:
            where.append("userId = ?"); params.append(user_id)
        if status is not None:
            where.append("status = ?"); params.append(status)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        rows = self._db.execute(
            f"SELECT * FROM ChatSession{clause}"
            " ORDER BY COALESCE(lastActivityAt, updatedAt) DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [_chat_session_row(r) for r in rows]

    def count_chat_sessions(
        self, *, profile_id: Optional[str] = None, user_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        where: list[str] = []
        params: list[Any] = []
        if profile_id is not None:
            where.append("profileId = ?"); params.append(profile_id)
        if user_id is not None:
            where.append("userId = ?"); params.append(user_id)
        if status is not None:
            where.append("status = ?"); params.append(status)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        row = self._db.execute(f"SELECT COUNT(*) FROM ChatSession{clause}", params).fetchone()
        return int(row[0]) if row else 0

    def update_chat_session(self, session_id: str, **patch: Any) -> Optional[dict[str, Any]]:
        allowed = {"title", "status", "summary", "archivedAt", "lastActivityAt", "profileId", "userId"}
        sets: list[str] = []
        params: list[Any] = []
        for key in patch:
            if key not in allowed:
                continue
            value = patch[key]
            sets.append(f"{key} = ?")
            params.append(json.dumps(value) if key == "summary" and value is not None else value)
        if not sets:
            return self.get_chat_session(session_id)
        sets.append("updatedAt = ?")
        params.append(now_iso())
        params.append(session_id)
        self._db.execute(f"UPDATE ChatSession SET {', '.join(sets)} WHERE id=?", params)
        self._db.commit()
        return self.get_chat_session(session_id)

    def touch_chat_session(self, session_id: str) -> None:
        self._db.execute(
            "UPDATE ChatSession SET lastActivityAt=?, updatedAt=? WHERE id=?",
            (now_iso(), now_iso(), session_id),
        )
        self._db.commit()

    def delete_chat_session(self, session_id: str, *, hard: bool = False) -> dict[str, Any]:
        """Archive (default) or remove a session. Archive is the safe default so
        history is never silently destroyed; a hard delete also clears its
        search-index messages but never the run traces."""
        session = self.get_chat_session(session_id)
        if session is None:
            return {"deleted": False, "reason": "not found"}
        run_ids = [
            r["id"] for r in self._db.execute(
                "SELECT id FROM HarnessRun WHERE sessionId=?", (session_id,)
            ).fetchall()
        ]
        if hard:
            self._db.execute("DELETE FROM ChatSession WHERE id=?", (session_id,))
            for run_id in run_ids:
                self.delete_session_messages(run_id)
            self._db.commit()
            return {"deleted": True, "hard": True, "runs": len(run_ids)}
        self.update_chat_session(session_id, status="archived", archivedAt=now_iso())
        return {"deleted": False, "archived": True}

    def fork_chat_session(self, session_id: str, new_session_id: str) -> Optional[dict[str, Any]]:
        """Fork a session: a new session links to the source; the source is
        untouched. Run history is not copied (the source link retains it)."""
        source = self.get_chat_session(session_id)
        if source is None:
            return None
        return self.create_chat_session(
            new_session_id, profile_id=source.get("profileId"), user_id=source.get("userId"),
            title=(source.get("title") or "") + " (fork)",
            summary=source.get("summary"), source_session_id=session_id,
        )

    def session_runs(self, session_id: str) -> list[str]:
        return [
            r["id"] for r in self._db.execute(
                "SELECT id FROM HarnessRun WHERE sessionId=? ORDER BY createdAt ASC", (session_id,)
            ).fetchall()
        ]

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM HarnessRun WHERE id = ?", (run_id,)).fetchone()
        return _run_row(row) if row else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        rows = self._db.execute(
            "SELECT * FROM HarnessRun ORDER BY createdAt DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_run_row(r) for r in rows]

    def unindexed_completed_runs(self, limit: int = 200) -> list[dict[str, Any]]:
        """Completed runs with no SessionMessage row, newest first."""
        bound = max(1, min(int(limit), 2000))
        rows = self._db.execute(
            """SELECT r.* FROM HarnessRun r
               WHERE r.status = 'completed'
                 AND NOT EXISTS (
                   SELECT 1 FROM SessionMessage m WHERE m.runId = r.id
                 )
               ORDER BY r.createdAt DESC LIMIT ?""",
            (bound,),
        ).fetchall()
        return [_run_row(r) for r in rows]

    # ── Usage analytics ─────────────────────────────────────────────────────
    # Token consumption is real, persisted data. `totalTokens` can legitimately
    # be 0 when a provider (e.g. a local Ollama server) omits a usage block — the
    # UI must render that honestly as "not reported", never as a fabricated
    # number. Hence `runsWithUsage` alongside the totals.
    def usage_summary(self, days: int = 30) -> dict[str, Any]:
        days = max(1, min(int(days), 365))
        since = _iso_days_ago(days)

        totals = self._db.execute(
            """SELECT
                 COUNT(*)                        AS runs,
                 COALESCE(SUM(promptTokens), 0)     AS promptTokens,
                 COALESCE(SUM(completionTokens), 0) AS completionTokens,
                 COALESCE(SUM(totalTokens), 0)      AS totalTokens,
                 COALESCE(SUM(modelSteps), 0)       AS modelSteps,
                 COALESCE(SUM(toolCalls), 0)        AS toolCalls,
                 COALESCE(SUM(toolErrors), 0)       AS toolErrors,
                 COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) AS completed,
                 COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0)    AS failed,
                 COALESCE(SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled,
                 COALESCE(SUM(CASE WHEN totalTokens > 0 THEN 1 ELSE 0 END), 0)      AS runsWithUsage
               FROM HarnessRun WHERE createdAt >= ?""",
            (since,),
        ).fetchone()

        by_model = self._db.execute(
            """SELECT COALESCE(provider, 'unknown') AS provider,
                      COALESCE(model, 'unknown')    AS model,
                      COUNT(*)                      AS runs,
                      COALESCE(SUM(promptTokens), 0)     AS promptTokens,
                      COALESCE(SUM(completionTokens), 0) AS completionTokens,
                      COALESCE(SUM(totalTokens), 0)      AS totalTokens
               FROM HarnessRun WHERE createdAt >= ?
               GROUP BY provider, model
               ORDER BY totalTokens DESC, runs DESC""",
            (since,),
        ).fetchall()

        by_day = self._db.execute(
            """SELECT substr(createdAt, 1, 10) AS date,
                      COUNT(*)                 AS runs,
                      COALESCE(SUM(promptTokens), 0)     AS promptTokens,
                      COALESCE(SUM(completionTokens), 0) AS completionTokens,
                      COALESCE(SUM(totalTokens), 0)      AS totalTokens
               FROM HarnessRun WHERE createdAt >= ?
               GROUP BY date ORDER BY date ASC""",
            (since,),
        ).fetchall()

        recent = self._db.execute(
            """SELECT id, agentId, status, provider, model, modelSteps, toolCalls,
                      toolErrors, promptTokens, completionTokens, totalTokens, createdAt
               FROM HarnessRun WHERE createdAt >= ?
               ORDER BY createdAt DESC LIMIT 20""",
            (since,),
        ).fetchall()

        # Zero-fill the window so the daily chart has a continuous time axis.
        # Grouping only returns days that had activity; without the gaps a
        # 30-day window with 3 active days would render 3 adjacent bars and
        # misrepresent the distribution.
        day_rollup = {r["date"]: r for r in by_day}
        start_date = _dt.datetime.strptime(since[:10], "%Y-%m-%d").date()
        end_date = _dt.datetime.now(_dt.timezone.utc).date()
        by_day_filled: list[dict[str, Any]] = []
        cursor = start_date
        while cursor <= end_date:
            key = cursor.isoformat()
            row = day_rollup.get(key)
            by_day_filled.append(
                {
                    "date": key,
                    "runs": row["runs"] if row else 0,
                    "promptTokens": row["promptTokens"] if row else 0,
                    "completionTokens": row["completionTokens"] if row else 0,
                    "totalTokens": row["totalTokens"] if row else 0,
                }
            )
            cursor += _dt.timedelta(days=1)

        return {
            "windowDays": days,
            "since": since,
            "totals": {
                "runs": totals["runs"],
                "promptTokens": totals["promptTokens"],
                "completionTokens": totals["completionTokens"],
                "totalTokens": totals["totalTokens"],
                "modelSteps": totals["modelSteps"],
                "toolCalls": totals["toolCalls"],
                "toolErrors": totals["toolErrors"],
                "completed": totals["completed"],
                "failed": totals["failed"],
                "cancelled": totals["cancelled"],
                "runsWithUsage": totals["runsWithUsage"],
            },
            "byModel": [
                {
                    "provider": r["provider"],
                    "model": r["model"],
                    "runs": r["runs"],
                    "promptTokens": r["promptTokens"],
                    "completionTokens": r["completionTokens"],
                    "totalTokens": r["totalTokens"],
                }
                for r in by_model
            ],
            "byDay": by_day_filled,
            "recent": [dict(r) for r in recent],
        }

    # ── Events ──────────────────────────────────────────────────────────────
    def append_event(self, run_id: str, event_type: str, seq: int, data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        event = {
            "id": new_id("evt"),
            "runId": run_id,
            "type": event_type,
            "seq": seq,
            "at": now_iso(),
            "data": data or {},
        }
        self._db.execute(
            "INSERT INTO HarnessEvent (id, runId, type, seq, at, data) VALUES (?, ?, ?, ?, ?, ?)",
            (event["id"], run_id, event_type, seq, event["at"], json.dumps(event["data"])),
        )
        self._db.commit()
        return event

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM HarnessEvent WHERE runId = ? ORDER BY seq ASC", (run_id,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "runId": r["runId"],
                "type": r["type"],
                "seq": r["seq"],
                "at": r["at"],
                "data": json.loads(r["data"]) if r["data"] else {},
            }
            for r in rows
        ]

    # ── Tool executions ─────────────────────────────────────────────────────
    def record_tool_execution(self, run_id: str, result: Any) -> None:
        self._db.execute(
            """INSERT INTO HarnessToolExecution
               (id, runId, toolCallId, name, ok, durationMs, args, text, error, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id("tex"),
                run_id,
                result.tool_call_id,
                result.name,
                1 if result.ok else 0,
                result.duration_ms,
                json.dumps(getattr(result, "args", {}) or {}),
                result.text[:4000],
                result.error.model_dump_json() if result.error else None,
                now_iso(),
            ),
        )
        self._db.commit()

    def list_tool_executions(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM HarnessToolExecution WHERE runId = ? ORDER BY createdAt ASC", (run_id,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "runId": r["runId"],
                "toolCallId": r["toolCallId"],
                "name": r["name"],
                "ok": bool(r["ok"]),
                "durationMs": r["durationMs"],
                "args": json.loads(r["args"]) if r["args"] else {},
                "text": r["text"],
                "error": json.loads(r["error"]) if r["error"] else None,
                "createdAt": r["createdAt"],
            }
            for r in rows
        ]

    # ── Learning recurrence ledger (bounded, signature-only) ────────────────
    def record_learning_recurrence(self, signature: str, run_id: Optional[str] = None) -> int:
        """Bump the seen-count for an evidence signature and return the new count.

        Only a digest is stored (never raw content). Recording the SAME
        (runId, signature) twice is a no-op, so re-analysing a run does not
        inflate recurrence. Prunes older rows so the ledger stays bounded.
        """
        if not signature:
            return 0
        now = now_iso()
        if run_id:
            try:
                inserted = self._db.execute(
                    "INSERT OR IGNORE INTO LearningRecurrenceRun (runId, signature, at) VALUES (?, ?, ?)",
                    (run_id, signature, now),
                )
                self._db.commit()
                if inserted.rowcount == 0:
                    # This run already contributed this signature.
                    return self.learning_recurrence(signature)
            except Exception:  # noqa: BLE001 - dedupe is best-effort
                pass
        row = self._db.execute(
            "SELECT seenCount FROM LearningRecurrence WHERE signature=?", (signature,)
        ).fetchone()
        if row:
            count = int(row["seenCount"]) + 1
            self._db.execute(
                "UPDATE LearningRecurrence SET seenCount=?, lastSeenAt=? WHERE signature=?",
                (count, now, signature),
            )
        else:
            count = 1
            self._db.execute(
                "INSERT INTO LearningRecurrence (signature, seenCount, firstRunId, firstSeenAt, lastSeenAt)"
                " VALUES (?, 1, ?, ?, ?)",
                (signature, run_id, now, now),
            )
        self._db.commit()
        self._prune_learning_recurrence()
        return count

    def learning_recurrence(self, signature: str) -> int:
        """How many times this evidence signature has been seen (0 when unseen)."""
        if not signature:
            return 0
        row = self._db.execute(
            "SELECT seenCount FROM LearningRecurrence WHERE signature=?", (signature,)
        ).fetchone()
        return int(row["seenCount"]) if row else 0

    def _prune_learning_recurrence(self, keep: int = 2000) -> None:
        try:
            self._db.execute(
                "DELETE FROM LearningRecurrence WHERE signature IN ("
                "  SELECT signature FROM LearningRecurrence ORDER BY lastSeenAt DESC LIMIT -1 OFFSET ?"
                ")",
                (max(1, int(keep)),),
            )
            self._db.commit()
        except Exception:  # noqa: BLE001 - pruning must never block a write
            pass

    # ── Session history search (M2) ─────────────────────────────────────────
    def fts5_available(self) -> bool:
        """Whether the SQLite runtime supports FTS5 virtual tables.

        Historical search must never claim success when it cannot run: callers
        check this and report "historical search unavailable" honestly.
        """
        cached = getattr(self, "_fts5_available", None)
        if cached is not None:
            return cached
        try:
            self._db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
            self._db.execute("DROP TABLE IF EXISTS _fts_probe")
            self._db.commit()
            self._fts5_available = True
        except Exception:  # noqa: BLE001 - absence is a supported outcome
            self._fts5_available = False
        return self._fts5_available

    def index_session_message(
        self,
        *,
        run_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
        kind: str = "message",
        ordinal: int = 0,
        created_at: Optional[str] = None,
        message_id: Optional[str] = None,
        session_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        project_id: Optional[str] = None,
        market: Optional[str] = None,
        skill_id: Optional[str] = None,
        memory_action: Optional[str] = None,
    ) -> Optional[str]:
        """Insert one bounded, searchable session message (idempotent per run+ordinal).

        Content is redacted + truncated by the caller/indexing helper; this store
        persists it and keeps the FTS5 index in sync when available.
        """
        content = (content or "").strip()
        if not content or not run_id:
            return None
        msg_id = message_id or new_id("msg")
        now = created_at or now_iso()
        # One row per (runId, ordinal): reindexing a run replaces rather than
        # duplicates. DELETE then INSERT keeps the FTS index consistent.
        self._db.execute(
            "DELETE FROM SessionMessage WHERE runId=? AND ordinal=?",
            (run_id, ordinal),
        )
        self._db.execute(
            """INSERT INTO SessionMessage
               (id, runId, userId, role, kind, content, createdAt, ordinal,
                sessionId, profileId, projectId, market, skillId, memoryAction)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, run_id, user_id, role, kind, content[:8000], now, ordinal,
             session_id, profile_id, project_id, market, skill_id, memory_action),
        )
        if self._ensure_fts_index():
            try:
                self._db.execute("DELETE FROM SessionMessageFts WHERE messageId=?", (msg_id,))
                self._db.execute(
                    "INSERT INTO SessionMessageFts (messageId, runId, role, content) VALUES (?, ?, ?, ?)",
                    (msg_id, run_id, role, content[:8000]),
                )
            except Exception:  # noqa: BLE001 - the FTS mirror is best-effort
                pass
        self._db.commit()
        return msg_id

    def delete_session_messages(self, run_id: str) -> int:
        """Remove all indexed messages for a run (privacy/delete control). The
        full run trace in HarnessRun/HarnessEvent is untouched by this."""
        rows = self._db.execute(
            "SELECT id FROM SessionMessage WHERE runId=?", (run_id,)
        ).fetchall()
        if not rows:
            return 0
        ids = [r["id"] for r in rows]
        self._db.execute("DELETE FROM SessionMessage WHERE runId=?", (run_id,))
        if self.fts5_available():
            try:
                self._db.executemany(
                    "DELETE FROM SessionMessageFts WHERE messageId=?", [(i,) for i in ids]
                )
            except Exception:  # noqa: BLE001
                pass
        self._db.commit()
        return len(ids)

    def session_message_count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) AS c FROM SessionMessage").fetchone()
        return int(row["c"]) if row else 0

    def _ensure_fts_index(self) -> bool:
        """Create the FTS5 mirror if the runtime supports it. Returns availability."""
        if not self.fts5_available():
            return False
        try:
            self._db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS SessionMessageFts USING fts5("
                "messageId UNINDEXED, runId UNINDEXED, role UNINDEXED, content)"
            )
            self._db.commit()
            return True
        except Exception:  # noqa: BLE001
            return False

    def search_session_messages(
        self,
        query: str,
        *,
        user_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        run_id: Optional[str] = None,
        role: Optional[str] = None,
        session_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        market: Optional[str] = None,
        skill_id: Optional[str] = None,
        memory_action: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Full-text search over indexed session messages.

        Uses FTS5 for BM25 ranking when available; otherwise falls back to a
        deterministic LIKE scan. Reports `engine` honestly so a caller can tell
        which path ran. Never returns unbounded snippets.

        Ranking is the documented hybrid: an exact-phrase hit wins, then BM25,
        then a decision/correction/skill-failure/memory-action boost, then
        recency, then assistant prose. The boosts are deterministic and small so
        they refine — never replace — a real text match.
        """
        query = (query or "").strip()
        limit = max(1, min(int(limit), 50))
        offset = max(0, int(offset))
        if not query:
            return {"available": True, "engine": "none", "results": [], "hasMore": False, "offset": offset}
        # Fetch one pool deep enough to rank then slice the requested page. The
        # hybrid ranking happens in Python, so a plain SQL OFFSET would page the
        # wrong order; ranking the pool and slicing preserves page semantics.
        pool = max(50, min(2000, (offset + limit + 1) * 4))
        # Sanitize the FTS query: keep word tokens only, join with AND so a
        # quote/operator cannot produce a syntax error or a wildcard scan.
        tokens = re.findall(r"[A-Za-z0-9]+", query)[:12]
        where = []
        params: list[Any] = []
        if user_id:
            where.append("m.userId = ?"); params.append(user_id)
        if run_id:
            where.append("m.runId = ?"); params.append(run_id)
        if session_id:
            where.append("m.sessionId = ?"); params.append(session_id)
        if profile_id:
            where.append("m.profileId = ?"); params.append(profile_id)
        if role:
            where.append("m.role = ?"); params.append(role)
        if kind:
            where.append("m.kind = ?"); params.append(kind)
        if market:
            where.append("m.market = ?"); params.append(market)
        if skill_id:
            where.append("m.skillId = ?"); params.append(skill_id)
        if memory_action:
            where.append("m.memoryAction = ?"); params.append(memory_action)
        if date_from:
            where.append("m.createdAt >= ?"); params.append(date_from)
        if date_to:
            where.append("m.createdAt <= ?"); params.append(date_to)
        filter_clause = (" AND " + " AND ".join(where)) if where else ""

        phrase = " ".join(tokens)

        def _hybrid_key(hit: dict[str, Any]) -> tuple:
            # Lower sorts first. Exact phrase beats everything; then the BM25
            # score (negated so a better score is smaller); then a deterministic
            # decision/correction/skill-failure/memory-action boost; then recency;
            # assistant prose ranks below a user/decision match at equal score.
            content = (hit.get("content") or hit.get("snippet") or "").lower()
            phrase_hit = 0 if phrase and phrase in content else 1
            bm25 = hit.get("score")
            bm25_key = bm25 if bm25 is not None else 0.0
            kind_boost = 0
            low_kind = (hit.get("kind") or "").lower()
            low_role = (hit.get("role") or "").lower()
            if low_kind in ("decision", "correction", "skill_failure", "memory_action"):
                kind_boost = 0
            elif low_role == "user":
                kind_boost = 1
            else:
                kind_boost = 2
            return (phrase_hit, bm25_key, kind_boost, hit.get("createdAt") or "")

        results: list[dict[str, Any]] = []
        engine = "like"
        match_mode = "all"
        has_more = False
        if tokens and self._ensure_fts_index():
            try:
                sql = (
                    "SELECT m.id, m.runId, m.userId, m.role, m.kind, m.content, m.createdAt,"
                    " snippet(SessionMessageFts, 3, '', '', '…', 12) AS snip,"
                    " bm25(SessionMessageFts) AS score "
                    "FROM SessionMessageFts f JOIN SessionMessage m ON m.id = f.messageId "
                    f"WHERE SessionMessageFts MATCH ?{filter_clause} "
                    "ORDER BY score LIMIT ?"
                )
                rows = self._db.execute(
                    sql, [" AND ".join(tokens), *params, pool],
                ).fetchall()
                # A natural-language query often has no single message containing
                # every token. Retry with OR and let the hybrid rank the phrase
                # hits first; a single-token query is unchanged.
                if not rows and len(tokens) > 1:
                    match_mode = "any"
                    rows = self._db.execute(
                        sql, [" OR ".join(tokens), *params, pool],
                    ).fetchall()
                engine = "fts5"
                hits = [_session_result(r, score=-float(r["score"])) for r in rows]
                hits.sort(key=_hybrid_key)
                results = hits[offset:offset + limit]
                has_more = len(hits) > offset + limit
                return {
                    "available": True, "engine": engine, "matchMode": match_mode,
                    "results": results, "hasMore": has_more, "offset": offset,
                }
            except Exception:  # noqa: BLE001 - fall through to the LIKE scan
                results = []
        # LIKE fallback (deterministic, bounded).
        if tokens:
            def _like_rows(mode: str) -> list[Any]:
                joiner = " AND " if mode == "all" else " OR "
                like = joiner.join(["m.content LIKE ?"] * len(tokens))
                return self._db.execute(
                    "SELECT m.id, m.runId, m.userId, m.role, m.kind, m.content, m.createdAt"
                    f" FROM SessionMessage m WHERE {like}{filter_clause}"
                    " ORDER BY m.createdAt DESC LIMIT ?",
                    [*(f"%{t}%" for t in tokens), *params, pool],
                ).fetchall()

            rows = _like_rows("all")
            if not rows and len(tokens) > 1:
                match_mode = "any"
                rows = _like_rows("any")
            hits = [_session_result(r, score=None) for r in rows]
            hits.sort(key=_hybrid_key)
            results = hits[offset:offset + limit]
            has_more = len(hits) > offset + limit
        return {
            "available": True, "engine": engine, "matchMode": match_mode,
            "results": results, "hasMore": has_more, "offset": offset,
        }

    def open_session(
        self,
        run_id: str,
        *,
        message_id: Optional[str] = None,
        before: int = 3,
        after: int = 3,
    ) -> dict[str, Any]:
        """Return a bounded window of a run's indexed messages.

        `message_id` anchors the window; otherwise the whole (bounded) run is
        returned from the start.
        """
        rows = self._db.execute(
            "SELECT id, runId, userId, role, kind, content, createdAt, ordinal"
            " FROM SessionMessage WHERE runId=? ORDER BY ordinal ASC",
            (run_id,),
        ).fetchall()
        if not rows:
            return {"runId": run_id, "messages": [], "truncated": False}
        before = max(0, min(int(before), 20))
        after = max(0, min(int(after), 20))
        anchor = 0
        if message_id:
            for index, row in enumerate(rows):
                if row["id"] == message_id:
                    anchor = index
                    break
        start = max(0, anchor - before)
        end = min(len(rows), anchor + after + 1)
        window = rows[start:end]
        return {
            "runId": run_id,
            "messages": [_session_result(r, score=None, full=True) for r in window],
            "truncated": start > 0 or end < len(rows),
        }

    # ── Learning review audit (M3) ──────────────────────────────────────────
    def save_learning_review(self, review: dict[str, Any]) -> dict[str, Any]:
        # One run has one review row. A direct/operator re-run updates it
        # instead of appending a duplicate with identical content.
        if (
            not review.get("id")
            and review.get("status") == "completed"
            and review.get("runId")
        ):
            existing = self.latest_learning_review(review.get("runId"))
            if existing is not None:
                refreshed_at = now_iso()
                updated = self.update_learning_review(
                    existing["id"],
                    status="completed",
                    createdAt=refreshed_at,
                    finishedAt=review.get("finishedAt") or refreshed_at,
                    mode=review.get("mode", existing.get("mode")),
                    result=review.get("result"),
                    error=review.get("error"),
                )
                if updated is not None:
                    return updated
        review_id = review.get("id") or new_id("lrev")
        self._db.execute(
            """INSERT OR REPLACE INTO LearningReview
               (id, runId, status, mode, startedAt, finishedAt, model, inputDigest,
                result, error, attempts, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                review_id, review["runId"], review.get("status", "queued"),
                review.get("mode", "deterministic"), review.get("startedAt"),
                review.get("finishedAt"), review.get("model"), review.get("inputDigest"),
                json.dumps(review.get("result")) if review.get("result") is not None else None,
                review.get("error"), int(review.get("attempts") or 0),
                review.get("createdAt") or now_iso(),
            ),
        )
        self._db.commit()
        return self.get_learning_review(review_id) or {"id": review_id}

    def update_learning_review(self, review_id: str, **patch: Any) -> Optional[dict[str, Any]]:
        allowed = {
            "status", "startedAt", "finishedAt", "model", "inputDigest",
            "result", "error", "attempts", "createdAt",
        }
        sets, params = [], []
        for key, value in patch.items():
            if key not in allowed:
                continue
            sets.append(f"{key} = ?")
            params.append(json.dumps(value) if key == "result" and value is not None else value)
        if not sets:
            return self.get_learning_review(review_id)
        params.append(review_id)
        self._db.execute(f"UPDATE LearningReview SET {', '.join(sets)} WHERE id=?", params)
        self._db.commit()
        return self.get_learning_review(review_id)

    def get_learning_review(self, review_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM LearningReview WHERE id=?", (review_id,)).fetchone()
        return _learning_review_row(row) if row else None

    def latest_learning_review(self, run_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        if run_id:
            row = self._db.execute(
                "SELECT * FROM LearningReview WHERE runId=? ORDER BY createdAt DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT * FROM LearningReview ORDER BY createdAt DESC LIMIT 1"
            ).fetchone()
        return _learning_review_row(row) if row else None

    def list_learning_reviews(
        self, *, status: Optional[str] = None, limit: int = 50, offset: int = 0,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        if status:
            rows = self._db.execute(
                "SELECT * FROM LearningReview WHERE status=? ORDER BY createdAt DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM LearningReview ORDER BY createdAt DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_learning_review_row(r) for r in rows]

    def count_learning_reviews(self, *, status: Optional[str] = None) -> int:
        if status:
            row = self._db.execute(
                "SELECT COUNT(*) FROM LearningReview WHERE status=?", (status,)
            ).fetchone()
        else:
            row = self._db.execute("SELECT COUNT(*) FROM LearningReview").fetchone()
        return int(row[0]) if row else 0

    def mark_legacy_reviews(self, since: str) -> int:
        """Mark pre-contract reviews as legacy_unscored (history, not rewrites)."""
        cursor = self._db.execute(
            "UPDATE LearningReview SET legacyUnscored=1 "
            "WHERE status='completed' AND legacyUnscored=0 "
            "AND COALESCE(finishedAt, createdAt) < ?",
            (since,),
        )
        self._db.commit()
        return int(cursor.rowcount or 0)

    def learning_review_health(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        try:
            rows = self._db.execute(
                "SELECT status, COUNT(*) AS c FROM LearningReview GROUP BY status"
            ).fetchall()
            counts = {r["status"]: int(r["c"]) for r in rows}
        except Exception:  # noqa: BLE001 - health must never raise
            counts = {}
        return {
            "total": sum(counts.values()),
            "byStatus": counts,
            "latest": self.latest_learning_review(),
        }

    # ── Durable retrieval records (D1) ──────────────────────────────────────
    def save_retrieval(
        self,
        key: str,
        data_type: str,
        instrument: Optional[str],
        market: Optional[str],
        result_json: dict[str, Any],
        provenance: dict[str, Any],
        data_timestamp: Optional[str] = None,
    ) -> None:
        self._db.execute(
            """INSERT INTO RetrievalRecord
               (key, dataType, instrument, market, result, provenance, retrievedAt, dataTimestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                 result = excluded.result,
                 provenance = excluded.provenance,
                 retrievedAt = excluded.retrievedAt,
                 dataTimestamp = excluded.dataTimestamp""",
            (
                key,
                data_type,
                instrument,
                market,
                json.dumps(result_json),
                json.dumps(provenance),
                now_iso(),
                data_timestamp,
            ),
        )
        self._db.commit()

    def get_retrieval(self, key: str) -> Optional[dict[str, Any]]:
        r = self._db.execute("SELECT * FROM RetrievalRecord WHERE key = ?", (key,)).fetchone()
        if r is None:
            return None
        return {
            "key": r["key"],
            "dataType": r["dataType"],
            "instrument": r["instrument"],
            "market": r["market"],
            "result": json.loads(r["result"]),
            "provenance": json.loads(r["provenance"]) if r["provenance"] else {},
            "retrievedAt": r["retrievedAt"],
            "dataTimestamp": r["dataTimestamp"],
        }

    # ── Research receipts (Phase 4) ─────────────────────────────────────────
    def save_receipt(self, receipt: dict[str, Any]) -> None:
        """Persist a bounded research receipt (idempotent per run).

        `receipt` is a `ResearchReceipt.model_dump()`. Persistence failures are
        raised to the caller so a save is never falsely claimed successful.
        """
        run_id = str(receipt.get("runId") or "")
        if not run_id:
            raise ValueError("receipt is missing a runId")
        self._db.execute(
            """INSERT INTO ResearchReceipt
               (runId, schemaVersion, taskType, objective, finalStatus, receipt, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(runId) DO UPDATE SET
                 schemaVersion = excluded.schemaVersion,
                 taskType = excluded.taskType,
                 objective = excluded.objective,
                 finalStatus = excluded.finalStatus,
                 receipt = excluded.receipt,
                 createdAt = excluded.createdAt""",
            (
                run_id,
                str(receipt.get("schemaVersion") or "1.0.0"),
                str(receipt.get("taskType") or "general"),
                str(receipt.get("objective") or ""),
                str(receipt.get("finalStatus") or "rejected"),
                json.dumps(receipt),
                now_iso(),
            ),
        )
        self._db.commit()

    def get_receipt(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM ResearchReceipt WHERE runId = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["receipt"]) if row["receipt"] else None

    def list_receipts(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        rows = self._db.execute(
            "SELECT * FROM ResearchReceipt ORDER BY createdAt DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "runId": r["runId"],
                "schemaVersion": r["schemaVersion"],
                "taskType": r["taskType"],
                "objective": r["objective"],
                "finalStatus": r["finalStatus"],
                "createdAt": r["createdAt"],
            }
            for r in rows
        ]

    # ── Agent memory ────────────────────────────────────────────────────────
    def remember(
        self,
        scope: str,
        kind: str,
        content: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        subject: Optional[str] = None,
        source: Optional[str] = None,
        confidence: float = 0.5,
    ) -> dict[str, Any]:
        record = {
            "id": new_id("mem"),
            "scope": scope,
            "userId": user_id,
            "agentId": agent_id,
            "subject": subject,
            "kind": kind,
            "content": content,
            "source": source,
            "confidence": max(0.0, min(float(confidence), 1.0)),
            "createdAt": now_iso(),
        }
        record["updatedAt"] = record["createdAt"]
        self._db.execute(
            """INSERT INTO AgentMemory
               (id, scope, userId, agentId, subject, kind, content, source, confidence, createdAt, updatedAt)
               VALUES (:id, :scope, :userId, :agentId, :subject, :kind, :content, :source, :confidence, :createdAt, :updatedAt)""",
            record,
        )
        self._db.commit()
        return record

    def recall(
        self,
        scope: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        subject: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        where, params = [], []
        for column, value in (("scope", scope), ("userId", user_id), ("agentId", agent_id), ("subject", subject)):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        limit = max(1, min(int(limit), 100))
        rows = self._db.execute(
            f"SELECT * FROM AgentMemory {clause} ORDER BY updatedAt DESC LIMIT ?", [*params, limit]
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Skills ──────────────────────────────────────────────────────────────
    def propose_skill(
        self,
        name: str,
        description: str,
        definition: dict[str, Any],
        origin_run_id: Optional[str] = None,
        status: str = "proposed",
    ) -> dict[str, Any]:
        existing = self._db.execute("SELECT * FROM AgentSkill WHERE name = ?", (name,)).fetchone()
        if existing:
            self._db.execute(
                "UPDATE AgentSkill SET description = ?, definition = ?, updatedAt = ? WHERE name = ?",
                (description, json.dumps(definition), now_iso(), name),
            )
            self._db.commit()
            return self.get_skill(name)  # type: ignore[return-value]
        now = now_iso()
        self._db.execute(
            """INSERT INTO AgentSkill
               (id, name, description, definition, status, originRunId, successCount, failCount, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?)""",
            (new_id("skill"), name, description, json.dumps(definition), status, origin_run_id, now, now),
        )
        self._db.commit()
        return self.get_skill(name)  # type: ignore[return-value]

    def get_skill(self, name: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM AgentSkill WHERE name = ?", (name,)).fetchone()
        if not row:
            return None
        record = dict(row)
        record["definition"] = json.loads(record["definition"])
        return record

    def list_skills(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        if status:
            rows = self._db.execute("SELECT * FROM AgentSkill WHERE status = ? ORDER BY updatedAt DESC", (status,)).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM AgentSkill ORDER BY updatedAt DESC").fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["definition"] = json.loads(record["definition"])
            out.append(record)
        return out

    def record_skill_outcome(self, name: str, ok: bool) -> None:
        column = "successCount" if ok else "failCount"
        self._db.execute(
            f"UPDATE AgentSkill SET {column} = {column} + 1, updatedAt = ? WHERE name = ?", (now_iso(), name)
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()


def _run_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "agentId": row["agentId"],
        "userId": row["userId"],
        "status": row["status"],
        "input": json.loads(row["input"]) if row["input"] else {},
        "output": row["output"],
        "error": json.loads(row["error"]) if row["error"] else None,
        "modelSteps": row["modelSteps"],
        "toolCalls": row["toolCalls"],
        "toolErrors": row["toolErrors"],
        "promptTokens": row["promptTokens"],
        "completionTokens": row["completionTokens"],
        "totalTokens": row["totalTokens"],
        "provider": row["provider"], "model": row["model"],
        "research": json.loads(row["research"]) if _has_column(row, "research") and row["research"] else None,
        "memory": json.loads(row["memory"]) if _has_column(row, "memory") and row["memory"] else None,
        "context": json.loads(row["context"]) if _has_column(row, "context") and row["context"] else None,
        "codeVerification": json.loads(row["codeVerification"]) if _has_column(row, "codeVerification") and row["codeVerification"] else None,
        "vision": json.loads(row["vision"]) if _has_column(row, "vision") and row["vision"] else None,
        "documents": json.loads(row["documents"]) if _has_column(row, "documents") and row["documents"] else None,
        "images": json.loads(row["images"]) if _has_column(row, "images") and row["images"] else None,
        "video": json.loads(row["video"]) if _has_column(row, "video") and row["video"] else None,
        "sessionId": row["sessionId"] if _has_column(row, "sessionId") else None,
        "profileId": row["profileId"] if _has_column(row, "profileId") else None,
        "projectId": row["projectId"] if _has_column(row, "projectId") else None,
        # Round 3 / W2 (ADR-H280): the run's tool-surface resolution. Additive
        # and NULL for rows written before the surface was published.
        "surface": json.loads(row["surface"]) if _has_column(row, "surface") and row["surface"] else None,
        "autonomy": row["autonomy"] if _has_column(row, "autonomy") else None,
        "workspaceId": row["workspaceId"] if _has_column(row, "workspaceId") else None,
        "parentRunId": row["parentRunId"] if _has_column(row, "parentRunId") else None,
        "workflowId": row["workflowId"] if _has_column(row, "workflowId") else None,
        # Additive + old-row-safe (the column is created by `delegation_tools`):
        # the bounded fan-out blob, so a reload can re-draw the parallel card.
        "delegation": json.loads(row["delegation"])
        if _has_column(row, "delegation") and row["delegation"] else None,
        "createdAt": row["createdAt"], "updatedAt": row["updatedAt"],
        "startedAt": row["startedAt"], "finishedAt": row["finishedAt"],
    }


def _has_column(row: sqlite3.Row, name: str) -> bool:
    try:
        return name in row.keys()
    except Exception:  # noqa: BLE001
        return False


def _session_result(row: sqlite3.Row, *, score: Optional[float], full: bool = False) -> dict[str, Any]:
    """A bounded session-search hit. Snippets are always length-capped."""
    keys = row.keys()
    content = row["content"] or ""
    snippet = row["snip"] if "snip" in keys and row["snip"] is not None else content
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if not full and len(snippet) > 320:
        snippet = snippet[:319].rstrip() + "…"
    return {
        "messageId": row["id"],
        "runId": row["runId"],
        "userId": row["userId"] if "userId" in keys else None,
        "role": row["role"],
        "kind": row["kind"] if "kind" in keys else "message",
        "snippet": snippet,
        "content": content if full else None,
        "createdAt": row["createdAt"],
        "score": score,
    }


def _chat_session_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    if record.get("summary"):
        try:
            record["summary"] = json.loads(record["summary"])
        except (TypeError, ValueError):
            record["summary"] = None
    return record


def _learning_review_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    if record.get("result"):
        try:
            record["result"] = json.loads(record["result"])
        except (TypeError, ValueError):
            pass
    return record


__all__ = ["AgentMemoryStore", "SCHEMA", "DB_FILENAME", "default_db_path", "now_iso", "new_id"]

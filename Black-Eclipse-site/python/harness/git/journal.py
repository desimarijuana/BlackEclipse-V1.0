"""The Git operation journal and in-progress operation store.

Bound to the ONE `agent-memory.db` connection, exactly like `code/store.py` and
`run_lineage.py`: this module owns only its own tables and never grows the
ratcheted `persistence.py`.

Two tables:

  * `GitOperation` — the journal. One row per mutating (and, optionally, read)
    operation: operation id, repository, type, SANITIZED arguments, risk, start/
    end time, status, exit code, error code, affected files, recovery state.
    Secrets never reach it: arguments are scrubbed and remote URLs are redacted
    before storage.
  * `GitActiveOperation` — the durable state machine. The source of truth for
    "is a merge/rebase/… open?" is still the repository (sentinel files); this
    table records the runtime's view so a restart can reconcile the two.

DDL is idempotent (`CREATE TABLE IF NOT EXISTS`) and applied on first use.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Optional

from ..persistence import now_iso

# A URL with embedded credentials: `scheme://user:token@host` → redact the token.
_CRED_URL_RE = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)(?P<user>[^/@\s]*):(?P<secret>[^/@\s]+)@")
_TOKENISH_RE = re.compile(r"(?i)\b(gh[pousr]_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9]{12,}|AKIA[0-9A-Z]{16})\b")

_JOURNAL_ARG_CHARS = 4_000
_JOURNAL_DETAIL_CHARS = 8_000


def redact_text(text: str) -> str:
    """Remove credential-shaped substrings from journal text. Never logs a value."""
    if not text:
        return ""
    cleaned = _CRED_URL_RE.sub(lambda m: f"{m.group('scheme')}{m.group('user')}:«redacted»@", str(text))
    cleaned = _TOKENISH_RE.sub("«redacted»", cleaned)
    return cleaned


def sanitize_argv(argv: Any) -> list[str]:
    """A journal-safe copy of an argv (redacted, bounded, NUL-free)."""
    out: list[str] = []
    if not isinstance(argv, (list, tuple)):
        return out
    for token in argv[:256]:
        text = redact_text(str(token))
        if "\x00" in text:
            text = text.replace("\x00", "?")
        out.append(text[:_JOURNAL_ARG_CHARS])
    return out


class GitJournal:
    """The git operation journal + active-operation state on agent-memory.db."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS GitOperation (
              id            TEXT PRIMARY KEY,
              repository    TEXT NOT NULL,
              operation     TEXT NOT NULL,
              args          TEXT NOT NULL,
              risk          TEXT NOT NULL,
              mutating      INTEGER NOT NULL DEFAULT 0,
              runId         TEXT,
              scopeId       TEXT,
              startedAt     TEXT NOT NULL,
              finishedAt    TEXT,
              status        TEXT NOT NULL,
              exitCode      INTEGER,
              errorCode     TEXT,
              affectedFiles TEXT NOT NULL DEFAULT '[]',
              recoveryState TEXT,
              durationMs    INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_git_op_repo ON GitOperation(repository, startedAt)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_git_op_run ON GitOperation(runId)"
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS GitActiveOperation (
              repository    TEXT PRIMARY KEY,
              operationId   TEXT NOT NULL,
              operation     TEXT NOT NULL,
              status        TEXT NOT NULL,
              nextAction    TEXT,
              headName      TEXT,
              onto          TEXT,
              updatedAt     TEXT NOT NULL
            )
            """
        )
        self._db.commit()

    # ── Journal ───────────────────────────────────────────────────────────────
    def start(
        self,
        *,
        repository: str,
        operation: str,
        argv: Any,
        risk: str,
        mutating: bool,
        run_id: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> str:
        operation_id = "gitop_" + uuid.uuid4().hex[:16]
        self._db.execute(
            """INSERT INTO GitOperation
               (id, repository, operation, args, risk, mutating, runId, scopeId,
                startedAt, finishedAt, status, exitCode, errorCode, affectedFiles,
                recoveryState, durationMs)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'IN_PROGRESS', NULL, NULL,
                       '[]', NULL, 0)""",
            (
                operation_id, str(repository), str(operation),
                json.dumps(sanitize_argv(argv), ensure_ascii=False),
                str(risk), 1 if mutating else 0, run_id, scope_id, now_iso(),
            ),
        )
        self._db.commit()
        return operation_id

    def finish(
        self,
        operation_id: str,
        *,
        status: str,
        exit_code: Optional[int] = None,
        error_code: Optional[str] = None,
        affected_files: Optional[list[str]] = None,
        recovery_state: Optional[dict[str, Any]] = None,
        duration_ms: int = 0,
    ) -> None:
        self._db.execute(
            """UPDATE GitOperation
               SET finishedAt=?, status=?, exitCode=?, errorCode=?, affectedFiles=?,
                   recoveryState=?, durationMs=?
               WHERE id=?""",
            (
                now_iso(), str(status), exit_code, error_code,
                json.dumps([redact_text(str(f)) for f in (affected_files or [])][:1000], ensure_ascii=False),
                json.dumps(recovery_state or {}, ensure_ascii=False) if recovery_state else None,
                int(duration_ms), operation_id,
            ),
        )
        self._db.commit()

    def get(self, operation_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM GitOperation WHERE id=?", (operation_id,)
        ).fetchone()
        return self._decode(dict(row)) if row else None

    def list(
        self, *, repository: Optional[str] = None, run_id: Optional[str] = None,
        status: Optional[str] = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        clauses: list[str] = []
        params: list[Any] = []
        if repository:
            clauses.append("repository = ?")
            params.append(repository)
        if run_id:
            clauses.append("runId = ?")
            params.append(run_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._db.execute(
            f"SELECT * FROM GitOperation{where} ORDER BY startedAt DESC LIMIT ?", tuple([*params[:-1], params[-1]])
        ).fetchall()
        return [self._decode(dict(r)) for r in rows]

    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        try:
            row["args"] = json.loads(row.get("args") or "[]")
        except (ValueError, TypeError):
            row["args"] = []
        try:
            row["affectedFiles"] = json.loads(row.get("affectedFiles") or "[]")
        except (ValueError, TypeError):
            row["affectedFiles"] = []
        try:
            row["recoveryState"] = json.loads(row["recoveryState"]) if row.get("recoveryState") else None
        except (ValueError, TypeError):
            row["recoveryState"] = None
        return row

    # ── Active-operation state ─────────────────────────────────────────────────
    def set_active(
        self, *, repository: str, operation_id: str, operation: str, status: str,
        next_action: Optional[str] = None, head_name: Optional[str] = None,
        onto: Optional[str] = None,
    ) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO GitActiveOperation
               (repository, operationId, operation, status, nextAction, headName, onto, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(repository), operation_id, operation, status, next_action,
             head_name, onto, now_iso()),
        )
        self._db.commit()

    def clear_active(self, repository: str) -> None:
        self._db.execute(
            "DELETE FROM GitActiveOperation WHERE repository=?", (str(repository),)
        )
        self._db.commit()

    def get_active(self, repository: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM GitActiveOperation WHERE repository=?", (str(repository),)
        ).fetchone()
        return dict(row) if row else None


__all__ = ["GitJournal", "redact_text", "sanitize_argv"]

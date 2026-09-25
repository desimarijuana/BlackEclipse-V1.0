"""Eclipse-Memory database connection + migration runner.

A single `EclipseMemoryDb` instance owns the connection to
`eclipse-memory.db`. Migrations are applied idempotently on open; the applied
version is recorded in `SchemaMigration`, so migrations never re-run and an
upgrade is observable (`migration_status()`).

Only stdlib `sqlite3` is used — one SQLite access library across the runtime
(the same choice `harness/persistence.py` makes); no Prisma and no second
driver.
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Optional

from .config import db_identity, legacy_candidate_paths, resolve_path
from .schema import MIGRATIONS, SCHEMA_VERSION


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() % 1 * 1000):03d}Z"


def new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4()}"


class EclipseMemoryDb:
    """Owns the connection and the schema lifecycle. Do not open two of these
    against the same file from different components — use the one instance the
    service holds."""

    def __init__(self, path: Optional[str] = None) -> None:
        # Reconcile legacy cwd-based databases ONLY when we are opening the
        # stable default (no explicit path and no env override). Tests and
        # callers that pass an explicit path must never pull in repo data.
        self._is_stable_default = path is None and not os.environ.get("ECLIPSE_MEMORY_DB_PATH")
        self.path = resolve_path(path)
        # A busy timeout makes a concurrent writer wait instead of failing
        # immediately with "database is locked" (local app: SQLite serialises).
        self._db = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode = WAL;")
        self._db.execute("PRAGMA synchronous = NORMAL;")
        self._db.execute("PRAGMA foreign_keys = ON;")
        self._db.execute("PRAGMA busy_timeout = 30000;")
        self._migrate()
        if self._is_stable_default:
            try:
                self.reconcile_legacy()
            except Exception:  # noqa: BLE001 - reconciliation must never block boot
                pass

    def integrity_ok(self) -> bool:
        """Whether the database passes an integrity check. Used to fail honestly
        (503 / "memory unavailable") rather than answer with corrupt data."""
        try:
            return self._db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        except Exception:  # noqa: BLE001 - unreadable is not ok
            return False

    # ── Migrations ──────────────────────────────────────────────────────────

    def _migrate(self) -> None:
        # Migration bookkeeping table must exist before we can read the version.
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS SchemaMigration (version INTEGER PRIMARY KEY, appliedAt TEXT NOT NULL)"
        )
        self._db.commit()
        applied = {
            row["version"]
            for row in self._db.execute("SELECT version FROM SchemaMigration").fetchall()
        }
        for version, statements in MIGRATIONS:
            if version in applied:
                continue
            for statement in statements:
                self._db.executescript(statement)
            self._db.execute(
                "INSERT OR REPLACE INTO SchemaMigration (version, appliedAt) VALUES (?, ?)",
                (version, now_iso()),
            )
            self._db.commit()

    def migration_status(self) -> dict[str, Any]:
        applied = [
            row["version"]
            for row in self._db.execute(
                "SELECT version FROM SchemaMigration ORDER BY version"
            ).fetchall()
        ]
        return {
            "path": self.path,
            "schemaVersion": SCHEMA_VERSION,
            "appliedVersions": applied,
            "upToDate": (SCHEMA_VERSION in applied),
        }

    # ── Health ──────────────────────────────────────────────────────────────

    def identity_summary(self) -> dict[str, Any]:
        """Cheap, non-secret identity for a polled health endpoint (no PRAGMA)."""
        return {"path": self.path, "identity": db_identity(self.path)}

    def health(self) -> dict[str, Any]:
        """A cheap liveness/consistency check for `GET /health`.

        Reports the RESOLVED database path plus a non-secret identity so an
        operator can tell which store the runtime is actually using (the failure
        mode this fixes: a runtime launched from a different cwd silently reading
        a different file).
        """
        try:
            integrity = self._db.execute("PRAGMA integrity_check").fetchone()[0]
            tables = [
                row["name"]
                for row in self._db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
            counts = {}
            for table in ("MemoryRecord", "Skill", "SkillVersion", "LearningCandidate", "SkillExecution"):
                if table in tables:
                    counts[table] = self._db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            return {
                "ok": integrity == "ok",
                "integrity": integrity,
                "path": self.path,
                "identity": db_identity(self.path),
                "tables": len(tables),
                "counts": counts,
                **self.migration_status(),
            }
        except Exception as exc:  # noqa: BLE001 - health must never raise
            return {"ok": False, "error": str(exc), "path": self.path, "identity": db_identity(self.path)}

    # ── Legacy reconciliation ───────────────────────────────────────────────

    def reconcile_legacy(self) -> dict[str, Any]:
        """One-time, non-destructive reconciliation of legacy cwd-based DBs.

        The stable default is `repo_root()/eclipse-memory.db`. Before the fix, a
        runtime launched from `python/` (or another cwd) could create
        `python/eclipse-memory.db`. If the stable database is EMPTY and a legacy
        candidate holds records, copy the memory/skill/learning rows forward.

        Guarantees:
          * never overwrites a newer record (INSERT OR IGNORE by primary key);
          * never deletes or modifies the source database;
          * a no-op when the stable database already has memory or skills, or
            when no legacy candidate exists.

        Runs on every open but is idempotent and cheap (it reads counts first).
        """
        try:
            local_memory = self._db.execute("SELECT COUNT(*) FROM MemoryRecord").fetchone()[0]
            local_skills = self._db.execute("SELECT COUNT(*) FROM Skill").fetchone()[0]
        except Exception:  # noqa: BLE001 - a half-migrated db must not block boot
            return {"reconciled": False, "reason": "local schema not ready"}
        if local_memory or local_skills:
            return {"reconciled": False, "reason": "stable database already populated"}

        for candidate in legacy_candidate_paths():
            if not os.path.isfile(candidate):
                continue
            result = self._import_legacy_tables(candidate)
            if result.get("imported"):
                return {"reconciled": True, "source": candidate, **result}
        return {"reconciled": False, "reason": "no legacy database with records found"}

    def _import_legacy_tables(self, legacy_path: str) -> dict[str, Any]:
        """Copy rows from a legacy eclipse-memory file. Source is never touched."""
        import sqlite3

        tables = (
            "MemoryRecord", "MemoryEvidence", "MemoryLink", "MemoryRetrievalEvent",
            "MemoryEvent", "MistakeRecord", "CorrectionRecord", "MemoryPolicy",
            "Skill", "SkillVersion", "SkillDependency", "SkillToolRequirement",
            "SkillPermissionRequirement", "SkillExecution", "SkillEvaluation",
            "SkillEvaluationCase", "LearningCandidate", "SkillPromotionRequest",
            "SkillReview", "SkillEvent", "UserSkill",
        )
        try:
            source = sqlite3.connect(legacy_path)
            source.row_factory = sqlite3.Row
            source_tables = {
                row["name"]
                for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
        except Exception as exc:  # noqa: BLE001
            return {"imported": False, "reason": f"cannot open legacy db: {exc}"}

        counts: dict[str, int] = {}
        try:
            for table in tables:
                if table not in source_tables:
                    continue
                local_cols = {
                    row["name"]
                    for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()
                }
                rows = source.execute(f"SELECT * FROM {table}").fetchall()
                if not rows:
                    continue
                for row in rows:
                    keys = [k for k in row.keys() if k in local_cols]
                    quoted = ", ".join(keys)
                    placeholders = ", ".join("?" for _ in keys)
                    self._db.execute(
                        f"INSERT OR IGNORE INTO {table} ({quoted}) VALUES ({placeholders})",
                        tuple(row[k] for k in keys),
                    )
                    counts[table] = counts.get(table, 0) + 1
            self._db.commit()
        finally:
            source.close()
        return {"imported": True, "source": legacy_path, "counts": counts}

    # ── Access ──────────────────────────────────────────────────────────────

    def execute(self, sql: str, params: Any = ()) -> sqlite3.Cursor:
        return self._db.execute(sql, params)

    def commit(self) -> None:
        self._db.commit()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._db

    def close(self) -> None:
        self._db.close()


__all__ = ["EclipseMemoryDb", "new_id", "now_iso"]

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

import sqlite3
import time
from typing import Any, Optional

from .config import resolve_path
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
        self.path = resolve_path(path)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode = WAL;")
        self._db.execute("PRAGMA synchronous = NORMAL;")
        self._db.execute("PRAGMA foreign_keys = ON;")
        self._migrate()

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

    def health(self) -> dict[str, Any]:
        """A cheap liveness/consistency check for `GET /health`."""
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
                "tables": len(tables),
                "counts": counts,
                **self.migration_status(),
            }
        except Exception as exc:  # noqa: BLE001 - health must never raise
            return {"ok": False, "error": str(exc), "path": self.path}

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

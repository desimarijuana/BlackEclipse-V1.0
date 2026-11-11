"""One ordered migration ledger for the harness databases (Round 5 / C2).

Before this, each subsystem created its own tables with
`CREATE TABLE IF NOT EXISTS` and its own ad-hoc `_migrate` method. There was no
single record of what had been applied, so "is this database current?" could not
be answered. The ledger does not rewrite the existing schema: it records
migrations that opt in, applies them exactly once, in order, and exposes the
applied set for diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .persistence import now_iso


@dataclass(frozen=True)
class Migration:
    """One ordered, idempotent schema change."""

    id: str
    description: str
    statements: tuple[str, ...]


class MigrationRunner:
    """A per-database ledger (`SchemaMigration`) and a transactional applier."""

    # NOT `SchemaMigration`: `eclipse_memory` already owns a table with that
    # name and a `(version, appliedAt)` shape on the shared file. This ledger is
    # namespaced and id-based, so it must not collide with the legacy one.
    TABLE = "HarnessMigration"

    def __init__(self, db: Any, namespace: str = "agent-memory") -> None:
        self._db = db
        self.namespace = namespace
        self._ensure_table()

    def _ensure_table(self) -> None:
        self._db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE} (
              namespace TEXT NOT NULL,
              id        TEXT NOT NULL,
              description TEXT,
              appliedAt TEXT NOT NULL,
              PRIMARY KEY (namespace, id)
            )
            """
        )

    def applied(self) -> set[str]:
        rows = self._db.execute(
            f"SELECT id FROM {self.TABLE} WHERE namespace=? ORDER BY id ASC",
            (self.namespace,),
        ).fetchall()
        return {row["id"] for row in rows}

    def current_version(self) -> Optional[str]:
        """The lexicographically last applied id (ids are date-prefixed)."""
        ids = sorted(self.applied())
        return ids[-1] if ids else None

    def apply(self, migrations: Iterable[Migration]) -> list[Migration]:
        """Apply every pending migration once, in id order.

        Returns the migrations actually applied (empty means the database was
        already current). A failure rolls the whole batch back: a half-applied
        schema is worse than a stale one.
        """
        ordered = sorted(migrations, key=lambda migration: migration.id)
        if not ordered:
            return []
        existing = self.applied()
        if all(migration.id in existing for migration in ordered):
            return []

        self._db.execute("BEGIN IMMEDIATE")
        try:
            # Re-read inside the write lock: two threads booting at once must not
            # both decide a migration is pending.
            applied = self.applied()
            pending = [migration for migration in ordered if migration.id not in applied]
            for migration in pending:
                for statement in migration.statements:
                    self._db.execute(statement)
                self._db.execute(
                    f"INSERT OR IGNORE INTO {self.TABLE} "
                    "(namespace, id, description, appliedAt) VALUES (?, ?, ?, ?)",
                    (self.namespace, migration.id, migration.description, now_iso()),
                )
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return pending


__all__ = ["Migration", "MigrationRunner"]

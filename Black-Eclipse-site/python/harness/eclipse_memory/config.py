"""Eclipse-Memory configuration — one place that decides the database path.

Resolution order:
  1. `ECLIPSE_MEMORY_DB_PATH` (absolute or relative). Tests set this to a temp
     file so the suite never touches the developer's real memory database.
  2. `<cwd>/eclipse-memory.db`.

The path is never a hardcoded absolute location; callers may always override it.
"""

from __future__ import annotations

import os

DB_FILENAME = "eclipse-memory.db"


def db_filename() -> str:
    return DB_FILENAME


def default_db_path() -> str:
    """The configured database path (env override first)."""
    override = os.environ.get("ECLIPSE_MEMORY_DB_PATH")
    if override:
        return os.path.abspath(override)
    return os.path.join(os.getcwd(), DB_FILENAME)


# Alias kept for symmetry with the harness persistence module.
memory_db_path = default_db_path


def resolve_path(path: str | None = None) -> str:
    return os.path.abspath(path) if path else default_db_path()


__all__ = ["DB_FILENAME", "db_filename", "default_db_path", "memory_db_path", "resolve_path"]

"""Eclipse-Memory configuration — one place that decides the database path.

Resolution order (stable, cwd-independent):
  1. `ECLIPSE_MEMORY_DB_PATH` (absolute or relative). Tests set this to a temp
     file so the suite never touches the developer's real memory database.
  2. `<repo root>/eclipse-memory.db` — the repository that contains this file
     (`Black-Eclipse-site/`), NOT the process working directory.

Why not `<cwd>`: the runtime is spawned by the Next.js front door from the repo
root, but a manual `uvicorn --app-dir python`, a pytest run, or any tool started
from `python/` would previously resolve a DIFFERENT file and silently write/read
a second memory store. Anchoring the default to the package location makes the
path stable across every launch directory. `ECLIPSE_MEMORY_DB_PATH` remains the
explicit override.

The path is never a hardcoded machine location; callers may always override it.
"""

from __future__ import annotations

import hashlib
import os

DB_FILENAME = "eclipse-memory.db"


def repo_root() -> str:
    """The application root that owns the databases (the repo containing this
    package), independent of the process working directory."""
    # .../<repo>/python/harness/eclipse_memory/config.py -> parents[3] = <repo>
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def db_filename() -> str:
    return DB_FILENAME


def default_db_path() -> str:
    """The configured database path (env override first)."""
    override = os.environ.get("ECLIPSE_MEMORY_DB_PATH")
    if override:
        return os.path.abspath(override)
    # `BE_DATA_DIR` relocates the personal databases onto an encrypted volume
    # (scripts/setup-data-vault.ps1), the same variable the other two stores read.
    data_dir = os.environ.get("BE_DATA_DIR")
    if data_dir:
        return os.path.join(os.path.abspath(data_dir), DB_FILENAME)
    return os.path.join(repo_root(), DB_FILENAME)


# Alias kept for symmetry with the harness persistence module.
memory_db_path = default_db_path


def resolve_path(path: str | None = None) -> str:
    return os.path.abspath(path) if path else default_db_path()


def legacy_candidate_paths() -> list[str]:
    """Older cwd-based locations a pre-fix install may have written to.

    Resolution is non-destructive: callers may READ these to reconcile an empty
    stable database, but never overwrite newer records or delete the source.
    """
    resolved = os.path.normcase(os.path.abspath(default_db_path()))
    candidates = [
        os.path.join(repo_root(), "python", DB_FILENAME),
        os.path.join(os.getcwd(), DB_FILENAME),
    ]
    out: list[str] = []
    for path in candidates:
        normalized = os.path.normcase(os.path.abspath(path)) if path else ""
        if normalized and normalized != resolved and path not in out:
            out.append(os.path.abspath(path))
    return out


def db_identity(path: str | None = None) -> dict[str, object]:
    """A stable, non-secret identity for the resolved database.

    Exposes enough for a health panel/diagnostic to tell two stores apart
    (resolved path, whether it exists, its size, and a short content-free
    fingerprint) without ever leaking memory contents. The fingerprint is a hash
    of the path only, so it is safe to display.
    """
    resolved = resolve_path(path)
    digest = hashlib.sha256(os.path.abspath(resolved).encode("utf-8")).hexdigest()[:16]
    info: dict[str, object] = {
        "path": resolved,
        "filename": os.path.basename(resolved),
        "identity": digest,
        "exists": os.path.isfile(resolved),
    }
    if info["exists"]:
        try:
            info["sizeBytes"] = os.path.getsize(resolved)
        except OSError:
            pass
    return info


__all__ = [
    "DB_FILENAME",
    "db_filename",
    "default_db_path",
    "legacy_candidate_paths",
    "memory_db_path",
    "repo_root",
    "resolve_path",
    "db_identity",
]

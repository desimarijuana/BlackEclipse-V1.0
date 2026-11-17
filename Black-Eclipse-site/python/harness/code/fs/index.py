"""The workspace index — a SEPARATE SQLite store, never agent memory.

The agent's memory database (`agent-memory.db`) and the control DB
(`eclipse-memory.db`) are NOT touched. The index lives in its own file under the
app's scratch directory (`.black-eclipse/workspace-index/<workspace>.db`), which
is gitignored, so indexing a user's folder never writes into that folder.

It tracks, per file: relative path, hash, size, language, modified time, and the
symbols/imports/exports and identifier mentions extracted from it. Updates are
INCREMENTAL: only files whose mtime/size/hash changed are re-parsed; removed
files are deleted. A single edit never triggers a full rebuild.

The index is a CACHE, never an authority: every query can fall back to a live
scan, and `find_references` names its engine so the agent knows the difference.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

from .. import policy
from . import errors as err
from . import resolver as res
from .context import FsContext
from .symbols import detect_language, extract_symbols

MAX_INDEX_FILES = 50_000
MAX_INDEX_FILE_BYTES = 2_000_000
MAX_IDENTIFIERS_PER_FILE = 400
MAX_MENTION_LINES = 25
_MAX_IDENTIFIER = 80

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  rel        TEXT PRIMARY KEY,
  sha256     TEXT,
  size       INTEGER NOT NULL,
  mtime_ns   INTEGER NOT NULL,
  language   TEXT NOT NULL,
  symbols    TEXT NOT NULL DEFAULT '[]',
  imports    TEXT NOT NULL DEFAULT '[]',
  exports    TEXT NOT NULL DEFAULT '[]',
  identifiers TEXT NOT NULL DEFAULT '{}',
  definitions TEXT NOT NULL DEFAULT '{}',
  indexed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_files_language ON files(language);
"""


def index_dir() -> Path:
    """`<app repo>/.black-eclipse/workspace-index` - never the user's folder.

    `HARNESS_WORKSPACE_INDEX_DIR` relocates the scratch store; the test suite
    points it at a temp dir so a run never leaves per-workspace DBs in the
    checkout.
    """
    override = os.environ.get("HARNESS_WORKSPACE_INDEX_DIR")
    if override:
        path = Path(override)
    else:
        try:
            from ...eclipse_memory.config import repo_root  # noqa: PLC0415

            base = Path(repo_root())
        except Exception:  # noqa: BLE001
            base = Path(os.path.expanduser("~"))
        path = base / ".black-eclipse" / "workspace-index"
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path(workspace_id: str) -> Path:
    safe = "".join(ch for ch in workspace_id if ch.isalnum() or ch in "_-") or "default"
    return index_dir() / f"{safe}.db"


@dataclass
class IndexStats:
    scanned: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0
    bytes: int = 0
    duration_ms: int = 0
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned, "updated": self.updated, "removed": self.removed,
            "unchanged": self.unchanged, "bytes": self.bytes,
            "durationMs": self.duration_ms, "truncated": self.truncated,
        }


class WorkspaceIndex:
    """A persistent, incremental index over one workspace."""

    def __init__(self, ws: Any, *, path: Optional[Path] = None) -> None:
        self.ws = ws
        self.path = path or index_path(getattr(ws, "id", "default"))
        self._db = sqlite3.connect(str(self.path), timeout=5.0)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(_SCHEMA)
        self._ensure_columns()
        self._db.commit()

    def _ensure_columns(self) -> None:
        """Add the additive `definitions` column to a database created before it."""
        try:
            columns = {row["name"] for row in self._db.execute("PRAGMA table_info(files)").fetchall()}
            if "definitions" not in columns:
                self._db.execute("ALTER TABLE files ADD COLUMN definitions TEXT NOT NULL DEFAULT '{}'")
        except sqlite3.Error:
            pass

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:  # noqa: BLE001
            pass

    # ── indexing ────────────────────────────────────────────────────────────
    def _iter_files(self) -> Iterator[tuple[str, Path]]:
        for dirpath, dirnames, filenames in os.walk(self.ws.root, followlinks=False):
            current = Path(dirpath)
            dirnames[:] = [
                d for d in dirnames
                if not policy.is_ignored(res.relative(self.ws, current / d))
                and not policy.is_protected(res.relative(self.ws, current / d))
            ]
            for name in filenames:
                full = current / name
                rel = res.relative(self.ws, full)
                if policy.is_ignored(rel) or policy.is_protected(rel):
                    continue
                if detect_language(rel) == "text":
                    continue
                yield rel, full

    def update(self, *, max_files: int = MAX_INDEX_FILES) -> IndexStats:
        """Incrementally re-index changed files. Returns honest counts."""
        from . import encoding as enc

        started = time.monotonic()
        stats = IndexStats()
        known: dict[str, sqlite3.Row] = {
            row["rel"]: row for row in self._db.execute("SELECT * FROM files").fetchall()
        }
        seen: set[str] = set()
        for rel, full in self._iter_files():
            if stats.scanned >= max_files:
                stats.truncated = True
                break
            stats.scanned += 1
            seen.add(rel)
            try:
                st = full.stat()
            except OSError:
                continue
            if st.st_size > MAX_INDEX_FILE_BYTES:
                continue
            prior = known.get(rel)
            if prior is not None and prior["mtime_ns"] == st.st_mtime_ns and prior["size"] == st.st_size:
                stats.unchanged += 1
                continue
            if res.is_binary_file(full):
                continue
            try:
                text = enc.read_text(full).text
            except err.FsError:
                continue
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if prior is not None and prior["sha256"] == digest:
                # Content identical despite a touch: refresh the mtime only.
                self._db.execute(
                    "UPDATE files SET mtime_ns=?, size=?, indexed_at=? WHERE rel=?",
                    (st.st_mtime_ns, st.st_size, _now(), rel),
                )
                stats.unchanged += 1
                continue
            symbols = extract_symbols(rel, text)
            imports = [s.name for s in symbols if s.kind == "import"]
            exports = [s.name for s in symbols if s.exported]
            identifiers = _identifiers(text)
            definitions = _definitions(symbols)
            self._db.execute(
                """INSERT OR REPLACE INTO files
                   (rel, sha256, size, mtime_ns, language, symbols, imports, exports,
                    identifiers, definitions, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rel, digest, st.st_size, st.st_mtime_ns, detect_language(rel),
                    json.dumps([s.to_dict() for s in symbols]),
                    json.dumps(imports), json.dumps(exports),
                    json.dumps(identifiers), json.dumps(definitions), _now(),
                ),
            )
            stats.updated += 1
            stats.bytes += st.st_size
        for rel in set(known) - seen:
            self._db.execute("DELETE FROM files WHERE rel=?", (rel,))
            stats.removed += 1
        self._db.commit()
        stats.duration_ms = int((time.monotonic() - started) * 1000)
        return stats

    # ── queries ─────────────────────────────────────────────────────────────
    def symbols(self, query: Optional[str] = None, *, kind: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        needle = (query or "").lower()
        for row in self._db.execute("SELECT rel, symbols FROM files").fetchall():
            for symbol in json.loads(row["symbols"]):
                if kind and symbol.get("kind") != kind:
                    continue
                if needle and needle not in str(symbol.get("name", "")).lower():
                    continue
                out.append(symbol)
                if len(out) >= limit:
                    return out
        return out

    def find_references(self, name: str, *, limit: int = 200) -> Optional[list[dict[str, Any]]]:
        """References from the identifier mentions, each marked `definition` when it
        is where the symbol is declared. None when the index is empty (so the
        caller falls back to a live scan)."""
        if self._db.execute("SELECT 1 FROM files LIMIT 1").fetchone() is None:
            return None
        out: list[dict[str, Any]] = []
        for row in self._db.execute("SELECT rel, identifiers, definitions FROM files").fetchall():
            identifiers = json.loads(row["identifiers"])
            definitions = json.loads(row["definitions"])
            mentions = identifiers.get(name) or identifiers.get(name.upper()) or identifiers.get(name.lower())
            if not mentions:
                continue
            declaration_lines = set(definitions.get(name, []))
            for line in mentions:
                out.append({
                    "path": row["rel"], "line": line,
                    "definition": line in declaration_lines,
                })
                if len(out) >= limit:
                    return out
        return out

    def status(self) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(size),0) AS bytes FROM files"
        ).fetchone()
        return {
            "status": "ok",
            "indexPath": str(self.path),
            "fileCount": int(row["n"]),
            "totalBytes": int(row["bytes"]),
            "engine": "sqlite",
        }

    def clear(self) -> None:
        self._db.execute("DELETE FROM files")
        self._db.commit()

    def remove(self, rel: str) -> None:
        """Drop one file from the index after an external change/deletion."""
        self._db.execute("DELETE FROM files WHERE rel=?", (rel,))
        self._db.commit()

    def reindex_file(self, rel: str) -> bool:
        """Re-parse ONE file (incremental). False when it is gone/ignored."""
        from . import encoding as enc

        if policy.is_protected(rel) or policy.is_ignored(rel):
            self.remove(rel)
            return False
        try:
            full = res.resolve(self.ws, rel)
        except err.FsError:
            self.remove(rel)
            return False
        if not full.exists() or not full.is_file() or detect_language(rel) == "text":
            self.remove(rel)
            return False
        try:
            st = full.stat()
            if st.st_size > MAX_INDEX_FILE_BYTES or res.is_binary_file(full):
                self.remove(rel)
                return False
            text = enc.read_text(full).text
        except (OSError, err.FsError):
            self.remove(rel)
            return False
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        symbols = extract_symbols(rel, text)
        self._db.execute(
            """INSERT OR REPLACE INTO files
               (rel, sha256, size, mtime_ns, language, symbols, imports, exports,
                identifiers, definitions, indexed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rel, digest, st.st_size, st.st_mtime_ns, detect_language(rel),
                json.dumps([s.to_dict() for s in symbols]),
                json.dumps([s.name for s in symbols if s.kind == "import"]),
                json.dumps([s.name for s in symbols if s.exported]),
                json.dumps(_identifiers(text)), json.dumps(_definitions(symbols)), _now(),
            ),
        )
        self._db.commit()
        return True


def _identifiers(text: str) -> dict[str, list[int]]:
    """Deduped identifier → line list, bounded per file.

    Keys are stored case-sensitively; lookups try the exact name then uppercase.
    The scan is bounded so a pathological file cannot grow the index without end.
    """
    import re as _re

    token = _re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
    out: dict[str, list[int]] = {}
    for index, line in enumerate(text.splitlines()):
        if len(line) > 2_000:
            line = line[:2_000]
        for match in token.finditer(line):
            name = match.group(0)
            if len(name) > _MAX_IDENTIFIER:
                continue
            lines = out.get(name)
            if lines is None:
                if len(out) >= MAX_IDENTIFIERS_PER_FILE:
                    continue
                out[name] = [index + 1]
            elif len(lines) < MAX_MENTION_LINES:
                lines.append(index + 1)
    return out


def _definitions(symbols: list[Any]) -> dict[str, list[int]]:
    """A map symbol-name → declaration line(s), so a reference can be marked as a
    definition rather than a usage."""
    out: dict[str, list[int]] = {}
    for symbol in symbols:
        try:
            name = str(symbol.name)
            line = int(symbol.line)
        except AttributeError:
            continue
        out.setdefault(name, [])
        if line not in out[name]:
            out[name].append(line)
    return out


def index_workspace(ctx: FsContext, *, force: bool = False) -> dict[str, Any]:
    """Update the workspace index and report the result. `force` clears first."""
    index = WorkspaceIndex(ctx.ws)
    try:
        if force:
            index.clear()
        stats = index.update()
        return {"status": "ok", **index.status(), "update": stats.to_dict()}
    except sqlite3.Error as exc:
        raise err.FsError(err.INDEX_FAILED, f"The index could not be updated: {exc}") from exc
    finally:
        index.close()


def open_index(ws: Any) -> WorkspaceIndex:
    return WorkspaceIndex(ws)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "MAX_INDEX_FILES",
    "IndexStats",
    "WorkspaceIndex",
    "index_path",
    "index_workspace",
    "open_index",
]

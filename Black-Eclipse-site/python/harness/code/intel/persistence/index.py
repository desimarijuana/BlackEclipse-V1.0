"""The CIUE code index — a DEDICATED SQLite store, separate from agent memory.

Domain separation is a hard rule (AGENTS.md / CIUE §23): the agent's memory and
the runtime control database are NOT touched. This index lives in its OWN file,
`eclipse-code-index.db`, under `.black-eclipse/code-index/`, which is gitignored,
so indexing a user's folder never writes into that folder.

Entities (the contract's `projects`, `workspaces`, `files`, `symbols`,
`references`, `imports`, `exports`, `dependencies`, `call_edges`, `diagnostics`,
`languages`, `frameworks`) are normalized into a small set of relational tables
with indexes. Updates are INCREMENTAL: only files whose mtime/size/hash changed
are re-parsed; removed files cascade their rows away. A single edit never rebuilds
the repository.

The index is a CACHE, never an authority: every query can fall back to a live
scan, and a corrupt database is detected, backed up, recreated and re-indexed
(`recover()`), so the index is never a single point of failure.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from ..errors import IntelError, INDEX_CORRUPT, INDEX_FAILED, IntelUnavailable

SCHEMA_VERSION = 1
MAX_INDEX_FILES = 60_000
MAX_INDEX_FILE_BYTES = 2_000_000
MAX_SYMBOLS_PER_FILE = 4_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
  project_id   TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  root         TEXT NOT NULL,
  languages    TEXT NOT NULL DEFAULT '[]',
  frameworks   TEXT NOT NULL DEFAULT '[]',
  updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
  project_id  TEXT NOT NULL,
  rel         TEXT NOT NULL,
  language    TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  size        INTEGER NOT NULL,
  mtime_ns    INTEGER NOT NULL,
  line_count  INTEGER NOT NULL DEFAULT 0,
  symbols     INTEGER NOT NULL DEFAULT 0,
  imports     INTEGER NOT NULL DEFAULT 0,
  exports     INTEGER NOT NULL DEFAULT 0,
  engine      TEXT NOT NULL DEFAULT '',
  indexed_at  TEXT NOT NULL,
  PRIMARY KEY (project_id, rel)
);
CREATE TABLE IF NOT EXISTS symbols (
  id            TEXT PRIMARY KEY,
  project_id    TEXT NOT NULL,
  rel           TEXT NOT NULL,
  name          TEXT NOT NULL,
  qualified     TEXT NOT NULL DEFAULT '',
  kind          TEXT NOT NULL,
  language      TEXT NOT NULL,
  line          INTEGER NOT NULL,
  col           INTEGER NOT NULL,
  end_line      INTEGER NOT NULL DEFAULT 0,
  end_col       INTEGER NOT NULL DEFAULT 0,
  container     TEXT NOT NULL DEFAULT '',
  signature     TEXT NOT NULL DEFAULT '',
  exported      INTEGER NOT NULL DEFAULT 0,
  engine        TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS references_ (
  project_id  TEXT NOT NULL,
  name        TEXT NOT NULL,
  rel         TEXT NOT NULL,
  line        INTEGER NOT NULL,
  col         INTEGER NOT NULL DEFAULT 1,
  is_def      INTEGER NOT NULL DEFAULT 0,
  engine      TEXT NOT NULL DEFAULT 'index'
);
CREATE TABLE IF NOT EXISTS imports (
  project_id  TEXT NOT NULL,
  rel         TEXT NOT NULL,
  module      TEXT NOT NULL,
  line        INTEGER NOT NULL DEFAULT 0,
  external    INTEGER NOT NULL DEFAULT 0,
  resolved    TEXT
);
CREATE TABLE IF NOT EXISTS dependencies (
  project_id  TEXT NOT NULL,
  source      TEXT NOT NULL,
  target      TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'import',
  external    INTEGER NOT NULL DEFAULT 0,
  line        INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS call_edges (
  project_id  TEXT NOT NULL,
  caller      TEXT NOT NULL,
  callee      TEXT NOT NULL,
  caller_name TEXT NOT NULL DEFAULT '',
  callee_name TEXT NOT NULL DEFAULT '',
  rel         TEXT NOT NULL DEFAULT '',
  line        INTEGER NOT NULL DEFAULT 0,
  resolved    INTEGER NOT NULL DEFAULT 1,
  engine      TEXT NOT NULL DEFAULT 'ast'
);
CREATE TABLE IF NOT EXISTS diagnostics (
  project_id  TEXT NOT NULL,
  rel         TEXT NOT NULL,
  line        INTEGER NOT NULL,
  col         INTEGER NOT NULL,
  severity    TEXT NOT NULL,
  message     TEXT NOT NULL,
  source      TEXT NOT NULL DEFAULT '',
  code        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified ON symbols(qualified);
CREATE INDEX IF NOT EXISTS idx_symbols_rel ON symbols(rel);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_refs_name ON references_(name);
CREATE INDEX IF NOT EXISTS idx_refs_rel ON references_(rel);
CREATE INDEX IF NOT EXISTS idx_deps_source ON dependencies(source);
CREATE INDEX IF NOT EXISTS idx_deps_target ON dependencies(target);
CREATE INDEX IF NOT EXISTS idx_calls_caller ON call_edges(caller);
CREATE INDEX IF NOT EXISTS idx_calls_callee ON call_edges(callee);
-- `callers_of`/`callees_of` match the resolved-name column too (`caller_name` /
-- `callee_name`). Without these, the `col=? OR name=?` predicate falls back to a
-- full scan of call_edges — one such query per context symbol, seconds of block.
CREATE INDEX IF NOT EXISTS idx_calls_caller_name ON call_edges(caller_name);
CREATE INDEX IF NOT EXISTS idx_calls_callee_name ON call_edges(callee_name);
CREATE INDEX IF NOT EXISTS idx_diag_rel ON diagnostics(rel);
"""


def code_index_dir() -> Path:
    """`<app repo>/.black-eclipse/code-index` — never the user's folder.

    `HARNESS_CODE_INTEL_INDEX_DIR` relocates the store (the same override
    `load_config()` reports); the test suite points it at a temp dir so a run
    never leaves per-workspace DBs in the checkout.
    """
    override = os.environ.get("HARNESS_CODE_INTEL_INDEX_DIR")
    if override:
        path = Path(override)
    else:
        try:
            from ....eclipse_memory.config import repo_root  # noqa: PLC0415

            base = Path(repo_root())
        except Exception:  # noqa: BLE001
            base = Path(os.path.expanduser("~"))
        path = base / ".black-eclipse" / "code-index"
    path.mkdir(parents=True, exist_ok=True)
    return path


def code_index_path(project_id: str) -> Path:
    safe = "".join(ch for ch in project_id if ch.isalnum() or ch in "_-") or "default"
    return code_index_dir() / f"{safe}.db"


@dataclass
class IndexStats:
    scanned: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0
    symbols: int = 0
    duration_ms: int = 0
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned, "updated": self.updated, "removed": self.removed,
            "unchanged": self.unchanged, "symbols": self.symbols,
            "durationMs": self.duration_ms, "truncated": self.truncated,
        }


class CodeIndex:
    """A persistent, incremental code index over one project."""

    def __init__(self, project_id: str, *, path: Optional[Path] = None) -> None:
        self.project_id = project_id
        self.path = path or code_index_path(project_id)
        self._db = self._connect(self.path)
        # The connection is `check_same_thread=False`: several threads (the
        # background watcher loop, a synchronous index trigger, the LSP diagnostics
        # writer) may mutate this one project's rows. A multi-statement transaction
        # on a shared connection is not atomic across threads, so EVERY mutation is
        # serialized through this re-entrant lock. Reads are unaffected.
        self._write_lock = threading.RLock()
        try:
            self._init_schema()
        except sqlite3.DatabaseError:
            # Not a usable SQLite database (truncated/corrupt/foreign bytes). Back it
            # up and start clean — the index is a cache holding no user code, so this
            # never loses anything but a rebuild's work.
            self.recover()

    def _init_schema(self) -> None:
        with self._write_lock:
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.executescript(_SCHEMA)
            self._db.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._db.commit()

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        return sqlite3.connect(str(path), timeout=5.0, check_same_thread=False)

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:  # noqa: BLE001
            pass

    # ── integrity / recovery ──────────────────────────────────────────────────
    def integrity_ok(self) -> bool:
        """A cheap, honest health check: readable, integrity-clean AND schema-present.

        `PRAGMA integrity_check` alone can return "ok" on a file of non-database
        bytes in some SQLite builds; the schema probe (`meta` + `symbols`) makes the
        check unambiguous — a database that cannot answer the index's own queries is
        not a usable index.
        """
        try:
            row = self._db.execute("PRAGMA integrity_check").fetchone()
            if not row or str(row[0]).lower() != "ok":
                return False
            self._db.execute("SELECT 1 FROM meta LIMIT 1").fetchone()
            self._db.execute("SELECT 1 FROM symbols LIMIT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def recover(self) -> dict[str, Any]:
        """Back up a corrupt index, recreate it, and re-index from source.

        Never loses user code (the index holds none): the corrupt file is moved
        aside with a timestamp, a fresh schema is written and the caller re-indexes.
        """
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_suffix(f".corrupt-{stamp}.db")
        with self._write_lock:
            try:
                if self.path.exists():
                    self._db.close()
                    shutil.move(str(self.path), str(backup))
            except OSError:
                pass
            self._db = self._connect(self.path)
            self._init_schema()
        return {"recovered": True, "backup": str(backup)}

    # ── project registration ──────────────────────────────────────────────────
    def set_project(self, *, workspace_id: str, root: str, languages: list[str], frameworks: list[str]) -> None:
      with self._write_lock:
        self._db.execute(
            """INSERT OR REPLACE INTO projects
               (project_id, workspace_id, root, languages, frameworks, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (self.project_id, workspace_id, root, json.dumps(languages), json.dumps(frameworks), _now()),
        )
        self._db.commit()

    # ── indexing ──────────────────────────────────────────────────────────────
    def file_signature(self, rel: str) -> Optional[tuple[str, int, int]]:
        row = self._db.execute(
            "SELECT sha256, size, mtime_ns FROM files WHERE project_id=? AND rel=?",
            (self.project_id, rel),
        ).fetchone()
        if row is None:
            return None
        return (row["sha256"], int(row["size"]), int(row["mtime_ns"]))

    def known_files(self) -> set[str]:
        rows = self._db.execute(
            "SELECT rel FROM files WHERE project_id=?", (self.project_id,)
        ).fetchall()
        return {r["rel"] for r in rows}

    def upsert_file(
        self, *,
        rel: str, language: str, sha256: str, size: int, mtime_ns: int,
        line_count: int, engine: str,
        symbols: list[dict[str, Any]],
        imports: list[dict[str, Any]],
        dependencies: list[dict[str, Any]],
        references: list[dict[str, Any]],
        call_edges: Optional[list[dict[str, Any]]] = None,
    ) -> int:
        """Replace one file's rows atomically. Returns the symbol count."""
        pid = self.project_id
        with self._write_lock, self._db:
            self._delete_file_rows(rel)
            self._db.execute(
                """INSERT OR REPLACE INTO files
                   (project_id, rel, language, sha256, size, mtime_ns, line_count,
                    symbols, imports, exports, engine, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid, rel, language, sha256, int(size), int(mtime_ns), int(line_count),
                    len(symbols), len(imports), sum(1 for s in symbols if s.get("exported")),
                    engine, _now(),
                ),
            )
            for symbol in symbols[:MAX_SYMBOLS_PER_FILE]:
                self._db.execute(
                    """INSERT OR REPLACE INTO symbols
                       (id, project_id, rel, name, qualified, kind, language, line, col,
                        end_line, end_col, container, signature, exported, engine)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        symbol["id"], pid, rel, symbol["name"], symbol.get("qualifiedName", ""),
                        symbol["kind"], symbol.get("language", language), int(symbol["line"]),
                        int(symbol.get("column", 1)), int(symbol.get("endLine", 0) or 0),
                        int(symbol.get("endColumn", 0) or 0), symbol.get("container", ""),
                        symbol.get("signature", "")[:400], 1 if symbol.get("exported") else 0,
                        symbol.get("engine", engine),
                    ),
                )
            for item in imports:
                self._db.execute(
                    """INSERT INTO imports (project_id, rel, module, line, external, resolved)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (pid, rel, item.get("module", ""), int(item.get("line", 0)),
                     0 if item.get("resolved") else 1, item.get("resolved")),
                )
            for dep in dependencies:
                self._db.execute(
                    """INSERT INTO dependencies (project_id, source, target, kind, external, line)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (pid, dep.get("source", rel), dep.get("target", ""), dep.get("kind", "import"),
                     1 if dep.get("external") else 0, int(dep.get("line", 0))),
                )
            for ref in references:
                self._db.execute(
                    """INSERT INTO references_ (project_id, name, rel, line, col, is_def, engine)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (pid, ref["name"], rel, int(ref.get("line", 0)), int(ref.get("column", 1)),
                     1 if ref.get("definition") else 0, ref.get("engine", "index")),
                )
            for edge in call_edges or []:
                self._db.execute(
                    """INSERT INTO call_edges
                       (project_id, caller, callee, caller_name, callee_name, rel, line, resolved, engine)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pid, edge.get("caller", ""), edge.get("callee", ""), edge.get("callerName", ""),
                     edge.get("calleeName", ""), rel, int(edge.get("line", 0)),
                     1 if edge.get("resolved", True) else 0, edge.get("engine", "ast")),
                )
        return len(symbols)

    def touch_file(self, rel: str, *, mtime_ns: int, size: int) -> None:
        """Refresh a file's mtime/size without touching its rows (content identical)."""
        with self._write_lock:
            self._db.execute(
                "UPDATE files SET mtime_ns=?, size=?, indexed_at=? WHERE project_id=? AND rel=?",
                (int(mtime_ns), int(size), _now(), self.project_id, rel),
            )
            self._db.commit()

    def remove_file(self, rel: str) -> None:
        with self._write_lock, self._db:
            self._delete_file_rows(rel)

    def _delete_file_rows(self, rel: str) -> None:
        pid = self.project_id
        self._db.execute("DELETE FROM files WHERE project_id=? AND rel=?", (pid, rel))
        self._db.execute("DELETE FROM symbols WHERE project_id=? AND rel=?", (pid, rel))
        self._db.execute("DELETE FROM references_ WHERE project_id=? AND rel=?", (pid, rel))
        self._db.execute("DELETE FROM imports WHERE project_id=? AND rel=?", (pid, rel))
        self._db.execute("DELETE FROM dependencies WHERE project_id=? AND source=?", (pid, rel))
        self._db.execute("DELETE FROM call_edges WHERE project_id=? AND rel=?", (pid, rel))
        self._db.execute("DELETE FROM diagnostics WHERE project_id=? AND rel=?", (pid, rel))

    def clear(self) -> None:
        with self._write_lock, self._db:
            for table in ("files", "symbols", "references_", "imports", "dependencies",
                          "call_edges", "diagnostics"):
                self._db.execute(f"DELETE FROM {table} WHERE project_id=?", (self.project_id,))

    # ── queries ───────────────────────────────────────────────────────────────
    def symbol_count(self, rel: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS n FROM symbols WHERE project_id=? AND rel=?",
            (self.project_id, rel),
        ).fetchone()
        return int(row["n"]) if row else 0

    def find_symbols(
        self, query: str = "", *, kind: Optional[str] = None, language: Optional[str] = None,
        file: Optional[str] = None, limit: int = 200, exact: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["project_id = ?"]
        params: list[Any] = [self.project_id]
        if query:
            if exact:
                clauses.append("(name = ? OR qualified = ?)")
                params.extend([query, query])
            else:
                clauses.append("(name LIKE ? OR qualified LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if language:
            clauses.append("language = ?")
            params.append(language)
        if file:
            clauses.append("rel = ?")
            params.append(file)
        params.append(max(1, min(int(limit), 1_000)))
        rows = self._db.execute(
            f"SELECT * FROM symbols WHERE {' AND '.join(clauses)} ORDER BY rel, line LIMIT ?",
            tuple(params),
        ).fetchall()
        return [_symbol_row(r) for r in rows]

    def symbol_by_id(self, symbol_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM symbols WHERE id=?", (symbol_id,)
        ).fetchone()
        return _symbol_row(row) if row else None

    def implementations_of(self, name: str, *, limit: int = 200) -> list[dict[str, Any]]:
        """Symbols whose signature extends/implements `name` (structural hierarchy).

        A class/interfaces declaration carries its heritage in `signature`
        (`class StripePaymentProvider implements PaymentProvider`), so the index can
        answer "what implements X" without a language server. It is bounded and
        explicit; the manager reports the `index` engine so the caller knows it is
        structural, not semantic.
        """
        rows = self._db.execute(
            """SELECT * FROM symbols
               WHERE project_id=? AND (signature LIKE ? OR signature LIKE ?)
               AND kind IN ('class','interface','type')
               ORDER BY rel, line LIMIT ?""",
            (self.project_id, f"%extends {name}%", f"%implements {name}%",
             max(1, min(int(limit), 1_000))),
        ).fetchall()
        out = [_symbol_row(r) for r in rows]
        # A single class may implement several interfaces; keep the whole clause.
        return [s for s in out if re.search(rf"\b{re.escape(name)}\b", s.get("signature", ""))]

    def symbol_at(self, rel: str, line: int) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """SELECT * FROM symbols WHERE project_id=? AND rel=? AND line<=? 
               AND (end_line=0 OR end_line>=?) ORDER BY line DESC""",
            (self.project_id, rel, int(line), int(line)),
        ).fetchall()
        return [_symbol_row(r) for r in rows]

    def find_references(self, name: str, *, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """SELECT rel, line, col, is_def, engine FROM references_
               WHERE project_id=? AND name=? ORDER BY rel, line LIMIT ?""",
            (self.project_id, name, max(1, min(int(limit), 1_000))),
        ).fetchall()
        return [
            {"file": r["rel"], "line": int(r["line"]), "column": int(r["col"]),
             "definition": bool(r["is_def"]), "engine": r["engine"]}
            for r in rows
        ]

    def imports_of(self, rel: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM imports WHERE project_id=? AND rel=? ORDER BY line",
            (self.project_id, rel),
        ).fetchall()
        return [dict(r) for r in rows]

    def importers_of(self, target: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """SELECT DISTINCT source FROM dependencies
               WHERE project_id=? AND target=? AND kind='import' ORDER BY source""",
            (self.project_id, target),
        ).fetchall()
        return [r["source"] for r in rows]

    def dependencies_of(self, rel: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM dependencies WHERE project_id=? AND source=? ORDER BY line",
            (self.project_id, rel),
        ).fetchall()
        return [dict(r) for r in rows]

    def dependents_of(self, rel: str) -> list[str]:
        rows = self._db.execute(
            """SELECT DISTINCT source FROM dependencies
               WHERE project_id=? AND target=? ORDER BY source""",
            (self.project_id, rel),
        ).fetchall()
        return [r["source"] for r in rows]

    def callers_of(self, callee_name: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """SELECT * FROM call_edges WHERE project_id=? AND (callee_name=? OR callee=?)
               ORDER BY caller_name""",
            (self.project_id, callee_name, callee_name),
        ).fetchall()
        return [dict(r) for r in rows]

    def callees_of(self, caller_name: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """SELECT * FROM call_edges WHERE project_id=? AND (caller_name=? OR caller=?)
               ORDER BY callee_name""",
            (self.project_id, caller_name, caller_name),
        ).fetchall()
        return [dict(r) for r in rows]

    def all_call_edges(self, *, limit: int = 20_000) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM call_edges WHERE project_id=? LIMIT ?", (self.project_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def file_rows(self, *, limit: int = 5_000) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM files WHERE project_id=? ORDER BY rel LIMIT ?",
            (self.project_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def all_symbols(self, *, limit: int = 20_000) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM symbols WHERE project_id=? ORDER BY rel, line LIMIT ?",
            (self.project_id, limit),
        ).fetchall()
        return [_symbol_row(r) for r in rows]

    def languages(self) -> dict[str, int]:
        rows = self._db.execute(
            "SELECT language, COUNT(*) AS n FROM files WHERE project_id=? GROUP BY language",
            (self.project_id,),
        ).fetchall()
        return {r["language"]: int(r["n"]) for r in rows}

    def set_diagnostics(self, rel: str, diagnostics: list[dict[str, Any]]) -> None:
        with self._write_lock, self._db:
            self._db.execute(
                "DELETE FROM diagnostics WHERE project_id=? AND rel=?", (self.project_id, rel),
            )
            for diag in diagnostics[:500]:
                self._db.execute(
                    """INSERT INTO diagnostics (project_id, rel, line, col, severity, message, source, code)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (self.project_id, rel, int(diag.get("line", 0)), int(diag.get("column", 1)),
                     diag.get("severity", "information"), str(diag.get("message", ""))[:1_000],
                     diag.get("source", ""), str(diag.get("code", ""))),
                )

    def diagnostics_for(self, rel: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM diagnostics WHERE project_id=? AND rel=? ORDER BY line",
            (self.project_id, rel),
        ).fetchall()
        return [dict(r) for r in rows]

    def status(self) -> dict[str, Any]:
        files = self._db.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(size),0) AS bytes FROM files WHERE project_id=?",
            (self.project_id,),
        ).fetchone()
        symbols = self._db.execute(
            "SELECT COUNT(*) AS n FROM symbols WHERE project_id=?", (self.project_id,),
        ).fetchone()
        refs = self._db.execute(
            "SELECT COUNT(*) AS n FROM references_ WHERE project_id=?", (self.project_id,),
        ).fetchone()
        return {
            "status": "ok",
            "indexPath": str(self.path),
            "engine": "sqlite",
            "projectId": self.project_id,
            "fileCount": int(files["n"]),
            "totalBytes": int(files["bytes"]),
            "symbolCount": int(symbols["n"]),
            "referenceCount": int(refs["n"]),
            "languages": self.languages(),
        }


def open_code_index(project_id: str, *, path: Optional[Path] = None) -> CodeIndex:
    """Open (and, if needed, recover) a code index. A corrupt index is rebuilt."""
    index = CodeIndex(project_id, path=path)
    if not index.integrity_ok():
        index.recover()
    return index


def _symbol_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "name": row["name"], "qualifiedName": row["qualified"] or row["name"],
        "kind": row["kind"], "file": row["rel"], "line": int(row["line"]),
        "column": int(row["col"]), "endLine": int(row["end_line"]), "endColumn": int(row["end_col"]),
        "language": row["language"], "container": row["container"],
        "signature": row["signature"], "exported": bool(row["exported"]),
        "engine": row["engine"],
    }


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "CodeIndex",
    "IndexStats",
    "MAX_INDEX_FILES",
    "SCHEMA_VERSION",
    "code_index_dir",
    "code_index_path",
    "open_code_index",
]

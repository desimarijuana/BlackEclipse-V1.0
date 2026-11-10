"""The source catalog: one row per file, plus the incremental text index.

This is a dedicated SQLite file (``.black-eclipse/sources/sources.db``), never
``agent-memory.db`` and never ``jdds.db``. It is written by exactly one scanner
thread and read by any number of query threads (WAL mode), so a long scan never
blocks a search and a search never blocks a scan.

Only metadata lives here. The bytes stay where they are.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import SourceConfig, load_config
from .contracts import FileRecord, Hit, RootRecord

SCHEMA_VERSION = 1


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "replace")).hexdigest()[:16]


def normalize_root(path: str) -> str:
    resolved = Path(os.path.abspath(os.path.expanduser(path))).resolve()
    return str(resolved)


def normalize_relpath(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def extension_of(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return suffix[1:] if suffix.startswith(".") else suffix


class Catalog:
    """SQLite-backed catalog + FTS + optional vector table."""

    def __init__(self, config: Optional[SourceConfig] = None) -> None:
        self.config = config or load_config()
        self.path = self.config.db_path
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            self.path, timeout=30.0, check_same_thread=False
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("PRAGMA busy_timeout=30000")
        self._init_schema()
        self._fts = self._fts_available()

    # ── lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        with self._lock:
            try:
                self._db.close()
            except Exception:  # noqa: BLE001 - closing twice is harmless
                pass

    def _init_schema(self) -> None:
        with self._lock:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS Meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS Root (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    createdAt TEXT NOT NULL,
                    lastScanAt TEXT,
                    fileCount INTEGER NOT NULL DEFAULT 0,
                    totalBytes INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'READY',
                    error TEXT,
                    scanEpoch INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS File (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rootId TEXT NOT NULL,
                    relpath TEXT NOT NULL,
                    name TEXT NOT NULL,
                    ext TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    inode TEXT,
                    rootPath TEXT NOT NULL DEFAULT '',
                    magic TEXT,
                    klass TEXT NOT NULL DEFAULT 'unknown',
                    scannedAt TEXT NOT NULL,
                    seenEpoch INTEGER NOT NULL DEFAULT 0,
                    indexedAt TEXT,
                    chunkCount INTEGER NOT NULL DEFAULT 0,
                    contentHash TEXT,
                    UNIQUE(rootId, relpath)
                );
                CREATE INDEX IF NOT EXISTS idx_file_root ON File(rootId, relpath);
                CREATE INDEX IF NOT EXISTS idx_file_class ON File(rootId, klass);
                CREATE INDEX IF NOT EXISTS idx_file_size ON File(size);
                CREATE INDEX IF NOT EXISTS idx_file_mtime ON File(mtime);
                CREATE INDEX IF NOT EXISTS idx_file_name ON File(name);
                CREATE TABLE IF NOT EXISTS Vector (
                    fileId INTEGER NOT NULL,
                    ord INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    dims INTEGER NOT NULL,
                    vec BLOB NOT NULL,
                    PRIMARY KEY(fileId, ord, model)
                );
                CREATE TABLE IF NOT EXISTS Job (
                    id TEXT PRIMARY KEY,
                    rootId TEXT,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    startedAt TEXT NOT NULL,
                    finishedAt TEXT,
                    processed INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                """
            )
            self._db.commit()
            self._ensure_column("File", "rootPath", "TEXT NOT NULL DEFAULT ''")
            self._db.execute(
                "INSERT OR IGNORE INTO Meta(key, value) VALUES('schemaVersion', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._db.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        columns = {row[1] for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _fts_available(self) -> bool:
        try:
            self._db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS ChunkFts USING fts5("
                "text, fileId UNINDEXED, rootId UNINDEXED, ord UNINDEXED, "
                "startOff UNINDEXED, endOff UNINDEXED, page UNINDEXED, "
                "tokenize='unicode61')"
            )
            self._db.commit()
            return True
        except sqlite3.OperationalError:
            return False

    @property
    def fts_available(self) -> bool:
        return self._fts

    # ── roots ────────────────────────────────────────────────────────────────

    def add_root(self, path: str, label: Optional[str] = None) -> RootRecord:
        from .errors import SourceError

        normalized = normalize_root(path)
        target = Path(normalized)
        if not target.exists():
            raise SourceError("ROOT_NOT_FOUND", f"{normalized} does not exist")
        if not target.is_dir():
            raise SourceError("ROOT_NOT_DIRECTORY", f"{normalized} is not a directory")
        with self._lock:
            count = self._db.execute("SELECT COUNT(*) FROM Root").fetchone()[0]
            if count >= self.config.max_roots:
                raise SourceError("ROOT_LIMIT", f"at most {self.config.max_roots} roots")
            existing = self._db.execute("SELECT * FROM Root WHERE path = ?", (normalized,)).fetchone()
            if existing:
                return _root_record(existing)
            root_id = _hash_id(normalized.lower())
            self._db.execute(
                "INSERT INTO Root(id, path, label, createdAt, status) VALUES(?,?,?,?,?)",
                (root_id, normalized, label or target.name or normalized, now_iso(), "READY"),
            )
            self._db.commit()
            row = self._db.execute("SELECT * FROM Root WHERE id = ?", (root_id,)).fetchone()
            return _root_record(row)

    def remove_root(self, root_id: str, *, purge_index: bool = True) -> bool:
        with self._lock:
            row = self._db.execute("SELECT * FROM Root WHERE id = ?", (root_id,)).fetchone()
            if not row:
                return False
            if purge_index and self._fts:
                self._db.execute("DELETE FROM ChunkFts WHERE rootId = ?", (root_id,))
            self._db.execute("DELETE FROM Vector WHERE fileId IN (SELECT id FROM File WHERE rootId = ?)", (root_id,))
            self._db.execute("DELETE FROM File WHERE rootId = ?", (root_id,))
            self._db.execute("DELETE FROM Root WHERE id = ?", (root_id,))
            self._db.commit()
            return True

    def list_roots(self) -> list[RootRecord]:
        rows = self._db.execute("SELECT * FROM Root ORDER BY createdAt").fetchall()
        return [_root_record(r) for r in rows]

    def get_root(self, root_id: str) -> Optional[RootRecord]:
        row = self._db.execute("SELECT * FROM Root WHERE id = ?", (root_id,)).fetchone()
        return _root_record(row) if row else None

    def find_root(self, root_id: Optional[str], root_path: Optional[str]) -> Optional[RootRecord]:
        if root_id:
            return self.get_root(root_id)
        if root_path:
            normalized = normalize_root(root_path)
            row = self._db.execute("SELECT * FROM Root WHERE path = ?", (normalized,)).fetchone()
            return _root_record(row) if row else None
        return None

    def root_for_path(self, path: str) -> Optional[tuple[RootRecord, str]]:
        """Longest-prefix match of an absolute path against the registered roots."""
        target = normalize_root(path)
        target_cmp = target.lower() if os.name == "nt" else target
        best: Optional[tuple[RootRecord, str]] = None
        for root in self.list_roots():
            root_cmp = root.path.lower() if os.name == "nt" else root.path
            if target_cmp == root_cmp or target_cmp.startswith(root_cmp + os.sep):
                rel = os.path.relpath(target, root.path)
                if best is None or len(root.path) > len(best[0].path):
                    best = (root, normalize_relpath(rel))
        return best

    def begin_scan(self, root_id: str) -> int:
        with self._lock:
            row = self._db.execute("SELECT scanEpoch FROM Root WHERE id = ?", (root_id,)).fetchone()
            if not row:
                from .errors import SourceError

                raise SourceError("ROOT_UNKNOWN", "the root is not registered")
            epoch = int(row[0]) + 1
            self._db.execute(
                "UPDATE Root SET scanEpoch = ?, status = 'SCANNING', error = NULL WHERE id = ?",
                (epoch, root_id),
            )
            self._db.commit()
            return epoch

    def upsert_file(self, root_id: str, entry: dict[str, Any], epoch: int) -> str:
        """Insert/update one file. Returns 'added' | 'updated' | 'unchanged'."""
        with self._lock:
            row = self._db.execute(
                "SELECT id, size, mtime, seenEpoch FROM File WHERE rootId = ? AND relpath = ?",
                (root_id, entry["relpath"]),
            ).fetchone()
            if row is None:
                self._db.execute(
                    "INSERT INTO File(rootId, relpath, name, ext, size, mtime, inode, rootPath,"
                    " magic, klass, scannedAt, seenEpoch) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        root_id, entry["relpath"], entry["name"], entry["ext"],
                        entry["size"], entry["mtime"], entry.get("inode"),
                        entry.get("root_path") or "", entry.get("magic"),
                        entry.get("klass") or "unknown", now_iso(), epoch,
                    ),
                )
                return "added"
            if float(row["size"]) == entry["size"] and float(row["mtime"]) == entry["mtime"]:
                if int(row["seenEpoch"]) != epoch:
                    self._db.execute(
                        "UPDATE File SET seenEpoch = ? WHERE id = ?", (epoch, row["id"])
                    )
                return "unchanged"
            self._db.execute(
                "UPDATE File SET name=?, ext=?, size=?, mtime=?, inode=?, rootPath=?, magic=?,"
                " klass=?, scannedAt=?, seenEpoch=?, indexedAt=NULL, chunkCount=0 WHERE id=?",
                (
                    entry["name"], entry["ext"], entry["size"], entry["mtime"],
                    entry.get("inode"), entry.get("root_path") or "", entry.get("magic"),
                    entry.get("klass") or "unknown", now_iso(), epoch, row["id"],
                ),
            )
            if self._fts:
                self._db.execute("DELETE FROM ChunkFts WHERE fileId = ?", (row["id"],))
            return "updated"

    def finish_scan(self, root_id: str, epoch: int) -> int:
        """Remove files not seen in this epoch. Returns how many were removed."""
        with self._lock:
            stale = self._db.execute(
                "SELECT id FROM File WHERE rootId = ? AND seenEpoch != ?", (root_id, epoch)
            ).fetchall()
            for row in stale:
                if self._fts:
                    self._db.execute("DELETE FROM ChunkFts WHERE fileId = ?", (row["id"],))
                self._db.execute("DELETE FROM Vector WHERE fileId = ?", (row["id"],))
            self._db.execute("DELETE FROM File WHERE rootId = ? AND seenEpoch != ?", (root_id, epoch))
            stats = self._db.execute(
                "SELECT COUNT(*), COALESCE(SUM(size),0) FROM File WHERE rootId = ?", (root_id,)
            ).fetchone()
            self._db.execute(
                "UPDATE Root SET lastScanAt=?, fileCount=?, totalBytes=?, status='READY' WHERE id=?",
                (now_iso(), int(stats[0]), int(stats[1]), root_id),
            )
            self._db.commit()
            return len(stale)

    def set_root_error(self, root_id: str, message: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE Root SET status='ERROR', error=? WHERE id=?", (message[:500], root_id)
            )
            self._db.commit()

    # ── files ────────────────────────────────────────────────────────────────

    def get_file(self, root_id: str, relpath: str) -> Optional[FileRecord]:
        row = self._db.execute(
            "SELECT * FROM File WHERE rootId = ? AND relpath = ?",
            (root_id, normalize_relpath(relpath)),
        ).fetchone()
        return _file_record(row) if row else None

    def get_file_by_id(self, file_id: int) -> Optional[FileRecord]:
        row = self._db.execute("SELECT * FROM File WHERE id = ?", (file_id,)).fetchone()
        return _file_record(row) if row else None

    def list_files(
        self,
        *,
        root_ids: Optional[Iterable[str]] = None,
        klass: Optional[str] = None,
        path_prefix: Optional[str] = None,
        name_like: Optional[str] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        modified_after: Optional[float] = None,
        modified_before: Optional[float] = None,
        limit: int = 200,
        order: str = "mtime_desc",
    ) -> list[FileRecord]:
        where, params = _file_where(
            root_ids=root_ids, klass=klass, path_prefix=path_prefix, name_like=name_like,
            min_size=min_size, max_size=max_size, modified_after=modified_after,
            modified_before=modified_before,
        )
        order_sql = {
            "mtime_desc": "mtime DESC",
            "mtime_asc": "mtime ASC",
            "size_desc": "size DESC",
            "size_asc": "size ASC",
            "name": "name COLLATE NOCASE ASC",
            "path": "relpath COLLATE NOCASE ASC",
        }.get(order, "mtime DESC")
        rows = self._db.execute(
            f"SELECT * FROM File{where} ORDER BY {order_sql} LIMIT ?",
            (*params, max(1, min(limit, 10_000))),
        ).fetchall()
        return [_file_record(r) for r in rows]

    def count_files(self, *, root_ids: Optional[Iterable[str]] = None, klass: Optional[str] = None) -> int:
        where, params = _file_where(root_ids=root_ids, klass=klass)
        row = self._db.execute(f"SELECT COUNT(*) FROM File{where}", tuple(params)).fetchone()
        return int(row[0]) if row else 0

    def candidates_for_scan(
        self,
        *,
        root_ids: Optional[Iterable[str]] = None,
        klass: Optional[str] = None,
        path_prefix: Optional[str] = None,
        name_like: Optional[str] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        modified_after: Optional[float] = None,
        limit: int = 20_000,
    ) -> list[FileRecord]:
        return self.list_files(
            root_ids=root_ids, klass=klass, path_prefix=path_prefix, name_like=name_like,
            min_size=min_size, max_size=max_size, modified_after=modified_after,
            limit=limit, order="size_desc",
        )

    def mark_indexed(self, file_id: int, chunks: int, content_hash: Optional[str] = None) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE File SET indexedAt=?, chunkCount=?, contentHash=? WHERE id=?",
                (now_iso(), chunks, content_hash, file_id),
            )
            self._db.commit()

    def indexed_files(self, *, root_ids: Optional[Iterable[str]] = None) -> list[FileRecord]:
        where, params = _file_where(root_ids=root_ids)
        clause = f"{where} AND indexedAt IS NOT NULL" if where else " WHERE indexedAt IS NOT NULL"
        rows = self._db.execute(f"SELECT * FROM File{clause}", tuple(params)).fetchall()
        return [_file_record(r) for r in rows]

    # ── chunks / FTS ─────────────────────────────────────────────────────────

    def replace_chunks(self, file: FileRecord, chunks: list[dict[str, Any]]) -> int:
        if not self._fts:
            return 0
        with self._lock:
            self._db.execute("DELETE FROM ChunkFts WHERE fileId = ?", (file.id,))
            self._db.executemany(
                "INSERT INTO ChunkFts(text, fileId, rootId, ord, startOff, endOff, page)"
                " VALUES(?,?,?,?,?,?,?)",
                [
                    (
                        c["text"], file.id, file.root_id, int(c["ord"]),
                        int(c.get("start", 0)), int(c.get("end", 0)), c.get("page"),
                    )
                    for c in chunks
                ],
            )
            self._db.commit()
            return len(chunks)

    def delete_chunks(self, file_id: int) -> None:
        if not self._fts:
            return
        with self._lock:
            self._db.execute("DELETE FROM ChunkFts WHERE fileId = ?", (file_id,))
            self._db.commit()

    def search_chunks(
        self,
        query: str,
        *,
        root_ids: Optional[Iterable[str]] = None,
        path_prefix: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """FTS5 BM25 search. Returns rows with snippet + file metadata."""
        if not self._fts or not query.strip():
            return []
        match = _fts_query(query)
        if not match:
            return []
        clauses = ["ChunkFts MATCH ?"]
        params: list[Any] = [match]
        if root_ids:
            ids = list(root_ids)
            clauses.append("File.rootId IN (" + ",".join("?" for _ in ids) + ")")
            params.extend(ids)
        if path_prefix:
            clauses.append("File.relpath LIKE ?")
            params.append(normalize_relpath(path_prefix) + "%")
        params.append(max(1, min(limit, self.config.max_results)))
        sql = (
            "SELECT ChunkFts.fileId AS fileId, ChunkFts.ord AS ord,"
            " ChunkFts.startOff AS startOff, ChunkFts.page AS page,"
            " snippet(ChunkFts, 0, '', '', ' … ', 24) AS snippet,"
            " bm25(ChunkFts) AS rank,"
            " File.rootId AS rootId, File.relpath AS relpath, File.name AS name,"
            " File.klass AS klass, File.size AS size, File.mtime AS mtime"
            " FROM ChunkFts JOIN File ON File.id = ChunkFts.fileId"
            f" WHERE {' AND '.join(clauses)} ORDER BY rank LIMIT ?"
        )
        try:
            rows = self._db.execute(sql, tuple(params)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in rows]

    def chunk_count(self) -> int:
        if not self._fts:
            return 0
        row = self._db.execute("SELECT COUNT(*) FROM ChunkFts").fetchone()
        return int(row[0]) if row else 0

    # ── vectors ─────────────────────────────────────────────────────────────

    def put_vectors(self, file_id: int, vectors: list[tuple[int, list[float]]], *, model: str) -> int:
        if not vectors:
            return 0
        dims = len(vectors[0][1])
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO Vector(fileId, ord, model, dims, vec) VALUES(?,?,?,?,?)",
                [
                    (file_id, int(ordinal), model, dims, _pack_vector(vector))
                    for ordinal, vector in vectors
                ],
            )
            self._db.commit()
            return len(vectors)

    def vectors_for_files(
        self, file_ids: Iterable[int], *, model: str, limit: int = 200_000
    ) -> list[tuple[int, int, bytes]]:
        ids = list(file_ids)
        if not ids:
            return []
        out: list[tuple[int, int, bytes]] = []
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            rows = self._db.execute(
                "SELECT fileId, ord, vec FROM Vector WHERE model = ? AND fileId IN ("
                + ",".join("?" for _ in chunk) + f") LIMIT {int(limit)}",
                (model, *chunk),
            ).fetchall()
            out.extend((int(r[0]), int(r[1]), bytes(r[2])) for r in rows)
        return out

    def clear_vectors(self, *, root_ids: Optional[Iterable[str]] = None, model: Optional[str] = None) -> int:
        with self._lock:
            where: list[str] = []
            params: list[Any] = []
            if root_ids:
                ids = list(root_ids)
                where.append("fileId IN (SELECT id FROM File WHERE rootId IN ("
                             + ",".join("?" for _ in ids) + "))")
                params.extend(ids)
            if model:
                where.append("model = ?")
                params.append(model)
            clause = (" WHERE " + " AND ".join(where)) if where else ""
            cursor = self._db.execute(f"DELETE FROM Vector{clause}", tuple(params))
            self._db.commit()
            return int(cursor.rowcount or 0)

    # ── stats / jobs ────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        roots = self._db.execute("SELECT COUNT(*) FROM Root").fetchone()[0]
        files = self._db.execute("SELECT COUNT(*), COALESCE(SUM(size),0) FROM File").fetchone()
        by_class = self._db.execute(
            "SELECT klass, COUNT(*), COALESCE(SUM(size),0) FROM File GROUP BY klass"
        ).fetchall()
        indexed = self._db.execute(
            "SELECT COUNT(*) FROM File WHERE indexedAt IS NOT NULL"
        ).fetchone()[0]
        return {
            "roots": int(roots),
            "files": int(files[0]),
            "bytes": int(files[1]),
            "indexedFiles": int(indexed),
            "chunks": self.chunk_count(),
            "fts": self._fts,
            "classes": {
                row[0]: {"files": int(row[1]), "bytes": int(row[2])} for row in by_class
            },
        }

    def recent_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM Job ORDER BY startedAt DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(r) for r in rows]


# ── helpers ─────────────────────────────────────────────────────────────────


def _root_record(row: sqlite3.Row) -> RootRecord:
    return RootRecord(
        id=row["id"], path=row["path"], label=row["label"],
        created_at=row["createdAt"], last_scan_at=row["lastScanAt"],
        file_count=int(row["fileCount"]), total_bytes=int(row["totalBytes"]),
        status=row["status"], error=row["error"],
    )


def _file_record(row: sqlite3.Row) -> FileRecord:
    keys = row.keys()
    return FileRecord(
        id=int(row["id"]), root_id=row["rootId"], relpath=row["relpath"],
        name=row["name"], ext=row["ext"], size=int(row["size"]),
        mtime=float(row["mtime"]), klass=row["klass"], magic=row["magic"],
        indexed_at=row["indexedAt"], chunk_count=int(row["chunkCount"] or 0),
        scanned_at=row["scannedAt"],
        root_path=(row["rootPath"] if "rootPath" in keys and row["rootPath"] else ""),
    )


def _file_where(
    *,
    root_ids: Optional[Iterable[str]] = None,
    klass: Optional[str] = None,
    path_prefix: Optional[str] = None,
    name_like: Optional[str] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    modified_after: Optional[float] = None,
    modified_before: Optional[float] = None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if root_ids:
        ids = list(root_ids)
        clauses.append("rootId IN (" + ",".join("?" for _ in ids) + ")")
        params.extend(ids)
    if klass:
        clauses.append("klass = ?")
        params.append(klass)
    if path_prefix:
        clauses.append("relpath LIKE ?")
        params.append(normalize_relpath(path_prefix) + "%")
    if name_like:
        clauses.append("name LIKE ?")
        params.append(f"%{name_like}%")
    if min_size is not None:
        clauses.append("size >= ?")
        params.append(int(min_size))
    if max_size is not None:
        clauses.append("size <= ?")
        params.append(int(max_size))
    if modified_after is not None:
        clauses.append("mtime >= ?")
        params.append(float(modified_after))
    if modified_before is not None:
        clauses.append("mtime <= ?")
        params.append(float(modified_before))
    return ((" WHERE " + " AND ".join(clauses)) if clauses else ""), params


def _fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 AND query (quoted terms, prefix last)."""
    terms = [t for t in text.replace('"', " ").split() if t.strip()][:12]
    if not terms:
        return ""
    parts = [f'"{t}"' for t in terms[:-1]]
    parts.append(f'"{terms[-1]}"*')
    return " AND ".join(parts)


def _pack_vector(vector: list[float]) -> bytes:
    import struct

    return struct.pack(f"<{len(vector)}f", *[float(v) for v in vector])


def unpack_vector(blob: bytes) -> list[float]:
    import struct

    if not blob:
        return []
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob[: count * 4]))


__all__ = [
    "Catalog", "SCHEMA_VERSION", "now_iso", "normalize_root", "normalize_relpath",
    "extension_of", "unpack_vector",
]

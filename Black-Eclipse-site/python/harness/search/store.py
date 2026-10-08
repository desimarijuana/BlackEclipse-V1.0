"""SearchIndexStore — the durable vector + full-text index.

A DEDICATED SQLite file (``<repo>/.black-eclipse/search/search.db`` or
``ECLIPSE_SEARCH_DB_PATH``), mirroring the code-index precedent rather than
sharing ``agent-memory.db``: the vector/FTS index is a derived artifact and
should not bloat the operational store. Source rows are read from their own
stores by the indexer; this store only holds the search projection.

Security invariant: retrieval NEVER scans the whole index and filters afterward.
A ``SearchScope`` is compiled to a SQL predicate that is part of every candidate
query, so an unauthorized row is never a candidate.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

from ..persistence import now_iso
from .config import SearchConfig, default_db_path
from .contracts import ChunkRecord, DocumentRecord, IndexState, SearchScope, SectionRecord
from .errors import SearchStoreError

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS SearchMeta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS SearchDocument (
  documentId TEXT PRIMARY KEY,
  sourceType TEXT NOT NULL DEFAULT 'unknown',
  sourceId TEXT NOT NULL DEFAULT '',
  namespace TEXT NOT NULL DEFAULT 'research',
  title TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  uri TEXT, mimeType TEXT, language TEXT DEFAULT 'en',
  entityType TEXT, entityId TEXT,
  documentType TEXT,
  publisher TEXT,
  publishedAt TEXT, retrievedAt TEXT, effectiveAt TEXT,
  validFrom TEXT, validTo TEXT,
  workspaceId TEXT, ownerId TEXT,
  visibility TEXT NOT NULL DEFAULT 'public',
  authority REAL NOT NULL DEFAULT 0,
  contentHash TEXT,
  state TEXT NOT NULL DEFAULT 'PENDING',
  stateError TEXT,
  chunkCount INTEGER NOT NULL DEFAULT 0,
  metadata TEXT,
  createdAt TEXT NOT NULL,
  updatedAt TEXT NOT NULL,
  indexedAt TEXT
);
CREATE INDEX IF NOT EXISTS idx_sdoc_ns ON SearchDocument(namespace);
CREATE INDEX IF NOT EXISTS idx_sdoc_entity ON SearchDocument(entityType, entityId);
CREATE INDEX IF NOT EXISTS idx_sdoc_source ON SearchDocument(sourceType, sourceId);
CREATE INDEX IF NOT EXISTS idx_sdoc_hash ON SearchDocument(contentHash);
CREATE INDEX IF NOT EXISTS idx_sdoc_state ON SearchDocument(state);
CREATE INDEX IF NOT EXISTS idx_sdoc_ws ON SearchDocument(workspaceId, visibility);
CREATE INDEX IF NOT EXISTS idx_sdoc_pub ON SearchDocument(publishedAt);
CREATE INDEX IF NOT EXISTS idx_sdoc_doctype ON SearchDocument(documentType);

-- Indexed document metadata for SQL-side filtering (tickers/sectors/industries
-- and arbitrary scalar `meta` equality). This is what lets a filter be applied
-- in the candidate query rather than post-filtered in Python.
CREATE TABLE IF NOT EXISTS SearchDocumentMeta (
  documentId TEXT NOT NULL,
  key        TEXT NOT NULL,
  value      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sdocmeta_lookup ON SearchDocumentMeta(key, value);
CREATE INDEX IF NOT EXISTS idx_sdocmeta_doc ON SearchDocumentMeta(documentId);

CREATE TABLE IF NOT EXISTS SearchSection (
  sectionId TEXT PRIMARY KEY,
  documentId TEXT NOT NULL,
  parentId TEXT,
  heading TEXT NOT NULL DEFAULT '',
  sectionPath TEXT NOT NULL DEFAULT '',
  ordinal INTEGER NOT NULL DEFAULT 0,
  metadata TEXT,
  FOREIGN KEY(documentId) REFERENCES SearchDocument(documentId) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ssection_doc ON SearchSection(documentId);

CREATE TABLE IF NOT EXISTS SearchChunk (
  chunkId TEXT PRIMARY KEY,
  documentId TEXT NOT NULL,
  sectionId TEXT,
  ordinal INTEGER NOT NULL DEFAULT 0,
  kind TEXT NOT NULL DEFAULT 'paragraph',
  page INTEGER,
  content TEXT NOT NULL,
  tokenCount INTEGER NOT NULL DEFAULT 0,
  contentHash TEXT,
  metadata TEXT,
  createdAt TEXT NOT NULL,
  FOREIGN KEY(documentId) REFERENCES SearchDocument(documentId) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_schunk_doc ON SearchChunk(documentId);
CREATE INDEX IF NOT EXISTS idx_schunk_section ON SearchChunk(sectionId);
CREATE INDEX IF NOT EXISTS idx_schunk_hash ON SearchChunk(contentHash);

CREATE TABLE IF NOT EXISTS SearchVector (
  chunkId TEXT NOT NULL,
  modelKey TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  version TEXT NOT NULL,
  dims INTEGER NOT NULL,
  vector BLOB NOT NULL,
  createdAt TEXT NOT NULL,
  PRIMARY KEY (chunkId, modelKey)
);
CREATE INDEX IF NOT EXISTS idx_svec_model ON SearchVector(modelKey);

-- ANN backend metadata: one row per vector space that has a sqlite-vec table.
-- The physical table name is derived from the model key so different models
-- (and dimension counts) never share a vector space.
CREATE TABLE IF NOT EXISTS SearchVectorAnnMeta (
  modelKey   TEXT PRIMARY KEY,
  tableName  TEXT NOT NULL,
  dims       INTEGER NOT NULL,
  metric     TEXT NOT NULL,
  updatedAt  TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS SearchChunkFts USING fts5(
  content,
  chunkId UNINDEXED,
  tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS EmbeddingCache (
  cacheKey TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  version TEXT NOT NULL,
  dims INTEGER NOT NULL,
  vector BLOB NOT NULL,
  createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS SearchIndexJob (
  jobId TEXT PRIMARY KEY,
  documentId TEXT,
  operation TEXT NOT NULL DEFAULT 'index',
  state TEXT NOT NULL DEFAULT 'PENDING',
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  namespace TEXT,
  payload TEXT,
  createdAt TEXT NOT NULL,
  updatedAt TEXT NOT NULL,
  startedAt TEXT,
  finishedAt TEXT
);
CREATE INDEX IF NOT EXISTS idx_sjob_state ON SearchIndexJob(state);

CREATE TABLE IF NOT EXISTS SearchEvent (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  queryId TEXT, runId TEXT, agentId TEXT, workspaceId TEXT, namespace TEXT,
  mode TEXT, latencyMs REAL, candidates INTEGER, results INTEGER,
  deduped INTEGER,
  cacheHit INTEGER, provider TEXT, model TEXT, detail TEXT,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sevent_created ON SearchEvent(createdAt);
CREATE INDEX IF NOT EXISTS idx_sevent_kind ON SearchEvent(kind);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


class SearchIndexStore:
    def __init__(self, path: Optional[str] = None, *, config: Optional[SearchConfig] = None) -> None:
        self.config = config or SearchConfig()
        self.path = path or self.config.db_path or default_db_path()
        Path(os.path.dirname(self.path) or ".").mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._write_lock = threading.RLock()
        self.vec_available = self._load_vector_extension()
        try:
            self._init_schema()
        except sqlite3.DatabaseError:
            self.recover()

    def _load_vector_extension(self) -> bool:
        """Load the optional sqlite-vec ANN extension. Absent ⇒ brute-force."""
        try:
            import sqlite_vec  # noqa: PLC0415

            self._db.enable_load_extension(True)
            sqlite_vec.load(self._db)
            self._db.enable_load_extension(False)
            return True
        except Exception:  # noqa: BLE001 - ANN is an optional acceleration
            return False

    def _init_schema(self) -> None:
        with self._write_lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.execute("PRAGMA busy_timeout=30000")
            self._db.executescript(_SCHEMA)
            self._db.execute(
                "INSERT OR REPLACE INTO SearchMeta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._migrate_columns()
            self._db.commit()

    def _migrate_columns(self) -> None:
        """Additive column migrations for databases created before a column."""
        added: dict[str, list[tuple[str, str]]] = {
            "SearchDocument": [("documentType", "TEXT")],
        }
        for table, columns in added.items():
            existing = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, ddl in columns:
                if name not in existing:
                    self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    @property
    def connection(self) -> sqlite3.Connection:
        return self._db

    def integrity_ok(self) -> bool:
        try:
            if self._db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return False
            self._db.execute("SELECT 1 FROM SearchMeta LIMIT 1").fetchone()
            return True
        except Exception:  # noqa: BLE001
            return False

    def recover(self) -> None:
        """Rename a corrupt/unusable database and start a clean one."""
        try:
            self._db.close()
        except Exception:  # noqa: BLE001
            pass
        stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        try:
            if os.path.exists(self.path):
                os.replace(self.path, f"{self.path}.corrupt-{stamp}")
        except OSError:
            pass
        self._db = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self.vec_available = self._load_vector_extension()
        self._init_schema()

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:  # noqa: BLE001
            pass

    def schema_version(self) -> int:
        row = self._db.execute("SELECT value FROM SearchMeta WHERE key='schema_version'").fetchone()
        return int(row["value"]) if row else 0

    # ── Documents ───────────────────────────────────────────────────────────

    def upsert_document(self, doc: DocumentRecord, *, state: str = IndexState.PENDING.value) -> None:
        now = now_iso()
        with self._write_lock, self._db:
            self._db.execute(
                """
                INSERT INTO SearchDocument (documentId, sourceType, sourceId, namespace, title, description,
                  uri, mimeType, language, entityType, entityId, documentType, publisher, publishedAt, retrievedAt,
                  effectiveAt, validFrom, validTo, workspaceId, ownerId, visibility, authority, contentHash, state,
                  stateError, chunkCount, metadata, createdAt, updatedAt, indexedAt)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(documentId) DO UPDATE SET
                  sourceType=excluded.sourceType, sourceId=excluded.sourceId, namespace=excluded.namespace,
                  title=excluded.title, description=excluded.description, uri=excluded.uri,
                  mimeType=excluded.mimeType, language=excluded.language, entityType=excluded.entityType,
                  entityId=excluded.entityId, documentType=excluded.documentType, publisher=excluded.publisher,
                  publishedAt=excluded.publishedAt,
                  retrievedAt=excluded.retrievedAt, effectiveAt=excluded.effectiveAt,
                  validFrom=excluded.validFrom, validTo=excluded.validTo,
                  workspaceId=excluded.workspaceId, ownerId=excluded.ownerId,
                  visibility=excluded.visibility, authority=excluded.authority,
                  contentHash=excluded.contentHash, state=excluded.state, updatedAt=excluded.updatedAt,
                  metadata=excluded.metadata
                """,
                (
                    doc.document_id, doc.source_type, doc.source_id, doc.namespace, doc.title, doc.description,
                    doc.uri, doc.mime_type, doc.language, doc.entity_type, doc.entity_id, doc.document_type,
                    doc.publisher, doc.published_at, doc.retrieved_at, doc.effective_at, doc.valid_from,
                    doc.valid_to, doc.workspace_id, doc.owner_id, doc.visibility, doc.authority, doc.content_hash,
                    state, None, 0, _json(doc.metadata), now, now, None,
                ),
            )
            self._write_meta_rows(doc)
            # Replace this document's projection atomically: remove the old
            # chunks (and their vectors + ANN rows) so a re-index of a shorter
            # document cannot leave orphaned vectors behind.
            old_chunks = [
                r["chunkId"]
                for r in self._db.execute(
                    "SELECT chunkId FROM SearchChunk WHERE documentId = ?", (doc.document_id,)
                ).fetchall()
            ]
            self._delete_ann_for_chunks(old_chunks)
            self._db.execute("DELETE FROM SearchVector WHERE chunkId IN "
                             "(SELECT chunkId FROM SearchChunk WHERE documentId = ?)", (doc.document_id,))
            self._db.execute("DELETE FROM SearchSection WHERE documentId = ?", (doc.document_id,))
            self._db.execute("DELETE FROM SearchChunk WHERE documentId = ?", (doc.document_id,))
            self._db.execute("DELETE FROM SearchChunkFts WHERE chunkId IN "
                             "(SELECT chunkId FROM SearchChunk WHERE documentId = ?)", (doc.document_id,))
    def set_document_state(self, document_id: str, state: str, *, error: Optional[str] = None,
                           indexed_at: Optional[str] = None, chunk_count: Optional[int] = None) -> None:
        with self._write_lock, self._db:
            self._db.execute(
                "UPDATE SearchDocument SET state=?, stateError=?, updatedAt=?, "
                "indexedAt=COALESCE(?, indexedAt), chunkCount=COALESCE(?, chunkCount) WHERE documentId=?",
                (state, error, now_iso(), indexed_at, chunk_count, document_id),
            )

    def get_document(self, document_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM SearchDocument WHERE documentId = ?", (document_id,)).fetchone()
        return self._document_dict(row) if row else None

    def find_by_source(self, source_type: str, source_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM SearchDocument WHERE sourceType=? AND sourceId=? ORDER BY updatedAt DESC LIMIT 1",
            (source_type, source_id),
        ).fetchone()
        return self._document_dict(row) if row else None

    def find_by_content_hash(self, content_hash: str) -> Optional[dict[str, Any]]:
        if not content_hash:
            return None
        row = self._db.execute(
            "SELECT * FROM SearchDocument WHERE contentHash=? ORDER BY updatedAt DESC LIMIT 1", (content_hash,)
        ).fetchone()
        return self._document_dict(row) if row else None

    def list_documents(self, *, namespace: Optional[str] = None, state: Optional[str] = None,
                       limit: int = 100) -> list[dict[str, Any]]:
        clauses, params = [], []
        if namespace:
            clauses.append("namespace = ?")
            params.append(namespace)
        if state:
            clauses.append("state = ?")
            params.append(state)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            f"SELECT * FROM SearchDocument{where} ORDER BY updatedAt DESC LIMIT ?", (*params, limit)
        ).fetchall()
        return [self._document_dict(r) for r in rows]

    def delete_document(self, document_id: str) -> bool:
        with self._write_lock, self._db:
            chunk_ids = [
                r["chunkId"]
                for r in self._db.execute(
                    "SELECT chunkId FROM SearchChunk WHERE documentId=?", (document_id,)
                ).fetchall()
            ]
            self._delete_ann_for_chunks(chunk_ids)
            self._db.execute("DELETE FROM SearchChunkFts WHERE chunkId IN "
                             "(SELECT chunkId FROM SearchChunk WHERE documentId=?)", (document_id,))
            self._db.execute("DELETE FROM SearchVector WHERE chunkId IN "
                             "(SELECT chunkId FROM SearchChunk WHERE documentId=?)", (document_id,))
            cur = self._db.execute("DELETE FROM SearchDocument WHERE documentId=?", (document_id,))
            self._db.execute("DELETE FROM SearchSection WHERE documentId=?", (document_id,))
            self._db.execute("DELETE FROM SearchChunk WHERE documentId=?", (document_id,))
            self._db.execute("DELETE FROM SearchDocumentMeta WHERE documentId=?", (document_id,))
        return cur.rowcount > 0

    def _delete_ann_for_chunks(self, chunk_ids: list[str]) -> None:
        if not self.vec_available or not chunk_ids:
            return
        tables = [r["tableName"] for r in self._db.execute(
            "SELECT tableName FROM SearchVectorAnnMeta").fetchall()]
        for table in tables:
            for chunk_id in chunk_ids:
                try:
                    self._db.execute(f"DELETE FROM {table} WHERE chunkId = ?", (chunk_id,))
                except Exception:  # noqa: BLE001 - a missing/corrupt ANN table is non-fatal
                    continue

    def mark_missing(self, namespace: str, keep_ids: set[str]) -> int:
        """Mark documents in a namespace as DELETED when no longer present."""
        rows = self._db.execute("SELECT documentId FROM SearchDocument WHERE namespace=?", (namespace,)).fetchall()
        stale = [r["documentId"] for r in rows if r["documentId"] not in keep_ids]
        with self._write_lock, self._db:
            for doc_id in stale:
                self._db.execute("UPDATE SearchDocument SET state=?, updatedAt=? WHERE documentId=?",
                                 (IndexState.DELETED.value, now_iso(), doc_id))
        return len(stale)

    def _write_meta_rows(self, doc: DocumentRecord) -> None:
        """Project filterable metadata into `SearchDocumentMeta` for SQL filtering.

        List-valued fields (tickers/sectors/industries) expand to one row per
        item; scalar fields become one row so `meta` equality is indexed too.
        """
        self._db.execute("DELETE FROM SearchDocumentMeta WHERE documentId = ?", (doc.document_id,))
        rows: list[tuple[str, str, str]] = []
        for key, value in (doc.metadata or {}).items():
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    if isinstance(item, (str, int, float, bool)):
                        rows.append((doc.document_id, str(key), str(item)))
            elif isinstance(value, (str, int, float, bool)):
                rows.append((doc.document_id, str(key), str(value)))
        if rows:
            self._db.executemany(
                "INSERT INTO SearchDocumentMeta (documentId, key, value) VALUES (?,?,?)", rows
            )

    # ── Sections / chunks ───────────────────────────────────────────────────

    def save_sections(self, sections: list[SectionRecord]) -> int:
        if not sections:
            return 0
        with self._write_lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO SearchSection (sectionId, documentId, parentId, heading, sectionPath, "
                "ordinal, metadata) VALUES (?,?,?,?,?,?,?)",
                [
                    (s.section_id, s.document_id, s.parent_id, s.heading, s.section_path, s.ordinal, _json(s.metadata))
                    for s in sections
                ],
            )
        return len(sections)

    def save_chunks(self, chunks: list[ChunkRecord]) -> int:
        if not chunks:
            return 0
        now = now_iso()
        with self._write_lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO SearchChunk (chunkId, documentId, sectionId, ordinal, kind, page, content, "
                "tokenCount, contentHash, metadata, createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (c.chunk_id, c.document_id, c.section_id, c.ordinal, c.kind, c.page, c.content,
                     c.token_count, c.content_hash, _json(c.metadata), now)
                    for c in chunks
                ],
            )
            self._db.executemany(
                "DELETE FROM SearchChunkFts WHERE chunkId = ?", [(c.chunk_id,) for c in chunks]
            )
            self._db.executemany(
                "INSERT INTO SearchChunkFts (content, chunkId) VALUES (?,?)",
                [(c.content, c.chunk_id) for c in chunks],
            )
        return len(chunks)

    def get_chunk(self, chunk_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM SearchChunk WHERE chunkId=?", (chunk_id,)).fetchone()
        return self._chunk_dict(row) if row else None

    def list_chunks(self, document_id: str, *, limit: int = 2_000) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM SearchChunk WHERE documentId=? ORDER BY ordinal ASC LIMIT ?", (document_id, limit)
        ).fetchall()
        return [self._chunk_dict(r) for r in rows]

    # ── Vectors ─────────────────────────────────────────────────────────────

    def store_vectors(self, entries: list[tuple[str, list[float]]], *, model_key: str, provider: str,
                      model: str, version: str, dims: int,
                      acl_by_chunk: Optional[dict[str, list[str]]] = None) -> int:
        if not entries:
            return 0
        from .embeddings.cache import vector_to_blob

        now = now_iso()
        with self._write_lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO SearchVector (chunkId, modelKey, provider, model, version, dims, vector, "
                "createdAt) VALUES (?,?,?,?,?,?,?,?)",
                [(chunk_id, model_key, provider, model, version, dims, vector_to_blob(vec), now)
                 for chunk_id, vec in entries],
            )
        self._store_ann_vectors(entries, model_key=model_key, dims=dims, acl_by_chunk=acl_by_chunk or {})
        return len(entries)

    # ── ANN (sqlite-vec) ────────────────────────────────────────────────────

    @staticmethod
    def _ann_table_name(model_key: str) -> str:
        import hashlib

        digest = hashlib.sha1(model_key.encode("utf-8")).hexdigest()[:20]
        return f"sv_{digest}"

    def _ann_meta(self, model_key: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM SearchVectorAnnMeta WHERE modelKey=?", (model_key,)
        ).fetchone()
        return _row(row) if row else None

    def _ensure_ann_table(self, model_key: str, dims: int) -> Optional[str]:
        """Create the vec0 table for a vector space. Returns the table name or None."""
        if not self.vec_available or dims <= 0:
            return None
        existing = self._ann_meta(model_key)
        if existing:
            if int(existing["dims"]) != int(dims):
                raise SearchStoreError(
                    f"vector space {model_key} declared {dims} dims but was indexed with "
                    f"{existing['dims']} — refusing to mix incompatible vectors"
                )
            return existing["tableName"]
        table = self._ann_table_name(model_key)
        # One physical table per vector space so dimensions never collide.
        self._db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0("
            "chunkId text, aclKey text, embedding float[" + str(int(dims)) + "] distance_metric=cosine)"
        )
        self._db.execute(
            "INSERT OR REPLACE INTO SearchVectorAnnMeta (modelKey, tableName, dims, metric, updatedAt) "
            "VALUES (?,?,?,?,?)",
            (model_key, table, int(dims), "cosine", now_iso()),
        )
        return table

    @staticmethod
    def acl_keys(visibility: str, workspace_id: Optional[str], owner_id: Optional[str]) -> list[str]:
        """The authorization buckets a row can be visible through.

        Mirrors `scope_clause` exactly but as a set of equality keys, so an ANN
        KNN can be restricted to the caller's authorized buckets BEFORE scoring
        (never scan-everything-then-filter). A row appears once per bucket it can
        be reached through; a query unions the buckets the caller may read.
        """
        keys: list[str] = []
        if visibility == "public":
            keys.append("public")
        if workspace_id:
            keys.append(f"w:{workspace_id}")
        if owner_id:
            keys.append(f"o:{owner_id}")
        if not keys:
            # A non-public row with no workspace/owner is reachable by no one.
            keys.append("restricted")
        return keys

    def _store_ann_vectors(self, entries: list[tuple[str, list[float]]], *, model_key: str, dims: int,
                           acl_by_chunk: dict[str, list[str]]) -> None:
        if not self.vec_available or not entries:
            return
        try:
            import sqlite_vec  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return
        with self._write_lock, self._db:
            table = self._ensure_ann_table(model_key, dims)
            if table is None:
                return
            for chunk_id, vector in entries:
                self._db.execute(f"DELETE FROM {table} WHERE chunkId = ?", (chunk_id,))
                acl = acl_by_chunk.get(chunk_id) or ["public"]
                for key in acl:
                    self._db.execute(
                        f"INSERT INTO {table} (chunkId, aclKey, embedding) VALUES (?,?,?)",
                        (chunk_id, key, sqlite_vec.serialize_float32([float(x) for x in vector])),
                    )

    def ann_search(self, query_vector: list[float], model_key: str, acl_keys: Optional[list[str]],
                   limit: int) -> Optional[list[tuple[str, float]]]:
        """Approximate nearest-neighbour search restricted to authorized buckets.

        `acl_keys=None` means an unrestricted scope. Returns
        `(chunkId, cosine_similarity)` or None when ANN is unavailable, so the
        caller falls back to brute-force cosine.
        """
        if not self.vec_available or not query_vector:
            return None
        meta = self._ann_meta(model_key)
        if meta is None:
            return None
        try:
            import sqlite_vec  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return None
        table = meta["tableName"]
        args: list[Any] = [sqlite_vec.serialize_float32([float(x) for x in query_vector])]
        where = "embedding MATCH ?"
        if acl_keys is not None:
            if not acl_keys:
                return []
            placeholders = ",".join("?" for _ in acl_keys)
            where += f" AND aclKey IN ({placeholders})"
            args.extend(acl_keys)
        args.append(max(1, limit))
        sql = f"SELECT chunkId, distance FROM {table} WHERE {where} ORDER BY distance LIMIT ?"
        try:
            rows = self._db.execute(sql, tuple(args)).fetchall()
        except Exception:  # noqa: BLE001 - a malformed query falls back to brute force
            return None
        seen: set[str] = set()
        out: list[tuple[str, float]] = []
        for row in rows:
            chunk_id = row["chunkId"]
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            out.append((chunk_id, 1.0 - float(row["distance"])))
        return out

    def ann_available_for(self, model_key: str) -> bool:
        return bool(self.vec_available and self._ann_meta(model_key))

    def rebuild_ann(self, model_key: Optional[str] = None) -> int:
        """Rebuild the ANN tables from `SearchVector` (e.g. after enabling it)."""
        if not self.vec_available:
            return 0
        import struct as _struct

        rebuilt = 0
        query = "SELECT modelKey, chunkId, dims, vector FROM SearchVector"
        params: tuple = ()
        if model_key:
            query += " WHERE modelKey=?"
            params = (model_key,)
        rows = self._db.execute(query, params).fetchall()
        grouped: dict[str, list[tuple[str, list[float], int, str]]] = {}
        for row in rows:
            grouped.setdefault(row["modelKey"], []).append(
                (row["chunkId"], list(_struct.unpack(f"<{row['dims']}f", row["vector"])), int(row["dims"]), "")
            )
        for key, items in grouped.items():
            dims = items[0][2]
            acl_map: dict[str, list[str]] = {}
            for chunk_id, _vec, _dims, _unused in items:
                acl_map[chunk_id] = self._acl_for_chunk(chunk_id)
            self._store_ann_vectors(
                [(cid, vec) for cid, vec, _d, _u in items], model_key=key, dims=dims, acl_by_chunk=acl_map
            )
            rebuilt += len(items)
        return rebuilt

    def _acl_for_chunk(self, chunk_id: str) -> list[str]:
        row = self._db.execute(
            "SELECT d.visibility AS visibility, d.workspaceId AS workspaceId, d.ownerId AS ownerId "
            "FROM SearchChunk c JOIN SearchDocument d ON d.documentId = c.documentId WHERE c.chunkId=?",
            (chunk_id,),
        ).fetchone()
        if row is None:
            return ["restricted"]
        return self.acl_keys(row["visibility"] or "public", row["workspaceId"], row["ownerId"])

    def vectors_for(self, chunk_ids: Iterable[str], model_key: str) -> dict[str, bytes]:
        ids = list(chunk_ids)
        found: dict[str, bytes] = {}
        for start in range(0, len(ids), 400):
            batch = ids[start : start + 400]
            placeholders = ",".join("?" for _ in batch)
            rows = self._db.execute(
                f"SELECT chunkId, vector FROM SearchVector WHERE modelKey=? AND chunkId IN ({placeholders})",
                (model_key, *batch),
            ).fetchall()
            for row in rows:
                found[row["chunkId"]] = row["vector"]
        return found

    def vector_models(self) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT modelKey, provider, model, version, dims, COUNT(*) AS n FROM SearchVector "
            "GROUP BY modelKey ORDER BY n DESC"
        ).fetchall()
        return [_row(r) for r in rows]

    def delete_vectors_for_model(self, model_key: str) -> int:
        with self._write_lock, self._db:
            cur = self._db.execute("DELETE FROM SearchVector WHERE modelKey=?", (model_key,))
        return cur.rowcount

    # ── Jobs ────────────────────────────────────────────────────────────────

    def enqueue_job(self, job_id: str, *, document_id: Optional[str], operation: str = "index",
                    namespace: Optional[str] = None, payload: Optional[dict[str, Any]] = None) -> None:
        now = now_iso()
        with self._write_lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO SearchIndexJob (jobId, documentId, operation, state, attempts, error, "
                "namespace, payload, createdAt, updatedAt) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (job_id, document_id, operation, IndexState.PENDING.value, 0, None, namespace,
                 _json(payload or {}), now, now),
            )

    def claim_job(self, job_id: str) -> bool:
        with self._write_lock, self._db:
            cur = self._db.execute(
                "UPDATE SearchIndexJob SET state=?, attempts=attempts+1, startedAt=?, updatedAt=? "
                "WHERE jobId=? AND state IN (?,?)",
                (IndexState.PROCESSING.value, now_iso(), now_iso(), job_id,
                 IndexState.PENDING.value, IndexState.RETRYING.value),
            )
        return cur.rowcount > 0

    def finish_job(self, job_id: str, state: str, *, error: Optional[str] = None) -> None:
        with self._write_lock, self._db:
            self._db.execute(
                "UPDATE SearchIndexJob SET state=?, error=?, finishedAt=?, updatedAt=? WHERE jobId=?",
                (state, error, now_iso(), now_iso(), job_id),
            )

    def list_jobs(self, *, state: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if state:
            rows = self._db.execute(
                "SELECT * FROM SearchIndexJob WHERE state=? ORDER BY updatedAt DESC LIMIT ?", (state, limit)
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM SearchIndexJob ORDER BY updatedAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row(r) for r in rows]

    def job_counts(self) -> dict[str, int]:
        rows = self._db.execute("SELECT state, COUNT(*) AS n FROM SearchIndexJob GROUP BY state").fetchall()
        return {r["state"]: r["n"] for r in rows}

    # ── Observability ───────────────────────────────────────────────────────

    def record_event(self, kind: str, data: dict[str, Any]) -> None:
        with self._write_lock, self._db:
            self._db.execute(
                "INSERT INTO SearchEvent (kind, queryId, runId, agentId, workspaceId, namespace, mode, latencyMs, "
                "candidates, results, deduped, cacheHit, provider, model, detail, createdAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    kind, data.get("queryId"), data.get("runId"), data.get("agentId"), data.get("workspaceId"),
                    data.get("namespace"), data.get("mode"), data.get("latencyMs"), data.get("candidates"),
                    data.get("results"), data.get("deduped"),
                    1 if data.get("cacheHit") else 0, data.get("provider"), data.get("model"),
                    _json(data.get("detail") or {}), now_iso(),
                ),
            )

    def recent_events(self, *, limit: int = 50, kind: Optional[str] = None) -> list[dict[str, Any]]:
        if kind:
            rows = self._db.execute(
                "SELECT * FROM SearchEvent WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, limit)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM SearchEvent ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_row(r) for r in rows]

    def prune_events(self, keep: int) -> int:
        with self._write_lock, self._db:
            cur = self._db.execute(
                "DELETE FROM SearchEvent WHERE id NOT IN (SELECT id FROM SearchEvent ORDER BY id DESC LIMIT ?)",
                (max(0, keep),),
            )
        return cur.rowcount

    def stats(self) -> dict[str, Any]:
        def count(sql: str, params: tuple = ()) -> int:
            return self._db.execute(sql, params).fetchone()[0]

        return {
            "path": self.path,
            "schemaVersion": self.schema_version(),
            "annBackend": self.vec_available,
            "documents": count("SELECT COUNT(*) FROM SearchDocument WHERE state != 'DELETED'"),
            "chunks": count("SELECT COUNT(*) FROM SearchChunk"),
            "vectors": count("SELECT COUNT(*) FROM SearchVector"),
            "cacheEntries": count("SELECT COUNT(*) FROM EmbeddingCache"),
            "jobs": self.job_counts(),
            "states": {r["state"]: r["n"] for r in self._db.execute(
                "SELECT state, COUNT(*) AS n FROM SearchDocument GROUP BY state").fetchall()},
            "vectorModels": self.vector_models(),
        }

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _document_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = _row(row)
        data["metadata"] = _loads(data.get("metadata"), {})
        return data

    @staticmethod
    def _chunk_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = _row(row)
        data["metadata"] = _loads(data.get("metadata"), {})
        return data


def scope_clause(scope: SearchScope, *, alias: str = "d") -> tuple[str, list[Any]]:
    """Compile an authorization scope into a SQL predicate (never post-filter).

    Non-operator callers see ``public`` rows plus rows in their own workspace,
    plus rows they own. An operator (or an explicitly unrestricted scope) sees
    everything — but that is an explicit, auditable choice.
    """
    if scope.unrestricted or scope.is_operator:
        return "1=1", []
    allowed = scope.allowed_visibilities()
    placeholders = ",".join("?" for _ in allowed)
    alternatives = [f"{alias}.visibility = 'public'"]
    params: list[Any] = []
    if scope.workspace_id:
        alternatives.append(f"({alias}.workspaceId = ? AND {alias}.visibility IN ({placeholders}))")
        params.append(scope.workspace_id)
        params.extend(allowed)
    if scope.owner_id:
        alternatives.append(f"{alias}.ownerId = ?")
        params.append(scope.owner_id)
    return "(" + " OR ".join(alternatives) + ")", params


def scope_acl_keys(scope: SearchScope) -> Optional[list[str]]:
    """The ANN authorization buckets a scope may read (None = unrestricted).

    The bucket vocabulary mirrors `SearchIndexStore.acl_keys` exactly, so an ANN
    KNN restricted to these keys can never surface an unauthorized vector.
    """
    if scope.unrestricted or scope.is_operator:
        return None
    keys: list[str] = ["public"]
    if scope.workspace_id:
        keys.append(f"w:{scope.workspace_id}")
    if scope.owner_id:
        keys.append(f"o:{scope.owner_id}")
    return keys


__all__ = ["SCHEMA_VERSION", "SearchIndexStore", "scope_acl_keys", "scope_clause"]

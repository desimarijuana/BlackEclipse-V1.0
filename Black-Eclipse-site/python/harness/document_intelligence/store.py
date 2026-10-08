"""Document store — the durable document intelligence tables on `agent-memory.db`.

Bound to the ONE `AgentMemoryStore` sqlite connection (never `jdds.db`, never
`eclipse-memory.db`), same pattern as `vision/storage.py`, `research/web_store.py`
and `jobs/store.py`. DDL is idempotent (`CREATE TABLE IF NOT EXISTS`) and a small
`_ADDED_COLUMNS` migration mirrors `persistence.py`, so a table added later never
breaks an existing database.

Tables: documents, versions, chunks (+ an optional FTS5 index), tables, images,
entities, OCR runs, processing jobs and a content-hash cache. Raw bytes are never
stored here — binaries live in the vision asset store; only metadata and text are
relational.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any, Optional

from .errors import DocumentError, DocumentErrorClass

#: Common English + finance stopwords, so a natural-language "query" (rather than
#: a keyword query) still finds the right passages deterministically.
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "was", "were", "be", "been", "being", "at", "by", "with", "as", "that", "this",
    "these", "those", "it", "its", "from", "into", "over", "under", "what", "how",
    "which", "who", "whom", "when", "where", "why", "did", "does", "do", "has",
    "have", "had", "can", "could", "should", "would", "will", "about", "per",
    "total", "any", "all", "some", "many", "much", "there", "their", "they",
})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS DiDocument (
    documentId TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    mimeType TEXT NOT NULL,
    title TEXT,
    fileName TEXT,
    sha256 TEXT,
    contentHash TEXT,
    byteSize INTEGER NOT NULL DEFAULT 0,
    pageCount INTEGER NOT NULL DEFAULT 0,
    sheetCount INTEGER NOT NULL DEFAULT 0,
    currentVersion INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'READY',
    textMethod TEXT NOT NULL DEFAULT 'none',
    confidence REAL NOT NULL DEFAULT 0,
    metadata TEXT,
    dates TEXT,
    parser TEXT,
    runId TEXT,
    sourceRef TEXT,
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_di_doc_hash ON DiDocument(contentHash);
CREATE INDEX IF NOT EXISTS idx_di_doc_sha ON DiDocument(sha256);
CREATE INDEX IF NOT EXISTS idx_di_doc_run ON DiDocument(runId);

CREATE TABLE IF NOT EXISTS DiVersion (
    documentId TEXT NOT NULL,
    version INTEGER NOT NULL,
    sha256 TEXT,
    contentHash TEXT,
    byteSize INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'READY',
    textMethod TEXT NOT NULL DEFAULT 'none',
    confidence REAL NOT NULL DEFAULT 0,
    pageCount INTEGER NOT NULL DEFAULT 0,
    sheetCount INTEGER NOT NULL DEFAULT 0,
    createdAt TEXT NOT NULL,
    publicationDate TEXT,
    sourceRef TEXT,
    PRIMARY KEY (documentId, version)
);

CREATE TABLE IF NOT EXISTS DiJob (
    jobId TEXT PRIMARY KEY,
    documentId TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'DISCOVERED',
    stage TEXT,
    progress REAL NOT NULL DEFAULT 0,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_di_job_status ON DiJob(status);
CREATE INDEX IF NOT EXISTS idx_di_job_doc ON DiJob(documentId);

CREATE TABLE IF NOT EXISTS DiChunk (
    chunkId TEXT PRIMARY KEY,
    documentId TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    kind TEXT NOT NULL DEFAULT 'paragraph',
    page INTEGER,
    sheet TEXT,
    section TEXT,
    blockId TEXT,
    tableId TEXT,
    cell TEXT,
    text TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'native',
    confidence REAL NOT NULL DEFAULT 0,
    contentHash TEXT,
    ord INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_di_chunk_doc ON DiChunk(documentId, version);
CREATE INDEX IF NOT EXISTS idx_di_chunk_page ON DiChunk(page);
CREATE INDEX IF NOT EXISTS idx_di_chunk_kind ON DiChunk(kind);

CREATE TABLE IF NOT EXISTS DiTable (
    tableId TEXT NOT NULL,
    documentId TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    page INTEGER,
    sheet TEXT,
    headers TEXT,
    rows TEXT,
    provenance TEXT,
    bbox TEXT,
    PRIMARY KEY (documentId, version, tableId)
);
CREATE INDEX IF NOT EXISTS idx_di_table_doc ON DiTable(documentId, version);

CREATE TABLE IF NOT EXISTS DiImage (
    imageId TEXT NOT NULL,
    documentId TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    assetId TEXT,
    contentType TEXT,
    page INTEGER,
    slide INTEGER,
    ocrText TEXT,
    caption TEXT,
    sha256 TEXT,
    width INTEGER,
    height INTEGER,
    byteSize INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (documentId, version, imageId)
);
CREATE INDEX IF NOT EXISTS idx_di_image_asset ON DiImage(assetId);

CREATE TABLE IF NOT EXISTS DiEntity (
    id TEXT PRIMARY KEY,
    documentId TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    type TEXT NOT NULL,
    value TEXT NOT NULL,
    page INTEGER,
    blockId TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    evidenceId TEXT,
    createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_di_entity_doc ON DiEntity(documentId, version);
CREATE INDEX IF NOT EXISTS idx_di_entity_value ON DiEntity(value);

CREATE TABLE IF NOT EXISTS DiOcrRun (
    id TEXT PRIMARY KEY,
    documentId TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    page INTEGER,
    engine TEXT,
    method TEXT NOT NULL DEFAULT 'ocr',
    confidence REAL NOT NULL DEFAULT 0,
    text TEXT,
    createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_di_ocr_doc ON DiOcrRun(documentId, version);

CREATE TABLE IF NOT EXISTS DiCache (
    contentHash TEXT PRIMARY KEY,
    documentId TEXT NOT NULL,
    kind TEXT,
    createdAt TEXT NOT NULL,
    expiresAt TEXT
);

CREATE TABLE IF NOT EXISTS DiMeta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "DiDocument": [("runId", "TEXT"), ("sourceRef", "TEXT")],
    "DiChunk": [("cell", "TEXT"), ("tableId", "TEXT")],
    "DiImage": [("slide", "INTEGER")],
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class DocumentStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self) -> sqlite3.Connection:
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        for table, columns in _ADDED_COLUMNS.items():
            existing = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, ddl in columns:
                if name not in existing:
                    self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        self._db.commit()

    # ── documents ───────────────────────────────────────────────────────────────

    def save_document(self, ir: Any, *, run_id: Optional[str] = None, source_ref: Optional[str] = None,
                      status: str = "READY") -> None:
        now = now_iso()
        existing = self.get_document(ir.document_id)
        with self._db:
            self._db.execute(
                """
                INSERT INTO DiDocument (documentId, kind, mimeType, title, fileName, sha256, contentHash,
                    byteSize, pageCount, sheetCount, currentVersion, status, textMethod, confidence,
                    metadata, dates, parser, runId, sourceRef, createdAt, updatedAt)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(documentId) DO UPDATE SET
                    title=excluded.title, contentHash=excluded.contentHash, sha256=excluded.sha256,
                    byteSize=excluded.byteSize, pageCount=excluded.pageCount, sheetCount=excluded.sheetCount,
                    currentVersion=excluded.currentVersion, status=excluded.status, textMethod=excluded.textMethod,
                    confidence=excluded.confidence, metadata=excluded.metadata, dates=excluded.dates,
                    parser=excluded.parser, updatedAt=excluded.updatedAt
                """,
                (
                    ir.document_id, ir.kind, ir.mime_type, ir.title, ir.file_name, ir.sha256, ir.content_hash,
                    ir.byte_size, ir.page_count, ir.sheet_count, ir.version, status, ir.text_method, ir.confidence,
                    json.dumps(ir.metadata, default=str), json.dumps(ir.dates.to_dict()), ir.parser,
                    run_id, source_ref, existing["createdAt"] if existing else now, now,
                ),
            )
            self._db.execute(
                """
                INSERT INTO DiVersion (documentId, version, sha256, contentHash, byteSize, status, textMethod,
                    confidence, pageCount, sheetCount, createdAt, publicationDate, sourceRef)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(documentId, version) DO UPDATE SET
                    sha256=excluded.sha256, contentHash=excluded.contentHash, byteSize=excluded.byteSize,
                    status=excluded.status, textMethod=excluded.textMethod, confidence=excluded.confidence,
                    pageCount=excluded.pageCount, sheetCount=excluded.sheetCount,
                    publicationDate=excluded.publicationDate
                """,
                (
                    ir.document_id, ir.version, ir.sha256, ir.content_hash, ir.byte_size, status, ir.text_method,
                    ir.confidence, ir.page_count, ir.sheet_count, now, ir.dates.publication_date, source_ref,
                ),
            )

    def get_document(self, document_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM DiDocument WHERE documentId = ?", (document_id,)).fetchone()
        return _row_doc(row) if row else None

    def list_documents(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM DiDocument ORDER BY updatedAt DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_doc(r) for r in rows]

    def find_by_hash(self, content_hash: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM DiDocument WHERE contentHash = ? ORDER BY updatedAt DESC LIMIT 1", (content_hash,)
        ).fetchone()
        return _row_doc(row) if row else None

    def delete_document(self, document_id: str) -> bool:
        with self._db:
            for table in ("DiChunk", "DiTable", "DiImage", "DiEntity", "DiOcrRun", "DiVersion", "DiJob"):
                self._db.execute(f"DELETE FROM {table} WHERE documentId = ?", (document_id,))
            cursor = self._db.execute("DELETE FROM DiDocument WHERE documentId = ?", (document_id,))
        return cursor.rowcount > 0

    def list_versions(self, document_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM DiVersion WHERE documentId = ? ORDER BY version ASC", (document_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── chunks ─────────────────────────────────────────────────────────────────────

    def save_chunks(self, chunks: list[Any]) -> int:
        if not chunks:
            return 0
        with self._db:
            self._db.executemany(
                """
                INSERT INTO DiChunk (chunkId, documentId, version, kind, page, sheet, section, blockId,
                    tableId, cell, text, method, confidence, contentHash, ord)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(chunkId) DO UPDATE SET text=excluded.text, confidence=excluded.confidence
                """,
                [
                    (c.chunk_id, c.document_id, c.version, c.kind, c.page, c.sheet, c.section, c.block_id,
                     c.table_id, c.cell, c.text, c.method, c.confidence, c.content_hash, c.order)
                    for c in chunks
                ],
            )
        return len(chunks)

    def search_chunks(self, query: str, *, document_id: Optional[str] = None, version: Optional[int] = None,
                      page: Optional[int] = None, sheet: Optional[str] = None, kind: Optional[str] = None,
                      limit: int = 20) -> list[dict[str, Any]]:
        return _search_chunks(self._db, query, document_id=document_id, version=version, page=page,
                              sheet=sheet, kind=kind, limit=limit)

    def get_chunk(self, chunk_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM DiChunk WHERE chunkId = ?", (chunk_id,)).fetchone()
        return dict(row) if row else None

    def list_chunks(self, document_id: str, *, version: Optional[int] = None, limit: int = 1000) -> list[dict[str, Any]]:
        if version is None:
            rows = self._db.execute(
                "SELECT * FROM DiChunk WHERE documentId = ? ORDER BY ord ASC LIMIT ?", (document_id, limit)
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM DiChunk WHERE documentId = ? AND version = ? ORDER BY ord ASC LIMIT ?",
                (document_id, version, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── tables / images / entities / ocr ─────────────────────────────────────────────

    def save_tables(self, document_id: str, version: int, tables: list[Any]) -> int:
        if not tables:
            return 0
        with self._db:
            self._db.executemany(
                """
                INSERT OR REPLACE INTO DiTable (tableId, documentId, version, page, sheet, headers, rows,
                    provenance, bbox)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                [
                    (t.table_id, document_id, version, t.page, t.sheet, json.dumps(t.headers),
                     json.dumps(t.rows), json.dumps(t.provenance.to_dict() if t.provenance else None),
                     json.dumps(t.bbox.to_dict() if t.bbox else None))
                    for t in tables
                ],
            )
        return len(tables)

    def get_table(self, document_id: str, table_id: str, *, version: Optional[int] = None) -> Optional[dict[str, Any]]:
        if version is None:
            row = self._db.execute(
                "SELECT * FROM DiTable WHERE documentId = ? AND tableId = ? ORDER BY version DESC LIMIT 1",
                (document_id, table_id),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT * FROM DiTable WHERE documentId = ? AND version = ? AND tableId = ?",
                (document_id, version, table_id),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        for key in ("headers", "rows", "provenance", "bbox"):
            try:
                out[key] = json.loads(out[key]) if out[key] else None
            except (TypeError, ValueError):
                out[key] = None
        return out

    def save_images(self, document_id: str, version: int, images: list[Any]) -> int:
        if not images:
            return 0
        with self._db:
            self._db.executemany(
                """
                INSERT OR REPLACE INTO DiImage (imageId, documentId, version, assetId, contentType, page, slide,
                    ocrText, caption, sha256, width, height, byteSize)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (i.image_id, document_id, version, i.asset_id, i.content_type, i.page, i.slide,
                     i.ocr_text, i.caption, i.sha256, i.width, i.height, i.byte_size)
                    for i in images
                ],
            )
        return len(images)

    def save_entities(self, document_id: str, version: int, entities: list[dict[str, Any]]) -> int:
        if not entities:
            return 0
        now = now_iso()
        with self._db:
            self._db.executemany(
                """
                INSERT OR REPLACE INTO DiEntity (id, documentId, version, type, value, page, blockId,
                    confidence, evidenceId, createdAt)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (e.get("id") or new_id("ent"), document_id, version, e.get("type", "other"),
                     e.get("value", ""), e.get("page"), e.get("blockId"),
                     float(e.get("confidence", 0.0) or 0.0), e.get("evidenceId"), now)
                    for e in entities
                ],
            )
        return len(entities)

    def list_entities(self, document_id: str, *, version: Optional[int] = None) -> list[dict[str, Any]]:
        if version is None:
            rows = self._db.execute(
                "SELECT * FROM DiEntity WHERE documentId = ? ORDER BY confidence DESC", (document_id,)
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM DiEntity WHERE documentId = ? AND version = ? ORDER BY confidence DESC",
                (document_id, version),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_ocr_run(self, run: dict[str, Any]) -> str:
        run_id = run.get("id") or new_id("ocr")
        with self._db:
            self._db.execute(
                """
                INSERT OR REPLACE INTO DiOcrRun (id, documentId, version, page, engine, method, confidence, text,
                    createdAt)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (run_id, run["documentId"], run.get("version", 1), run.get("page"), run.get("engine"),
                 run.get("method", "ocr"), float(run.get("confidence", 0.0) or 0.0),
                 run.get("text", ""), run.get("createdAt") or now_iso()),
            )
        return run_id

    # ── processing jobs ─────────────────────────────────────────────────────────────

    def create_job(self, document_id: Optional[str], *, version: int = 1, status: str = "DISCOVERED",
                   stage: Optional[str] = None) -> str:
        job_id = new_id("dijob")
        now = now_iso()
        with self._db:
            self._db.execute(
                "INSERT INTO DiJob (jobId, documentId, version, status, stage, progress, createdAt, updatedAt) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (job_id, document_id, version, status, stage, 0.0, now, now),
            )
        return job_id

    def update_job(self, job_id: str, *, status: Optional[str] = None, stage: Optional[str] = None,
                   progress: Optional[float] = None, error: Optional[str] = None, document_id: Optional[str] = None,
                   version: Optional[int] = None, attempts: Optional[int] = None) -> None:
        fields: list[str] = ["updatedAt = ?"]
        values: list[Any] = [now_iso()]
        for column, value in (("status", status), ("stage", stage), ("progress", progress), ("error", error),
                              ("documentId", document_id), ("version", version), ("attempts", attempts)):
            if value is not None:
                fields.append(f"{column} = ?")
                values.append(value)
        values.append(job_id)
        with self._db:
            self._db.execute(f"UPDATE DiJob SET {', '.join(fields)} WHERE jobId = ?", values)

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM DiJob WHERE jobId = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, *, status: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM DiJob WHERE status = ? ORDER BY createdAt DESC LIMIT ?", (status, limit)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM DiJob ORDER BY createdAt DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── cache ────────────────────────────────────────────────────────────────────────

    def get_cached_document(self, content_hash: str) -> Optional[str]:
        row = self._db.execute("SELECT * FROM DiCache WHERE contentHash = ?", (content_hash,)).fetchone()
        if not row:
            return None
        data = dict(row)
        if data.get("expiresAt") and data["expiresAt"] < now_iso():
            return None
        return data["documentId"]

    def put_cache(self, content_hash: str, document_id: str, *, kind: Optional[str] = None,
                  ttl_seconds: int = 0) -> None:
        expires = None
        if ttl_seconds:
            expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + ttl_seconds))
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO DiCache (contentHash, documentId, kind, createdAt, expiresAt) "
                "VALUES (?,?,?,?,?)",
                (content_hash, document_id, kind, now_iso(), expires),
            )

    def count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) AS n FROM DiDocument").fetchone()
        return int(row["n"]) if row else 0

    # ── IR blob (metadata-only; binaries stay in the vision asset store) ─────────────

    def _ir_path(self, document_id: str, version: int) -> str:
        import os

        from .config import document_config

        root = document_config().artifacts_root / "ir"
        root.mkdir(parents=True, exist_ok=True)
        return str(root / f"{document_id}_{version}.json")

    def save_ir(self, ir: Any) -> str:
        path = self._ir_path(ir.document_id, ir.version)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(ir.to_dict(), handle, default=str)
        except OSError as exc:
            raise DocumentError(DocumentErrorClass.STORAGE_ERROR, f"the IR could not be stored: {exc}", cause=exc) from exc
        return path

    def get_ir(self, document_id: str, *, version: Optional[int] = None) -> Optional[Any]:
        import os

        from .ir import DocumentIR

        doc = self.get_document(document_id)
        if doc is None:
            return None
        if version is None:
            version = int(doc.get("currentVersion", 1) or 1)
        path = self._ir_path(document_id, version)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return DocumentIR.from_dict(json.load(handle))
        except (OSError, ValueError):
            return None


# ── search ───────────────────────────────────────────────────────────────────────

def _fts_available(db: sqlite3.Connection) -> bool:
    try:
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS DiChunkFts USING fts5(chunkId, text)")
        return True
    except sqlite3.OperationalError:
        return False


def _search_chunks(db: sqlite3.Connection, query: str, *, document_id: Optional[str], version: Optional[int],
                  page: Optional[int], sheet: Optional[str], kind: Optional[str], limit: int) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if document_id:
        clauses.append("documentId = ?"); params.append(document_id)
    if version is not None:
        clauses.append("version = ?"); params.append(version)
    if page is not None:
        clauses.append("page = ?"); params.append(page)
    if sheet:
        clauses.append("sheet = ?"); params.append(sheet)
    if kind:
        clauses.append("kind = ?"); params.append(kind)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    terms = [t for t in _terms(query)]
    if not terms:
        rows = db.execute(
            f"SELECT * FROM DiChunk{where} ORDER BY ord ASC LIMIT ?", (*params, limit)
        ).fetchall()
        return [_chunk_row(r) for r in rows]

    # Lexical scoring over the candidate set: term overlap + phrase bonus + BM25-ish
    # length normalization. Deterministic, no model, no embeddings (documented).
    like_clause = " AND ".join("text LIKE ?" for _ in terms)
    rows = db.execute(
        f"SELECT * FROM DiChunk{where}{' AND ' if where else ' WHERE '}{like_clause} LIMIT ?",
        (*params, *[f"%{t}%" for t in terms], max(limit * 5, 50)),
    ).fetchall()
    scored: list[tuple[float, dict[str, Any]]] = []
    lowered_terms = [t.lower() for t in terms]
    for row in rows:
        text = (row["text"] or "").lower()
        score = 0.0
        for term in lowered_terms:
            count = text.count(term)
            if count:
                score += 1.0 + (count - 1) * 0.25
        if query.lower().strip() and query.lower().strip() in text:
            score += 2.0
        length = max(1, len(text))
        score = score / (1 + length / 2000.0)
        scored.append((score, _chunk_row(row)))
    scored.sort(key=lambda kv: kv[0], reverse=True)
    return [item for _, item in scored[:limit]]


def _terms(query: str) -> list[str]:
    words = [t.lower() for t in re.findall(r"[A-Za-z0-9_]+", query or "") if len(t) > 1]
    content = [w for w in words if w not in _STOPWORDS]
    return content[:12]


def _chunk_row(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    if "ord" in out:
        out["order"] = out.pop("ord")
    return out


def _row_doc(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    for key in ("metadata", "dates"):
        try:
            out[key] = json.loads(out[key]) if out.get(key) else ({} if key == "metadata" else None)
        except (TypeError, ValueError):
            out[key] = {} if key == "metadata" else None
    return out


__all__ = ["DocumentStore", "now_iso", "new_id"]

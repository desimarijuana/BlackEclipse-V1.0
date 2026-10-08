"""Source adapters: existing stores → indexable documents.

Each adapter reads an existing subsystem's rows from the ONE ``agent-memory.db``
connection and produces ``DocumentRecord``s for the indexer. Adapters are
defensive: a missing table or column yields no documents rather than an error, so
the search layer works before every subsystem has ever produced a row.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from .chunking import chunk_text
from .contracts import ChunkRecord, DocumentRecord, SectionRecord


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    try:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?", (name,)
        ).fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    try:
        cursor = conn.execute(sql, params)
        return [{k: row[k] for k in row.keys()} for row in cursor.fetchall()]
    except Exception:  # noqa: BLE001 - defensive: a shape mismatch yields nothing
        return []


def _chunks_from_text(text: str, document_id: str, **kwargs: Any) -> list[ChunkRecord]:
    return chunk_text(text, document_id=document_id, **kwargs)


def documents_from_memory(
    conn: sqlite3.Connection, *, namespace: str = "memory", limit: int = 5_000,
    chunk_target: int = 1_200, chunk_overlap: int = 150,
) -> list[DocumentRecord]:
    if not _table_exists(conn, "MemoryRecord"):
        return []
    rows = _rows(
        conn,
        "SELECT id, memoryType, scope, scopeId, subject, content, confidence, importance, source, "
        "status, createdAt, updatedAt FROM MemoryRecord WHERE status='active' "
        "ORDER BY updatedAt DESC LIMIT ?",
        (limit,),
    )
    docs: list[DocumentRecord] = []
    for row in rows:
        document_id = f"memory:{row['id']}"
        scope = (row.get("scope") or "general").lower()
        scope_id = row.get("scopeId")
        if scope == "user" and scope_id:
            visibility = "private"
        elif scope in ("project", "workspace") and scope_id:
            visibility = "workspace"
        else:
            visibility = "public"
        chunks = _chunks_from_text(
            row.get("content") or "", document_id, target_chars=chunk_target,
            overlap_chars=chunk_overlap, strategy="structural",
        )
        if not chunks:
            continue
        docs.append(
            DocumentRecord(
                document_id=document_id,
                source_type="memory",
                source_id=row["id"],
                namespace=namespace,
                title=row.get("subject") or f"Memory {row['id']}",
                description=(row.get("content") or "")[:200],
                language="en",
                document_type=row.get("memoryType") or "memory",
                owner_id=row.get("scopeId") if visibility != "public" else None,
                visibility=visibility,
                authority=float(row.get("importance") or 0.5),
                content_hash=_hash(row.get("content") or ""),
                metadata={
                    "memoryType": row.get("memoryType"),
                    "scope": row.get("scope"),
                    "verification": row.get("status"),
                    "createdAt": row.get("createdAt"),
                },
                chunks=chunks,
            )
        )
    return docs


def documents_from_evidence(
    conn: sqlite3.Connection, *, namespace: str = "evidence", limit: int = 5_000,
    chunk_target: int = 1_200, chunk_overlap: int = 150,
) -> list[DocumentRecord]:
    if not _table_exists(conn, "WebResearchEvidence"):
        return []
    rows = _rows(
        conn,
        "SELECT evidenceId, sourceId, sourceUrl, sourceType, publisher, publishedAt, retrievedAt, "
        "effectiveAt, documentId, page, section, rawText, contentHash FROM WebResearchEvidence "
        "ORDER BY retrievedAt DESC LIMIT ?",
        (limit,),
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.get("sourceId") or row.get("sourceUrl") or row.get("evidenceId")
        group = grouped.setdefault(key, {"rows": [], "meta": row})
        group["rows"].append(row)
    docs: list[DocumentRecord] = []
    for key, group in grouped.items():
        meta = group["meta"]
        document_id = f"evidence:{key}"
        chunks: list[ChunkRecord] = []
        for ordinal, row in enumerate(group["rows"]):
            text = (row.get("rawText") or "").strip()
            if not text:
                continue
            chunks.append(
                ChunkRecord(
                    chunk_id=f"{document_id}:{ordinal}",
                    content=text,
                    document_id=document_id,
                    ordinal=ordinal,
                    page=row.get("page"),
                    kind="paragraph",
                    token_count=max(1, len(text) // 4),
                    metadata={"section": row.get("section"), "evidenceId": row.get("evidenceId")},
                )
            )
        if not chunks:
            continue
        docs.append(
            DocumentRecord(
                document_id=document_id,
                source_type="web",
                source_id=str(key),
                namespace=namespace,
                title=(meta.get("sourceUrl") or str(key))[:200],
                uri=meta.get("sourceUrl"),
                publisher=meta.get("publisher"),
                language="en",
                entity_type=None,
                entity_id=meta.get("documentId"),
                document_type=meta.get("sourceType") or "web",
                published_at=meta.get("publishedAt"),
                retrieved_at=meta.get("retrievedAt"),
                effective_at=meta.get("effectiveAt"),
                visibility="public",
                authority=0.5,
                content_hash=meta.get("contentHash"),
                metadata={"sourceType": meta.get("sourceType")},
                chunks=chunks,
            )
        )
    return docs


def documents_from_document_store(conn: sqlite3.Connection, *, namespace: str = "documents", limit: int = 2_000) -> list[DocumentRecord]:
    if not _table_exists(conn, "DiDocument") or not _table_exists(conn, "DiChunk"):
        return []
    documents = _rows(
        conn,
        "SELECT * FROM DiDocument ORDER BY rowid DESC LIMIT ?",
        (limit,),
    )
    docs: list[DocumentRecord] = []
    for document in documents:
        doc_id = document.get("documentId")
        version = document.get("version") or 1
        if not doc_id:
            continue
        chunk_rows = _rows(
            conn,
            "SELECT chunkId, kind, page, sheet, section, blockId, tableId, cell, text, ord "
            "FROM DiChunk WHERE documentId=? AND version=? ORDER BY ord ASC",
            (doc_id, version),
        )
        chunks: list[ChunkRecord] = []
        sections: dict[str, SectionRecord] = {}
        for ordinal, row in enumerate(chunk_rows):
            text = (row.get("text") or "").strip()
            if not text:
                continue
            section_name = row.get("section")
            section_id = None
            if section_name:
                section_id = f"{doc_id}#{section_name}"
                sections.setdefault(
                    section_id,
                    SectionRecord(section_id=section_id, document_id=f"document:{doc_id}@{version}",
                                  heading=section_name, section_path=section_name, ordinal=0),
                )
            chunks.append(
                ChunkRecord(
                    chunk_id=f"document:{doc_id}@{version}:{row.get('chunkId') or ordinal}",
                    content=text,
                    document_id=f"document:{doc_id}@{version}",
                    section_id=section_id,
                    ordinal=ordinal,
                    kind=row.get("kind") or "paragraph",
                    page=row.get("page"),
                    token_count=max(1, len(text) // 4),
                    metadata={"sheet": row.get("sheet"), "tableId": row.get("tableId"), "cell": row.get("cell")},
                )
            )
        if not chunks:
            continue
        published = document.get("publishedAt") or document.get("createdAt")
        docs.append(
            DocumentRecord(
                document_id=f"document:{doc_id}@{version}",
                source_type="document",
                source_id=doc_id,
                namespace=namespace,
                title=document.get("fileName") or str(doc_id),
                uri=document.get("sourceRef"),
                language=document.get("language") or "en",
                document_type=document.get("kind") or "document",
                published_at=published,
                visibility="public",
                authority=0.6,
                content_hash=document.get("contentHash"),
                metadata={"kind": document.get("kind"), "parser": document.get("parser")},
                sections=list(sections.values()),
                chunks=chunks,
            )
        )
    return docs


def documents_from_skills(conn: sqlite3.Connection, *, namespace: str = "skills", limit: int = 2_000) -> list[DocumentRecord]:
    if not _table_exists(conn, "Skill"):
        return []
    skills = _rows(conn, "SELECT id, name, description, category, latestVersion, tags, status FROM Skill LIMIT ?", (limit,))
    has_versions = _table_exists(conn, "SkillVersion")
    docs: list[DocumentRecord] = []
    for skill in skills:
        skill_id = skill.get("id")
        if not skill_id:
            continue
        version = skill.get("latestVersion") or "1.0.0"
        instructions = ""
        if has_versions:
            rows = _rows(
                conn,
                "SELECT instructions, manifest FROM SkillVersion WHERE skillId=? AND version=? LIMIT 1",
                (skill_id, version),
            )
            if rows:
                instructions = rows[0].get("instructions") or ""
        parts = [
            f"Skill: {skill.get('name')}",
            f"Category: {skill.get('category')}",
            f"Description: {skill.get('description')}",
        ]
        if instructions:
            parts.append(f"Instructions:\n{instructions}")
        text = "\n".join(p for p in parts if p and p.strip())
        document_id = f"skill:{skill_id}@{version}"
        chunks = _chunks_from_text(text, document_id, strategy="structural")
        if not chunks:
            continue
        docs.append(
            DocumentRecord(
                document_id=document_id,
                source_type="skill",
                source_id=skill_id,
                namespace=namespace,
                title=skill.get("name") or skill_id,
                description=skill.get("description") or "",
                document_type="skill",
                visibility="public",
                authority=0.6,
                content_hash=_hash(text),
                metadata={"category": skill.get("category"), "tags": _safe_json(skill.get("tags")), "version": version},
                chunks=chunks,
            )
        )
    return docs


def collect_documents(conn: sqlite3.Connection, *, namespaces: Optional[list[str]] = None) -> list[DocumentRecord]:
    """Read every adapter and return the union, filtered by namespace if given."""
    everything: list[DocumentRecord] = []
    everything.extend(documents_from_memory(conn))
    everything.extend(documents_from_evidence(conn))
    everything.extend(documents_from_document_store(conn))
    everything.extend(documents_from_skills(conn))
    if namespaces:
        wanted = set(namespaces)
        everything = [d for d in everything if d.namespace in wanted]
    return everything


def _safe_json(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "collect_documents",
    "documents_from_document_store",
    "documents_from_evidence",
    "documents_from_memory",
    "documents_from_skills",
]

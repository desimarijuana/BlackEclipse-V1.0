"""Artifact catalog store — the durable rows on the ONE `agent-memory.db`.

Owns its own tables and NEVER reads another subsystem's rows. The catalog is
not JDdS (`jdds.db`) and not the agent-memory tables of other subsystems.

All state changes go through explicit methods; the service layer validates
before calling here. Filtering/sorting build a parameterized WHERE clause —
caller-supplied column names never reach SQL (sort keys are looked up in the
closed ``model.SORT_COLUMNS`` table).
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import new_id, now_iso
from .model import (
    Artifact,
    ArtifactCategory,
    ArtifactCollection,
    ArtifactEvent,
    ArtifactSourceType,
    ArtifactStatus,
    ArtifactTag,
    ArtifactVersion,
    ListArtifactsQuery,
    PreviewStatus,
    SORT_COLUMNS,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS HarnessArtifact (
  id             TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  originalName   TEXT,
  description    TEXT NOT NULL DEFAULT '',
  category       TEXT NOT NULL DEFAULT 'other',
  mimeType       TEXT NOT NULL DEFAULT 'application/octet-stream',
  extension      TEXT NOT NULL DEFAULT '',
  sizeBytes      INTEGER,
  checksum       TEXT,
  storageBackend TEXT NOT NULL DEFAULT 'local',
  storageKey     TEXT,
  ownerId        TEXT NOT NULL DEFAULT 'local',
  workspaceId    TEXT,
  projectId      TEXT,
  conversationId TEXT,
  agentId        TEXT,
  taskId         TEXT,
  runId          TEXT,
  parentArtifactId TEXT,
  sourceType     TEXT NOT NULL DEFAULT 'agent',
  sourceTool     TEXT,
  status         TEXT NOT NULL DEFAULT 'ACTIVE',
  previewStatus  TEXT NOT NULL DEFAULT 'PENDING',
  previewKind    TEXT,
  thumbnailKey   TEXT,
  favorite       INTEGER NOT NULL DEFAULT 0,
  pinned         INTEGER NOT NULL DEFAULT 0,
  versionNumber  INTEGER NOT NULL DEFAULT 1,
  metadata       TEXT NOT NULL DEFAULT '{}',
  provenance     TEXT NOT NULL DEFAULT '{}',
  retentionUntil TEXT,
  archivedAt     TEXT,
  deletedAt      TEXT,
  lastAccessedAt TEXT,
  createdAt      TEXT NOT NULL,
  updatedAt      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS HarnessArtifactVersion (
  id            TEXT PRIMARY KEY,
  artifactId    TEXT NOT NULL,
  versionNumber INTEGER NOT NULL,
  storageKey    TEXT,
  checksum      TEXT,
  sizeBytes     INTEGER,
  mimeType      TEXT,
  createdBy     TEXT,
  agentId       TEXT,
  taskId        TEXT,
  runId         TEXT,
  changeNote    TEXT,
  metadata      TEXT NOT NULL DEFAULT '{}',
  createdAt     TEXT NOT NULL,
  UNIQUE(artifactId, versionNumber)
);

CREATE TABLE IF NOT EXISTS HarnessArtifactCollection (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  parentId    TEXT,
  ownerId     TEXT NOT NULL DEFAULT 'local',
  createdAt   TEXT NOT NULL,
  updatedAt   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS HarnessArtifactCollectionMember (
  collectionId TEXT NOT NULL,
  artifactId   TEXT NOT NULL,
  addedAt      TEXT NOT NULL,
  PRIMARY KEY (collectionId, artifactId)
);

CREATE TABLE IF NOT EXISTS HarnessArtifactTag (
  id        TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  ownerId   TEXT NOT NULL DEFAULT 'local',
  createdAt TEXT NOT NULL,
  UNIQUE(ownerId, name)
);

CREATE TABLE IF NOT EXISTS HarnessArtifactTagLink (
  artifactId TEXT NOT NULL,
  tagId      TEXT NOT NULL,
  createdAt  TEXT NOT NULL,
  PRIMARY KEY (artifactId, tagId)
);

CREATE TABLE IF NOT EXISTS HarnessArtifactEvent (
  id         TEXT PRIMARY KEY,
  artifactId TEXT,
  type       TEXT NOT NULL,
  seq        INTEGER NOT NULL DEFAULT 0,
  actor      TEXT,
  data       TEXT NOT NULL DEFAULT '{}',
  createdAt  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS HarnessArtifactIdempotency (
  key        TEXT PRIMARY KEY,
  artifactId TEXT NOT NULL,
  createdAt  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifact_status     ON HarnessArtifact(status, createdAt);
CREATE INDEX IF NOT EXISTS idx_artifact_category   ON HarnessArtifact(category);
CREATE INDEX IF NOT EXISTS idx_artifact_owner      ON HarnessArtifact(ownerId, createdAt);
CREATE INDEX IF NOT EXISTS idx_artifact_project    ON HarnessArtifact(projectId);
CREATE INDEX IF NOT EXISTS idx_artifact_agent      ON HarnessArtifact(agentId);
CREATE INDEX IF NOT EXISTS idx_artifact_task       ON HarnessArtifact(taskId);
CREATE INDEX IF NOT EXISTS idx_artifact_run        ON HarnessArtifact(runId);
CREATE INDEX IF NOT EXISTS idx_artifact_conversation ON HarnessArtifact(conversationId);
CREATE INDEX IF NOT EXISTS idx_artifact_created    ON HarnessArtifact(createdAt);
CREATE INDEX IF NOT EXISTS idx_artifact_name       ON HarnessArtifact(name);
CREATE INDEX IF NOT EXISTS idx_artifact_updated    ON HarnessArtifact(updatedAt);
CREATE INDEX IF NOT EXISTS idx_artifact_favorite   ON HarnessArtifact(favorite);
CREATE INDEX IF NOT EXISTS idx_artifact_version    ON HarnessArtifactVersion(artifactId, versionNumber);
CREATE INDEX IF NOT EXISTS idx_artifact_event      ON HarnessArtifactEvent(artifactId, seq);
CREATE INDEX IF NOT EXISTS idx_artifact_member     ON HarnessArtifactCollectionMember(artifactId);
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


def _enum(cls: Any, value: Any, default: Any) -> Any:
    try:
        return cls(value)
    except (ValueError, TypeError):
        return default


class ArtifactStore:
    """Rows describing the artifact catalog."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._db.executescript(_SCHEMA)
        self._db.commit()

    @property
    def _db(self):
        return self._store._db

    # ── Artifact rows ────────────────────────────────────────────────────────

    def create(
        self,
        *,
        name: str,
        original_name: Optional[str] = None,
        description: str = "",
        category: ArtifactCategory = ArtifactCategory.OTHER,
        mime_type: str = "application/octet-stream",
        extension: str = "",
        size_bytes: Optional[int] = None,
        checksum: Optional[str] = None,
        storage_backend: str = "local",
        storage_key: Optional[str] = None,
        owner_id: str = "local",
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        parent_artifact_id: Optional[str] = None,
        source_type: ArtifactSourceType = ArtifactSourceType.AGENT,
        source_tool: Optional[str] = None,
        status: ArtifactStatus = ArtifactStatus.ACTIVE,
        preview_status: PreviewStatus = PreviewStatus.PENDING,
        preview_kind: Optional[str] = None,
        thumbnail_key: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        provenance: Optional[dict[str, Any]] = None,
        retention_until: Optional[str] = None,
    ) -> Artifact:
        artifact_id = new_id("art")
        now = now_iso()
        self._db.execute(
            """
            INSERT INTO HarnessArtifact
              (id, name, originalName, description, category, mimeType, extension,
               sizeBytes, checksum, storageBackend, storageKey, ownerId, workspaceId,
               projectId, conversationId, agentId, taskId, runId, parentArtifactId,
               sourceType, sourceTool, status, previewStatus, previewKind, thumbnailKey,
               favorite, pinned, versionNumber, metadata, provenance, retentionUntil,
               archivedAt, deletedAt, lastAccessedAt, createdAt, updatedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                artifact_id, name, original_name, description, category.value, mime_type,
                extension, size_bytes, checksum, storage_backend, storage_key, owner_id,
                workspace_id, project_id, conversation_id, agent_id, task_id, run_id,
                parent_artifact_id, source_type.value, source_tool, status.value,
                preview_status.value, preview_kind, thumbnail_key, 0, 0, 1,
                _json(metadata or {}), _json(provenance or {}), retention_until,
                None, None, None, now, now,
            ),
        )
        self._db.commit()
        created = self.get(artifact_id)
        assert created is not None
        return created

    def get(self, artifact_id: str, *, owner_id: Optional[str] = None) -> Optional[Artifact]:
        row = self._db.execute(
            "SELECT * FROM HarnessArtifact WHERE id=?", (artifact_id,)
        ).fetchone()
        if row is None:
            return None
        if owner_id is not None and row["ownerId"] != owner_id:
            return None
        return self._hydrate(row)

    def touch_accessed(self, artifact_id: str) -> None:
        self._db.execute(
            "UPDATE HarnessArtifact SET lastAccessedAt=? WHERE id=?", (now_iso(), artifact_id)
        )
        self._db.commit()

    def update_fields(self, artifact_id: str, fields: dict[str, Any]) -> Optional[Artifact]:
        """Update a validated subset of columns. Unknown keys are ignored."""
        allowed = {
            "name", "description", "category", "mimeType", "previewStatus", "previewKind",
            "thumbnailKey", "favorite", "pinned", "status", "archivedAt", "deletedAt",
            "metadata", "provenance", "retentionUntil", "sizeBytes", "checksum",
            "storageKey", "versionNumber", "deletedAt", "lastAccessedAt", "agentId",
            "taskId", "runId", "projectId", "conversationId",
        }
        sets: list[str] = []
        params: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in ("metadata", "provenance"):
                value = _json(value)
            if key in ("favorite", "pinned"):
                value = 1 if value else 0
            sets.append(f"{key}=?")
            params.append(value)
        if not sets:
            return self.get(artifact_id)
        sets.append("updatedAt=?")
        params.append(now_iso())
        params.append(artifact_id)
        self._db.execute(
            f"UPDATE HarnessArtifact SET {', '.join(sets)} WHERE id=?", params  # noqa: S608 - keys allowlisted
        )
        self._db.commit()
        return self.get(artifact_id)

    def set_status(
        self,
        artifact_id: str,
        status: ArtifactStatus,
        *,
        archived_at: Optional[str] = None,
        deleted_at: Optional[str] = None,
    ) -> Optional[Artifact]:
        fields: dict[str, Any] = {"status": status}
        if archived_at is not None:
            fields["archivedAt"] = archived_at
        if deleted_at is not None:
            fields["deletedAt"] = deleted_at
        return self.update_fields(artifact_id, fields)

    # ── listing / search (server-side, parameterized) ────────────────────────

    def list(self, query: ListArtifactsQuery, *, owner_id: Optional[str] = None) -> tuple[list[Artifact], int]:
        where: list[str] = []
        params: list[Any] = []
        statuses: list[str] = []
        if not query.include_archived:
            statuses.append(ArtifactStatus.ARCHIVED.value)
        if not query.include_deleted:
            statuses.append(ArtifactStatus.DELETED.value)
            statuses.append(ArtifactStatus.PURGED.value)
        if statuses:
            where.append(f"status NOT IN ({','.join('?' for _ in statuses)})")
            params.extend(statuses)
        if query.status is not None:
            where.append("status=?")
            params.append(query.status.value)
        if owner_id is not None:
            where.append("ownerId=?")
            params.append(owner_id)
        if query.q:
            like = f"%{query.q.lower()}%"
            where.append("(lower(name) LIKE ? OR lower(description) LIKE ?)")
            params.extend([like, like])
        if query.category is not None:
            where.append("category=?")
            params.append(query.category.value)
        if query.project_id:
            where.append("projectId=?")
            params.append(query.project_id)
        if query.agent_id:
            where.append("agentId=?")
            params.append(query.agent_id)
        if query.task_id:
            where.append("taskId=?")
            params.append(query.task_id)
        if query.run_id:
            where.append("runId=?")
            params.append(query.run_id)
        if query.conversation_id:
            where.append("conversationId=?")
            params.append(query.conversation_id)
        if query.source_type is not None:
            where.append("sourceType=?")
            params.append(query.source_type.value)
        if query.mime_type:
            where.append("mimeType=?")
            params.append(query.mime_type)
        if query.extension:
            where.append("extension=?")
            params.append(query.extension.casefold())
        if query.favorite is not None:
            where.append("favorite=?")
            params.append(1 if query.favorite else 0)
        if query.created_after:
            where.append("createdAt >= ?")
            params.append(query.created_after)
        if query.created_before:
            where.append("createdAt <= ?")
            params.append(query.created_before)
        if query.collection_id:
            where.append(
                "id IN (SELECT artifactId FROM HarnessArtifactCollectionMember WHERE collectionId=?)"
            )
            params.append(query.collection_id)
        if query.tags:
            placeholders = ",".join("?" for _ in query.tags)
            where.append(
                "id IN (SELECT l.artifactId FROM HarnessArtifactTagLink l "
                f"JOIN HarnessArtifactTag t ON t.id=l.tagId WHERE lower(t.name) IN ({placeholders}))"
            )
            params.extend(t.casefold() for t in query.tags)

        clause = f"WHERE {' AND '.join(where)}" if where else ""
        total = self._db.execute(
            f"SELECT COUNT(*) AS n FROM HarnessArtifact {clause}", params  # noqa: S608
        ).fetchone()["n"]
        order = SORT_COLUMNS[query.sort]
        sql = (
            f"SELECT * FROM HarnessArtifact {clause} ORDER BY {order}, id ASC LIMIT ? OFFSET ?"  # noqa: S608
        )
        rows = self._db.execute(sql, [*params, query.limit, query.offset]).fetchall()
        return [self._hydrate(row) for row in rows], int(total)

    # ── versions ─────────────────────────────────────────────────────────────

    def add_version(
        self,
        *,
        artifact_id: str,
        version_number: int,
        storage_key: Optional[str],
        checksum: Optional[str],
        size_bytes: Optional[int],
        mime_type: Optional[str],
        created_by: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        change_note: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ArtifactVersion:
        version = ArtifactVersion(
            id=new_id("artv"), artifact_id=artifact_id, version_number=version_number,
            storage_key=storage_key, checksum=checksum, size_bytes=size_bytes,
            mime_type=mime_type, created_by=created_by, agent_id=agent_id, task_id=task_id,
            run_id=run_id, change_note=change_note, metadata=metadata or {},
            created_at=now_iso(),
        )
        self._db.execute(
            """
            INSERT INTO HarnessArtifactVersion
              (id, artifactId, versionNumber, storageKey, checksum, sizeBytes, mimeType,
               createdBy, agentId, taskId, runId, changeNote, metadata, createdAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                version.id, artifact_id, version_number, storage_key, checksum, size_bytes,
                mime_type, created_by, agent_id, task_id, run_id, change_note,
                _json(version.metadata), version.created_at,
            ),
        )
        self._db.commit()
        return version

    def list_versions(self, artifact_id: str) -> list[ArtifactVersion]:
        rows = self._db.execute(
            "SELECT * FROM HarnessArtifactVersion WHERE artifactId=? ORDER BY versionNumber DESC",
            (artifact_id,),
        ).fetchall()
        return [self._version_row(r) for r in rows]

    def get_version(self, artifact_id: str, version_number: int) -> Optional[ArtifactVersion]:
        row = self._db.execute(
            "SELECT * FROM HarnessArtifactVersion WHERE artifactId=? AND versionNumber=?",
            (artifact_id, version_number),
        ).fetchone()
        return self._version_row(row) if row else None

    # ── tags ─────────────────────────────────────────────────────────────────

    def ensure_tag(self, name: str, owner_id: str = "local") -> ArtifactTag:
        normalized = name.strip()
        row = self._db.execute(
            "SELECT * FROM HarnessArtifactTag WHERE ownerId=? AND name=? COLLATE NOCASE",
            (owner_id, normalized),
        ).fetchone()
        if row:
            return self._tag_row(row)
        tag = ArtifactTag(id=new_id("artt"), name=normalized, owner_id=owner_id, created_at=now_iso())
        self._db.execute(
            "INSERT INTO HarnessArtifactTag (id, name, ownerId, createdAt) VALUES (?,?,?,?)",
            (tag.id, tag.name, tag.owner_id, tag.created_at),
        )
        self._db.commit()
        return tag

    def link_tag(self, artifact_id: str, tag_id: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO HarnessArtifactTagLink (artifactId, tagId, createdAt) VALUES (?,?,?)",
            (artifact_id, tag_id, now_iso()),
        )
        self._db.commit()

    def unlink_tag(self, artifact_id: str, tag_id: str) -> None:
        self._db.execute(
            "DELETE FROM HarnessArtifactTagLink WHERE artifactId=? AND tagId=?",
            (artifact_id, tag_id),
        )
        self._db.commit()

    def tags_for(self, artifact_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT t.name FROM HarnessArtifactTag t JOIN HarnessArtifactTagLink l ON l.tagId=t.id "
            "WHERE l.artifactId=? ORDER BY t.name COLLATE NOCASE",
            (artifact_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def list_tags(self, owner_id: str = "local") -> list[ArtifactTag]:
        rows = self._db.execute(
            "SELECT * FROM HarnessArtifactTag WHERE ownerId=? ORDER BY name COLLATE NOCASE",
            (owner_id,),
        ).fetchall()
        return [self._tag_row(r) for r in rows]

    # ── collections ──────────────────────────────────────────────────────────

    def create_collection(
        self, *, name: str, description: str = "", parent_id: Optional[str] = None,
        owner_id: str = "local",
    ) -> ArtifactCollection:
        now = now_iso()
        collection = ArtifactCollection(
            id=new_id("artc"), name=name.strip(), description=description,
            parent_id=parent_id, owner_id=owner_id, created_at=now, updated_at=now,
        )
        self._db.execute(
            "INSERT INTO HarnessArtifactCollection (id, name, description, parentId, ownerId, createdAt, updatedAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (collection.id, collection.name, collection.description, parent_id, owner_id, now, now),
        )
        self._db.commit()
        return collection

    def get_collection(self, collection_id: str) -> Optional[ArtifactCollection]:
        row = self._db.execute(
            "SELECT * FROM HarnessArtifactCollection WHERE id=?", (collection_id,)
        ).fetchone()
        return self._collection_row(row) if row else None

    def list_collections(self, owner_id: str = "local") -> list[ArtifactCollection]:
        rows = self._db.execute(
            "SELECT * FROM HarnessArtifactCollection WHERE ownerId=? ORDER BY name COLLATE NOCASE",
            (owner_id,),
        ).fetchall()
        return [self._collection_row(r) for r in rows]

    def update_collection(self, collection_id: str, fields: dict[str, Any]) -> Optional[ArtifactCollection]:
        allowed = {"name", "description", "parentId"}
        sets, params = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key}=?")
                params.append(value)
        if not sets:
            return self.get_collection(collection_id)
        sets.append("updatedAt=?")
        params.append(now_iso())
        params.append(collection_id)
        self._db.execute(
            f"UPDATE HarnessArtifactCollection SET {', '.join(sets)} WHERE id=?", params  # noqa: S608
        )
        self._db.commit()
        return self.get_collection(collection_id)

    def delete_collection(self, collection_id: str) -> bool:
        self._db.execute(
            "DELETE FROM HarnessArtifactCollectionMember WHERE collectionId=?", (collection_id,)
        )
        cur = self._db.execute(
            "DELETE FROM HarnessArtifactCollection WHERE id=?", (collection_id,)
        )
        self._db.commit()
        return cur.rowcount > 0

    def add_to_collection(self, collection_id: str, artifact_id: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO HarnessArtifactCollectionMember (collectionId, artifactId, addedAt) "
            "VALUES (?,?,?)",
            (collection_id, artifact_id, now_iso()),
        )
        self._db.commit()

    def remove_from_collection(self, collection_id: str, artifact_id: str) -> None:
        self._db.execute(
            "DELETE FROM HarnessArtifactCollectionMember WHERE collectionId=? AND artifactId=?",
            (collection_id, artifact_id),
        )
        self._db.commit()

    def collections_for(self, artifact_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT collectionId FROM HarnessArtifactCollectionMember WHERE artifactId=?",
            (artifact_id,),
        ).fetchall()
        return [r["collectionId"] for r in rows]

    def collection_members(self, collection_id: str, limit: int = 1000) -> list[str]:
        rows = self._db.execute(
            "SELECT artifactId FROM HarnessArtifactCollectionMember WHERE collectionId=? "
            "ORDER BY addedAt DESC LIMIT ?",
            (collection_id, limit),
        ).fetchall()
        return [r["artifactId"] for r in rows]

    def _collection_row(self, row: Any) -> ArtifactCollection:
        count = self._db.execute(
            "SELECT COUNT(*) AS n FROM HarnessArtifactCollectionMember WHERE collectionId=?",
            (row["id"],),
        ).fetchone()["n"]
        return ArtifactCollection(
            id=row["id"], name=row["name"], description=row["description"] or "",
            parent_id=row["parentId"], owner_id=row["ownerId"], artifact_count=int(count),
            created_at=row["createdAt"], updated_at=row["updatedAt"],
        )

    # ── events (audit/lifecycle) ─────────────────────────────────────────────

    def add_event(
        self, artifact_id: Optional[str], event_type: str, *, actor: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> ArtifactEvent:
        seq = 0
        if artifact_id:
            row = self._db.execute(
                "SELECT COALESCE(MAX(seq),0)+1 AS s FROM HarnessArtifactEvent WHERE artifactId=?",
                (artifact_id,),
            ).fetchone()
            seq = int(row["s"])
        event = ArtifactEvent(
            id=new_id("arte"), artifact_id=artifact_id, type=event_type, seq=seq,
            actor=actor, data=data or {}, created_at=now_iso(),
        )
        self._db.execute(
            "INSERT INTO HarnessArtifactEvent (id, artifactId, type, seq, actor, data, createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (event.id, artifact_id, event_type, seq, actor, _json(event.data), event.created_at),
        )
        self._db.commit()
        return event

    def list_events(self, artifact_id: str, limit: int = 100) -> list[ArtifactEvent]:
        rows = self._db.execute(
            "SELECT * FROM HarnessArtifactEvent WHERE artifactId=? ORDER BY seq DESC LIMIT ?",
            (artifact_id, limit),
        ).fetchall()
        return [
            ArtifactEvent(
                id=r["id"], artifact_id=r["artifactId"], type=r["type"], seq=r["seq"],
                actor=r["actor"], data=_loads(r["data"], {}), created_at=r["createdAt"],
            )
            for r in rows
        ]

    # ── idempotency ──────────────────────────────────────────────────────────

    def lookup_idempotency(self, key: str) -> Optional[str]:
        row = self._db.execute(
            "SELECT artifactId FROM HarnessArtifactIdempotency WHERE key=?", (key,)
        ).fetchone()
        return row["artifactId"] if row else None

    def find_by_checksum(self, checksum: str, *, run_id: Optional[str] = None) -> Optional[str]:
        if run_id is None:
            row = self._db.execute(
                "SELECT id FROM HarnessArtifact WHERE checksum=? LIMIT 1", (checksum,)
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT id FROM HarnessArtifact WHERE checksum=? AND runId=? LIMIT 1",
                (checksum, run_id),
            ).fetchone()
        return row["id"] if row else None

    def record_idempotency(self, key: str, artifact_id: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO HarnessArtifactIdempotency (key, artifactId, createdAt) VALUES (?,?,?)",
            (key, artifact_id, now_iso()),
        )
        self._db.commit()

    # ── reconciliation / stats helpers ───────────────────────────────────────

    def iter_storage_keys(self) -> list[tuple[str, str, str, Optional[str]]]:
        rows = self._db.execute(
            "SELECT id, status, storageKey, checksum FROM HarnessArtifact WHERE storageKey IS NOT NULL"
        ).fetchall()
        return [(r["id"], r["status"], r["storageKey"], r["checksum"]) for r in rows]

    def list_deleted(self, limit: int = 500) -> list[dict[str, Any]]:
        """Soft-deleted rows (bounded), oldest deletion first, for retention."""
        rows = self._db.execute(
            "SELECT id, retentionUntil, deletedAt FROM HarnessArtifact "
            "WHERE status=? ORDER BY deletedAt ASC LIMIT ?",
            (ArtifactStatus.DELETED.value, limit),
        ).fetchall()
        return [
            {"id": r["id"], "retentionUntil": r["retentionUntil"], "deletedAt": r["deletedAt"]}
            for r in rows
        ]

    def stats(self, *, owner_id: Optional[str] = None) -> dict[str, Any]:
        clause = "WHERE ownerId=?" if owner_id else ""
        params = [owner_id] if owner_id else []
        by_status = {
            r["status"]: r["n"]
            for r in self._db.execute(
                f"SELECT status, COUNT(*) AS n FROM HarnessArtifact {clause} GROUP BY status", params  # noqa: S608
            ).fetchall()
        }
        by_category = {
            r["category"]: r["n"]
            for r in self._db.execute(
                f"SELECT category, COUNT(*) AS n FROM HarnessArtifact {clause} GROUP BY category", params  # noqa: S608
            ).fetchall()
        }
        total_bytes = self._db.execute(
            f"SELECT COALESCE(SUM(sizeBytes),0) AS n FROM HarnessArtifact {clause}", params  # noqa: S608
        ).fetchone()["n"]
        total = self._db.execute(
            f"SELECT COUNT(*) AS n FROM HarnessArtifact {clause}", params  # noqa: S608
        ).fetchone()["n"]
        return {
            "total": int(total),
            "totalBytes": int(total_bytes),
            "byStatus": by_status,
            "byCategory": by_category,
        }

    # ── row mapping ──────────────────────────────────────────────────────────

    def _hydrate(self, row: Any) -> Artifact:
        return Artifact(
            id=row["id"], name=row["name"], original_name=row["originalName"],
            description=row["description"] or "",
            category=_enum(ArtifactCategory, row["category"], ArtifactCategory.OTHER),
            mime_type=row["mimeType"], extension=row["extension"] or "",
            size_bytes=row["sizeBytes"], checksum=row["checksum"],
            storage_backend=row["storageBackend"], storage_key=row["storageKey"],
            owner_id=row["ownerId"], workspace_id=row["workspaceId"],
            project_id=row["projectId"], conversation_id=row["conversationId"],
            agent_id=row["agentId"], task_id=row["taskId"], run_id=row["runId"],
            parent_artifact_id=row["parentArtifactId"],
            source_type=_enum(ArtifactSourceType, row["sourceType"], ArtifactSourceType.AGENT),
            source_tool=row["sourceTool"],
            status=_enum(ArtifactStatus, row["status"], ArtifactStatus.ACTIVE),
            preview_status=_enum(PreviewStatus, row["previewStatus"], PreviewStatus.PENDING),
            preview_kind=row["previewKind"], thumbnail_key=row["thumbnailKey"],
            favorite=bool(row["favorite"]), pinned=bool(row["pinned"]),
            version_number=row["versionNumber"],
            tags=self.tags_for(row["id"]),
            collection_ids=self.collections_for(row["id"]),
            metadata=_loads(row["metadata"], {}), provenance=_loads(row["provenance"], {}),
            retention_until=row["retentionUntil"], archived_at=row["archivedAt"],
            deleted_at=row["deletedAt"], last_accessed_at=row["lastAccessedAt"],
            created_at=row["createdAt"], updated_at=row["updatedAt"],
        )

    def _version_row(self, row: Any) -> ArtifactVersion:
        return ArtifactVersion(
            id=row["id"], artifact_id=row["artifactId"], version_number=row["versionNumber"],
            storage_key=row["storageKey"], checksum=row["checksum"], size_bytes=row["sizeBytes"],
            mime_type=row["mimeType"], created_by=row["createdBy"], agent_id=row["agentId"],
            task_id=row["taskId"], run_id=row["runId"], change_note=row["changeNote"],
            metadata=_loads(row["metadata"], {}), created_at=row["createdAt"],
        )

    def _tag_row(self, row: Any) -> ArtifactTag:
        return ArtifactTag(
            id=row["id"], name=row["name"], owner_id=row["ownerId"], created_at=row["createdAt"]
        )


__all__ = ["ArtifactStore"]

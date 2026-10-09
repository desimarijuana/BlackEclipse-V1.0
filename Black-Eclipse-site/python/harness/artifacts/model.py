"""Artifact Center contracts — the durable vocabulary of the artifact catalog.

This module defines ONLY shape and vocabulary: the closed sets of categories,
lifecycle states, preview states and event types, plus the pydantic contracts
used to validate EXTERNAL input (tool arguments, API bodies) and to serialize
persisted rows. The runtime never trusts an LLM- or client-supplied artifact
definition, so every field a caller may supply passes through one of these
models before it is persisted.

The persisted form is a set of SQLite rows (see `store.py`) on the ONE
`agent-memory.db` connection. Field names are snake_case in Python and camelCase
on the wire (the TS front door), exactly like `tasks.model` and `jobs.model`.

The artifact catalog is deliberately separate from JDdS (`jdds.db`, market data)
and from the agent-memory tables owned by other subsystems: it owns its own
tables and never reads another subsystem's rows.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


# ── Closed vocabularies ───────────────────────────────────────────────────────


class ArtifactCategory(str, Enum):
    """The primary content class of an artifact. Extensible, never free-form."""

    DOCUMENT = "document"
    IMAGE = "image"
    SPREADSHEET = "spreadsheet"
    DATASET = "dataset"
    CHART = "chart"
    CODE = "code"
    SCRIPT = "script"
    LOG = "log"
    AUDIO = "audio"
    VIDEO = "video"
    ARCHIVE = "archive"
    LINK = "link"
    REPORT = "report"
    FINANCIAL = "financial"
    BACKTEST = "backtest"
    PRESENTATION = "presentation"
    OTHER = "other"


class ArtifactStatus(str, Enum):
    """The lifecycle state. Archive and delete are DISTINCT.

    ACTIVE     — content is persisted, validated and available.
    PROCESSING — ingestion/preview still running; content may not be final.
    FAILED     — registration could not complete; the record is honest about it.
    MISSING    — the record exists but its storage object is gone.
    ARCHIVED   — hidden from the default view; content retained.
    DELETED    — soft-deleted; recoverable until purged.
    PURGED     — permanently deleted; storage object removed.
    """

    ACTIVE = "ACTIVE"
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"
    MISSING = "MISSING"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"
    PURGED = "PURGED"


class PreviewStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"


class ArtifactSourceType(str, Enum):
    """Where an artifact came from. Never inferred from a filename."""

    AGENT = "agent"
    UPLOAD = "upload"
    IMPORT = "import"
    TERMINAL = "terminal"
    TOOL = "tool"
    JOB = "job"
    USER = "user"
    DERIVED = "derived"


class ArtifactEventType(str, Enum):
    """The immutable lifecycle/audit event vocabulary."""

    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    ARTIFACT_VERSION_ADDED = "ARTIFACT_VERSION_ADDED"
    ARTIFACT_UPDATED = "ARTIFACT_UPDATED"
    ARTIFACT_MOVED = "ARTIFACT_MOVED"
    ARTIFACT_TAGGED = "ARTIFACT_TAGGED"
    ARTIFACT_ARCHIVED = "ARTIFACT_ARCHIVED"
    ARTIFACT_RESTORED = "ARTIFACT_RESTORED"
    ARTIFACT_DELETED = "ARTIFACT_DELETED"
    ARTIFACT_PURGED = "ARTIFACT_PURGED"
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    ARTIFACT_RECONCILED = "ARTIFACT_RECONCILED"
    ARTIFACT_PREVIEW_READY = "ARTIFACT_PREVIEW_READY"
    ARTIFACT_PREVIEW_FAILED = "ARTIFACT_PREVIEW_FAILED"


#: Lifecycle states in which the content is expected to be retrievable.
RETRIEVABLE_STATUSES: frozenset[ArtifactStatus] = frozenset(
    {ArtifactStatus.ACTIVE, ArtifactStatus.ARCHIVED}
)

#: Default sort keys the API accepts, mapped to a safe column expression. No
#: caller-supplied column ever reaches SQL.
SORT_COLUMNS: dict[str, str] = {
    "newest": "createdAt DESC",
    "oldest": "createdAt ASC",
    "modified": "updatedAt DESC",
    "name": "name COLLATE NOCASE ASC",
    "name_desc": "name COLLATE NOCASE DESC",
    "size": "COALESCE(sizeBytes,0) DESC",
    "size_asc": "COALESCE(sizeBytes,0) ASC",
}

LIST_SORTS: frozenset[str] = frozenset(SORT_COLUMNS)

# Bounds. Keep the catalog bounded and honest.
MAX_NAME = 300
MAX_DESCRIPTION = 8_000
MAX_TAGS_PER_ARTIFACT = 50
MAX_TAG_LENGTH = 60
MAX_COLLECTION_NAME = 200
MAX_LIST_LIMIT = 200
DEFAULT_LIST_LIMIT = 50
MAX_METADATA_BYTES = 16_384
MAX_IMPORT_BYTES = 256 * 1024 * 1024


# ── Contracts ─────────────────────────────────────────────────────────────────


class ArtifactVersion(BaseModel):
    """One immutable revision of an artifact's bytes."""

    model_config = _CAMEL

    id: str
    artifact_id: str
    version_number: int
    storage_key: Optional[str] = None
    checksum: Optional[str] = None
    size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    created_by: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    change_note: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ArtifactTag(BaseModel):
    model_config = _CAMEL

    id: str
    name: str
    owner_id: str = "local"
    created_at: str


class ArtifactCollection(BaseModel):
    model_config = _CAMEL

    id: str
    name: str
    description: str = ""
    parent_id: Optional[str] = None
    owner_id: str = "local"
    artifact_count: int = 0
    created_at: str
    updated_at: str


class Artifact(BaseModel):
    """The durable view of one catalog row. Never the bytes."""

    model_config = _CAMEL

    id: str
    name: str
    original_name: Optional[str] = None
    description: str = ""
    category: ArtifactCategory = ArtifactCategory.OTHER
    mime_type: str = "application/octet-stream"
    extension: str = ""
    size_bytes: Optional[int] = None
    checksum: Optional[str] = None
    storage_backend: str = "local"
    storage_key: Optional[str] = None

    owner_id: str = "local"
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    conversation_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    parent_artifact_id: Optional[str] = None

    source_type: ArtifactSourceType = ArtifactSourceType.AGENT
    source_tool: Optional[str] = None

    status: ArtifactStatus = ArtifactStatus.ACTIVE
    preview_status: PreviewStatus = PreviewStatus.PENDING
    preview_kind: Optional[str] = None
    thumbnail_key: Optional[str] = None

    favorite: bool = False
    pinned: bool = False
    version_number: int = 1

    tags: list[str] = Field(default_factory=list)
    collection_ids: list[str] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    retention_until: Optional[str] = None

    archived_at: Optional[str] = None
    deleted_at: Optional[str] = None
    last_accessed_at: Optional[str] = None

    created_at: str
    updated_at: str


class ArtifactEvent(BaseModel):
    model_config = _CAMEL

    id: str
    artifact_id: Optional[str] = None
    type: str
    seq: int = 0
    actor: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ArtifactPage(BaseModel):
    """A stable, server-paginated page of artifacts."""

    model_config = _CAMEL

    artifacts: list[Artifact]
    total: int
    limit: int
    offset: int
    has_more: bool


# ── Input contracts (tool arguments / API bodies) ─────────────────────────────


class RegisterArtifactInput(BaseModel):
    """Validated input for registering an existing file into the catalog.

    The caller may supply a workspace-relative OR absolute source path inside an
    authorized workspace root; the storage adapter copies (or references) it.
    A client may NEVER supply a storage key directly.
    """

    model_config = _CAMEL

    source_path: Optional[str] = None       # a path the storage adapter will confine
    content_base64: Optional[str] = None    # inline content for small generated files
    name: str = Field(..., min_length=1, max_length=MAX_NAME)
    description: str = Field("", max_length=MAX_DESCRIPTION)
    category: Optional[ArtifactCategory] = None
    mime_type: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    source_type: ArtifactSourceType = ArtifactSourceType.AGENT
    source_tool: Optional[str] = None
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    conversation_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    parent_artifact_id: Optional[str] = None
    collection_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(None, max_length=200)
    make_version: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateArtifactInput(BaseModel):
    model_config = _CAMEL

    name: Optional[str] = Field(None, min_length=1, max_length=MAX_NAME)
    description: Optional[str] = Field(None, max_length=MAX_DESCRIPTION)
    tags: Optional[list[str]] = None
    favorite: Optional[bool] = None
    pinned: Optional[bool] = None
    category: Optional[ArtifactCategory] = None
    collection_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class ListArtifactsQuery(BaseModel):
    """The normalized, server-validated list/search request."""

    model_config = _CAMEL

    q: Optional[str] = Field(None, max_length=200)
    category: Optional[ArtifactCategory] = None
    status: Optional[ArtifactStatus] = None
    tags: list[str] = Field(default_factory=list)
    project_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    conversation_id: Optional[str] = None
    collection_id: Optional[str] = None
    source_type: Optional[ArtifactSourceType] = None
    mime_type: Optional[str] = None
    extension: Optional[str] = None
    favorite: Optional[bool] = None
    include_archived: bool = False
    include_deleted: bool = False
    created_after: Optional[str] = None
    created_before: Optional[str] = None
    sort: str = "newest"
    limit: int = Field(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(0, ge=0)

    @field_validator("sort")
    @classmethod
    def _known_sort(cls, value: str) -> str:
        if value not in LIST_SORTS:
            raise ValueError(f"unknown sort {value!r}; expected one of {sorted(LIST_SORTS)}")
        return value

    @field_validator("q")
    @classmethod
    def _clean_q(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class AddVersionInput(BaseModel):
    model_config = _CAMEL

    source_path: Optional[str] = None
    content_base64: Optional[str] = None
    change_note: Optional[str] = Field(None, max_length=1_000)
    mime_type: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(None, max_length=200)


class CollectionInput(BaseModel):
    model_config = _CAMEL

    name: str = Field(..., min_length=1, max_length=MAX_COLLECTION_NAME)
    description: str = Field("", max_length=MAX_DESCRIPTION)
    parent_id: Optional[str] = None


class BulkActionInput(BaseModel):
    model_config = _CAMEL

    artifact_ids: list[str] = Field(..., min_length=1, max_length=200)
    action: str  # archive | restore | delete | add_tags | remove_tags | move | favorite | unfavorite
    tags: list[str] = Field(default_factory=list)
    collection_id: Optional[str] = None

    @field_validator("action")
    @classmethod
    def _known_action(cls, value: str) -> str:
        allowed = {
            "archive", "restore", "delete", "add_tags", "remove_tags",
            "move", "favorite", "unfavorite",
        }
        if value not in allowed:
            raise ValueError(f"unknown bulk action {value!r}")
        return value


__all__ = [
    "AddVersionInput",
    "Artifact",
    "ArtifactCategory",
    "ArtifactCollection",
    "ArtifactEvent",
    "ArtifactEventType",
    "ArtifactPage",
    "ArtifactSourceType",
    "ArtifactStatus",
    "ArtifactTag",
    "ArtifactVersion",
    "BulkActionInput",
    "CollectionInput",
    "DEFAULT_LIST_LIMIT",
    "LIST_SORTS",
    "ListArtifactsQuery",
    "MAX_COLLECTION_NAME",
    "MAX_DESCRIPTION",
    "MAX_IMPORT_BYTES",
    "MAX_LIST_LIMIT",
    "MAX_METADATA_BYTES",
    "MAX_NAME",
    "MAX_TAG_LENGTH",
    "MAX_TAGS_PER_ARTIFACT",
    "PreviewStatus",
    "RegisterArtifactInput",
    "RETRIEVABLE_STATUSES",
    "SORT_COLUMNS",
    "UpdateArtifactInput",
]

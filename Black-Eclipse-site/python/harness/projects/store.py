"""The Project store — a named scope for the work that belongs together.

A **project** is the thing a quant workspace is missing: a name, the
instruments it covers, and the members that belong to it — a strategy, a
backtest, a dataset, an artifact, a note. Everything else in the system can
already carry a `projectId` label (runs, session messages, artifacts); what was
missing is the entity that label refers to.

Three properties matter:

1. **One store, one connection.** The tables live on `agent-memory.db`, the
   runtime's own database, owned by this module alone — never
   `eclipse-memory.db`, never `jdds.db`.
2. **The DDL is idempotent.** `CREATE TABLE IF NOT EXISTS` on first use, so a
   store can be constructed in any order and a migration is a no-op.
3. **A project is a label with a body, not a container of pointers.** A member
   is a `(kind, ref)` pair plus a label; the reference is owned by its own
   subsystem, and the project only remembers where to look.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

#: The kinds of thing a project can hold.
MEMBER_KINDS = ("strategy", "experiment", "dataset", "artifact", "chat", "note")


class ProjectError(ValueError):
    pass


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


@dataclass
class Project:
    """One project."""

    id: str
    name: str
    description: str = ""
    symbols: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    last_activity_at: str = ""
    archived_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "symbols": list(self.symbols),
            "tags": list(self.tags),
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "lastActivityAt": self.last_activity_at,
            "archivedAt": self.archived_at,
        }


@dataclass
class ProjectMember:
    """One thing attached to a project."""

    id: str
    project_id: str
    kind: str
    ref: str
    label: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "projectId": self.project_id,
            "kind": self.kind,
            "ref": self.ref,
            "label": self.label,
            "meta": dict(self.meta),
            "createdAt": self.created_at,
        }


_DDL = """
CREATE TABLE IF NOT EXISTS Project (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  description     TEXT NOT NULL DEFAULT '',
  symbolsJson     TEXT NOT NULL DEFAULT '[]',
  tagsJson        TEXT NOT NULL DEFAULT '[]',
  status          TEXT NOT NULL DEFAULT 'active',
  createdAt       TEXT NOT NULL,
  updatedAt       TEXT NOT NULL,
  lastActivityAt  TEXT NOT NULL,
  archivedAt      TEXT
);
CREATE TABLE IF NOT EXISTS ProjectMember (
  id          TEXT PRIMARY KEY,
  projectId   TEXT NOT NULL,
  kind        TEXT NOT NULL,
  ref         TEXT NOT NULL,
  label       TEXT NOT NULL DEFAULT '',
  metaJson    TEXT NOT NULL DEFAULT '{}',
  createdAt   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_project_member_project ON ProjectMember(projectId);
CREATE INDEX IF NOT EXISTS idx_project_status ON Project(status, updatedAt);
"""


class ProjectStore:
    """The projects and their members, on the runtime's own database."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_DDL)
        self._db.commit()

    # ── projects ─────────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        *,
        description: str = "",
        symbols: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        project_id: Optional[str] = None,
    ) -> Project:
        clean = str(name or "").strip()
        if not clean:
            raise ProjectError("a project needs a name")
        now = _now()
        project = Project(
            id=project_id or f"proj_{uuid.uuid4().hex[:12]}",
            name=clean[:200],
            description=str(description or "")[:2_000],
            symbols=[str(s) for s in (symbols or [])][:64],
            tags=[str(t) for t in (tags or [])][:32],
            status="active",
            created_at=now,
            updated_at=now,
            last_activity_at=now,
        )
        self._db.execute(
            "INSERT INTO Project (id,name,description,symbolsJson,tagsJson,status,"
            "createdAt,updatedAt,lastActivityAt,archivedAt) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (project.id, project.name, project.description,
             json.dumps(project.symbols), json.dumps(project.tags), project.status,
             project.created_at, project.updated_at, project.last_activity_at, None),
        )
        self._db.commit()
        return project

    def get(self, project_id: str) -> Optional[Project]:
        row = self._db.execute(
            "SELECT * FROM Project WHERE id=?", (str(project_id),)).fetchone()
        return self._row_to_project(row) if row else None

    def list(self, *, status: Optional[str] = None, limit: int = 50) -> list[Project]:
        limit = max(1, min(int(limit or 50), 200))
        if status:
            rows = self._db.execute(
                "SELECT * FROM Project WHERE status=? ORDER BY lastActivityAt DESC, "
                "rowid DESC LIMIT ?", (str(status), limit)).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM Project ORDER BY lastActivityAt DESC, rowid DESC "
                "LIMIT ?", (limit,)).fetchall()
        return [self._row_to_project(row) for row in rows]

    def update(self, project_id: str, **patch: Any) -> Optional[Project]:
        project = self.get(project_id)
        if project is None:
            return None
        if "name" in patch and patch["name"]:
            project.name = str(patch["name"])[:200]
        if "description" in patch:
            project.description = str(patch["description"] or "")[:2_000]
        if "symbols" in patch and patch["symbols"] is not None:
            project.symbols = [str(s) for s in patch["symbols"]][:64]
        if "tags" in patch and patch["tags"] is not None:
            project.tags = [str(t) for t in patch["tags"]][:32]
        if "status" in patch and patch["status"]:
            project.status = str(patch["status"])[:32]
        now = _now()
        project.updated_at = now
        self._db.execute(
            "UPDATE Project SET name=?,description=?,symbolsJson=?,tagsJson=?,status=?,"
            "updatedAt=?,archivedAt=? WHERE id=?",
            (project.name, project.description, json.dumps(project.symbols),
             json.dumps(project.tags), project.status, project.updated_at,
             now if project.status == "archived" else project.archived_at, project.id),
        )
        self._db.commit()
        return project

    def delete(self, project_id: str) -> bool:
        project = self.get(project_id)
        if project is None:
            return False
        self._db.execute("DELETE FROM ProjectMember WHERE projectId=?", (project.id,))
        self._db.execute("DELETE FROM Project WHERE id=?", (project.id,))
        self._db.commit()
        return True

    def touch(self, project_id: str) -> None:
        now = _now()
        self._db.execute(
            "UPDATE Project SET lastActivityAt=?, updatedAt=? WHERE id=?",
            (now, now, str(project_id)))
        self._db.commit()

    # ── members ──────────────────────────────────────────────────────────────

    def attach(
        self,
        project_id: str,
        kind: str,
        ref: str,
        *,
        label: str = "",
        meta: Optional[dict[str, Any]] = None,
    ) -> ProjectMember:
        project = self.get(project_id)
        if project is None:
            raise ProjectError(f"no project {project_id!r}")
        kind = str(kind or "").strip().lower()
        if kind not in MEMBER_KINDS:
            raise ProjectError(
                f"unknown member kind {kind!r}; expected one of "
                f"{', '.join(MEMBER_KINDS)}")
        ref = str(ref or "").strip()
        if not ref:
            raise ProjectError("a member needs a reference")
        member = ProjectMember(
            id=f"pmem_{uuid.uuid4().hex[:12]}",
            project_id=project.id,
            kind=kind,
            ref=ref[:400],
            label=str(label or "")[:300],
            meta=dict(meta or {}),
            created_at=_now(),
        )
        self._db.execute(
            "INSERT INTO ProjectMember (id,projectId,kind,ref,label,metaJson,createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (member.id, member.project_id, member.kind, member.ref, member.label,
             json.dumps(member.meta), member.created_at),
        )
        self.touch(project.id)
        return member

    def detach(self, project_id: str, member_id: str) -> bool:
        row = self._db.execute(
            "SELECT id FROM ProjectMember WHERE id=? AND projectId=?",
            (str(member_id), str(project_id))).fetchone()
        if row is None:
            return False
        self._db.execute("DELETE FROM ProjectMember WHERE id=?", (row["id"],))
        self._db.commit()
        self.touch(project_id)
        return True

    def members(self, project_id: str) -> list[ProjectMember]:
        rows = self._db.execute(
            "SELECT * FROM ProjectMember WHERE projectId=? ORDER BY createdAt ASC",
            (str(project_id),)).fetchall()
        return [self._row_to_member(row) for row in rows]

    # ── the brief ────────────────────────────────────────────────────────────

    def brief(self, project_id: str, *, max_members: int = 40) -> str:
        """A compact, honest summary of what the project holds."""
        project = self.get(project_id)
        if project is None:
            return ""
        members = self.members(project.id)
        lines = [f"## Project: {project.name} (`{project.id}`)"]
        if project.description:
            lines.append(project.description)
        if project.symbols:
            lines.append(f"Instruments: {', '.join(project.symbols)}")
        if project.tags:
            lines.append(f"Tags: {', '.join(project.tags)}")
        if members:
            lines.append("Members:")
            for member in members[:max_members]:
                label = f" — {member.label}" if member.label else ""
                lines.append(f"- {member.kind}: `{member.ref}`{label}")
            if len(members) > max_members:
                lines.append(f"- …and {len(members) - max_members} more")
        else:
            lines.append("Members: none yet.")
        return "\n".join(lines)

    def detail(self, project_id: str) -> Optional[dict[str, Any]]:
        project = self.get(project_id)
        if project is None:
            return None
        members = self.members(project.id)
        by_kind: dict[str, list[dict[str, Any]]] = {}
        for member in members:
            by_kind.setdefault(member.kind, []).append(member.to_dict())
        return {
            "project": project.to_dict(),
            "members": [m.to_dict() for m in members],
            "membersByKind": by_kind,
            "memberCount": len(members),
        }

    # ── row mapping ──────────────────────────────────────────────────────────

    def _row_to_project(self, row: Any) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"] or "",
            symbols=json.loads(row["symbolsJson"] or "[]"),
            tags=json.loads(row["tagsJson"] or "[]"),
            status=row["status"] or "active",
            created_at=row["createdAt"] or "",
            updated_at=row["updatedAt"] or "",
            last_activity_at=row["lastActivityAt"] or "",
            archived_at=row["archivedAt"],
        )

    def _row_to_member(self, row: Any) -> ProjectMember:
        try:
            meta = json.loads(row["metaJson"] or "{}")
        except (TypeError, ValueError):
            meta = {}
        return ProjectMember(
            id=row["id"],
            project_id=row["projectId"],
            kind=row["kind"],
            ref=row["ref"],
            label=row["label"] or "",
            meta=meta if isinstance(meta, dict) else {},
            created_at=row["createdAt"] or "",
        )


__all__ = [
    "MEMBER_KINDS",
    "Project",
    "ProjectError",
    "ProjectMember",
    "ProjectStore",
]

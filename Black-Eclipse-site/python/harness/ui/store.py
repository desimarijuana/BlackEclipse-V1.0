"""UI store — the durable rows on the ONE `agent-memory.db`.

Owns its own tables and NEVER reads another subsystem's rows. It is not JDdS
(`jdds.db`) and not another subsystem's agent-memory tables. Blueprints,
their bounded revision history, registered component specs and the operation
audit log all live here, so a restart restores the same UI state.

All state changes go through explicit methods; the service layer validates
before calling here. Listing builds a parameterized WHERE clause — no
caller-supplied string reaches SQL.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import new_id, now_iso
from .model import (
    Availability,
    BlueprintKind,
    BlueprintOwner,
    BlueprintScope,
    BlueprintSummary,
    CatalogQuery,
    ListBlueprintsQuery,
    MAX_HISTORY,
    OwnershipKind,
    UiBlueprint,
    UiComponentSpec,
    UiOperation,
    WorkspaceLayout,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS UiBlueprint (
  id          TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  description TEXT,
  kind        TEXT NOT NULL DEFAULT 'page',
  ownerKind   TEXT NOT NULL DEFAULT 'user',
  ownerId     TEXT NOT NULL DEFAULT 'operator',
  scope       TEXT NOT NULL DEFAULT 'personal',
  path        TEXT,
  tags        TEXT NOT NULL DEFAULT '[]',
  layout      TEXT NOT NULL DEFAULT '{}',
  revision    INTEGER NOT NULL DEFAULT 1,
  createdAt   TEXT NOT NULL,
  updatedAt   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS UiBlueprintRevision (
  id          TEXT PRIMARY KEY,
  blueprintId TEXT NOT NULL,
  revision    INTEGER NOT NULL,
  summary     TEXT NOT NULL DEFAULT '',
  changes     TEXT NOT NULL DEFAULT '[]',
  snapshot    TEXT NOT NULL,
  createdAt   TEXT NOT NULL,
  UNIQUE(blueprintId, revision)
);

CREATE TABLE IF NOT EXISTS UiComponent (
  id           TEXT PRIMARY KEY,
  version      TEXT NOT NULL DEFAULT '1.0.0',
  displayName  TEXT NOT NULL,
  description  TEXT NOT NULL DEFAULT '',
  category     TEXT NOT NULL DEFAULT 'other',
  icon         TEXT NOT NULL DEFAULT 'dashboard',
  tags         TEXT NOT NULL DEFAULT '[]',
  configSchema TEXT NOT NULL DEFAULT '[]',
  defaultConfig TEXT NOT NULL DEFAULT '{}',
  dataSources  TEXT NOT NULL DEFAULT '[]',
  actions      TEXT NOT NULL DEFAULT '[]',
  layout       TEXT NOT NULL DEFAULT '{}',
  availability TEXT NOT NULL DEFAULT 'available',
  owner        TEXT NOT NULL DEFAULT 'core',
  pluginId     TEXT,
  createdAt    TEXT NOT NULL,
  updatedAt    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS UiOperation (
  id          TEXT PRIMARY KEY,
  operation   TEXT NOT NULL,
  blueprintId TEXT,
  status      TEXT NOT NULL,
  actor       TEXT,
  detail      TEXT NOT NULL DEFAULT '',
  result      TEXT NOT NULL DEFAULT '{}',
  error       TEXT,
  createdAt   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS UiIdempotency (
  key         TEXT PRIMARY KEY,
  blueprintId TEXT NOT NULL,
  createdAt   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_uibp_scope    ON UiBlueprint(scope, kind);
CREATE INDEX IF NOT EXISTS idx_uibp_owner    ON UiBlueprint(ownerId, updatedAt);
CREATE INDEX IF NOT EXISTS idx_uibp_updated  ON UiBlueprint(updatedAt);
CREATE INDEX IF NOT EXISTS idx_uirev_bp      ON UiBlueprintRevision(blueprintId, revision);
CREATE INDEX IF NOT EXISTS idx_uicomp_owner  ON UiComponent(owner, category);
CREATE INDEX IF NOT EXISTS idx_uiop_bp       ON UiOperation(blueprintId, createdAt);
CREATE INDEX IF NOT EXISTS idx_uiop_created  ON UiOperation(createdAt);
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


class UiStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._db.executescript(_SCHEMA)
        self._db.commit()

    @property
    def _db(self):
        return self._store._db

    # ── blueprints ────────────────────────────────────────────────────────────

    def save_blueprint(self, blueprint: UiBlueprint, *, summary: str = "") -> UiBlueprint:
        now = now_iso()
        existing = self._db.execute("SELECT createdAt FROM UiBlueprint WHERE id=?", (blueprint.id,)).fetchone()
        created_at = existing["createdAt"] if existing else (blueprint.created_at or now)
        blueprint = blueprint.model_copy(update={"created_at": created_at, "updated_at": now})
        payload = blueprint.model_dump(by_alias=True)
        self._db.execute(
            """
            INSERT INTO UiBlueprint
              (id, title, description, kind, ownerKind, ownerId, scope, path, tags, layout,
               revision, createdAt, updatedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title, description=excluded.description, kind=excluded.kind,
              ownerKind=excluded.ownerKind, ownerId=excluded.ownerId, scope=excluded.scope,
              path=excluded.path, tags=excluded.tags, layout=excluded.layout,
              revision=excluded.revision, updatedAt=excluded.updatedAt
            """,
            (
                blueprint.id, blueprint.title, blueprint.description, blueprint.kind.value,
                blueprint.owner.kind.value, blueprint.owner.id, blueprint.scope.value,
                blueprint.path, _json(blueprint.tags or []), _json(payload["layout"]),
                blueprint.revision, created_at, now,
            ),
        )
        self._db.commit()
        self.append_revision(blueprint, summary=summary)
        return blueprint

    def get_blueprint(self, blueprint_id: str, *, owner_id: Optional[str] = None) -> Optional[UiBlueprint]:
        row = self._db.execute("SELECT * FROM UiBlueprint WHERE id=?", (blueprint_id,)).fetchone()
        if row is None:
            return None
        if owner_id is not None and row["ownerId"] != owner_id:
            return None
        return self._hydrate(row)

    def get_blueprint_unscoped(self, blueprint_id: str) -> Optional[UiBlueprint]:
        """Fetch by id WITHOUT owner filtering.

        The service layer uses this so it can distinguish "no such blueprint"
        from "the blueprint exists but belongs to another owner" and raise a
        distinct, actionable error instead of collapsing both into not-found.
        """
        row = self._db.execute("SELECT * FROM UiBlueprint WHERE id=?", (blueprint_id,)).fetchone()
        return self._hydrate(row) if row is not None else None

    def list_blueprints(self, query: ListBlueprintsQuery, *, owner_id: Optional[str] = None) -> tuple[list[BlueprintSummary], int]:
        where: list[str] = []
        params: list[Any] = []
        if query.scope is not None:
            where.append("scope=?")
            params.append(query.scope.value)
        if query.kind is not None:
            where.append("kind=?")
            params.append(query.kind.value)
        if query.owner_id is not None:
            where.append("ownerId=?")
            params.append(query.owner_id)
        if owner_id is not None:
            where.append("ownerId=?")
            params.append(owner_id)
        if query.q:
            like = f"%{query.q.lower()}%"
            where.append("(lower(title) LIKE ? OR lower(COALESCE(description,'')) LIKE ? OR lower(COALESCE(path,'')) LIKE ?)")
            params.extend([like, like, like])
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        total = self._db.execute(f"SELECT COUNT(*) AS n FROM UiBlueprint {clause}", params).fetchone()["n"]  # noqa: S608
        rows = self._db.execute(
            f"SELECT * FROM UiBlueprint {clause} ORDER BY updatedAt DESC, id ASC LIMIT ? OFFSET ?",  # noqa: S608
            [*params, query.limit, query.offset],
        ).fetchall()
        return [self._summary(row) for row in rows], int(total)

    def delete_blueprint(self, blueprint_id: str) -> bool:
        cur = self._db.execute("DELETE FROM UiBlueprint WHERE id=?", (blueprint_id,))
        self._db.execute("DELETE FROM UiBlueprintRevision WHERE blueprintId=?", (blueprint_id,))
        self._db.commit()
        return cur.rowcount > 0

    # ── revisions ─────────────────────────────────────────────────────────────

    def append_revision(self, blueprint: UiBlueprint, *, summary: str = "", changes: Optional[list[dict[str, Any]]] = None) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO UiBlueprintRevision "
            "(id, blueprintId, revision, summary, changes, snapshot, createdAt) VALUES (?,?,?,?,?,?,?)",
            (
                new_id("uirev"), blueprint.id, blueprint.revision, summary or f"revision {blueprint.revision}",
                _json(changes or []), _json(blueprint.model_dump(by_alias=True)), now_iso(),
            ),
        )
        # Bound the retained history to MAX_HISTORY snapshots (oldest dropped).
        self._db.execute(
            "DELETE FROM UiBlueprintRevision WHERE blueprintId=? AND revision NOT IN "
            "(SELECT revision FROM UiBlueprintRevision WHERE blueprintId=? ORDER BY revision DESC LIMIT ?)",
            (blueprint.id, blueprint.id, MAX_HISTORY),
        )
        self._db.commit()

    def history(self, blueprint_id: str, limit: int = MAX_HISTORY) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT revision, summary, changes, snapshot, createdAt FROM UiBlueprintRevision "
            "WHERE blueprintId=? ORDER BY revision DESC LIMIT ?",
            (blueprint_id, limit),
        ).fetchall()
        return [
            {
                "revision": r["revision"], "summary": r["summary"],
                "changes": _loads(r["changes"], []), "snapshot": _loads(r["snapshot"], {}),
                "createdAt": r["createdAt"],
            }
            for r in rows
        ]

    def get_revision(self, blueprint_id: str, revision: int) -> Optional[UiBlueprint]:
        row = self._db.execute(
            "SELECT snapshot FROM UiBlueprintRevision WHERE blueprintId=? AND revision=?",
            (blueprint_id, revision),
        ).fetchone()
        if row is None:
            return None
        try:
            return UiBlueprint.model_validate(_loads(row["snapshot"], {}))
        except Exception:  # noqa: BLE001
            return None

    # ── components ────────────────────────────────────────────────────────────

    def upsert_component(self, spec: UiComponentSpec) -> UiComponentSpec:
        now = now_iso()
        payload = spec.model_dump(by_alias=True)
        self._db.execute(
            """
            INSERT INTO UiComponent
              (id, version, displayName, description, category, icon, tags, configSchema,
               defaultConfig, dataSources, actions, layout, availability, owner, pluginId, createdAt, updatedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              version=excluded.version, displayName=excluded.displayName, description=excluded.description,
              category=excluded.category, icon=excluded.icon, tags=excluded.tags,
              configSchema=excluded.configSchema, defaultConfig=excluded.defaultConfig,
              dataSources=excluded.dataSources, actions=excluded.actions, layout=excluded.layout,
              availability=excluded.availability, owner=excluded.owner, pluginId=excluded.pluginId,
              updatedAt=excluded.updatedAt
            """,
            (
                spec.id, spec.version, spec.display_name, spec.description, spec.category, spec.icon,
                _json(spec.tags), _json(payload["configSchema"]), _json(spec.default_config),
                _json(spec.data_sources), _json(spec.actions), _json(payload["layout"]),
                spec.availability.value, spec.owner.value, spec.plugin_id, now, now,
            ),
        )
        self._db.commit()
        return spec

    def get_component(self, component_id: str) -> Optional[UiComponentSpec]:
        row = self._db.execute("SELECT * FROM UiComponent WHERE id=?", (component_id,)).fetchone()
        return self._component_row(row) if row else None

    def list_components(self, query: Optional[CatalogQuery] = None) -> list[UiComponentSpec]:
        rows = self._db.execute("SELECT * FROM UiComponent ORDER BY id ASC").fetchall()
        specs = [self._component_row(r) for r in rows]
        if query is not None and query.owner is not None:
            specs = [s for s in specs if s.owner == query.owner]
        return specs

    def delete_component(self, component_id: str) -> bool:
        cur = self._db.execute("DELETE FROM UiComponent WHERE id=?", (component_id,))
        self._db.commit()
        return cur.rowcount > 0

    # ── operations ────────────────────────────────────────────────────────────

    def record_operation(self, operation: UiOperation) -> UiOperation:
        self._db.execute(
            "INSERT OR REPLACE INTO UiOperation "
            "(id, operation, blueprintId, status, actor, detail, result, error, createdAt) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                operation.id, operation.operation, operation.blueprint_id, operation.status,
                operation.actor, operation.detail, _json(operation.result), operation.error,
                operation.created_at,
            ),
        )
        self._db.commit()
        return operation

    def get_operation(self, operation_id: str) -> Optional[UiOperation]:
        row = self._db.execute("SELECT * FROM UiOperation WHERE id=?", (operation_id,)).fetchone()
        if row is None:
            return None
        return UiOperation(
            id=row["id"], operation=row["operation"], blueprint_id=row["blueprintId"],
            status=row["status"], actor=row["actor"], detail=row["detail"] or "",
            result=_loads(row["result"], {}), error=row["error"], created_at=row["createdAt"],
        )

    # ── idempotency ───────────────────────────────────────────────────────────

    def lookup_idempotency(self, key: str) -> Optional[str]:
        row = self._db.execute("SELECT blueprintId FROM UiIdempotency WHERE key=?", (key,)).fetchone()
        return row["blueprintId"] if row else None

    def record_idempotency(self, key: str, blueprint_id: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO UiIdempotency (key, blueprintId, createdAt) VALUES (?,?,?)",
            (key, blueprint_id, now_iso()),
        )
        self._db.commit()

    # ── row mapping ───────────────────────────────────────────────────────────

    def _hydrate(self, row: Any) -> UiBlueprint:
        return UiBlueprint(
            schema_version=1,
            id=row["id"], title=row["title"], description=row["description"],
            kind=_enum(BlueprintKind, row["kind"], BlueprintKind.PAGE),
            owner=BlueprintOwner(kind=_enum(OwnershipKind, row["ownerKind"], OwnershipKind.USER), id=row["ownerId"]),
            scope=_enum(BlueprintScope, row["scope"], BlueprintScope.PERSONAL),
            path=row["path"], tags=_loads(row["tags"], []),
            layout=WorkspaceLayout.model_validate(_loads(row["layout"], {"version": 2, "sections": []})),
            revision=row["revision"], created_at=row["createdAt"], updated_at=row["updatedAt"],
        )

    def _summary(self, row: Any) -> BlueprintSummary:
        layout = WorkspaceLayout.model_validate(_loads(row["layout"], {"version": 2, "sections": []}))
        components = [w.widget_id for s in layout.sections for c in s.columns for w in c.widgets]
        return BlueprintSummary(
            id=row["id"], title=row["title"], kind=_enum(BlueprintKind, row["kind"], BlueprintKind.PAGE),
            scope=_enum(BlueprintScope, row["scope"], BlueprintScope.PERSONAL), owner_id=row["ownerId"],
            path=row["path"], revision=row["revision"], updated_at=row["updatedAt"],
            widget_count=len(components), component_ids=components,
        )

    def _component_row(self, row: Any) -> UiComponentSpec:
        payload = {
            "id": row["id"], "version": row["version"], "displayName": row["displayName"],
            "description": row["description"], "category": row["category"], "icon": row["icon"],
            "tags": _loads(row["tags"], []), "configSchema": _loads(row["configSchema"], []),
            "defaultConfig": _loads(row["defaultConfig"], {}),
            "dataSources": _loads(row["dataSources"], []), "actions": _loads(row["actions"], []),
            "layout": _loads(row["layout"], {}), "availability": row["availability"],
            "owner": row["owner"], "pluginId": row["pluginId"],
        }
        return UiComponentSpec.model_validate(payload)


__all__ = ["UiStore"]

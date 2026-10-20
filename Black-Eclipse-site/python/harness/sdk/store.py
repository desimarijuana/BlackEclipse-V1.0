"""Durable rows for the Eclipse SDK on the ONE `agent-memory.db`.

Four tables only:
  * `SdkWidget` — a user widget definition (a primitive + source + config);
  * `SdkLock`   — a passphrase lock over a page/widget/portfolio/design;
  * `SdkMeta`   — small runtime secrets (the lock-token signing key).
  * `SdkAudit`  - append-only SDK activity (no secrets), bounded to 2,000 rows.

The SDK owns no second database and no second blueprint/portfolio store; those
remain the UI Engineering and Portfolio subsystems.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import new_id, now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS SdkWidget (
  id           TEXT PRIMARY KEY,
  componentId  TEXT NOT NULL UNIQUE,
  slug         TEXT NOT NULL UNIQUE,
  label        TEXT NOT NULL,
  description  TEXT NOT NULL DEFAULT '',
  icon         TEXT NOT NULL DEFAULT 'dashboard',
  category     TEXT NOT NULL DEFAULT 'custom',
  primitive    TEXT NOT NULL DEFAULT 'data-table',
  source       TEXT,
  surface      TEXT NOT NULL DEFAULT 'both',
  config       TEXT NOT NULL DEFAULT '{}',
  sizes        TEXT NOT NULL DEFAULT '[]',
  createdAt    TEXT NOT NULL,
  updatedAt    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS SdkLock (
  id            TEXT PRIMARY KEY,
  resourceType  TEXT NOT NULL,
  resourceId    TEXT NOT NULL,
  label         TEXT,
  hint          TEXT,
  passphraseHash TEXT NOT NULL,
  salt          TEXT NOT NULL,
  iterations    INTEGER NOT NULL DEFAULT 200000,
  createdBy     TEXT,
  createdAt     TEXT NOT NULL,
  updatedAt     TEXT NOT NULL,
  UNIQUE(resourceType, resourceId)
);

CREATE TABLE IF NOT EXISTS SdkMeta (
  key       TEXT PRIMARY KEY,
  value     TEXT NOT NULL,
  updatedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS SdkAudit (
  id           TEXT PRIMARY KEY,
  actor        TEXT,
  action       TEXT NOT NULL,
  resourceType TEXT,
  resourceId   TEXT,
  summary      TEXT NOT NULL DEFAULT '',
  detail       TEXT NOT NULL DEFAULT '{}',
  createdAt    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sdk_widget_updated ON SdkWidget(updatedAt);
CREATE INDEX IF NOT EXISTS idx_sdk_lock_resource ON SdkLock(resourceType, resourceId);
CREATE INDEX IF NOT EXISTS idx_sdk_audit_created ON SdkAudit(createdAt);
CREATE INDEX IF NOT EXISTS idx_sdk_audit_action ON SdkAudit(action);
"""

MAX_AUDIT_ROWS = 2_000
MAX_AUDIT_LIST = 500


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


class SdkStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._db.executescript(_SCHEMA)
        self._ensure_column("SdkWidget", "surface", "surface TEXT NOT NULL DEFAULT 'both'")
        self._db.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        columns = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            self._db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    @property
    def _db(self):
        return self._store._db

    # ── user widgets ─────────────────────────────────────────────────────────

    def upsert_widget(
        self,
        *,
        slug: str,
        component_id: str,
        label: str,
        description: str,
        icon: str,
        category: str,
        primitive: str,
        source: Optional[str],
        surface: str,
        config: dict[str, Any],
        sizes: list[str],
    ) -> dict[str, Any]:
        now = now_iso()
        existing = self._db.execute("SELECT id, createdAt FROM SdkWidget WHERE slug=?", (slug,)).fetchone()
        widget_id = existing["id"] if existing else new_id("sdkw")
        created_at = existing["createdAt"] if existing else now
        self._db.execute(
            """
            INSERT INTO SdkWidget
              (id, componentId, slug, label, description, icon, category, primitive,
               source, surface, config, sizes, createdAt, updatedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(slug) DO UPDATE SET
              componentId=excluded.componentId, label=excluded.label,
              description=excluded.description, icon=excluded.icon,
              category=excluded.category, primitive=excluded.primitive,
              source=excluded.source, surface=excluded.surface,
              config=excluded.config, sizes=excluded.sizes,
              updatedAt=excluded.updatedAt
            """,
            (
                widget_id, component_id, slug, label, description, icon, category,
                primitive, source, surface, _json(config), _json(sizes), created_at, now,
            ),
        )
        self._db.commit()
        row = self.get_widget(component_id)
        assert row is not None
        return row

    def get_widget(self, component_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM SdkWidget WHERE componentId=?", (component_id,)).fetchone()
        return self._widget_row(row) if row else None

    def list_widgets(self) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT * FROM SdkWidget ORDER BY updatedAt DESC, id ASC").fetchall()
        return [self._widget_row(r) for r in rows]

    def delete_widget(self, component_id: str) -> bool:
        cur = self._db.execute("DELETE FROM SdkWidget WHERE componentId=?", (component_id,))
        self._db.commit()
        return cur.rowcount > 0

    def _widget_row(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "componentId": row["componentId"],
            "slug": row["slug"],
            "label": row["label"],
            "description": row["description"] or "",
            "icon": row["icon"] or "dashboard",
            "category": row["category"] or "custom",
            "primitive": row["primitive"] or "data-table",
            "source": row["source"],
            "surface": row["surface"] or "both",
            "config": _loads(row["config"], {}),
            "sizes": _loads(row["sizes"], []),
            "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
        }

    # ── locks ────────────────────────────────────────────────────────────────

    def create_lock(
        self,
        *,
        resource_type: str,
        resource_id: str,
        passphrase_hash: str,
        salt: str,
        iterations: int,
        label: Optional[str],
        hint: Optional[str],
        created_by: Optional[str],
    ) -> dict[str, Any]:
        now = now_iso()
        existing = self._db.execute(
            "SELECT id FROM SdkLock WHERE resourceType=? AND resourceId=?",
            (resource_type, resource_id),
        ).fetchone()
        lock_id = existing["id"] if existing else new_id("lock")
        self._db.execute(
            """
            INSERT INTO SdkLock
              (id, resourceType, resourceId, label, hint, passphraseHash, salt,
               iterations, createdBy, createdAt, updatedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(resourceType, resourceId) DO UPDATE SET
              label=excluded.label, hint=excluded.hint,
              passphraseHash=excluded.passphraseHash, salt=excluded.salt,
              iterations=excluded.iterations, createdBy=excluded.createdBy,
              updatedAt=excluded.updatedAt
            """,
            (
                lock_id, resource_type, resource_id, label, hint, passphrase_hash,
                salt, iterations, created_by, now, now,
            ),
        )
        self._db.commit()
        return self.get_lock_by_resource(resource_type, resource_id)  # type: ignore[return-value]

    def get_lock(self, lock_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM SdkLock WHERE id=?", (lock_id,)).fetchone()
        return dict(row) if row else None

    def get_lock_by_resource(self, resource_type: str, resource_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM SdkLock WHERE resourceType=? AND resourceId=?",
            (resource_type, resource_id),
        ).fetchone()
        return dict(row) if row else None

    def list_locks(self, *, resource_type: Optional[str] = None, resource_id: Optional[str] = None) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if resource_type:
            where.append("resourceType=?")
            params.append(resource_type)
        if resource_id:
            where.append("resourceId=?")
            params.append(resource_id)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._db.execute(
            f"SELECT * FROM SdkLock {clause} ORDER BY updatedAt DESC, id ASC",  # noqa: S608
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_lock(self, lock_id: str) -> bool:
        cur = self._db.execute("DELETE FROM SdkLock WHERE id=?", (lock_id,))
        self._db.commit()
        return cur.rowcount > 0

    # ── meta ─────────────────────────────────────────────────────────────────

    def get_meta(self, key: str) -> Optional[str]:
        row = self._db.execute("SELECT value FROM SdkMeta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO SdkMeta (key, value, updatedAt) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updatedAt=excluded.updatedAt",
            (key, value, now_iso()),
        )
        self._db.commit()

    # ── audit ─────────────────────────────────────────────────────────────────

    def record_audit(
        self,
        *,
        action: str,
        actor: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        summary: str = "",
        detail: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Append one SDK activity row. Never stores passphrases or lock hashes."""
        entry_id = new_id("aud")
        now = now_iso()
        self._db.execute(
            "INSERT INTO SdkAudit "
            "(id, actor, action, resourceType, resourceId, summary, detail, createdAt) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (entry_id, actor, action, resource_type, resource_id, summary, _json(detail or {}), now),
        )
        # Keep the local audit bounded; the newest rows win.
        self._db.execute(
            "DELETE FROM SdkAudit WHERE rowid NOT IN "
            "(SELECT rowid FROM SdkAudit ORDER BY createdAt DESC, rowid DESC LIMIT ?)",
            (MAX_AUDIT_ROWS,),
        )
        self._db.commit()
        row = self._db.execute("SELECT * FROM SdkAudit WHERE id=?", (entry_id,)).fetchone()
        return self._audit_row(row) if row else {
            "id": entry_id,
            "actor": actor,
            "action": action,
            "resourceType": resource_type,
            "resourceId": resource_id,
            "summary": summary,
            "detail": detail or {},
            "createdAt": now,
        }

    def list_audit(
        self,
        *,
        limit: int = 100,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        count = max(1, min(int(limit), MAX_AUDIT_LIST))
        where: list[str] = []
        params: list[Any] = []
        if action:
            where.append("action=?")
            params.append(action)
        if resource_type:
            where.append("resourceType=?")
            params.append(resource_type)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(count)
        rows = self._db.execute(
            f"SELECT * FROM SdkAudit {clause} ORDER BY createdAt DESC, rowid DESC LIMIT ?",  # noqa: S608
            params,
        ).fetchall()
        return [self._audit_row(row) for row in rows]

    def audit_count(self) -> int:
        row = self._db.execute("SELECT COUNT(*) AS n FROM SdkAudit").fetchone()
        return int(row["n"]) if row else 0

    @staticmethod
    def _audit_row(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "actor": row["actor"],
            "action": row["action"],
            "resourceType": row["resourceType"],
            "resourceId": row["resourceId"],
            "summary": row["summary"] or "",
            "detail": _loads(row["detail"], {}),
            "createdAt": row["createdAt"],
        }


__all__ = ["MAX_AUDIT_LIST", "MAX_AUDIT_ROWS", "SdkStore"]

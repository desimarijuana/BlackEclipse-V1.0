"""Plugin persistence, bound to the ONE agent-memory connection.

Owns the plugin registry tables on `agent-memory.db` (never `eclipse-memory.db`
and never `jdds.db`). The DDL is idempotent (`CREATE TABLE IF NOT EXISTS`) and is
applied on first use, mirroring `code/store.py`, `run_lineage.py` and
`mcp/approvals.py`, so `persistence.py` — pinned at its size ratchet — does not
grow.

The store is the source of truth for installed plugins, their state, their
contributions, configuration, secrets (ciphertext only), scoped storage, health,
install history and a bounded log. Filesystem scanning is discovery, never
authority.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..persistence import now_iso


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
from .model import PluginRecord, PluginState, TrustLevel

MAX_LOG_ROWS = 2000
MAX_EVENT_ROWS = 5000


def _record(row: Any) -> PluginRecord:
    return PluginRecord(
        plugin_id=row["id"],
        name=row["name"],
        version=row["version"],
        publisher=row["publisher"] or "unknown",
        manifest=json.loads(row["manifest"]) if row["manifest"] else {},
        status=PluginState(row["status"]) if row["status"] in {s.value for s in PluginState} else PluginState.DISCOVERED,
        enabled=bool(row["enabled"]),
        trust=TrustLevel(row["trust"]) if row["trust"] in {t.value for t in TrustLevel} else TrustLevel.COMMUNITY,
        installation_path=row["installPath"] or "",
        installed_at=row["installedAt"] or "",
        updated_at=row["updatedAt"] or "",
        sdk_version=row["sdkVersion"] or "",
        runtime_type=row["runtimeType"] or "python",
        permissions=json.loads(row["permissions"]) if row["permissions"] else [],
        dependencies=json.loads(row["dependencies"]) if row["dependencies"] else [],
        checksum=row["checksum"] or "",
        signature=row["signature"],
        verification=row["verification"] or "unsigned",
        health=row["health"] or "unknown",
        configuration=json.loads(row["configuration"]) if row["configuration"] else {},
        last_error=row["lastError"],
    )


class PluginStore:
    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS Plugin (
              id           TEXT PRIMARY KEY,
              name         TEXT NOT NULL,
              version      TEXT NOT NULL,
              publisher    TEXT,
              manifest     TEXT NOT NULL,
              status       TEXT NOT NULL DEFAULT 'DISCOVERED',
              enabled      INTEGER NOT NULL DEFAULT 0,
              trust        TEXT NOT NULL DEFAULT 'community',
              installPath  TEXT,
              sdkVersion   TEXT,
              runtimeType  TEXT,
              permissions  TEXT,
              dependencies TEXT,
              checksum     TEXT,
              signature    TEXT,
              verification TEXT DEFAULT 'unsigned',
              health       TEXT DEFAULT 'unknown',
              configuration TEXT,
              lastError    TEXT,
              installedAt  TEXT,
              updatedAt    TEXT
            );

            CREATE TABLE IF NOT EXISTS PluginContribution (
              id         TEXT PRIMARY KEY,
              pluginId   TEXT NOT NULL,
              kind       TEXT NOT NULL,
              name       TEXT NOT NULL,
              meta       TEXT,
              registeredAt TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_plugin_contrib_plugin ON PluginContribution(pluginId, kind);

            CREATE TABLE IF NOT EXISTS PluginConfig (
              pluginId   TEXT NOT NULL,
              key        TEXT NOT NULL,
              value      TEXT,
              updatedAt  TEXT NOT NULL,
              PRIMARY KEY (pluginId, key)
            );

            CREATE TABLE IF NOT EXISTS PluginSecret (
              pluginId   TEXT NOT NULL,
              name       TEXT NOT NULL,
              ciphertext TEXT NOT NULL,
              createdAt  TEXT NOT NULL,
              updatedAt  TEXT NOT NULL,
              PRIMARY KEY (pluginId, name)
            );

            CREATE TABLE IF NOT EXISTS PluginStorage (
              pluginId   TEXT NOT NULL,
              namespace  TEXT NOT NULL,
              key        TEXT NOT NULL,
              value      TEXT,
              updatedAt  TEXT NOT NULL,
              PRIMARY KEY (pluginId, namespace, key)
            );

            CREATE TABLE IF NOT EXISTS PluginEventLog (
              id         TEXT PRIMARY KEY,
              pluginId   TEXT NOT NULL,
              type       TEXT NOT NULL,
              status     TEXT NOT NULL,
              detail     TEXT,
              at         TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_plugin_event_plugin ON PluginEventLog(pluginId, at);

            CREATE TABLE IF NOT EXISTS PluginHealth (
              pluginId       TEXT PRIMARY KEY,
              status         TEXT NOT NULL DEFAULT 'unknown',
              uptimeS        REAL NOT NULL DEFAULT 0,
              toolCalls      INTEGER NOT NULL DEFAULT 0,
              toolFailures   INTEGER NOT NULL DEFAULT 0,
              eventFailures  INTEGER NOT NULL DEFAULT 0,
              httpFailures   INTEGER NOT NULL DEFAULT 0,
              hookFailures   INTEGER NOT NULL DEFAULT 0,
              crashes        INTEGER NOT NULL DEFAULT 0,
              restarts       INTEGER NOT NULL DEFAULT 0,
              latencyMs      REAL NOT NULL DEFAULT 0,
              authStatus     TEXT,
              lastError      TEXT,
              startedAt      TEXT,
              updatedAt      TEXT
            );

            CREATE TABLE IF NOT EXISTS PluginInstallHistory (
              id          TEXT PRIMARY KEY,
              pluginId    TEXT NOT NULL,
              action      TEXT NOT NULL,
              fromVersion TEXT,
              toVersion   TEXT,
              status      TEXT NOT NULL,
              snapshot    TEXT,
              at          TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_plugin_history_plugin ON PluginInstallHistory(pluginId, at);

            CREATE TABLE IF NOT EXISTS PluginLog (
              id       TEXT PRIMARY KEY,
              pluginId TEXT NOT NULL,
              level    TEXT NOT NULL,
              message  TEXT NOT NULL,
              at       TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_plugin_log_plugin ON PluginLog(pluginId, at);
            """
        )
        self._db.commit()

    # ── registry rows ────────────────────────────────────────────────────────

    def upsert_plugin(self, record: PluginRecord) -> None:
        now = now_iso()
        record.updated_at = record.updated_at or now
        record.installed_at = record.installed_at or now
        self._db.execute(
            """
            INSERT INTO Plugin (id, name, version, publisher, manifest, status, enabled, trust,
                                installPath, sdkVersion, runtimeType, permissions, dependencies,
                                checksum, signature, verification, health, configuration, lastError,
                                installedAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, version=excluded.version, publisher=excluded.publisher,
                manifest=excluded.manifest, status=excluded.status, enabled=excluded.enabled,
                trust=excluded.trust, installPath=excluded.installPath, sdkVersion=excluded.sdkVersion,
                runtimeType=excluded.runtimeType, permissions=excluded.permissions,
                dependencies=excluded.dependencies, checksum=excluded.checksum,
                signature=excluded.signature, verification=excluded.verification,
                health=excluded.health, configuration=excluded.configuration,
                lastError=excluded.lastError, updatedAt=excluded.updatedAt
            """,
            (
                record.plugin_id, record.name, record.version, record.publisher,
                json.dumps(record.manifest), record.status.value, int(record.enabled),
                record.trust.value, record.installation_path, record.sdk_version,
                record.runtime_type, json.dumps(record.permissions),
                json.dumps(record.dependencies), record.checksum, record.signature,
                record.verification, record.health, json.dumps(record.configuration),
                record.last_error, record.installed_at, record.updated_at,
            ),
        )
        self._db.commit()

    def get_plugin(self, plugin_id: str) -> Optional[PluginRecord]:
        row = self._db.execute("SELECT * FROM Plugin WHERE id=?", (plugin_id,)).fetchone()
        return _record(row) if row else None

    def list_plugins(self) -> list[PluginRecord]:
        rows = self._db.execute("SELECT * FROM Plugin ORDER BY name COLLATE NOCASE").fetchall()
        return [_record(r) for r in rows]

    def set_state(
        self, plugin_id: str, state: PluginState, *, enabled: Optional[bool] = None,
        last_error: Optional[str] = None, health: Optional[str] = None,
    ) -> None:
        sets = ["status = ?", "updatedAt = ?"]
        params: list[Any] = [state.value, now_iso()]
        if enabled is not None:
            sets.append("enabled = ?")
            params.append(int(enabled))
        if last_error is not None:
            sets.append("lastError = ?")
            params.append(last_error)
        if health is not None:
            sets.append("health = ?")
            params.append(health)
        params.append(plugin_id)
        self._db.execute(f"UPDATE Plugin SET {', '.join(sets)} WHERE id=?", params)
        self._db.commit()

    def delete_plugin(self, plugin_id: str) -> None:
        for table in ("Plugin", "PluginContribution", "PluginConfig", "PluginSecret",
                      "PluginStorage", "PluginHealth", "PluginInstallHistory", "PluginLog"):
            self._db.execute(f"DELETE FROM {table} WHERE {'id' if table == 'Plugin' else 'pluginId'}=?", (plugin_id,))
        self._db.commit()

    # ── contributions ────────────────────────────────────────────────────────

    def register_contribution(self, plugin_id: str, kind: str, name: str, meta: Optional[dict[str, Any]] = None) -> None:
        cid = f"{plugin_id}:{kind}:{name}"
        self._db.execute(
            """INSERT INTO PluginContribution (id, pluginId, kind, name, meta, registeredAt)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET meta=excluded.meta, registeredAt=excluded.registeredAt""",
            (cid, plugin_id, kind, name, json.dumps(meta or {}), now_iso()),
        )
        self._db.commit()

    def list_contributions(self, plugin_id: Optional[str] = None, kind: Optional[str] = None) -> list[dict[str, Any]]:
        where, params = [], []
        if plugin_id:
            where.append("pluginId=?"); params.append(plugin_id)
        if kind:
            where.append("kind=?"); params.append(kind)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self._db.execute(f"SELECT * FROM PluginContribution{clause} ORDER BY kind, name", params).fetchall()
        return [
            {"pluginId": r["pluginId"], "kind": r["kind"], "name": r["name"], "meta": json.loads(r["meta"] or "{}")}
            for r in rows
        ]

    def clear_contributions(self, plugin_id: str) -> None:
        self._db.execute("DELETE FROM PluginContribution WHERE pluginId=?", (plugin_id,))
        self._db.commit()

    # ── configuration ────────────────────────────────────────────────────────

    def get_config(self, plugin_id: str) -> dict[str, Any]:
        rows = self._db.execute("SELECT key, value FROM PluginConfig WHERE pluginId=?", (plugin_id,)).fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    def set_config(self, plugin_id: str, key: str, value: Any) -> None:
        self._db.execute(
            """INSERT INTO PluginConfig (pluginId, key, value, updatedAt) VALUES (?, ?, ?, ?)
               ON CONFLICT(pluginId, key) DO UPDATE SET value=excluded.value, updatedAt=excluded.updatedAt""",
            (plugin_id, key, json.dumps(value), now_iso()),
        )
        self._db.commit()

    def delete_config(self, plugin_id: str, key: str) -> None:
        self._db.execute("DELETE FROM PluginConfig WHERE pluginId=? AND key=?", (plugin_id, key))
        self._db.commit()

    # ── secrets (ciphertext only — never plaintext here) ─────────────────────

    def set_secret(self, plugin_id: str, name: str, ciphertext: str, *, created: bool = False) -> None:
        now = now_iso()
        self._db.execute(
            """INSERT INTO PluginSecret (pluginId, name, ciphertext, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(pluginId, name) DO UPDATE SET ciphertext=excluded.ciphertext, updatedAt=excluded.updatedAt""",
            (plugin_id, name, ciphertext, now, now),
        )
        self._db.commit()

    def get_secret_ciphertext(self, plugin_id: str, name: str) -> Optional[str]:
        row = self._db.execute(
            "SELECT ciphertext FROM PluginSecret WHERE pluginId=? AND name=?", (plugin_id, name)
        ).fetchone()
        return row["ciphertext"] if row else None

    def list_secret_names(self, plugin_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT name FROM PluginSecret WHERE pluginId=? ORDER BY name", (plugin_id,)
        ).fetchall()
        return [r["name"] for r in rows]

    def delete_secret(self, plugin_id: str, name: str) -> None:
        self._db.execute("DELETE FROM PluginSecret WHERE pluginId=? AND name=?", (plugin_id, name))
        self._db.commit()

    # ── scoped storage ───────────────────────────────────────────────────────

    def kv_set(self, plugin_id: str, namespace: str, key: str, value: Any) -> None:
        self._db.execute(
            """INSERT INTO PluginStorage (pluginId, namespace, key, value, updatedAt)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(pluginId, namespace, key) DO UPDATE SET value=excluded.value, updatedAt=excluded.updatedAt""",
            (plugin_id, namespace, key, json.dumps(value), now_iso()),
        )
        self._db.commit()

    def kv_get(self, plugin_id: str, namespace: str, key: str) -> Any:
        row = self._db.execute(
            "SELECT value FROM PluginStorage WHERE pluginId=? AND namespace=? AND key=?",
            (plugin_id, namespace, key),
        ).fetchone()
        return json.loads(row["value"]) if row and row["value"] is not None else None

    def kv_delete(self, plugin_id: str, namespace: str, key: str) -> None:
        self._db.execute(
            "DELETE FROM PluginStorage WHERE pluginId=? AND namespace=? AND key=?",
            (plugin_id, namespace, key),
        )
        self._db.commit()

    def kv_list(self, plugin_id: str, namespace: str) -> dict[str, Any]:
        rows = self._db.execute(
            "SELECT key, value FROM PluginStorage WHERE pluginId=? AND namespace=? ORDER BY key",
            (plugin_id, namespace),
        ).fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    def kv_namespaces(self, plugin_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT DISTINCT namespace FROM PluginStorage WHERE pluginId=? ORDER BY namespace",
            (plugin_id,),
        ).fetchall()
        return [r["namespace"] for r in rows]

    def clear_storage(self, plugin_id: str) -> None:
        self._db.execute("DELETE FROM PluginStorage WHERE pluginId=?", (plugin_id,))
        self._db.commit()

    # ── event log ────────────────────────────────────────────────────────────

    def log_event(self, plugin_id: str, event_type: str, status: str, detail: Optional[dict[str, Any]] = None) -> None:
        self._db.execute(
            "INSERT INTO PluginEventLog (id, pluginId, type, status, detail, at) VALUES (?, ?, ?, ?, ?, ?)",
            (_new_id("pev"), plugin_id, event_type, status,
             json.dumps(detail or {}), now_iso()),
        )
        self._db.commit()
        if count := self._db.execute("SELECT COUNT(*) AS c FROM PluginEventLog").fetchone()["c"]:
            if count > MAX_EVENT_ROWS:
                self._db.execute(
                    "DELETE FROM PluginEventLog WHERE id IN (SELECT id FROM PluginEventLog ORDER BY at ASC LIMIT ?)",
                    (count - MAX_EVENT_ROWS,),
                )
                self._db.commit()

    def list_events(self, plugin_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if plugin_id:
            rows = self._db.execute(
                "SELECT * FROM PluginEventLog WHERE pluginId=? ORDER BY at DESC LIMIT ?", (plugin_id, limit)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM PluginEventLog ORDER BY at DESC LIMIT ?", (limit,)).fetchall()
        return [
            {"pluginId": r["pluginId"], "type": r["type"], "status": r["status"],
             "detail": json.loads(r["detail"] or "{}"), "at": r["at"]}
            for r in rows
        ]

    # ── health ───────────────────────────────────────────────────────────────

    def get_health(self, plugin_id: str) -> dict[str, Any]:
        row = self._db.execute("SELECT * FROM PluginHealth WHERE pluginId=?", (plugin_id,)).fetchone()
        if row is None:
            return {"pluginId": plugin_id, "status": "unknown", "uptimeS": 0.0, "toolCalls": 0,
                    "toolFailures": 0, "eventFailures": 0, "httpFailures": 0, "hookFailures": 0,
                    "crashes": 0, "restarts": 0, "latencyMs": 0.0, "authStatus": None,
                    "lastError": None, "startedAt": None}
        return dict(row)

    def bump_health(self, plugin_id: str, **deltas: float) -> None:
        allowed = {"uptimeS", "toolCalls", "toolFailures", "eventFailures", "httpFailures",
                   "hookFailures", "crashes", "restarts", "latencyMs"}
        self._db.execute(
            "INSERT INTO PluginHealth (pluginId, updatedAt) VALUES (?, ?) ON CONFLICT(pluginId) DO NOTHING",
            (plugin_id, now_iso()),
        )
        sets, params = [], []
        for key, value in deltas.items():
            if key in allowed:
                sets.append(f"{key} = {key} + ?")
                params.append(value)
        sets.append("updatedAt = ?")
        params.append(now_iso())
        params.append(plugin_id)
        self._db.execute(f"UPDATE PluginHealth SET {', '.join(sets)} WHERE pluginId=?", params)
        self._db.commit()

    def set_health(self, plugin_id: str, **fields: Any) -> None:
        allowed = {"status", "lastError", "startedAt", "authStatus"}
        self._db.execute(
            "INSERT INTO PluginHealth (pluginId, updatedAt) VALUES (?, ?) ON CONFLICT(pluginId) DO NOTHING",
            (plugin_id, now_iso()),
        )
        sets, params = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = ?")
                params.append(value)
        sets.append("updatedAt = ?")
        params.append(now_iso())
        params.append(plugin_id)
        self._db.execute(f"UPDATE PluginHealth SET {', '.join(sets)} WHERE pluginId=?", params)
        self._db.commit()

    # ── install history (snapshot / rollback) ────────────────────────────────

    def record_history(
        self, plugin_id: str, action: str, status: str, *,
        from_version: Optional[str] = None, to_version: Optional[str] = None,
        snapshot: Optional[dict[str, Any]] = None,
    ) -> None:
        self._db.execute(
            """INSERT INTO PluginInstallHistory (id, pluginId, action, fromVersion, toVersion, status, snapshot, at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (_new_id("phist"), plugin_id, action, from_version, to_version,
             status, json.dumps(snapshot) if snapshot is not None else None, now_iso()),
        )
        self._db.commit()

    def list_history(self, plugin_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM PluginInstallHistory WHERE pluginId=? ORDER BY at DESC LIMIT ?",
            (plugin_id, limit),
        ).fetchall()
        return [
            {"pluginId": r["pluginId"], "action": r["action"], "fromVersion": r["fromVersion"],
             "toVersion": r["toVersion"], "status": r["status"],
             "snapshot": json.loads(r["snapshot"]) if r["snapshot"] else None, "at": r["at"]}
            for r in rows
        ]

    def latest_snapshot(self, plugin_id: str) -> Optional[dict[str, Any]]:
        """The most recent recorded snapshot that holds a full manifest + path."""
        for row in self.list_history(plugin_id, limit=25):
            snapshot = row.get("snapshot")
            if snapshot and snapshot.get("manifest") and snapshot.get("installationPath"):
                return snapshot
        return None

    # ── logs ─────────────────────────────────────────────────────────────────

    def log(self, plugin_id: str, level: str, message: str) -> None:
        self._db.execute(
            "INSERT INTO PluginLog (id, pluginId, level, message, at) VALUES (?, ?, ?, ?, ?)",
            (_new_id("plog"), plugin_id, level, message[:2000], now_iso()),
        )
        self._db.commit()
        count = self._db.execute("SELECT COUNT(*) AS c FROM PluginLog").fetchone()["c"]
        if count > MAX_LOG_ROWS:
            self._db.execute(
                "DELETE FROM PluginLog WHERE id IN (SELECT id FROM PluginLog ORDER BY at ASC LIMIT ?)",
                (count - MAX_LOG_ROWS,),
            )
            self._db.commit()

    def list_logs(self, plugin_id: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        if plugin_id:
            rows = self._db.execute(
                "SELECT * FROM PluginLog WHERE pluginId=? ORDER BY at DESC LIMIT ?", (plugin_id, limit)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM PluginLog ORDER BY at DESC LIMIT ?", (limit,)).fetchall()
        return [{"pluginId": r["pluginId"], "level": r["level"], "message": r["message"], "at": r["at"]} for r in rows]


__all__ = ["PluginStore", "MAX_LOG_ROWS", "MAX_EVENT_ROWS"]

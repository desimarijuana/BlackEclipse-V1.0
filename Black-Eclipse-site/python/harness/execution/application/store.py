"""Runtime state persistence — the app/runtime tables on the ONE memory connection.

Mirrors `execution/store.py` and `terminal/store.py`: idempotent
`CREATE TABLE IF NOT EXISTS`, bound to the shared `AgentMemoryStore._db`, and it
NEVER touches `eclipse-memory.db` or `jdds.db`.

Eclipse must be able to recover knowledge of its running processes after its own
restart, so the runtime, its services, ports, processes, containers, health checks
and events are all persisted. Every relationship is a column or a child table —
no new database.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ...persistence import now_iso


def _row(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _new(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:12]


def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None


def _decode(data: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    for key in keys:
        raw = data.get(key)
        if isinstance(raw, str) and raw:
            try:
                data[key] = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                pass
    return data


class ApplicationRuntimeStore:
    """Rows describing applications, runtimes and their live components."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS Application (
              id          TEXT PRIMARY KEY,
              name        TEXT,
              path        TEXT,
              language    TEXT,
              framework   TEXT,
              runtime     TEXT,
              packageManager TEXT,
              descriptor  TEXT,
              workspaceId TEXT,
              createdAt   TEXT NOT NULL,
              updatedAt   TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS AppRuntime (
              id           TEXT PRIMARY KEY,
              applicationId TEXT,
              state        TEXT NOT NULL,
              descriptor   TEXT,
              serviceGraph TEXT,
              health       TEXT,
              workspaceId  TEXT,
              runId        TEXT,
              agentId      TEXT,
              owner        TEXT,
              restartCount INTEGER NOT NULL DEFAULT 0,
              lastError    TEXT,
              warnings     TEXT,
              extra        TEXT,
              startedAt    REAL DEFAULT 0,
              updatedAt    TEXT NOT NULL,
              createdAt    TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_appruntime_app ON AppRuntime(applicationId)"
        )
        for table, ddl in (
            ("AppService",
             """CREATE TABLE IF NOT EXISTS AppService (
                  id TEXT PRIMARY KEY, runtimeId TEXT NOT NULL, name TEXT NOT NULL,
                  kind TEXT, image TEXT, containerId TEXT, processId TEXT, ports TEXT,
                  dependsOn TEXT, state TEXT, health TEXT, compose INTEGER DEFAULT 0,
                  notes TEXT, updatedAt TEXT NOT NULL)"""),
            ("AppPort",
             """CREATE TABLE IF NOT EXISTS AppPort (
                  id TEXT PRIMARY KEY, runtimeId TEXT NOT NULL, port INTEGER,
                  host TEXT, purpose TEXT, source TEXT, service TEXT, pid INTEGER,
                  processId TEXT, protocol TEXT, updatedAt TEXT NOT NULL)"""),
            ("AppHealthCheck",
             """CREATE TABLE IF NOT EXISTS AppHealthCheck (
                  id TEXT PRIMARY KEY, runtimeId TEXT NOT NULL, name TEXT, kind TEXT,
                  target TEXT, status TEXT, ok INTEGER DEFAULT 0, detail TEXT,
                  attempts INTEGER DEFAULT 0, latencyMs INTEGER DEFAULT 0,
                  evidence TEXT, checkedAt TEXT NOT NULL)"""),
            ("AppRuntimeEvent",
             """CREATE TABLE IF NOT EXISTS AppRuntimeEvent (
                  id TEXT PRIMARY KEY, runtimeId TEXT NOT NULL, type TEXT NOT NULL,
                  category TEXT, severity TEXT, message TEXT, data TEXT,
                  createdAt TEXT NOT NULL)"""),
            ("AppDeployment",
             """CREATE TABLE IF NOT EXISTS AppDeployment (
                  id TEXT PRIMARY KEY, runtimeId TEXT, applicationId TEXT, provider TEXT,
                  status TEXT, detail TEXT, data TEXT, createdAt TEXT NOT NULL)"""),
        ):
            self._db.execute(ddl)
            self._db.execute(f"CREATE INDEX IF NOT EXISTS idx_{table.lower()}_rt ON {table}(runtimeId)")
        self._db.commit()

    # ── applications ──────────────────────────────────────────────────────────────
    def upsert_application(self, descriptor: Any, *, workspace_id: Optional[str] = None) -> str:
        app_id = "app_" + _stable(descriptor.path or descriptor.name)
        now = now_iso()
        existing = self._db.execute("SELECT id FROM Application WHERE id=?", (app_id,)).fetchone()
        values = (
            descriptor.name, descriptor.path, descriptor.language, descriptor.framework,
            descriptor.runtime, descriptor.package_manager, _json(descriptor.to_dict()),
            workspace_id, now,
        )
        if existing is None:
            self._db.execute(
                """INSERT INTO Application
                   (id, name, path, language, framework, runtime, packageManager, descriptor, workspaceId, createdAt, updatedAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (app_id, *values, now),
            )
        else:
            self._db.execute(
                """UPDATE Application SET name=?, path=?, language=?, framework=?, runtime=?,
                   packageManager=?, descriptor=?, workspaceId=?, updatedAt=? WHERE id=?""",
                (*values, app_id),
            )
        self._db.commit()
        return app_id

    def get_application(self, app_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM Application WHERE id=?", (app_id,)).fetchone()
        return _decode(_row(row), ("descriptor",)) if row else None

    def list_applications(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute("SELECT * FROM Application ORDER BY updatedAt DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
        return [_decode(_row(r), ("descriptor",)) for r in rows]

    # ── runtimes ─────────────────────────────────────────────────────────────────
    def upsert_runtime(self, handle: Any) -> dict[str, Any]:
        now = now_iso()
        record = {
            "id": handle.runtime_id,
            "applicationId": handle.application_id,
            "state": handle.state.value if hasattr(handle.state, "value") else str(handle.state),
            "descriptor": _json(handle.descriptor.to_dict() if handle.descriptor else None),
            "serviceGraph": _json(handle.graph.to_dict() if handle.graph else None),
            "health": _json(handle.health.to_dict() if handle.health else None),
            "workspaceId": handle.workspace_id,
            "runId": handle.run_id,
            "agentId": handle.agent_id,
            "owner": handle.owner,
            "restartCount": int(handle.restart_count or 0),
            "lastError": _json(handle.last_error),
            "warnings": _json(handle.warnings),
            "extra": _json(handle.extra),
            "startedAt": float(handle.started_at or 0),
            "updatedAt": now,
            "createdAt": now,
        }
        self._db.execute(
            """INSERT OR REPLACE INTO AppRuntime
               (id, applicationId, state, descriptor, serviceGraph, health, workspaceId, runId,
                agentId, owner, restartCount, lastError, warnings, extra, startedAt, updatedAt, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(record.values()),
        )
        self._db.commit()
        return record

    def get_runtime(self, runtime_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM AppRuntime WHERE id=?", (runtime_id,)).fetchone()
        if row is None:
            return None
        data = _decode(_row(row), ("descriptor", "serviceGraph", "health", "lastError", "warnings", "extra"))
        data["services"] = [_row(r) for r in self._db.execute("SELECT * FROM AppService WHERE runtimeId=?", (runtime_id,)).fetchall()]
        data["ports"] = [_row(r) for r in self._db.execute("SELECT * FROM AppPort WHERE runtimeId=?", (runtime_id,)).fetchall()]
        return data

    def list_runtimes(self, *, state: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        if state:
            rows = self._db.execute("SELECT * FROM AppRuntime WHERE state=? ORDER BY updatedAt DESC LIMIT ?", (state, limit)).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM AppRuntime ORDER BY updatedAt DESC LIMIT ?", (limit,)).fetchall()
        return [_decode(_row(r), ("descriptor", "serviceGraph", "health", "lastError", "warnings", "extra")) for r in rows]

    def list_active_runtimes(self) -> list[dict[str, Any]]:
        """Runtimes that were active at the last write — for boot reconciliation."""
        active = ("RUNNING", "DEGRADED", "STARTING", "BUILDING", "INSTALLING", "PREPARING", "OBSERVING", "STOPPING")
        placeholders = ",".join("?" for _ in active)
        rows = self._db.execute(
            f"SELECT * FROM AppRuntime WHERE state IN ({placeholders}) ORDER BY updatedAt DESC",
            active,
        ).fetchall()
        return [_decode(_row(r), ("descriptor", "serviceGraph", "health", "lastError", "warnings", "extra")) for r in rows]

    def delete_runtime(self, runtime_id: str) -> None:
        for table in ("AppService", "AppPort", "AppHealthCheck"):
            self._db.execute(f"DELETE FROM {table} WHERE runtimeId=?", (runtime_id,))
        self._db.commit()

    # ── children ─────────────────────────────────────────────────────────────────
    def save_services(self, runtime_id: str, nodes: list[dict[str, Any]]) -> None:
        now = now_iso()
        self._db.execute("DELETE FROM AppService WHERE runtimeId=?", (runtime_id,))
        for node in nodes:
            self._db.execute(
                """INSERT INTO AppService
                   (id, runtimeId, name, kind, image, containerId, processId, ports, dependsOn, state, health, compose, notes, updatedAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (_new("svc_"), runtime_id, node.get("name", ""), node.get("kind", ""), node.get("image", ""),
                 node.get("containerId", ""), node.get("processId", ""), _json(node.get("ports")),
                 _json(node.get("dependsOn")), node.get("state", ""), node.get("health", ""),
                 1 if node.get("compose") else 0, node.get("notes", ""), now),
            )
        self._db.commit()

    def save_ports(self, runtime_id: str, ports: list[dict[str, Any]]) -> None:
        now = now_iso()
        self._db.execute("DELETE FROM AppPort WHERE runtimeId=?", (runtime_id,))
        for port in ports:
            self._db.execute(
                """INSERT INTO AppPort
                   (id, runtimeId, port, host, purpose, source, service, pid, processId, protocol, updatedAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (_new("port_"), runtime_id, port.get("port", 0), port.get("host", ""), port.get("purpose", ""),
                 port.get("source", ""), port.get("service", ""), port.get("pid"), port.get("processId"),
                 port.get("protocol", "tcp"), now),
            )
        self._db.commit()

    def save_health(self, runtime_id: str, report: dict[str, Any]) -> None:
        now = now_iso()
        self._db.execute("DELETE FROM AppHealthCheck WHERE runtimeId=?", (runtime_id,))
        for check in report.get("checks", []) or []:
            self._db.execute(
                """INSERT INTO AppHealthCheck
                   (id, runtimeId, name, kind, target, status, ok, detail, attempts, latencyMs, evidence, checkedAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (_new("hc_"), runtime_id, check.get("check", ""), check.get("kind", ""), check.get("detail", ""),
                 check.get("status", ""), 1 if check.get("ok") else 0, check.get("detail", ""),
                 int(check.get("attempts", 0)), int(check.get("latencyMs", 0)), _json(check.get("evidence")), now),
            )
        self._db.commit()

    # ── events ───────────────────────────────────────────────────────────────────
    def append_event(self, runtime_id: str, event_type: str, data: Optional[dict[str, Any]] = None, *, category: str = "", severity: str = "", message: str = "") -> None:
        payload = data or {}
        self._db.execute(
            """INSERT INTO AppRuntimeEvent (id, runtimeId, type, category, severity, message, data, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (_new("rte_"), runtime_id, event_type, category, severity, message, _json(payload), now_iso()),
        )
        self._db.commit()

    def list_events(self, runtime_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM AppRuntimeEvent WHERE runtimeId=? ORDER BY createdAt DESC LIMIT ?",
            (runtime_id, max(1, min(limit, 1000))),
        ).fetchall()
        return [_decode(_row(r), ("data",)) for r in rows]

    def record_deployment(self, *, runtime_id: str, application_id: str, provider: str, status: str, detail: str = "", data: Optional[dict[str, Any]] = None) -> str:
        deployment_id = _new("dep_")
        self._db.execute(
            """INSERT INTO AppDeployment (id, runtimeId, applicationId, provider, status, detail, data, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (deployment_id, runtime_id, application_id, provider, status, detail, _json(data), now_iso()),
        )
        self._db.commit()
        return deployment_id


def _stable(text: str) -> str:
    import hashlib

    return hashlib.sha1(str(text or "").encode("utf-8", "replace")).hexdigest()[:16]


__all__ = ["ApplicationRuntimeStore"]

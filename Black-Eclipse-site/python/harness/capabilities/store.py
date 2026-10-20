"""Durable capability requests, versions, usage and activation state."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from ..persistence import now_iso

_LOCK = threading.Lock()
_FALLBACK_REQUESTS: dict[str, dict[str, Any]] = {}
_FALLBACK_RECORDS: dict[tuple[str, str], dict[str, Any]] = {}
_FALLBACK_USAGE: list[dict[str, Any]] = []

_SCHEMA = """
CREATE TABLE IF NOT EXISTS CapabilityRequest (
  id        TEXT PRIMARY KEY,
  need      TEXT NOT NULL,
  kind      TEXT,
  scope     TEXT,
  status    TEXT NOT NULL,
  payload   TEXT NOT NULL,
  createdAt TEXT NOT NULL,
  updatedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_capability_request_created
  ON CapabilityRequest(createdAt);

CREATE TABLE IF NOT EXISTS CapabilityRecord (
  id           TEXT PRIMARY KEY,
  capabilityId TEXT NOT NULL,
  version      TEXT NOT NULL,
  kind         TEXT NOT NULL,
  title        TEXT NOT NULL,
  description  TEXT NOT NULL DEFAULT '',
  scope        TEXT NOT NULL,
  status       TEXT NOT NULL,
  manifest     TEXT NOT NULL,
  sourceDigest TEXT NOT NULL DEFAULT '',
  testDigest   TEXT NOT NULL DEFAULT '',
  testStatus   TEXT NOT NULL DEFAULT '',
  tests        TEXT NOT NULL DEFAULT '[]',
  dir          TEXT NOT NULL DEFAULT '',
  runId        TEXT,
  taskId       TEXT,
  createdAt    TEXT NOT NULL,
  updatedAt    TEXT NOT NULL,
  UNIQUE(capabilityId, version)
);
CREATE INDEX IF NOT EXISTS idx_capability_record_id
  ON CapabilityRecord(capabilityId, status);
CREATE INDEX IF NOT EXISTS idx_capability_record_status
  ON CapabilityRecord(status);

CREATE TABLE IF NOT EXISTS CapabilityUsage (
  id           TEXT PRIMARY KEY,
  capabilityId TEXT NOT NULL,
  version      TEXT NOT NULL,
  runId        TEXT,
  status       TEXT NOT NULL,
  durationMs   INTEGER NOT NULL DEFAULT 0,
  createdAt    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_capability_usage_id
  ON CapabilityUsage(capabilityId, version, createdAt);
"""


@dataclass
class CapabilityRecord:
    capability_id: str
    version: str
    kind: str
    title: str
    description: str
    scope: str
    status: str
    manifest: dict[str, Any]
    source_digest: str = ""
    test_digest: str = ""
    test_status: str = ""
    tests: list[str] = field(default_factory=list)
    directory: str = ""
    run_id: Optional[str] = None
    task_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": f"{self.capability_id}@{self.version}",
            "capabilityId": self.capability_id,
            "version": self.version,
            "kind": self.kind,
            "title": self.title,
            "description": self.description,
            "scope": self.scope,
            "status": self.status,
            "manifest": self.manifest,
            "sourceDigest": self.source_digest,
            "testDigest": self.test_digest,
            "testStatus": self.test_status,
            "tests": list(self.tests),
            "dir": self.directory,
            "runId": self.run_id,
            "taskId": self.task_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


def _row_to_record(row: Any) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": f"{data.get('capabilityId')}@{data.get('version')}",
        "capabilityId": data.get("capabilityId"),
        "version": data.get("version"),
        "kind": data.get("kind"),
        "title": data.get("title"),
        "description": data.get("description"),
        "scope": data.get("scope"),
        "status": data.get("status"),
        "manifest": _load_json(data.get("manifest"), {}),
        "sourceDigest": data.get("sourceDigest") or "",
        "testDigest": data.get("testDigest") or "",
        "testStatus": data.get("testStatus") or "",
        "tests": _load_json(data.get("tests"), []),
        "dir": data.get("dir") or "",
        "runId": data.get("runId"),
        "taskId": data.get("taskId"),
        "createdAt": data.get("createdAt"),
        "updatedAt": data.get("updatedAt"),
    }


def _load_json(raw: Any, fallback: Any) -> Any:
    try:
        return json.loads(raw) if raw else fallback
    except (TypeError, ValueError):
        return fallback


class CapabilityStore:
    def __init__(self, memory_store: Any = None) -> None:
        self._store = memory_store
        self._db: Optional[sqlite3.Connection] = None
        if memory_store is not None:
            try:
                self._db = getattr(memory_store, "_db", None)
                if self._db is not None:
                    self._db.executescript(_SCHEMA)
                    self._db.commit()
                    self._ensure_columns()
            except Exception:
                self._db = None

    def _ensure_columns(self) -> None:
        """Additive migration for a store created before `taskId` existed."""
        if self._db is None:
            return
        try:
            columns = {
                str(row[1]) for row in self._db.execute("PRAGMA table_info(CapabilityRecord)")
            }
            if "taskId" not in columns:
                self._db.execute("ALTER TABLE CapabilityRecord ADD COLUMN taskId TEXT")
                self._db.commit()
        except Exception:  # noqa: BLE001 - an old row must stay readable
            pass

    @property
    def durable(self) -> bool:
        return self._db is not None

    def save_request(self, request: Any, *, status: str = "open") -> dict[str, Any]:
        payload = request.to_dict() if hasattr(request, "to_dict") else dict(request or {})
        request_id = str(payload.get("requestId") or "")
        now = now_iso()
        record = {
            "id": request_id,
            "need": str(payload.get("need") or ""),
            "kind": str(payload.get("kind") or "auto"),
            "scope": str(payload.get("scope") or "workspace"),
            "status": status,
            "payload": payload,
            "createdAt": now,
            "updatedAt": now,
        }
        if self._db is not None:
            try:
                self._db.execute(
                    """
                    INSERT INTO CapabilityRequest
                      (id, need, kind, scope, status, payload, createdAt, updatedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      need=excluded.need, kind=excluded.kind, scope=excluded.scope,
                      status=excluded.status, payload=excluded.payload,
                      updatedAt=excluded.updatedAt
                    """,
                    (
                        request_id, record["need"], record["kind"], record["scope"],
                        status, json.dumps(payload, default=str), now, now,
                    ),
                )
                self._db.commit()
                return record
            except Exception:
                pass
        with _LOCK:
            existing = _FALLBACK_REQUESTS.get(request_id)
            if existing:
                existing.update(record)
                existing["createdAt"] = existing.get("createdAt") or now
                return dict(existing)
            _FALLBACK_REQUESTS[request_id] = record
        return record

    def get_request(self, request_id: str) -> Optional[dict[str, Any]]:
        if self._db is not None:
            try:
                row = self._db.execute(
                    "SELECT * FROM CapabilityRequest WHERE id = ?", (request_id,)
                ).fetchone()
                if row is not None:
                    data = dict(row)
                    data["payload"] = _load_json(data.get("payload"), {})
                    return data
            except Exception:
                pass
        with _LOCK:
            record = _FALLBACK_REQUESTS.get(request_id)
            return dict(record) if record else None

    def set_request_status(self, request_id: str, status: str) -> None:
        if self._db is not None:
            try:
                self._db.execute(
                    "UPDATE CapabilityRequest SET status = ?, updatedAt = ? WHERE id = ?",
                    (status, now_iso(), request_id),
                )
                self._db.commit()
            except Exception:
                pass
        with _LOCK:
            if request_id in _FALLBACK_REQUESTS:
                _FALLBACK_REQUESTS[request_id]["status"] = status
                _FALLBACK_REQUESTS[request_id]["updatedAt"] = now_iso()

    def save_record(self, record: CapabilityRecord) -> dict[str, Any]:
        now = now_iso()
        record.created_at = record.created_at or now
        record.updated_at = now
        data = record.to_dict()
        if self._db is not None:
            try:
                self._db.execute(
                    """
                    INSERT INTO CapabilityRecord
                      (id, capabilityId, version, kind, title, description, scope,
                       status, manifest, sourceDigest, testDigest, testStatus,
                       tests, dir, runId, taskId, createdAt, updatedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(capabilityId, version) DO UPDATE SET
                      kind=excluded.kind, title=excluded.title,
                      description=excluded.description, scope=excluded.scope,
                      status=excluded.status, manifest=excluded.manifest,
                      sourceDigest=excluded.sourceDigest, testDigest=excluded.testDigest,
                      testStatus=excluded.testStatus, tests=excluded.tests,
                      dir=excluded.dir, runId=excluded.runId, taskId=excluded.taskId,
                      updatedAt=excluded.updatedAt
                    """,
                    (
                        "cap_" + uuid.uuid4().hex[:16], record.capability_id,
                        record.version, record.kind, record.title, record.description,
                        record.scope, record.status,
                        json.dumps(record.manifest, default=str),
                        record.source_digest, record.test_digest, record.test_status,
                        json.dumps(record.tests, default=str), record.directory,
                        record.run_id, record.task_id, record.created_at, record.updated_at,
                    ),
                )
                self._db.commit()
                return data
            except Exception:
                pass
        key = (record.capability_id, record.version)
        with _LOCK:
            existing = _FALLBACK_RECORDS.get(key)
            if existing:
                data["createdAt"] = existing.get("createdAt") or data["createdAt"]
                data["updatedAt"] = now
            _FALLBACK_RECORDS[key] = data
        return data

    def get(self, capability_id: str, version: Optional[str] = None) -> Optional[dict[str, Any]]:
        records = self.records(capability_id=capability_id, limit=200)
        if version:
            return next((item for item in records if item.get("version") == version), None)
        return records[0] if records else None

    def records(
        self,
        *,
        capability_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if self._db is not None:
            try:
                clauses: list[str] = []
                params: list[Any] = []
                if capability_id:
                    clauses.append("capabilityId = ?")
                    params.append(capability_id)
                if status:
                    clauses.append("status = ?")
                    params.append(status)
                where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
                params.append(max(1, int(limit)))
                rows = self._db.execute(
                    f"SELECT * FROM CapabilityRecord{where} ORDER BY updatedAt DESC LIMIT ?",
                    tuple(params),
                ).fetchall()
                return [_row_to_record(row) for row in rows]
            except Exception:
                pass
        with _LOCK:
            items = [dict(item) for item in _FALLBACK_RECORDS.values()]
        if capability_id:
            items = [item for item in items if item.get("capabilityId") == capability_id]
        if status:
            items = [item for item in items if item.get("status") == status]
        items.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
        return items[: max(1, int(limit))]

    def versions(self, capability_id: str) -> list[dict[str, Any]]:
        items = self.records(capability_id=capability_id, limit=200)
        return sorted(items, key=lambda item: _version_key(str(item.get("version") or "0.0.0")))

    def usage(
        self, capability_id: str, version: Optional[str] = None, *, limit: int = 50,
    ) -> list[dict[str, Any]]:
        if self._db is not None:
            try:
                clauses = ["capabilityId = ?"]
                params: list[Any] = [capability_id]
                if version:
                    clauses.append("version = ?")
                    params.append(version)
                params.append(max(1, int(limit)))
                rows = self._db.execute(
                    "SELECT status, runId, durationMs, createdAt FROM CapabilityUsage "
                    f"WHERE {' AND '.join(clauses)} ORDER BY createdAt DESC LIMIT ?",
                    tuple(params),
                ).fetchall()
                return [
                    {
                        "status": _row_value(row, "status"),
                        "runId": _row_value(row, "runId"),
                        "durationMs": _row_value(row, "durationMs") or 0,
                        "createdAt": _row_value(row, "createdAt"),
                    }
                    for row in rows
                ]
            except Exception:
                pass
        with _LOCK:
            items = [
                dict(item) for item in reversed(_FALLBACK_USAGE)
                if item.get("capabilityId") == capability_id
                and (version is None or item.get("version") == version)
            ][: max(1, int(limit))]
        return [
            {
                "status": item.get("status"), "runId": None,
                "durationMs": 0, "createdAt": item.get("createdAt"),
            }
            for item in items
        ]

    def next_version(self, capability_id: str) -> str:
        versions = self.versions(capability_id)
        if not versions:
            return "1.0.0"
        major, minor, patch = _version_key(str(versions[-1].get("version") or "1.0.0"))
        return f"{major}.{minor}.{patch + 1}"

    def set_status(
        self, capability_id: str, version: str, status: str, **fields: Any,
    ) -> Optional[dict[str, Any]]:
        current = self.get(capability_id, version)
        if current is None:
            return None
        current["status"] = status
        current["updatedAt"] = now_iso()
        record = CapabilityRecord(
            capability_id=capability_id,
            version=version,
            kind=str(current.get("kind") or ""),
            title=str(current.get("title") or ""),
            description=str(current.get("description") or ""),
            scope=str(current.get("scope") or "workspace"),
            status=status,
            manifest=dict(current.get("manifest") or {}),
            source_digest=str(current.get("sourceDigest") or ""),
            test_digest=str(current.get("testDigest") or ""),
            test_status=str(current.get("testStatus") or ""),
            tests=list(current.get("tests") or []),
            directory=str(fields.get("dir") or current.get("dir") or ""),
            run_id=fields.get("runId", current.get("runId")),
            task_id=fields.get("taskId", current.get("taskId")),
            created_at=str(current.get("createdAt") or ""),
        )
        return self.save_record(record)

    def record_usage(
        self,
        capability_id: str,
        version: str,
        *,
        ok: bool,
        run_id: Optional[str] = None,
        duration_ms: int = 0,
    ) -> dict[str, Any]:
        now = now_iso()
        status = "ok" if ok else "failed"
        if self._db is not None:
            try:
                self._db.execute(
                    "INSERT INTO CapabilityUsage "
                    "(id, capabilityId, version, runId, status, durationMs, createdAt) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("capuse_" + uuid.uuid4().hex[:16], capability_id, version, run_id,
                     status, int(duration_ms or 0), now),
                )
                self._db.commit()
                rows = self._db.execute(
                    "SELECT status FROM CapabilityUsage WHERE capabilityId = ? AND version = ? "
                    "ORDER BY createdAt DESC LIMIT 3",
                    (capability_id, version),
                ).fetchall()
            except Exception:
                rows = []
        else:
            with _LOCK:
                _FALLBACK_USAGE.append({
                    "capabilityId": capability_id, "version": version,
                    "status": status, "createdAt": now,
                })
                rows = [
                    {"status": item["status"]}
                    for item in reversed(_FALLBACK_USAGE)
                    if item.get("capabilityId") == capability_id
                    and item.get("version") == version
                ][:3]
        failures = sum(1 for row in rows if _row_value(row, "status") != "ok")
        disabled = len(rows) >= 3 and failures == len(rows)
        if disabled:
            self.set_status(capability_id, version, "disabled")
        return {"consecutiveFailures": failures, "disabled": disabled}


def _row_value(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return None


def _version_key(version: str) -> tuple[int, int, int]:
    parts = [int(part) for part in str(version).split(".") if part.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


__all__ = ["CapabilityRecord", "CapabilityStore"]

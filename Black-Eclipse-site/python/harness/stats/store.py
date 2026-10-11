"""Persistence for the statistical engine.

Follows the harness convention: metadata lives in the ONE `agent-memory.db`
connection (additive, idempotent DDL — never `jdds.db`, never
`eclipse-memory.db`); large result series are written as gzipped JSON artifacts
under `.black-eclipse/stats/artifacts/` so a wide series never bloats a
relational row.

Persisted entities:
  * `StatsFeature` / `StatsFeatureVersion` — the feature registry with immutable
    versions (a rollback selects an earlier version; history is never erased),
  * `StatsAnalysis`            — every executed analysis + its result summary,
  * `StatsRun`                 — a durable mirror of background job state,
  * `StatsValidation`          — feature/formula validation runs,
  * `StatsAudit`               — audit trail of sensitive operations,
  * `StatsArtifact`            — checksummed large-result references.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import uuid
from typing import Any, Optional

from ..persistence import now_iso

try:  # pragma: no cover - import guard mirrors the rest of the harness
    from ..persistence import now_iso as _now_iso  # noqa: F401
except Exception:  # noqa: BLE001
    pass

_SCHEMA = """
CREATE TABLE IF NOT EXISTS StatsFeature (
  id               TEXT PRIMARY KEY,
  name             TEXT NOT NULL,
  description      TEXT,
  owner            TEXT,
  visibility       TEXT NOT NULL DEFAULT 'personal',
  category         TEXT,
  tagsJson         TEXT,
  latestVersion    TEXT NOT NULL,
  validationStatus TEXT NOT NULL DEFAULT 'unvalidated',
  archived         INTEGER NOT NULL DEFAULT 0,
  createdAt        TEXT NOT NULL,
  updatedAt        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stats_feature_name ON StatsFeature(name);

CREATE TABLE IF NOT EXISTS StatsFeatureVersion (
  id               TEXT PRIMARY KEY,
  featureId        TEXT NOT NULL,
  version          TEXT NOT NULL,
  expression       TEXT,
  pipelineJson     TEXT,
  paramSchemaJson  TEXT,
  inputSchemaJson  TEXT,
  outputSchemaJson TEXT,
  dependenciesJson TEXT,
  changelog        TEXT,
  pitSafe          INTEGER NOT NULL DEFAULT 1,
  definitionHash   TEXT,
  createdAt        TEXT NOT NULL,
  UNIQUE(featureId, version)
);
CREATE INDEX IF NOT EXISTS idx_stats_fv_feature ON StatsFeatureVersion(featureId);

CREATE TABLE IF NOT EXISTS StatsAnalysis (
  id             TEXT PRIMARY KEY,
  tool           TEXT NOT NULL,
  toolVersion    TEXT,
  parametersJson TEXT,
  datasetRefJson TEXT,
  status         TEXT NOT NULL,
  summaryJson    TEXT,
  resultRef      TEXT,
  provenanceJson TEXT,
  durationMs     INTEGER,
  owner          TEXT,
  createdAt      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stats_analysis_tool ON StatsAnalysis(tool);
CREATE INDEX IF NOT EXISTS idx_stats_analysis_created ON StatsAnalysis(createdAt);

CREATE TABLE IF NOT EXISTS StatsRun (
  id           TEXT PRIMARY KEY,
  kind         TEXT NOT NULL,
  status       TEXT NOT NULL,
  stage        TEXT,
  done         INTEGER NOT NULL DEFAULT 0,
  total        INTEGER NOT NULL DEFAULT 0,
  message      TEXT,
  errorJson    TEXT,
  createdAt    TEXT NOT NULL,
  finishedAt   TEXT
);

CREATE TABLE IF NOT EXISTS StatsValidation (
  id         TEXT PRIMARY KEY,
  featureId  TEXT,
  version    TEXT,
  status     TEXT NOT NULL,
  detailJson TEXT,
  createdAt  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS StatsAudit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  action      TEXT NOT NULL,
  subjectType TEXT,
  subjectId   TEXT,
  actor       TEXT,
  detailJson  TEXT,
  createdAt   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS StatsArtifact (
  id          TEXT PRIMARY KEY,
  analysisId  TEXT,
  path        TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  bytes       INTEGER NOT NULL,
  contentType TEXT,
  createdAt   TEXT NOT NULL
);
"""


def _artifact_root() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(root, ".black-eclipse", "stats", "artifacts")


def _json(value: Any) -> Optional[str]:
    return None if value is None else json.dumps(value, default=str)


def _loads(value: Optional[str], default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class StatsStore:
    def __init__(self, agent_memory_store: Any, *, artifact_root: Optional[str] = None) -> None:
        self._store = agent_memory_store
        self._root = artifact_root or _artifact_root()
        self._ensure_schema()
        os.makedirs(self._root, exist_ok=True)

    @property
    def _db(self):  # sqlite3.Connection
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ── features ─────────────────────────────────────────────────────────────
    def upsert_feature_metadata(self, *, feature_id: str, name: str, description: Optional[str],
                                owner: Optional[str], visibility: str, category: Optional[str],
                                tags: list[str], latest_version: str) -> dict:
        now = now_iso()
        row = self._db.execute("SELECT id, createdAt FROM StatsFeature WHERE id = ?", (feature_id,)).fetchone()
        if row is None:
            self._db.execute(
                "INSERT INTO StatsFeature (id,name,description,owner,visibility,category,tagsJson,"
                "latestVersion,validationStatus,archived,createdAt,updatedAt) VALUES (?,?,?,?,?,?,?,?,"
                "'unvalidated',0,?,?)",
                (feature_id, name, description, owner, visibility, category, _json(tags), latest_version, now, now),
            )
        else:
            self._db.execute(
                "UPDATE StatsFeature SET name=?, description=?, owner=?, visibility=?, category=?, "
                "tagsJson=?, latestVersion=?, archived=0, updatedAt=? WHERE id=?",
                (name, description, owner, visibility, category, _json(tags), latest_version, now, feature_id),
            )
        self._db.commit()
        return self.get_feature(feature_id)  # type: ignore[return-value]

    def add_feature_version(self, *, feature_id: str, version: str, expression: Optional[str],
                            pipeline: Optional[list], param_schema: Optional[dict],
                            input_schema: Optional[dict], output_schema: Optional[dict],
                            dependencies: list[str], changelog: Optional[str],
                            pit_safe: bool) -> dict:
        definition = {
            "expression": expression, "pipeline": pipeline, "paramSchema": param_schema,
            "inputSchema": input_schema, "outputSchema": output_schema,
            "dependencies": dependencies, "pitSafe": pit_safe,
        }
        definition_hash = hashlib.sha256(_json(definition).encode()).hexdigest()[:32]
        vid = f"{feature_id}@{version}"
        self._db.execute(
            "INSERT OR REPLACE INTO StatsFeatureVersion (id,featureId,version,expression,pipelineJson,"
            "paramSchemaJson,inputSchemaJson,outputSchemaJson,dependenciesJson,changelog,pitSafe,"
            "definitionHash,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, feature_id, version, expression, _json(pipeline), _json(param_schema),
             _json(input_schema), _json(output_schema), _json(dependencies), changelog,
             1 if pit_safe else 0, definition_hash, now_iso()),
        )
        self._db.commit()
        return self.get_feature_version(feature_id, version)  # type: ignore[return-value]

    def set_feature_validation(self, feature_id: str, status: str) -> None:
        self._db.execute("UPDATE StatsFeature SET validationStatus=?, updatedAt=? WHERE id=?",
                         (status, now_iso(), feature_id))
        self._db.commit()

    def get_feature(self, feature_id: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM StatsFeature WHERE id=?", (feature_id,)).fetchone()
        return self._feature_row(row) if row else None

    def get_feature_by_name(self, name: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM StatsFeature WHERE name=? AND archived=0 "
                               "ORDER BY updatedAt DESC LIMIT 1", (name,)).fetchone()
        return self._feature_row(row) if row else None

    def list_features(self, *, owner: Optional[str] = None, category: Optional[str] = None,
                      include_archived: bool = False) -> list[dict]:
        sql = "SELECT * FROM StatsFeature WHERE 1=1"
        args: list[Any] = []
        if not include_archived:
            sql += " AND archived=0"
        if owner:
            sql += " AND owner=?"
            args.append(owner)
        if category:
            sql += " AND category=?"
            args.append(category)
        sql += " ORDER BY updatedAt DESC"
        return [self._feature_row(r) for r in self._db.execute(sql, args).fetchall()]

    def get_feature_version(self, feature_id: str, version: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM StatsFeatureVersion WHERE featureId=? AND version=?",
                               (feature_id, version)).fetchone()
        return self._version_row(row) if row else None

    def list_feature_versions(self, feature_id: str) -> list[dict]:
        rows = self._db.execute("SELECT * FROM StatsFeatureVersion WHERE featureId=? ORDER BY createdAt",
                                (feature_id,)).fetchall()
        return [self._version_row(r) for r in rows]

    def _feature_row(self, row: Any) -> dict:
        return {
            "id": row["id"], "name": row["name"], "description": row["description"],
            "owner": row["owner"], "visibility": row["visibility"], "category": row["category"],
            "tags": _loads(row["tagsJson"], []), "latestVersion": row["latestVersion"],
            "validationStatus": row["validationStatus"], "archived": bool(row["archived"]),
            "createdAt": row["createdAt"], "updatedAt": row["updatedAt"],
        }

    def _version_row(self, row: Any) -> dict:
        return {
            "featureId": row["featureId"], "version": row["version"], "expression": row["expression"],
            "pipeline": _loads(row["pipelineJson"], None), "paramSchema": _loads(row["paramSchemaJson"], {}),
            "inputSchema": _loads(row["inputSchemaJson"], {}), "outputSchema": _loads(row["outputSchemaJson"], {}),
            "dependencies": _loads(row["dependenciesJson"], []), "changelog": row["changelog"],
            "pitSafe": bool(row["pitSafe"]), "definitionHash": row["definitionHash"],
            "createdAt": row["createdAt"],
        }

    # ── analyses ─────────────────────────────────────────────────────────────
    def record_analysis(self, *, tool: str, tool_version: Optional[str], parameters: dict,
                        dataset_ref: Optional[dict], status: str, summary: dict,
                        provenance: dict, duration_ms: int, owner: Optional[str],
                        result_ref: Optional[str] = None) -> str:
        analysis_id = f"san_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO StatsAnalysis (id,tool,toolVersion,parametersJson,datasetRefJson,status,"
            "summaryJson,resultRef,provenanceJson,durationMs,owner,createdAt) VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?)",
            (analysis_id, tool, tool_version, _json(parameters), _json(dataset_ref), status,
             _json(summary), result_ref, _json(provenance), duration_ms, owner, now_iso()),
        )
        self._db.commit()
        return analysis_id

    def get_analysis(self, analysis_id: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM StatsAnalysis WHERE id=?", (analysis_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "tool": row["tool"], "toolVersion": row["toolVersion"],
            "parameters": _loads(row["parametersJson"], {}), "datasetRef": _loads(row["datasetRefJson"], None),
            "status": row["status"], "summary": _loads(row["summaryJson"], {}), "resultRef": row["resultRef"],
            "provenance": _loads(row["provenanceJson"], {}), "durationMs": row["durationMs"],
            "owner": row["owner"], "createdAt": row["createdAt"],
        }

    def list_analyses(self, *, tool: Optional[str] = None, limit: int = 50) -> list[dict]:
        sql = "SELECT id,tool,toolVersion,status,summaryJson,createdAt,durationMs FROM StatsAnalysis"
        args: list[Any] = []
        if tool:
            sql += " WHERE tool=?"
            args.append(tool)
        sql += " ORDER BY createdAt DESC LIMIT ?"
        args.append(int(limit))
        out = []
        for r in self._db.execute(sql, args).fetchall():
            out.append({"id": r["id"], "tool": r["tool"], "toolVersion": r["toolVersion"],
                        "status": r["status"], "summary": _loads(r["summaryJson"], {}),
                        "createdAt": r["createdAt"], "durationMs": r["durationMs"]})
        return out

    # ── validation ───────────────────────────────────────────────────────────
    def record_validation(self, *, feature_id: Optional[str], version: Optional[str], status: str,
                          detail: dict) -> str:
        vid = f"val_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO StatsValidation (id,featureId,version,status,detailJson,createdAt) "
            "VALUES (?,?,?,?,?,?)",
            (vid, feature_id, version, status, _json(detail), now_iso()),
        )
        self._db.commit()
        return vid

    def list_validations(self, feature_id: str) -> list[dict]:
        rows = self._db.execute("SELECT * FROM StatsValidation WHERE featureId=? ORDER BY createdAt DESC",
                                (feature_id,)).fetchall()
        return [{"id": r["id"], "featureId": r["featureId"], "version": r["version"],
                 "status": r["status"], "detail": _loads(r["detailJson"], {}),
                 "createdAt": r["createdAt"]} for r in rows]

    # ── audit ────────────────────────────────────────────────────────────────
    def audit(self, *, action: str, subject_type: Optional[str] = None,
              subject_id: Optional[str] = None, actor: Optional[str] = None,
              detail: Optional[dict] = None) -> None:
        self._db.execute(
            "INSERT INTO StatsAudit (action,subjectType,subjectId,actor,detailJson,createdAt) "
            "VALUES (?,?,?,?,?,?)",
            (action, subject_type, subject_id, actor, _json(detail), now_iso()),
        )
        self._db.commit()

    def list_audit(self, limit: int = 100) -> list[dict]:
        rows = self._db.execute("SELECT * FROM StatsAudit ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [{"id": r["id"], "action": r["action"], "subjectType": r["subjectType"],
                 "subjectId": r["subjectId"], "actor": r["actor"], "detail": _loads(r["detailJson"], {}),
                 "createdAt": r["createdAt"]} for r in rows]

    # ── artifacts ────────────────────────────────────────────────────────────
    def save_artifact(self, content: Any, *, analysis_id: Optional[str] = None,
                      content_type: str = "application/json") -> dict:
        raw = json.dumps(content, default=str).encode()
        digest = hashlib.sha256(raw).hexdigest()
        name = f"{digest[:16]}.json.gz"
        path = os.path.join(self._root, name)
        with gzip.open(path, "wb") as fh:
            fh.write(raw)
        artifact_id = f"sart_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO StatsArtifact (id,analysisId,path,sha256,bytes,contentType,createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (artifact_id, analysis_id, path, digest, len(raw), content_type, now_iso()),
        )
        self._db.commit()
        return {"id": artifact_id, "path": path, "sha256": digest, "bytes": len(raw),
                "contentType": content_type}

    def get_artifact(self, artifact_id: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM StatsArtifact WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            return None
        with gzip.open(row["path"], "rb") as fh:
            content = json.loads(fh.read().decode())
        return {"id": row["id"], "analysisId": row["analysisId"], "sha256": row["sha256"],
                "bytes": row["bytes"], "contentType": row["contentType"], "content": content}

    # ── runs ─────────────────────────────────────────────────────────────────
    def upsert_run(self, run_id: str, *, kind: str, status: str, stage: str = "",
                   done: int = 0, total: int = 0, message: str = "",
                   error: Optional[dict] = None, finished_at: Optional[str] = None) -> None:
        row = self._db.execute("SELECT id FROM StatsRun WHERE id=?", (run_id,)).fetchone()
        if row is None:
            self._db.execute(
                "INSERT INTO StatsRun (id,kind,status,stage,done,total,message,errorJson,createdAt,finishedAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (run_id, kind, status, stage, done, total, message, _json(error), now_iso(), finished_at),
            )
        else:
            self._db.execute(
                "UPDATE StatsRun SET status=?, stage=?, done=?, total=?, message=?, errorJson=?, "
                "finishedAt=? WHERE id=?",
                (status, stage, done, total, message, _json(error), finished_at, run_id),
            )
        self._db.commit()


__all__ = ["StatsStore"]

"""Persistence for the ML Research Lab.

Follows the harness convention exactly: relational metadata lives in the ONE
`agent-memory.db` connection (additive, idempotent DDL — never `jdds.db`, never
`eclipse-memory.db`); large arrays (feature matrices, split assignments, out-of-
fold predictions, model state) are written as gzipped JSON artifacts under
`.black-eclipse/ml/artifacts/` so a wide matrix never bloats a relational row.

Immutable version records (a dataset version, a model version) are kept distinct
from mutable operational status (an experiment run's stage). Histories are
append-only; nothing here erases a prior version.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import uuid
from typing import Any, Optional

from ..persistence import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS MLDataset (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  description TEXT,
  owner       TEXT,
  assetClass  TEXT,
  createdAt   TEXT NOT NULL,
  updatedAt   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MLDatasetVersion (
  id             TEXT PRIMARY KEY,
  datasetId      TEXT NOT NULL,
  version        TEXT NOT NULL,
  manifestJson   TEXT NOT NULL,
  dataHash       TEXT,
  rows           INTEGER NOT NULL DEFAULT 0,
  featureCount   INTEGER NOT NULL DEFAULT 0,
  coverage       REAL,
  qualityStatus  TEXT,
  artifactId     TEXT,
  createdAt      TEXT NOT NULL,
  UNIQUE(datasetId, version)
);
CREATE INDEX IF NOT EXISTS idx_ml_dv_dataset ON MLDatasetVersion(datasetId);

CREATE TABLE IF NOT EXISTS MLTargetDefinition (
  id         TEXT PRIMARY KEY,
  datasetId  TEXT,
  version    TEXT,
  specJson   TEXT NOT NULL,
  createdAt  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MLSplitDefinition (
  id         TEXT PRIMARY KEY,
  runId      TEXT,
  specJson   TEXT NOT NULL,
  assignmentsArtifactId TEXT,
  createdAt  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MLFeatureSelection (
  id         TEXT PRIMARY KEY,
  runId      TEXT,
  fold       INTEGER,
  method     TEXT NOT NULL,
  selectedJson TEXT,
  scoresJson TEXT,
  createdAt  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MLExperiment (
  id              TEXT PRIMARY KEY,
  title           TEXT NOT NULL,
  datasetId       TEXT,
  datasetVersion  TEXT,
  targetJson      TEXT,
  featureNamesJson TEXT,
  modelFamily     TEXT NOT NULL,
  hyperparamsJson TEXT,
  selectionJson   TEXT,
  splitSpecJson   TEXT,
  seed            INTEGER,
  task            TEXT,
  owner           TEXT,
  status          TEXT NOT NULL DEFAULT 'draft',
  createdAt       TEXT NOT NULL,
  updatedAt       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ml_exp_dataset ON MLExperiment(datasetId);
CREATE INDEX IF NOT EXISTS idx_ml_exp_status ON MLExperiment(status);

CREATE TABLE IF NOT EXISTS MLExperimentRun (
  id            TEXT PRIMARY KEY,
  experimentId  TEXT NOT NULL,
  status        TEXT NOT NULL,
  stage         TEXT,
  errorJson     TEXT,
  metricsJson   TEXT,
  artifactId    TEXT,
  startedAt     TEXT,
  finishedAt    TEXT,
  durationMs    INTEGER,
  createdAt     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ml_run_experiment ON MLExperimentRun(experimentId);

CREATE TABLE IF NOT EXISTS MLFoldResult (
  id         TEXT PRIMARY KEY,
  runId      TEXT NOT NULL,
  fold       INTEGER NOT NULL,
  status     TEXT NOT NULL,
  nTrain     INTEGER NOT NULL DEFAULT 0,
  nTest      INTEGER NOT NULL DEFAULT 0,
  nPurged    INTEGER NOT NULL DEFAULT 0,
  nEmbargoed INTEGER NOT NULL DEFAULT 0,
  metricsJson TEXT,
  createdAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ml_fold_run ON MLFoldResult(runId, fold);

CREATE TABLE IF NOT EXISTS MLModel (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  family     TEXT NOT NULL,
  owner      TEXT,
  status     TEXT NOT NULL DEFAULT 'draft',
  latestVersion TEXT,
  createdAt  TEXT NOT NULL,
  updatedAt  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MLModelVersion (
  id          TEXT PRIMARY KEY,
  modelId     TEXT NOT NULL,
  version     TEXT NOT NULL,
  runId       TEXT,
  datasetId   TEXT,
  datasetVersion TEXT,
  family      TEXT NOT NULL,
  task        TEXT,
  artifactId  TEXT,
  stateArtifactId TEXT,
  sha256      TEXT,
  signatureJson TEXT,
  depsJson    TEXT,
  metricsJson TEXT,
  status      TEXT NOT NULL DEFAULT 'draft',
  createdAt   TEXT NOT NULL,
  UNIQUE(modelId, version)
);
CREATE INDEX IF NOT EXISTS idx_ml_mv_model ON MLModelVersion(modelId);

CREATE TABLE IF NOT EXISTS MLArtifact (
  id          TEXT PRIMARY KEY,
  kind        TEXT,
  path        TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  bytes       INTEGER NOT NULL,
  contentType TEXT,
  createdAt   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MLPredictionBatch (
  id         TEXT PRIMARY KEY,
  runId      TEXT,
  modelId    TEXT,
  version    TEXT,
  artifactId TEXT,
  rows       INTEGER NOT NULL DEFAULT 0,
  createdAt  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MLApprovalEvent (
  id         TEXT PRIMARY KEY,
  modelId    TEXT NOT NULL,
  version    TEXT,
  action     TEXT NOT NULL,
  actor      TEXT,
  reason     TEXT,
  createdAt  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MLAudit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  action      TEXT NOT NULL,
  subjectType TEXT,
  subjectId   TEXT,
  actor       TEXT,
  detailJson  TEXT,
  createdAt   TEXT NOT NULL
);
"""


def _artifact_root() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(root, ".black-eclipse", "ml", "artifacts")


def _json(value: Any) -> Optional[str]:
    return None if value is None else json.dumps(value, default=str)


def _loads(value: Optional[str], default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class MLStore:
    def __init__(self, agent_memory_store: Any, *, artifact_root: Optional[str] = None) -> None:
        self._store = agent_memory_store
        self._root = artifact_root or _artifact_root()
        self._db.executescript(_SCHEMA)
        self._db.commit()
        os.makedirs(self._root, exist_ok=True)

    @property
    def _db(self):  # sqlite3.Connection
        return self._store._db

    # ── artifacts ────────────────────────────────────────────────────────────
    def save_artifact(self, content: Any, *, kind: str = "json",
                      content_type: str = "application/json") -> dict[str, Any]:
        raw = json.dumps(content, default=str).encode()
        digest = hashlib.sha256(raw).hexdigest()
        name = f"{kind}-{digest[:16]}.json.gz"
        path = os.path.join(self._root, name)
        if not os.path.exists(path):
            with gzip.open(path, "wb") as fh:
                fh.write(raw)
        artifact_id = f"mla_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO MLArtifact (id,kind,path,sha256,bytes,contentType,createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (artifact_id, kind, path, digest, len(raw), content_type, now_iso()),
        )
        self._db.commit()
        return {"id": artifact_id, "path": path, "sha256": digest, "bytes": len(raw),
                "kind": kind, "contentType": content_type}

    def get_artifact(self, artifact_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM MLArtifact WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            return None
        if not os.path.exists(row["path"]):
            return None
        with gzip.open(row["path"], "rb") as fh:
            content = json.loads(fh.read().decode())
        return {"id": row["id"], "kind": row["kind"], "sha256": row["sha256"],
                "bytes": row["bytes"], "contentType": row["contentType"], "content": content}

    def verify_artifact(self, artifact_id: str) -> dict[str, Any]:
        """Re-hash the stored file and compare with the recorded digest."""
        row = self._db.execute("SELECT * FROM MLArtifact WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            return {"ok": False, "reason": "artifact not found"}
        if not os.path.exists(row["path"]):
            return {"ok": False, "reason": "artifact file missing"}
        try:
            with gzip.open(row["path"], "rb") as fh:
                raw = fh.read()
        except Exception as exc:  # noqa: BLE001 - a corrupt file is a failed verification
            return {"ok": False, "reason": f"artifact is unreadable or corrupt: {exc}"}
        digest = hashlib.sha256(raw).hexdigest()
        return {"ok": digest == row["sha256"], "expected": row["sha256"], "actual": digest}

    # ── datasets ─────────────────────────────────────────────────────────────
    def save_dataset(self, *, name: str, description: Optional[str], owner: Optional[str],
                     asset_class: Optional[str], manifest: dict[str, Any],
                     arrays: dict[str, Any]) -> dict[str, Any]:
        dataset_id = manifest.get("datasetId") or f"mld_{uuid.uuid4().hex[:12]}"
        version = manifest.get("version") or "1.0.0"
        existing = self._db.execute(
            "SELECT id FROM MLDatasetVersion WHERE datasetId=? AND version=?",
            (dataset_id, version)).fetchone()
        if existing is not None:
            from .models import MLError, IMMUTABLE_VERSION
            raise MLError(IMMUTABLE_VERSION,
                          f"dataset {dataset_id} version {version} already exists", 409)
        now = now_iso()
        row = self._db.execute("SELECT id FROM MLDataset WHERE id=?", (dataset_id,)).fetchone()
        if row is None:
            self._db.execute(
                "INSERT INTO MLDataset (id,name,description,owner,assetClass,createdAt,updatedAt) "
                "VALUES (?,?,?,?,?,?,?)",
                (dataset_id, name, description, owner, asset_class, now, now))
        else:
            self._db.execute("UPDATE MLDataset SET updatedAt=? WHERE id=?", (now, dataset_id))

        artifact = self.save_artifact({"manifest": manifest, "arrays": arrays}, kind="dataset")
        quality_status = "ok" if manifest.get("quality", {}).get("ok") else "warning"
        self._db.execute(
            "INSERT INTO MLDatasetVersion (id,datasetId,version,manifestJson,dataHash,rows,"
            "featureCount,coverage,qualityStatus,artifactId,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"{dataset_id}@{version}", dataset_id, version, _json(manifest),
             manifest.get("dataHash"), int(manifest.get("rows") or 0),
             len(manifest.get("featureNames") or []), float(manifest.get("coverage") or 0.0),
             quality_status, artifact["id"], now))
        self._db.execute(
            "INSERT INTO MLTargetDefinition (id,datasetId,version,specJson,createdAt) VALUES (?,?,?,?,?)",
            (f"mlt_{uuid.uuid4().hex[:12]}", dataset_id, version, _json(manifest.get("target")), now))
        self._db.commit()
        return {"datasetId": dataset_id, "version": version, "artifactId": artifact["id"],
                "dataHash": manifest.get("dataHash"), "quality": manifest.get("quality")}

    def list_datasets(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT d.id,d.name,d.description,d.assetClass,d.createdAt,d.updatedAt,"
            " (SELECT COUNT(*) FROM MLDatasetVersion v WHERE v.datasetId=d.id) AS versions "
            "FROM MLDataset d ORDER BY d.updatedAt DESC LIMIT ?", (int(limit),)).fetchall()
        return [{"id": r["id"], "name": r["name"], "description": r["description"],
                 "assetClass": r["assetClass"], "createdAt": r["createdAt"],
                 "updatedAt": r["updatedAt"], "versions": r["versions"]} for r in rows]

    def list_dataset_versions(self, dataset_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM MLDatasetVersion WHERE datasetId=? ORDER BY createdAt", (dataset_id,)).fetchall()
        return [{"datasetId": r["datasetId"], "version": r["version"], "rows": r["rows"],
                 "featureCount": r["featureCount"], "coverage": r["coverage"],
                 "qualityStatus": r["qualityStatus"], "dataHash": r["dataHash"],
                 "artifactId": r["artifactId"], "createdAt": r["createdAt"],
                 "manifest": _loads(r["manifestJson"], {})} for r in rows]

    def get_dataset_version(self, dataset_id: str, version: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM MLDatasetVersion WHERE datasetId=? AND version=?",
            (dataset_id, version)).fetchone()
        if not row:
            return None
        artifact = self.get_artifact(row["artifactId"]) if row["artifactId"] else None
        return {"datasetId": row["datasetId"], "version": row["version"],
                "manifest": _loads(row["manifestJson"], {}), "dataHash": row["dataHash"],
                "artifact": artifact}

    # ── experiments / runs ────────────────────────────────────────────────────
    def create_experiment(self, *, title: str, dataset_id: str, dataset_version: str,
                          target: dict, feature_names: list[str], model_family: str,
                          hyperparameters: dict, selection: dict, split_spec: dict,
                          seed: int, task: Optional[str], owner: Optional[str]) -> str:
        experiment_id = f"mle_{uuid.uuid4().hex[:14]}"
        now = now_iso()
        self._db.execute(
            "INSERT INTO MLExperiment (id,title,datasetId,datasetVersion,targetJson,"
            "featureNamesJson,modelFamily,hyperparamsJson,selectionJson,splitSpecJson,seed,task,"
            "owner,status,createdAt,updatedAt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (experiment_id, title, dataset_id, dataset_version, _json(target),
             _json(feature_names), model_family, _json(hyperparameters), _json(selection),
             _json(split_spec), int(seed), task, owner, "draft", now, now))
        self._db.commit()
        return experiment_id

    def create_run(self, experiment_id: str) -> str:
        run_id = f"mlr_{uuid.uuid4().hex[:14]}"
        now = now_iso()
        self._db.execute(
            "INSERT INTO MLExperimentRun (id,experimentId,status,stage,startedAt,createdAt) "
            "VALUES (?,?,?,?,?,?)",
            (run_id, experiment_id, "running", "starting", now, now))
        self._db.execute("UPDATE MLExperiment SET status='running', updatedAt=? WHERE id=?",
                         (now, experiment_id))
        self._db.commit()
        return run_id

    def finish_run(self, run_id: str, *, status: str, metrics: Optional[dict] = None,
                   error: Optional[dict] = None, artifact_id: Optional[str] = None,
                   duration_ms: Optional[int] = None, stage: str = "finished") -> None:
        started = self._db.execute("SELECT startedAt, experimentId FROM MLExperimentRun WHERE id=?",
                                   (run_id,)).fetchone()
        now = now_iso()
        self._db.execute(
            "UPDATE MLExperimentRun SET status=?, stage=?, metricsJson=?, errorJson=?, "
            "artifactId=?, finishedAt=?, durationMs=? WHERE id=?",
            (status, stage, _json(metrics), _json(error), artifact_id, now, duration_ms, run_id))
        if started is not None:
            self._db.execute("UPDATE MLExperiment SET status=?, updatedAt=? WHERE id=?",
                             (status, now, started["experimentId"]))
        self._db.commit()

    def record_folds(self, run_id: str, folds: list[dict[str, Any]]) -> None:
        now = now_iso()
        for f in folds:
            self._db.execute(
                "INSERT INTO MLFoldResult (id,runId,fold,status,nTrain,nTest,nPurged,nEmbargoed,"
                "metricsJson,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (f"mlf_{uuid.uuid4().hex[:12]}", run_id, int(f.get("index", 0)),
                 f.get("status", "ok"), int(f.get("nTrain", 0)), int(f.get("nTest", 0)),
                 int(f.get("nPurged", 0)), int(f.get("nEmbargoed", 0)), _json(f.get("metrics")), now))
        self._db.commit()

    def list_experiments(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT e.*, (SELECT COUNT(*) FROM MLExperimentRun r WHERE r.experimentId=e.id) AS runs "
            "FROM MLExperiment e ORDER BY e.createdAt DESC LIMIT ?", (int(limit),)).fetchall()
        return [self._experiment_row(r, runs=r["runs"]) for r in rows]

    def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM MLExperiment WHERE id=?", (experiment_id,)).fetchone()
        return self._experiment_row(row) if row else None

    def list_runs(self, experiment_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM MLExperimentRun WHERE experimentId=? ORDER BY createdAt DESC LIMIT ?",
            (experiment_id, int(limit))).fetchall()
        return [{"id": r["id"], "experimentId": r["experimentId"], "status": r["status"],
                 "stage": r["stage"], "metrics": _loads(r["metricsJson"], {}),
                 "error": _loads(r["errorJson"], None), "artifactId": r["artifactId"],
                 "startedAt": r["startedAt"], "finishedAt": r["finishedAt"],
                 "durationMs": r["durationMs"], "createdAt": r["createdAt"]} for r in rows]

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM MLExperimentRun WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        folds = self._db.execute(
            "SELECT * FROM MLFoldResult WHERE runId=? ORDER BY fold", (run_id,)).fetchall()
        return {"id": row["id"], "experimentId": row["experimentId"], "status": row["status"],
                "stage": row["stage"], "metrics": _loads(row["metricsJson"], {}),
                "error": _loads(row["errorJson"], None), "artifactId": row["artifactId"],
                "startedAt": row["startedAt"], "finishedAt": row["finishedAt"],
                "durationMs": row["durationMs"], "createdAt": row["createdAt"],
                "folds": [{"fold": f["fold"], "status": f["status"], "nTrain": f["nTrain"],
                           "nTest": f["nTest"], "nPurged": f["nPurged"],
                           "nEmbargoed": f["nEmbargoed"], "metrics": _loads(f["metricsJson"], {})}
                          for f in folds]}

    def get_run_result(self, run_id: str) -> Optional[dict[str, Any]]:
        run = self.get_run(run_id)
        if run is None:
            return None
        if run.get("artifactId"):
            artifact = self.get_artifact(run["artifactId"])
            run["result"] = artifact["content"] if artifact else None
        return run

    # ── models / registry ─────────────────────────────────────────────────────
    def register_model(self, *, name: str, family: str, task: str, run_id: str,
                       dataset_id: str, dataset_version: str, model_state: dict[str, Any],
                       metrics: dict[str, Any], signature: dict[str, Any],
                       deps: dict[str, Any], owner: Optional[str],
                       model_id: Optional[str] = None) -> dict[str, Any]:
        now = now_iso()
        created = False
        if not model_id:
            model_id = f"mlm_{uuid.uuid4().hex[:12]}"
        row = self._db.execute("SELECT latestVersion FROM MLModel WHERE id=?", (model_id,)).fetchone()
        if row is None:
            version = "1.0.0"
            self._db.execute(
                "INSERT INTO MLModel (id,name,family,owner,status,latestVersion,createdAt,updatedAt) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (model_id, name, family, owner, "draft", version, now, now))
            created = True
        else:
            version = _bump(row["latestVersion"] or "1.0.0")

        state_artifact = self.save_artifact(model_state, kind="model-state")
        version_id = f"{model_id}@{version}"
        self._db.execute(
            "INSERT INTO MLModelVersion (id,modelId,version,runId,datasetId,datasetVersion,family,"
            "task,stateArtifactId,sha256,signatureJson,depsJson,metricsJson,status,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (version_id, model_id, version, run_id, dataset_id, dataset_version, family, task,
             state_artifact["id"], state_artifact["sha256"], _json(signature), _json(deps),
             _json(metrics), "draft", now))
        self._db.execute("UPDATE MLModel SET latestVersion=?, updatedAt=? WHERE id=?",
                         (version, now, model_id))
        self._db.commit()
        return {"modelId": model_id, "version": version, "created": created,
                "stateArtifactId": state_artifact["id"], "sha256": state_artifact["sha256"],
                "status": "draft"}

    def list_models(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT m.*, (SELECT COUNT(*) FROM MLModelVersion v WHERE v.modelId=m.id) AS versions "
            "FROM MLModel m ORDER BY m.updatedAt DESC LIMIT ?", (int(limit),)).fetchall()
        return [{"id": r["id"], "name": r["name"], "family": r["family"], "owner": r["owner"],
                 "status": r["status"], "latestVersion": r["latestVersion"],
                 "versions": r["versions"], "createdAt": r["createdAt"],
                 "updatedAt": r["updatedAt"]} for r in rows]

    def get_model_version(self, model_id: str, version: Optional[str] = None) -> Optional[dict[str, Any]]:
        model = self._db.execute("SELECT * FROM MLModel WHERE id=?", (model_id,)).fetchone()
        if model is None:
            return None
        ver = version or model["latestVersion"]
        mv = self._db.execute("SELECT * FROM MLModelVersion WHERE modelId=? AND version=?",
                              (model_id, ver)).fetchone()
        if mv is None:
            return None
        approvals = self._db.execute(
            "SELECT * FROM MLApprovalEvent WHERE modelId=? AND version=? ORDER BY createdAt",
            (model_id, ver)).fetchall()
        return {
            "modelId": model_id, "name": model["name"], "family": model["family"],
            "status": model["status"], "version": ver, "task": mv["task"],
            "datasetId": mv["datasetId"], "datasetVersion": mv["datasetVersion"],
            "runId": mv["runId"], "sha256": mv["sha256"],
            "signature": _loads(mv["signatureJson"], {}), "deps": _loads(mv["depsJson"], {}),
            "metrics": _loads(mv["metricsJson"], {}), "stateArtifactId": mv["stateArtifactId"],
            "approvals": [{"action": a["action"], "actor": a["actor"], "reason": a["reason"],
                           "createdAt": a["createdAt"]} for a in approvals],
        }

    def transition_model(self, model_id: str, *, version: str, action: str, actor: Optional[str],
                         reason: Optional[str] = None, to_status: Optional[str] = None) -> dict[str, Any]:
        now = now_iso()
        self._db.execute(
            "INSERT INTO MLApprovalEvent (id,modelId,version,action,actor,reason,createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (f"mlap_{uuid.uuid4().hex[:12]}", model_id, version, action, actor, reason, now))
        if to_status:
            self._db.execute("UPDATE MLModelVersion SET status=? WHERE modelId=? AND version=?",
                             (to_status, model_id, version))
            self._db.execute("UPDATE MLModel SET status=?, updatedAt=? WHERE id=?",
                             (to_status, now, model_id))
        self._db.commit()
        return self.get_model_version(model_id, version) or {}

    def save_prediction_batch(self, *, run_id: str, model_id: str, version: str,
                              predictions: dict[str, Any]) -> dict[str, Any]:
        artifact = self.save_artifact(predictions, kind="predictions")
        batch_id = f"mlp_{uuid.uuid4().hex[:12]}"
        rows = len(predictions.get("pred") or [])
        self._db.execute(
            "INSERT INTO MLPredictionBatch (id,runId,modelId,version,artifactId,rows,createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (batch_id, run_id, model_id, version, artifact["id"], rows, now_iso()))
        self._db.commit()
        return {"id": batch_id, "artifactId": artifact["id"], "rows": rows}

    # ── audit ────────────────────────────────────────────────────────────────
    def audit(self, *, action: str, subject_type: Optional[str] = None,
              subject_id: Optional[str] = None, actor: Optional[str] = None,
              detail: Optional[dict] = None) -> None:
        self._db.execute(
            "INSERT INTO MLAudit (action,subjectType,subjectId,actor,detailJson,createdAt) "
            "VALUES (?,?,?,?,?,?)",
            (action, subject_type, subject_id, actor, _json(detail), now_iso()))
        self._db.commit()

    # ── rows ─────────────────────────────────────────────────────────────────
    def _experiment_row(self, row: Any, runs: int = 0) -> dict[str, Any]:
        return {
            "id": row["id"], "title": row["title"], "datasetId": row["datasetId"],
            "datasetVersion": row["datasetVersion"], "modelFamily": row["modelFamily"],
            "hyperparameters": _loads(row["hyperparamsJson"], {}),
            "selection": _loads(row["selectionJson"], {}),
            "splitSpec": _loads(row["splitSpecJson"], {}), "seed": row["seed"],
            "task": row["task"], "owner": row["owner"], "status": row["status"],
            "createdAt": row["createdAt"], "updatedAt": row["updatedAt"], "runs": runs,
        }


def _bump(version: str) -> str:
    parts = version.split(".")
    try:
        nums = [int(p) for p in parts[:3]]
    except ValueError:
        return "1.0.0"
    while len(nums) < 3:
        nums.append(0)
    return f"{nums[0]}.{nums[1]}.{nums[2] + 1}"


__all__ = ["MLStore"]

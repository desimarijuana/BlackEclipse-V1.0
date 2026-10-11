"""Persistence for the Factor & Alpha Research Lab.

Follows the harness convention: metadata lives in the ONE `agent-memory.db`
connection (additive, idempotent DDL — never `jdds.db`, never
`eclipse-memory.db`); large result series are written as gzipped JSON artifacts
under `.black-eclipse/factors/`.

Entities:
  * `Factor` / `FactorVersion` — the factor registry with immutable versions,
  * `FactorRun`               — an evaluation/portfolio/validation run,
  * `AlphaExperiment`         — a research experiment configuration,
  * `AlphaMetric`             — a named metric attached to an experiment,
  * `PortfolioRun`            — a quantile-portfolio simulation result,
  * `FactorValidation`        — a structured validation-gate outcome,
  * `FactorLineage`           — dependency/lineage edges,
  * `FactorArtifact`          — checksummed large-result references.
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
CREATE TABLE IF NOT EXISTS Factor (
  id               TEXT PRIMARY KEY,
  name             TEXT NOT NULL,
  description      TEXT,
  family           TEXT NOT NULL DEFAULT 'custom',
  owner            TEXT,
  direction        TEXT,
  frequency        TEXT NOT NULL DEFAULT '1d',
  assetClass       TEXT NOT NULL DEFAULT 'equity',
  tagsJson         TEXT,
  latestVersion    TEXT NOT NULL,
  lifecycleStatus  TEXT NOT NULL DEFAULT 'active',
  validationStatus TEXT NOT NULL DEFAULT 'unvalidated',
  builtIn          INTEGER NOT NULL DEFAULT 0,
  archived         INTEGER NOT NULL DEFAULT 0,
  createdAt        TEXT NOT NULL,
  updatedAt        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_factor_name ON Factor(name);
CREATE INDEX IF NOT EXISTS idx_factor_family ON Factor(family);

CREATE TABLE IF NOT EXISTS FactorVersion (
  id               TEXT PRIMARY KEY,
  factorId         TEXT NOT NULL,
  version          TEXT NOT NULL,
  expression       TEXT NOT NULL,
  inputsJson       TEXT,
  paramsJson       TEXT,
  normalization    TEXT NOT NULL DEFAULT 'cross_sectional_zscore',
  missingPolicy    TEXT NOT NULL DEFAULT 'drop',
  lookback         INTEGER NOT NULL DEFAULT 1,
  outputType       TEXT NOT NULL DEFAULT 'float',
  pitSafe          INTEGER NOT NULL DEFAULT 1,
  definitionHash   TEXT,
  changelog        TEXT,
  createdAt        TEXT NOT NULL,
  UNIQUE(factorId, version)
);
CREATE INDEX IF NOT EXISTS idx_factorversion_factor ON FactorVersion(factorId);

CREATE TABLE IF NOT EXISTS FactorRun (
  id             TEXT PRIMARY KEY,
  factorId       TEXT,
  version        TEXT,
  kind           TEXT NOT NULL,
  datasetRefJson TEXT,
  configJson     TEXT,
  status         TEXT NOT NULL,
  stage          TEXT,
  done           INTEGER NOT NULL DEFAULT 0,
  total          INTEGER NOT NULL DEFAULT 0,
  errorJson      TEXT,
  resultRef      TEXT,
  provenanceJson TEXT,
  createdAt      TEXT NOT NULL,
  finishedAt     TEXT
);
CREATE INDEX IF NOT EXISTS idx_factorrun_factor ON FactorRun(factorId);
CREATE INDEX IF NOT EXISTS idx_factorrun_created ON FactorRun(createdAt);

CREATE TABLE IF NOT EXISTS AlphaExperiment (
  id              TEXT PRIMARY KEY,
  hypothesis      TEXT,
  factorRefsJson  TEXT,
  universeJson    TEXT,
  horizonsJson    TEXT,
  splitsJson      TEXT,
  costJson        TEXT,
  configJson      TEXT,
  status          TEXT NOT NULL,
  outcomeJson     TEXT,
  createdAt       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alphaexp_created ON AlphaExperiment(createdAt);

CREATE TABLE IF NOT EXISTS AlphaMetric (
  id           TEXT PRIMARY KEY,
  experimentId TEXT NOT NULL,
  name         TEXT NOT NULL,
  value        REAL,
  paramsJson   TEXT,
  createdAt    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alphametric_exp ON AlphaMetric(experimentId);

CREATE TABLE IF NOT EXISTS PortfolioRun (
  id           TEXT PRIMARY KEY,
  experimentId TEXT,
  configJson   TEXT,
  metricsJson  TEXT,
  artifactRef  TEXT,
  createdAt    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_portfoliorun_exp ON PortfolioRun(experimentId);

CREATE TABLE IF NOT EXISTS FactorValidation (
  id           TEXT PRIMARY KEY,
  experimentId TEXT,
  factorRef    TEXT,
  status       TEXT NOT NULL,
  detailJson   TEXT,
  createdAt    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_factorvalidation_exp ON FactorValidation(experimentId);

CREATE TABLE IF NOT EXISTS FactorLineage (
  id         TEXT PRIMARY KEY,
  childType  TEXT NOT NULL,
  childId    TEXT NOT NULL,
  parentType TEXT NOT NULL,
  parentId   TEXT NOT NULL,
  relation   TEXT NOT NULL,
  createdAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_factorlineage_child ON FactorLineage(childType, childId);

CREATE TABLE IF NOT EXISTS FactorArtifact (
  id          TEXT PRIMARY KEY,
  runId       TEXT,
  path        TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  bytes       INTEGER NOT NULL,
  contentType TEXT,
  createdAt   TEXT NOT NULL
);
"""


def _artifact_root() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(root, ".black-eclipse", "factors", "artifacts")


def _json(value: Any) -> Optional[str]:
    return None if value is None else json.dumps(value, default=str)


def _loads(value: Optional[str], default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class FactorStore:
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

    # ── factor registry ──────────────────────────────────────────────────────
    def upsert_factor(self, *, factor_id: str, name: str, description: Optional[str], family: str,
                      owner: Optional[str], direction: Optional[str], frequency: str,
                      asset_class: str, tags: list[str], latest_version: str,
                      built_in: bool = False) -> dict:
        now = now_iso()
        row = self._db.execute("SELECT id FROM Factor WHERE id=?", (factor_id,)).fetchone()
        if row is None:
            self._db.execute(
                "INSERT INTO Factor (id,name,description,family,owner,direction,frequency,assetClass,"
                "tagsJson,latestVersion,lifecycleStatus,validationStatus,builtIn,archived,createdAt,"
                "updatedAt) VALUES (?,?,?,?,?,?,?,?,?,?,'active','unvalidated',?,0,?,?)",
                (factor_id, name, description, family, owner, direction, frequency, asset_class,
                 _json(tags), latest_version, 1 if built_in else 0, now, now),
            )
        else:
            self._db.execute(
                "UPDATE Factor SET name=?, description=?, family=?, owner=?, direction=?, frequency=?, "
                "assetClass=?, tagsJson=?, latestVersion=?, archived=0, updatedAt=? WHERE id=?",
                (name, description, family, owner, direction, frequency, asset_class, _json(tags),
                 latest_version, now, factor_id),
            )
        self._db.commit()
        return self.get_factor(factor_id)  # type: ignore[return-value]

    def add_version(self, *, factor_id: str, version: str, expression: str, inputs: list[str],
                    params: dict, normalization: str, missing_policy: str, lookback: int,
                    output_type: str, pit_safe: bool, changelog: Optional[str]) -> dict:
        definition = {
            "expression": expression, "inputs": inputs, "params": params,
            "normalization": normalization, "missingPolicy": missing_policy,
            "lookback": lookback, "outputType": output_type, "pitSafe": pit_safe,
        }
        definition_hash = hashlib.sha256(_json(definition).encode()).hexdigest()[:32]
        vid = f"{factor_id}@{version}"
        self._db.execute(
            "INSERT OR REPLACE INTO FactorVersion (id,factorId,version,expression,inputsJson,paramsJson,"
            "normalization,missingPolicy,lookback,outputType,pitSafe,definitionHash,changelog,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, factor_id, version, expression, _json(inputs), _json(params), normalization,
             missing_policy, lookback, output_type, 1 if pit_safe else 0, definition_hash, changelog,
             now_iso()),
        )
        self._db.commit()
        return self.get_version(factor_id, version)  # type: ignore[return-value]

    def set_validation(self, factor_id: str, status: str) -> None:
        self._db.execute("UPDATE Factor SET validationStatus=?, updatedAt=? WHERE id=?",
                         (status, now_iso(), factor_id))
        self._db.commit()

    def get_factor(self, factor_id: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM Factor WHERE id=?", (factor_id,)).fetchone()
        return self._factor_row(row) if row else None

    def get_factor_by_name(self, name: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM Factor WHERE name=? AND archived=0 "
                               "ORDER BY updatedAt DESC LIMIT 1", (name,)).fetchone()
        return self._factor_row(row) if row else None

    def list_factors(self, *, family: Optional[str] = None, include_archived: bool = False) -> list[dict]:
        sql = "SELECT * FROM Factor WHERE 1=1"
        args: list[Any] = []
        if not include_archived:
            sql += " AND archived=0"
        if family:
            sql += " AND family=?"
            args.append(family)
        sql += " ORDER BY updatedAt DESC"
        return [self._factor_row(r) for r in self._db.execute(sql, args).fetchall()]

    def get_version(self, factor_id: str, version: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM FactorVersion WHERE factorId=? AND version=?",
                               (factor_id, version)).fetchone()
        return self._version_row(row) if row else None

    def list_versions(self, factor_id: str) -> list[dict]:
        rows = self._db.execute("SELECT * FROM FactorVersion WHERE factorId=? ORDER BY createdAt",
                                (factor_id,)).fetchall()
        return [self._version_row(r) for r in rows]

    def _factor_row(self, row: Any) -> dict:
        return {
            "id": row["id"], "name": row["name"], "description": row["description"],
            "family": row["family"], "owner": row["owner"], "direction": row["direction"],
            "frequency": row["frequency"], "assetClass": row["assetClass"],
            "tags": _loads(row["tagsJson"], []), "latestVersion": row["latestVersion"],
            "lifecycleStatus": row["lifecycleStatus"], "validationStatus": row["validationStatus"],
            "builtIn": bool(row["builtIn"]), "archived": bool(row["archived"]),
            "createdAt": row["createdAt"], "updatedAt": row["updatedAt"],
        }

    def _version_row(self, row: Any) -> dict:
        return {
            "factorId": row["factorId"], "version": row["version"], "expression": row["expression"],
            "inputs": _loads(row["inputsJson"], []), "params": _loads(row["paramsJson"], {}),
            "normalization": row["normalization"], "missingPolicy": row["missingPolicy"],
            "lookback": row["lookback"], "outputType": row["outputType"],
            "pitSafe": bool(row["pitSafe"]), "definitionHash": row["definitionHash"],
            "changelog": row["changelog"], "createdAt": row["createdAt"],
        }

    # ── experiments / runs ───────────────────────────────────────────────────
    def create_experiment(self, *, hypothesis: Optional[str], factor_refs: list[dict],
                          universe: dict, horizons: list[int], splits: dict, cost: dict,
                          config: dict) -> str:
        exp_id = f"aexp_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO AlphaExperiment (id,hypothesis,factorRefsJson,universeJson,horizonsJson,"
            "splitsJson,costJson,configJson,status,outcomeJson,createdAt) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (exp_id, hypothesis, _json(factor_refs), _json(universe), _json(horizons), _json(splits),
             _json(cost), _json(config), "created", None, now_iso()),
        )
        self._db.commit()
        return exp_id

    def set_experiment_status(self, experiment_id: str, status: str, outcome: Optional[dict] = None) -> None:
        self._db.execute("UPDATE AlphaExperiment SET status=?, outcomeJson=? WHERE id=?",
                         (status, _json(outcome), experiment_id))
        self._db.commit()

    def get_experiment(self, experiment_id: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM AlphaExperiment WHERE id=?", (experiment_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "hypothesis": row["hypothesis"],
            "factorRefs": _loads(row["factorRefsJson"], []), "universe": _loads(row["universeJson"], {}),
            "horizons": _loads(row["horizonsJson"], []), "splits": _loads(row["splitsJson"], {}),
            "cost": _loads(row["costJson"], {}), "config": _loads(row["configJson"], {}),
            "status": row["status"], "outcome": _loads(row["outcomeJson"], None),
            "createdAt": row["createdAt"],
        }

    def list_experiments(self, limit: int = 50) -> list[dict]:
        rows = self._db.execute(
            "SELECT id,hypothesis,status,createdAt,outcomeJson FROM AlphaExperiment "
            "ORDER BY createdAt DESC LIMIT ?", (int(limit),)).fetchall()
        return [{"id": r["id"], "hypothesis": r["hypothesis"], "status": r["status"],
                 "outcome": _loads(r["outcomeJson"], None), "createdAt": r["createdAt"]} for r in rows]

    def add_metric(self, experiment_id: str, name: str, value: Optional[float], params: dict) -> str:
        mid = f"amet_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO AlphaMetric (id,experimentId,name,value,paramsJson,createdAt) VALUES (?,?,?,?,?,?)",
            (mid, experiment_id, name, value, _json(params), now_iso()),
        )
        self._db.commit()
        return mid

    def list_metrics(self, experiment_id: str) -> list[dict]:
        rows = self._db.execute("SELECT * FROM AlphaMetric WHERE experimentId=? ORDER BY createdAt",
                                (experiment_id,)).fetchall()
        return [{"id": r["id"], "name": r["name"], "value": r["value"],
                 "params": _loads(r["paramsJson"], {})} for r in rows]

    def save_portfolio_run(self, *, experiment_id: Optional[str], config: dict, metrics: dict,
                           artifact_ref: Optional[str]) -> str:
        rid = f"prun_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO PortfolioRun (id,experimentId,configJson,metricsJson,artifactRef,createdAt) "
            "VALUES (?,?,?,?,?,?)",
            (rid, experiment_id, _json(config), _json(metrics), artifact_ref, now_iso()),
        )
        self._db.commit()
        return rid

    def get_portfolio_run(self, run_id: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM PortfolioRun WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "experimentId": row["experimentId"],
                "config": _loads(row["configJson"], {}), "metrics": _loads(row["metricsJson"], {}),
                "artifactRef": row["artifactRef"], "createdAt": row["createdAt"]}

    def record_validation(self, *, experiment_id: Optional[str], factor_ref: Optional[str], status: str,
                          detail: dict) -> str:
        vid = f"fval_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO FactorValidation (id,experimentId,factorRef,status,detailJson,createdAt) "
            "VALUES (?,?,?,?,?,?)",
            (vid, experiment_id, factor_ref, status, _json(detail), now_iso()),
        )
        self._db.commit()
        return vid

    def list_validations(self, experiment_id: str) -> list[dict]:
        rows = self._db.execute("SELECT * FROM FactorValidation WHERE experimentId=? ORDER BY createdAt DESC",
                                (experiment_id,)).fetchall()
        return [{"id": r["id"], "status": r["status"], "factorRef": r["factorRef"],
                 "detail": _loads(r["detailJson"], {}), "createdAt": r["createdAt"]} for r in rows]

    def add_lineage(self, *, child_type: str, child_id: str, parent_type: str, parent_id: str,
                    relation: str) -> str:
        lid = f"flin_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO FactorLineage (id,childType,childId,parentType,parentId,relation,createdAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (lid, child_type, child_id, parent_type, parent_id, relation, now_iso()),
        )
        self._db.commit()
        return lid

    def lineage_for(self, child_type: str, child_id: str) -> list[dict]:
        rows = self._db.execute("SELECT * FROM FactorLineage WHERE childType=? AND childId=?",
                                (child_type, child_id)).fetchall()
        return [{"parentType": r["parentType"], "parentId": r["parentId"], "relation": r["relation"]}
                for r in rows]

    # ── runs ─────────────────────────────────────────────────────────────────
    def upsert_run(self, run_id: str, *, factor_id: Optional[str], version: Optional[str], kind: str,
                   dataset_ref: Optional[dict], config: dict, status: str, stage: str = "",
                   done: int = 0, total: int = 0, error: Optional[dict] = None,
                   result_ref: Optional[str] = None, provenance: Optional[dict] = None,
                   finished_at: Optional[str] = None) -> None:
        row = self._db.execute("SELECT id FROM FactorRun WHERE id=?", (run_id,)).fetchone()
        if row is None:
            self._db.execute(
                "INSERT INTO FactorRun (id,factorId,version,kind,datasetRefJson,configJson,status,stage,"
                "done,total,errorJson,resultRef,provenanceJson,createdAt,finishedAt) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, factor_id, version, kind, _json(dataset_ref), _json(config), status, stage,
                 done, total, _json(error), result_ref, _json(provenance), now_iso(), finished_at),
            )
        else:
            self._db.execute(
                "UPDATE FactorRun SET status=?, stage=?, done=?, total=?, errorJson=?, resultRef=?, "
                "finishedAt=? WHERE id=?",
                (status, stage, done, total, _json(error), result_ref, finished_at, run_id),
            )
        self._db.commit()

    def get_run(self, run_id: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM FactorRun WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "factorId": row["factorId"], "version": row["version"], "kind": row["kind"],
            "datasetRef": _loads(row["datasetRefJson"], None), "config": _loads(row["configJson"], {}),
            "status": row["status"], "stage": row["stage"], "done": row["done"], "total": row["total"],
            "error": _loads(row["errorJson"], None), "resultRef": row["resultRef"],
            "provenance": _loads(row["provenanceJson"], {}), "createdAt": row["createdAt"],
            "finishedAt": row["finishedAt"],
        }

    def list_runs(self, limit: int = 50) -> list[dict]:
        rows = self._db.execute(
            "SELECT id,factorId,version,kind,status,stage,done,total,createdAt,finishedAt FROM FactorRun "
            "ORDER BY createdAt DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    # ── artifacts ────────────────────────────────────────────────────────────
    def save_artifact(self, content: Any, *, run_id: Optional[str] = None,
                      content_type: str = "application/json") -> dict:
        raw = json.dumps(content, default=str).encode()
        digest = hashlib.sha256(raw).hexdigest()
        name = f"{digest[:16]}.json.gz"
        path = os.path.join(self._root, name)
        with gzip.open(path, "wb") as fh:
            fh.write(raw)
        artifact_id = f"fart_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO FactorArtifact (id,runId,path,sha256,bytes,contentType,createdAt) VALUES (?,?,?,?,?,?,?)",
            (artifact_id, run_id, path, digest, len(raw), content_type, now_iso()),
        )
        self._db.commit()
        return {"id": artifact_id, "path": path, "sha256": digest, "bytes": len(raw),
                "contentType": content_type}

    def get_artifact(self, artifact_id: str) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM FactorArtifact WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            return None
        with gzip.open(row["path"], "rb") as fh:
            content = json.loads(fh.read().decode())
        return {"id": row["id"], "runId": row["runId"], "sha256": row["sha256"],
                "bytes": row["bytes"], "contentType": row["contentType"], "content": content}


def build_version_string(prev: Optional[str], bump: str = "patch") -> str:
    major, minor, patch = (int(x) for x in (prev or "0.0.0").split(".")[:3])
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


__all__ = ["FactorStore", "build_version_string"]

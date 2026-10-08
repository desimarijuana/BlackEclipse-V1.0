"""Persistence for strategies and experiments.

Follows the harness convention: metadata lives in the ONE `agent-memory.db`
connection (additive, idempotent DDL — never `jdds.db`, never
`eclipse-memory.db`); large result series (equity/drawdown/trades/orders) are
written as gzipped JSON artifacts under `.black-eclipse/quant/experiments/`
so a wide equity curve never bloats a relational row.

Every experiment stores the full reproducibility envelope: strategy id+version,
dataset symbols/interval/range, engine version, seed, execution assumptions and
metrics — so historical research can be reproduced exactly.
"""

from __future__ import annotations

import gzip
import json
import os
import time
import uuid
from typing import Any, Optional

from .errors import ExperimentNotFound, StrategyNotFound, StrategyVersionNotFound
from .strategy import StrategySpec


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def _artifact_root() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(root, ".black-eclipse", "quant", "experiments")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS QuantStrategy (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  assetClass TEXT,
  latestVersion TEXT NOT NULL,
  archived INTEGER NOT NULL DEFAULT 0,
  createdAt TEXT NOT NULL,
  updatedAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS QuantStrategyVersion (
  id TEXT PRIMARY KEY,
  strategyId TEXT NOT NULL,
  version TEXT NOT NULL,
  specJson TEXT NOT NULL,
  createdAt TEXT NOT NULL,
  UNIQUE(strategyId, version)
);
CREATE INDEX IF NOT EXISTS idx_qsv_strategy ON QuantStrategyVersion(strategyId);
CREATE TABLE IF NOT EXISTS QuantExperiment (
  id TEXT PRIMARY KEY,
  strategyId TEXT,
  strategyVersion TEXT,
  kind TEXT NOT NULL,
  symbolsJson TEXT,
  interval TEXT,
  startTs TEXT,
  endTs TEXT,
  initialCapital REAL,
  seed INTEGER,
  engineVersion TEXT,
  status TEXT NOT NULL,
  metricsJson TEXT,
  configurationJson TEXT,
  warningsJson TEXT,
  artifactPath TEXT,
  durationMs INTEGER,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qexp_strategy ON QuantExperiment(strategyId);
CREATE INDEX IF NOT EXISTS idx_qexp_created ON QuantExperiment(createdAt);
"""


class QuantStore:
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

    # ── Strategies ───────────────────────────────────────────────────────────
    def save_strategy(self, spec: StrategySpec, *, description: Optional[str] = None) -> dict:
        now = _iso_now()
        spec_json = spec.to_json()
        existing = self._db.execute(
            "SELECT id, createdAt FROM QuantStrategy WHERE id = ?", (spec.id,)
        ).fetchone()
        if existing is None:
            self._db.execute(
                "INSERT INTO QuantStrategy (id,name,description,assetClass,latestVersion,"
                "archived,createdAt,updatedAt) VALUES (?,?,?,?,?,0,?,?)",
                (spec.id, spec.name, description or spec.description, spec.asset_class,
                 spec.version, now, now),
            )
        else:
            self._db.execute(
                "UPDATE QuantStrategy SET name=?, description=?, assetClass=?, latestVersion=?, "
                "archived=0, updatedAt=? WHERE id=?",
                (spec.name, description or spec.description, spec.asset_class,
                 spec.version, now, spec.id),
            )
        version_id = f"{spec.id}@{spec.version}"
        self._db.execute(
            "INSERT OR REPLACE INTO QuantStrategyVersion "
            "(id,strategyId,version,specJson,createdAt) VALUES (?,?,?,?,?)",
            (version_id, spec.id, spec.version, spec_json, now),
        )
        self._db.commit()
        return self.get_strategy(spec.id, spec.version)  # type: ignore[return-value]

    def _row_to_spec(self, row) -> dict:
        spec = json.loads(row["specJson"])
        return {"spec": spec, "version": row["version"], "createdAt": row["createdAt"]}

    def get_strategy(self, strategy_id: str, version: Optional[str] = None) -> Optional[dict]:
        head = self._db.execute(
            "SELECT * FROM QuantStrategy WHERE id = ?", (strategy_id,)
        ).fetchone()
        if head is None:
            raise StrategyNotFound(f"strategy {strategy_id!r} not found",
                                   detail={"strategyId": strategy_id})
        target = version or head["latestVersion"]
        row = self._db.execute(
            "SELECT * FROM QuantStrategyVersion WHERE strategyId=? AND version=?",
            (strategy_id, target),
        ).fetchone()
        if row is None:
            raise StrategyVersionNotFound(
                f"strategy {strategy_id!r} version {target!r} not found",
                detail={"strategyId": strategy_id, "version": target},
            )
        data = self._row_to_spec(row)
        return {
            "id": head["id"], "name": head["name"], "description": head["description"],
            "assetClass": head["assetClass"], "latestVersion": head["latestVersion"],
            "archived": bool(head["archived"]), "createdAt": head["createdAt"],
            "updatedAt": head["updatedAt"], **data,
        }

    def list_strategies(self, *, include_archived: bool = False) -> list[dict]:
        clause = "" if include_archived else "WHERE archived = 0"
        rows = self._db.execute(
            f"SELECT * FROM QuantStrategy {clause} ORDER BY updatedAt DESC"
        ).fetchall()
        return [
            {
                "id": r["id"], "name": r["name"], "description": r["description"],
                "assetClass": r["assetClass"], "latestVersion": r["latestVersion"],
                "archived": bool(r["archived"]), "createdAt": r["createdAt"],
                "updatedAt": r["updatedAt"],
            }
            for r in rows
        ]

    def list_versions(self, strategy_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT version, createdAt FROM QuantStrategyVersion WHERE strategyId=? "
            "ORDER BY createdAt ASC", (strategy_id,),
        ).fetchall()
        return [{"version": r["version"], "createdAt": r["createdAt"]} for r in rows]

    def archive_strategy(self, strategy_id: str, archived: bool = True) -> None:
        cur = self._db.execute(
            "UPDATE QuantStrategy SET archived=?, updatedAt=? WHERE id=?",
            (1 if archived else 0, _iso_now(), strategy_id),
        )
        if cur.rowcount == 0:
            raise StrategyNotFound(f"strategy {strategy_id!r} not found")
        self._db.commit()

    def delete_strategy(self, strategy_id: str) -> None:
        self._db.execute("DELETE FROM QuantStrategyVersion WHERE strategyId=?", (strategy_id,))
        cur = self._db.execute("DELETE FROM QuantStrategy WHERE id=?", (strategy_id,))
        if cur.rowcount == 0:
            raise StrategyNotFound(f"strategy {strategy_id!r} not found")
        self._db.commit()

    # ── Experiments ──────────────────────────────────────────────────────────
    def save_experiment(
        self,
        result: Any,
        *,
        strategy_id: Optional[str],
        strategy_version: Optional[str],
        kind: str,
    ) -> str:
        exp_id = f"exp_{uuid.uuid4().hex[:16]}"
        payload = result.to_dict(include_series=True)
        path = os.path.join(self._root, f"{exp_id}.json.gz")
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh)
        cfg = result.configuration
        md = result.metadata
        cmd = self._db.execute(
            "INSERT INTO QuantExperiment (id,strategyId,strategyVersion,kind,symbolsJson,"
            "interval,startTs,endTs,initialCapital,seed,engineVersion,status,metricsJson,"
            "configurationJson,warningsJson,artifactPath,durationMs,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                exp_id, strategy_id, strategy_version, kind,
                json.dumps(md.get("symbols", [])), md.get("interval") or cfg.get("interval"),
                cfg.get("start"), cfg.get("end"), cfg.get("initialCapital"),
                cfg.get("randomSeed"), md.get("engineVersion"), result.status,
                json.dumps(result.metrics), json.dumps(cfg),
                json.dumps(result.warnings), path,
                result.observability.get("durationMs"), _iso_now(),
            ),
        )
        self._db.commit()
        assert cmd is not None
        return exp_id

    def _exp_row(self, row) -> dict:
        return {
            "id": row["id"], "strategyId": row["strategyId"],
            "strategyVersion": row["strategyVersion"], "kind": row["kind"],
            "symbols": json.loads(row["symbolsJson"] or "[]"), "interval": row["interval"],
            "start": row["startTs"], "end": row["endTs"],
            "initialCapital": row["initialCapital"], "seed": row["seed"],
            "engineVersion": row["engineVersion"], "status": row["status"],
            "metrics": json.loads(row["metricsJson"] or "{}"),
            "configuration": json.loads(row["configurationJson"] or "{}"),
            "warnings": json.loads(row["warningsJson"] or "[]"),
            "durationMs": row["durationMs"], "createdAt": row["createdAt"],
            "hasArtifact": bool(row["artifactPath"]),
        }

    def get_experiment(self, experiment_id: str, *, with_artifact: bool = False) -> dict:
        row = self._db.execute(
            "SELECT * FROM QuantExperiment WHERE id=?", (experiment_id,)
        ).fetchone()
        if row is None:
            raise ExperimentNotFound(f"experiment {experiment_id!r} not found",
                                     detail={"experimentId": experiment_id})
        data = self._exp_row(row)
        if with_artifact:
            data["artifact"] = self.read_artifact(experiment_id)
        return data

    def list_experiments(self, *, strategy_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        if strategy_id:
            rows = self._db.execute(
                "SELECT * FROM QuantExperiment WHERE strategyId=? ORDER BY createdAt DESC LIMIT ?",
                (strategy_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM QuantExperiment ORDER BY createdAt DESC LIMIT ?", (limit,),
            ).fetchall()
        return [self._exp_row(r) for r in rows]

    def read_artifact(self, experiment_id: str) -> dict:
        row = self._db.execute(
            "SELECT artifactPath FROM QuantExperiment WHERE id=?", (experiment_id,)
        ).fetchone()
        if row is None:
            raise ExperimentNotFound(f"experiment {experiment_id!r} not found")
        path = row["artifactPath"]
        if not path or not os.path.exists(path):
            raise ExperimentNotFound(
                f"artifact for experiment {experiment_id!r} is missing",
                detail={"experimentId": experiment_id, "path": path},
            )
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)

    def delete_experiment(self, experiment_id: str) -> None:
        row = self._db.execute(
            "SELECT artifactPath FROM QuantExperiment WHERE id=?", (experiment_id,)
        ).fetchone()
        if row is None:
            raise ExperimentNotFound(f"experiment {experiment_id!r} not found")
        path = row["artifactPath"]
        self._db.execute("DELETE FROM QuantExperiment WHERE id=?", (experiment_id,))
        self._db.commit()
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    # ── Comparison ───────────────────────────────────────────────────────────
    COMPARE_METRICS = [
        "total_return", "cagr", "max_drawdown", "sharpe", "sortino", "calmar",
        "volatility", "win_rate", "profit_factor", "trade_count", "expectancy",
    ]

    def compare_experiments(self, experiment_ids: list[str]) -> dict:
        experiments = [self.get_experiment(eid) for eid in experiment_ids]
        rows: list[dict] = []
        for exp in experiments:
            metrics = exp.get("metrics", {})
            rows.append({
                "experimentId": exp["id"], "strategyId": exp["strategyId"],
                "strategyVersion": exp["strategyVersion"], "kind": exp["kind"],
                "symbols": exp["symbols"], "interval": exp["interval"],
                "start": exp["start"], "end": exp["end"],
                "initialCapital": exp["initialCapital"], "createdAt": exp["createdAt"],
                "metrics": {k: metrics.get(k) for k in self.COMPARE_METRICS},
            })
        return {"metrics": self.COMPARE_METRICS, "experiments": rows}


__all__ = ["QuantStore"]

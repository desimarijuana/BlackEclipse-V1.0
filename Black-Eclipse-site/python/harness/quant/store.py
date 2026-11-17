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

from .errors import (
    ApprovalRequired,
    ExperimentNotFound,
    LiveTradingDisabled,
    QuantError,
    StrategyNotFound,
    StrategyVersionImmutable,
    StrategyVersionNotFound,
)
from .schema import STRATEGY_SCHEMA_VERSION, spec_content_hash
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
CREATE TABLE IF NOT EXISTS QuantStrategyApproval (
  id TEXT PRIMARY KEY,
  strategyId TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  actor TEXT,
  note TEXT,
  createdAt TEXT NOT NULL,
  decidedAt TEXT
);
CREATE INDEX IF NOT EXISTS idx_qappr_strategy ON QuantStrategyApproval(strategyId, version);
CREATE TABLE IF NOT EXISTS QuantStrategyDeployment (
  id TEXT PRIMARY KEY,
  strategyId TEXT NOT NULL,
  version TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT,
  createdAt TEXT NOT NULL,
  updatedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qdeploy_strategy ON QuantStrategyDeployment(strategyId);
CREATE TABLE IF NOT EXISTS QuantPaperRun (
  id TEXT PRIMARY KEY,
  deploymentId TEXT NOT NULL,
  strategyId TEXT NOT NULL,
  version TEXT NOT NULL,
  experimentId TEXT,
  status TEXT NOT NULL,
  symbolsJson TEXT,
  metricsJson TEXT,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qpaper_deployment ON QuantPaperRun(deploymentId);
CREATE TABLE IF NOT EXISTS QuantRunManifest (
  experimentId TEXT PRIMARY KEY,
  manifestJson TEXT NOT NULL,
  digest TEXT,
  createdAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS QuantResearchSession (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  question TEXT,
  strategyId TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  createdAt TEXT NOT NULL,
  updatedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qsession_created ON QuantResearchSession(createdAt);
CREATE TABLE IF NOT EXISTS QuantHypothesis (
  id TEXT PRIMARY KEY,
  sessionId TEXT NOT NULL,
  statement TEXT NOT NULL,
  universeJson TEXT,
  periodJson TEXT,
  metric TEXT,
  acceptance TEXT,
  status TEXT NOT NULL DEFAULT 'registered',
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qhyp_session ON QuantHypothesis(sessionId);
CREATE TABLE IF NOT EXISTS QuantTrial (
  id TEXT PRIMARY KEY,
  sessionId TEXT NOT NULL,
  hypothesisId TEXT,
  experimentId TEXT,
  kind TEXT NOT NULL,
  parametersJson TEXT,
  metricsJson TEXT,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qtrial_session ON QuantTrial(sessionId);
CREATE INDEX IF NOT EXISTS idx_qtrial_hyp ON QuantTrial(hypothesisId);
CREATE TABLE IF NOT EXISTS QuantMethod (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  methodFamily TEXT,
  status TEXT NOT NULL DEFAULT 'discovered',
  specJson TEXT,
  evidenceJson TEXT,
  strategyId TEXT,
  createdAt TEXT NOT NULL,
  updatedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qmethod_status ON QuantMethod(status);
"""


def _dict_diff(a: Any, b: Any, path: str, out: list[dict]) -> None:
    """Append structural changes (added/removed/changed) with dotted paths."""
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            child = f"{path}.{key}" if path else key
            if key not in a:
                out.append({"path": child, "kind": "added", "b": b[key]})
            elif key not in b:
                out.append({"path": child, "kind": "removed", "a": a[key]})
            else:
                _dict_diff(a[key], b[key], child, out)
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            child = f"{path}[{i}]"
            if i >= len(a):
                out.append({"path": child, "kind": "added", "b": b[i]})
            elif i >= len(b):
                out.append({"path": child, "kind": "removed", "a": a[i]})
            else:
                _dict_diff(a[i], b[i], child, out)
    elif a != b:
        out.append({"path": path or "(root)", "kind": "changed", "a": a, "b": b})


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
        # Additive columns for immutability/provenance (idempotent upgrade path).
        self._ensure_column("QuantStrategyVersion", "contentHash", "TEXT")
        self._ensure_column("QuantStrategyVersion", "schemaVersion", "TEXT")
        self._db.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        cols = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # ── Strategies ───────────────────────────────────────────────────────────
    def save_strategy(self, spec: StrategySpec, *, description: Optional[str] = None,
                      force: bool = False) -> dict:
        """Persist a strategy version.

        Immutability contract: a version already referenced by an experiment is
        frozen. Re-saving the *same* content is a no-op; re-saving *different*
        content under a referenced version raises `StrategyVersionImmutable` —
        the caller must bump the version. `force=True` overrides deliberately.
        """
        now = _iso_now()
        spec_json = spec.to_json()
        content_hash = spec_content_hash(spec)
        version_id = f"{spec.id}@{spec.version}"

        prior = self._db.execute(
            "SELECT specJson, contentHash FROM QuantStrategyVersion WHERE id=?", (version_id,)
        ).fetchone()
        if prior is not None and not force:
            prior_hash = prior["contentHash"] or spec_content_hash(json.loads(prior["specJson"]))
            if prior_hash != content_hash:
                referenced = self._db.execute(
                    "SELECT 1 FROM QuantExperiment WHERE strategyId=? AND strategyVersion=? LIMIT 1",
                    (spec.id, spec.version),
                ).fetchone()
                if referenced is not None:
                    raise StrategyVersionImmutable(
                        f"strategy {spec.id!r} version {spec.version!r} is immutable: it is "
                        "referenced by an experiment; bump the version to change it",
                        detail={"strategyId": spec.id, "version": spec.version},
                    )

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
        self._db.execute(
            "INSERT INTO QuantStrategyVersion "
            "(id,strategyId,version,specJson,contentHash,schemaVersion,createdAt) "
            "VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET specJson=excluded.specJson, "
            "contentHash=excluded.contentHash, schemaVersion=excluded.schemaVersion",
            (version_id, spec.id, spec.version, spec_json, content_hash,
             STRATEGY_SCHEMA_VERSION, now),
        )
        self._db.commit()
        return self.get_strategy(spec.id, spec.version)  # type: ignore[return-value]

    def _row_to_spec(self, row) -> dict:
        spec = json.loads(row["specJson"])
        content_hash = row["contentHash"] or spec_content_hash(spec)
        return {
            "spec": spec,
            "version": row["version"],
            "contentHash": content_hash,
            "schemaVersion": row["schemaVersion"] or STRATEGY_SCHEMA_VERSION,
            "createdAt": row["createdAt"],
        }

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

    def list_strategy_catalog(
        self, *, include_archived: bool = False, include_evidence: bool = True,
    ) -> list[dict]:
        """Strategies with the evidence a person needs before choosing one.

        One row per strategy (its LATEST version), plus the newest backtest,
        approval and paper run for that version. Additive to `list_strategies`;
        every field is a real stored row, and a missing one is `None` (never a
        green badge).
        """
        items = self.list_strategies(include_archived=include_archived)
        if not include_evidence:
            return items
        for item in items:
            strategy_id = item["id"]
            version = item.get("latestVersion") or ""
            backtest = self._db.execute(
                "SELECT id, status, createdAt FROM QuantExperiment "
                "WHERE strategyId=? AND strategyVersion=? AND kind='backtest' "
                "ORDER BY createdAt DESC LIMIT 1",
                (strategy_id, version),
            ).fetchone()
            approval = self._db.execute(
                "SELECT id, status, version, createdAt FROM QuantStrategyApproval "
                "WHERE strategyId=? AND version=? ORDER BY createdAt DESC LIMIT 1",
                (strategy_id, version),
            ).fetchone()
            paper = self._db.execute(
                "SELECT id, status, createdAt FROM QuantPaperRun "
                "WHERE strategyId=? ORDER BY createdAt DESC LIMIT 1",
                (strategy_id,),
            ).fetchone()
            item["latestBacktest"] = (
                {"id": backtest["id"], "status": backtest["status"],
                 "createdAt": backtest["createdAt"]} if backtest else None
            )
            item["approval"] = (
                {"id": approval["id"], "status": approval["status"],
                 "version": approval["version"], "createdAt": approval["createdAt"]}
                if approval else None
            )
            item["lastPaperRun"] = (
                {"id": paper["id"], "status": paper["status"],
                 "createdAt": paper["createdAt"]} if paper else None
            )
        return items

    def list_versions(self, strategy_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT version, contentHash, schemaVersion, createdAt FROM QuantStrategyVersion "
            "WHERE strategyId=? ORDER BY createdAt ASC", (strategy_id,),
        ).fetchall()
        return [
            {
                "version": r["version"],
                "contentHash": r["contentHash"],
                "schemaVersion": r["schemaVersion"] or STRATEGY_SCHEMA_VERSION,
                "createdAt": r["createdAt"],
            }
            for r in rows
        ]

    def version_meta(self, strategy_id: str, version: str) -> dict:
        """Content hash + schema version + experiment-reference count for a version."""
        row = self._db.execute(
            "SELECT specJson, contentHash, schemaVersion, createdAt FROM QuantStrategyVersion "
            "WHERE strategyId=? AND version=?", (strategy_id, version),
        ).fetchone()
        if row is None:
            raise StrategyVersionNotFound(
                f"strategy {strategy_id!r} version {version!r} not found",
                detail={"strategyId": strategy_id, "version": version},
            )
        content_hash = row["contentHash"] or spec_content_hash(json.loads(row["specJson"]))
        refs = self._db.execute(
            "SELECT COUNT(*) AS n FROM QuantExperiment WHERE strategyId=? AND strategyVersion=?",
            (strategy_id, version),
        ).fetchone()
        return {
            "strategyId": strategy_id,
            "version": version,
            "contentHash": content_hash,
            "schemaVersion": row["schemaVersion"] or STRATEGY_SCHEMA_VERSION,
            "createdAt": row["createdAt"],
            "experimentCount": int(refs["n"]) if refs else 0,
            "immutable": bool(refs and refs["n"] > 0),
        }

    def diff_versions(self, strategy_id: str, a: str, b: str) -> dict:
        """A structural diff between two stored versions of one strategy."""
        sa = self.get_strategy(strategy_id, a)
        sb = self.get_strategy(strategy_id, b)
        changes: list[dict] = []
        _dict_diff(sa["spec"], sb["spec"], "", changes)
        by_section: dict[str, int] = {}
        for change in changes:
            section = change["path"].split(".")[0].split("[")[0] or "(root)"
            by_section[section] = by_section.get(section, 0) + 1
        return {
            "strategyId": strategy_id,
            "a": a,
            "b": b,
            "sameContent": sa.get("contentHash") == sb.get("contentHash"),
            "hashA": sa.get("contentHash"),
            "hashB": sb.get("contentHash"),
            "changeCount": len(changes),
            "bySection": by_section,
            "changes": changes,
        }

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

    # ── Approvals & deployments (governance; NO live order routing) ──────────
    def request_approval(self, strategy_id: str, version: str, *, actor: Optional[str] = None,
                         note: Optional[str] = None) -> dict:
        self.get_strategy(strategy_id, version)  # 404 if missing
        appr_id = f"appr_{uuid.uuid4().hex[:16]}"
        now = _iso_now()
        self._db.execute(
            "INSERT INTO QuantStrategyApproval "
            "(id,strategyId,version,status,actor,note,createdAt,decidedAt) "
            "VALUES (?,?,?,'requested',?,?,?,NULL)",
            (appr_id, strategy_id, version, actor, note, now))
        self._db.commit()
        return self._approval_row(self._db.execute(
            "SELECT * FROM QuantStrategyApproval WHERE id=?", (appr_id,)).fetchone())

    @staticmethod
    def _approval_row(row) -> dict:
        return {
            "id": row["id"], "strategyId": row["strategyId"], "version": row["version"],
            "status": row["status"], "actor": row["actor"], "note": row["note"],
            "createdAt": row["createdAt"], "decidedAt": row["decidedAt"],
        }

    def decide_approval(self, approval_id: str, *, approve: bool,
                        actor: Optional[str] = None, note: Optional[str] = None) -> dict:
        row = self._db.execute("SELECT * FROM QuantStrategyApproval WHERE id=?",
                               (approval_id,)).fetchone()
        if row is None:
            raise StrategyNotFound(f"approval {approval_id!r} not found",
                                   detail={"approvalId": approval_id})
        self._db.execute(
            "UPDATE QuantStrategyApproval SET status=?, actor=COALESCE(?,actor), "
            "note=COALESCE(?,note), decidedAt=? WHERE id=?",
            ("approved" if approve else "rejected", actor, note, _iso_now(), approval_id))
        self._db.commit()
        return self._approval_row(self._db.execute(
            "SELECT * FROM QuantStrategyApproval WHERE id=?", (approval_id,)).fetchone())

    def list_approvals(self, strategy_id: Optional[str] = None) -> list[dict]:
        if strategy_id:
            rows = self._db.execute(
                "SELECT * FROM QuantStrategyApproval WHERE strategyId=? ORDER BY createdAt DESC",
                (strategy_id,)).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM QuantStrategyApproval ORDER BY createdAt DESC").fetchall()
        return [self._approval_row(r) for r in rows]

    def is_approved(self, strategy_id: str, version: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM QuantStrategyApproval WHERE strategyId=? AND version=? AND "
            "status='approved' LIMIT 1", (strategy_id, version)).fetchone()
        return row is not None

    def create_deployment(self, strategy_id: str, version: str, *, mode: str = "paper",
                          note: Optional[str] = None, require_approval: bool = True) -> dict:
        """Record a deployment. `paper` is a record only; `live` is refused."""
        if mode not in ("paper", "live"):
            raise QuantError(f"unknown deployment mode {mode!r}",
                             detail={"mode": mode})
        if mode == "live":
            raise LiveTradingDisabled(
                "live trading is not available; Eclipse never auto-enables live order routing",
                detail={"strategyId": strategy_id, "version": version})
        self.get_strategy(strategy_id, version)
        if require_approval and not self.is_approved(strategy_id, version):
            raise ApprovalRequired(
                "this strategy version has no approved approval record",
                detail={"strategyId": strategy_id, "version": version})
        dep_id = f"dep_{uuid.uuid4().hex[:16]}"
        now = _iso_now()
        self._db.execute(
            "INSERT INTO QuantStrategyDeployment "
            "(id,strategyId,version,mode,status,note,createdAt,updatedAt) "
            "VALUES (?,?,?,?,'active',?,?,?)",
            (dep_id, strategy_id, version, mode, note, now, now))
        self._db.commit()
        return self._deployment_row(self._db.execute(
            "SELECT * FROM QuantStrategyDeployment WHERE id=?", (dep_id,)).fetchone())

    @staticmethod
    def _deployment_row(row) -> dict:
        return {
            "id": row["id"], "strategyId": row["strategyId"], "version": row["version"],
            "mode": row["mode"], "status": row["status"], "note": row["note"],
            "createdAt": row["createdAt"], "updatedAt": row["updatedAt"],
            "liveExecution": False,
        }

    def list_deployments(self, strategy_id: Optional[str] = None) -> list[dict]:
        if strategy_id:
            rows = self._db.execute(
                "SELECT * FROM QuantStrategyDeployment WHERE strategyId=? ORDER BY createdAt DESC",
                (strategy_id,)).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM QuantStrategyDeployment ORDER BY createdAt DESC").fetchall()
        return [self._deployment_row(r) for r in rows]

    def stop_deployment(self, deployment_id: str) -> dict:
        row = self._db.execute("SELECT * FROM QuantStrategyDeployment WHERE id=?",
                               (deployment_id,)).fetchone()
        if row is None:
            raise QuantError(f"deployment {deployment_id!r} not found",
                             detail={"deploymentId": deployment_id})
        self._db.execute(
            "UPDATE QuantStrategyDeployment SET status='stopped', updatedAt=? WHERE id=?",
            (_iso_now(), deployment_id))
        self._db.commit()
        return self._deployment_row(self._db.execute(
            "SELECT * FROM QuantStrategyDeployment WHERE id=?", (deployment_id,)).fetchone())

    def get_deployment(self, deployment_id: str) -> dict:
        row = self._db.execute("SELECT * FROM QuantStrategyDeployment WHERE id=?",
                               (deployment_id,)).fetchone()
        if row is None:
            raise QuantError(f"deployment {deployment_id!r} not found",
                             detail={"deploymentId": deployment_id})
        return self._deployment_row(row)

    # ── Paper shadow runs (records of a real backtest; NO orders) ─────────────
    def save_paper_run(self, result: Any, *, deployment_id: str, strategy_id: str,
                       version: str) -> dict:
        exp_id = self.save_experiment(result, strategy_id=strategy_id,
                                      strategy_version=version, kind="paper")
        run_id = f"paper_{uuid.uuid4().hex[:16]}"
        now = _iso_now()
        self._db.execute(
            "INSERT INTO QuantPaperRun "
            "(id,deploymentId,strategyId,version,experimentId,status,symbolsJson,"
            "metricsJson,createdAt) VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, deployment_id, strategy_id, version, exp_id, result.status,
             json.dumps(result.metadata.get("symbols", [])),
             json.dumps(result.metrics), now))
        self._db.commit()
        return self._paper_row(self._db.execute(
            "SELECT * FROM QuantPaperRun WHERE id=?", (run_id,)).fetchone())

    @staticmethod
    def _paper_row(row) -> dict:
        return {
            "id": row["id"], "deploymentId": row["deploymentId"],
            "strategyId": row["strategyId"], "version": row["version"],
            "experimentId": row["experimentId"], "status": row["status"],
            "symbols": json.loads(row["symbolsJson"] or "[]"),
            "metrics": json.loads(row["metricsJson"] or "{}"),
            "createdAt": row["createdAt"], "liveExecution": False,
        }

    def list_paper_runs(self, *, deployment_id: Optional[str] = None,
                        strategy_id: Optional[str] = None) -> list[dict]:
        if deployment_id:
            rows = self._db.execute(
                "SELECT * FROM QuantPaperRun WHERE deploymentId=? ORDER BY createdAt DESC",
                (deployment_id,)).fetchall()
        elif strategy_id:
            rows = self._db.execute(
                "SELECT * FROM QuantPaperRun WHERE strategyId=? ORDER BY createdAt DESC",
                (strategy_id,)).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM QuantPaperRun ORDER BY createdAt DESC").fetchall()
        return [self._paper_row(r) for r in rows]

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
        manifest = getattr(result, "manifest", None)
        if manifest:
            try:
                self.save_run_manifest(exp_id, manifest)
            except Exception:  # noqa: BLE001 - a manifest must not lose the result
                pass
        assert cmd is not None
        return exp_id

    # ── Run manifests ────────────────────────────────────────────────────────
    def save_run_manifest(self, experiment_id: str, manifest: dict) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO QuantRunManifest "
            "(experimentId,manifestJson,digest,createdAt) VALUES (?,?,?,?)",
            (experiment_id, json.dumps(manifest, sort_keys=True),
             manifest.get("digest"), _iso_now()),
        )
        self._db.commit()

    def get_run_manifest(self, experiment_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM QuantRunManifest WHERE experimentId=?", (experiment_id,)
        ).fetchone()
        if row is None:
            # Fall back to the artifact's embedded manifest before giving up.
            try:
                artifact = self.read_artifact(experiment_id)
                manifest = artifact.get("manifest")
                if manifest:
                    return manifest
            except Exception:  # noqa: BLE001
                pass
            raise ExperimentNotFound(
                f"no run manifest is stored for experiment {experiment_id!r}",
                detail={"experimentId": experiment_id},
            )
        return json.loads(row["manifestJson"] or "{}")

    # ── Research sessions, hypotheses and trials ─────────────────────────────
    def create_research_session(self, *, title: str, question: Optional[str] = None,
                                strategy_id: Optional[str] = None) -> dict:
        now = _iso_now()
        session_id = f"ses_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO QuantResearchSession "
            "(id,title,question,strategyId,status,createdAt,updatedAt) "
            "VALUES (?,?,?,?,?,?,?)",
            (session_id, title, question, strategy_id, "open", now, now),
        )
        self._db.commit()
        return self.get_research_session(session_id)

    def list_research_sessions(self, *, limit: int = 50,
                               status: Optional[str] = None) -> list[dict]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM QuantResearchSession WHERE status=? "
                "ORDER BY updatedAt DESC LIMIT ?", (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM QuantResearchSession ORDER BY updatedAt DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._session_row(r) for r in rows]

    @staticmethod
    def _session_row(row) -> dict:
        return {
            "id": row["id"], "title": row["title"], "question": row["question"],
            "strategyId": row["strategyId"], "status": row["status"],
            "createdAt": row["createdAt"], "updatedAt": row["updatedAt"],
        }

    def get_research_session(self, session_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM QuantResearchSession WHERE id=?", (session_id,)
        ).fetchone()
        if row is None:
            raise ExperimentNotFound(
                f"research session {session_id!r} not found",
                detail={"sessionId": session_id},
            )
        data = self._session_row(row)
        data["hypotheses"] = self.list_hypotheses(session_id)
        data["trials"] = self.list_trials(session_id)
        data["trialCount"] = len(data["trials"])
        return data

    def pre_register_hypothesis(self, session_id: str, *, statement: str,
                                universe: Optional[list[str]] = None,
                                period: Optional[dict] = None,
                                metric: Optional[str] = None,
                                acceptance: Optional[str] = None) -> dict:
        self.get_research_session(session_id)
        now = _iso_now()
        hyp_id = f"hyp_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO QuantHypothesis "
            "(id,sessionId,statement,universeJson,periodJson,metric,acceptance,status,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (hyp_id, session_id, statement, json.dumps(universe or []),
             json.dumps(period or {}), metric, acceptance, "registered", now),
        )
        self._touch_session(session_id, now)
        self._db.commit()
        return self.get_hypothesis(hyp_id)

    def get_hypothesis(self, hypothesis_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM QuantHypothesis WHERE id=?", (hypothesis_id,)
        ).fetchone()
        if row is None:
            raise ExperimentNotFound(f"hypothesis {hypothesis_id!r} not found")
        return self._hypothesis_row(row)

    @staticmethod
    def _hypothesis_row(row) -> dict:
        return {
            "id": row["id"], "sessionId": row["sessionId"],
            "statement": row["statement"], "universe": json.loads(row["universeJson"] or "[]"),
            "period": json.loads(row["periodJson"] or "{}"), "metric": row["metric"],
            "acceptance": row["acceptance"], "status": row["status"],
            "createdAt": row["createdAt"],
            "trials": [],
        }

    def list_hypotheses(self, session_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM QuantHypothesis WHERE sessionId=? ORDER BY createdAt",
            (session_id,),
        ).fetchall()
        hypotheses = [self._hypothesis_row(r) for r in rows]
        by_id = {h["id"]: h for h in hypotheses}
        for trial in self.list_trials(session_id):
            hyp = by_id.get(trial.get("hypothesisId"))
            if hyp is not None:
                hyp["trials"].append(trial)
        return hypotheses

    def record_trial(self, session_id: str, *, kind: str,
                     hypothesis_id: Optional[str] = None,
                     experiment_id: Optional[str] = None,
                     parameters: Optional[dict] = None,
                     metrics: Optional[dict] = None) -> dict:
        self.get_research_session(session_id)
        now = _iso_now()
        trial_id = f"trl_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO QuantTrial "
            "(id,sessionId,hypothesisId,experimentId,kind,parametersJson,metricsJson,createdAt) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (trial_id, session_id, hypothesis_id, experiment_id, kind,
             json.dumps(parameters or {}), json.dumps(metrics or {}), now),
        )
        if hypothesis_id:
            self._db.execute(
                "UPDATE QuantHypothesis SET status='tested' WHERE id=? AND status='registered'",
                (hypothesis_id,),
            )
        self._touch_session(session_id, now)
        self._db.commit()
        return self.get_trial(trial_id)

    def get_trial(self, trial_id: str) -> dict:
        row = self._db.execute("SELECT * FROM QuantTrial WHERE id=?", (trial_id,)).fetchone()
        if row is None:
            raise ExperimentNotFound(f"trial {trial_id!r} not found")
        return self._trial_row(row)

    @staticmethod
    def _trial_row(row) -> dict:
        return {
            "id": row["id"], "sessionId": row["sessionId"],
            "hypothesisId": row["hypothesisId"], "experimentId": row["experimentId"],
            "kind": row["kind"], "parameters": json.loads(row["parametersJson"] or "{}"),
            "metrics": json.loads(row["metricsJson"] or "{}"), "createdAt": row["createdAt"],
        }

    def list_trials(self, session_id: str, *,
                    hypothesis_id: Optional[str] = None) -> list[dict]:
        if hypothesis_id:
            rows = self._db.execute(
                "SELECT * FROM QuantTrial WHERE sessionId=? AND hypothesisId=? "
                "ORDER BY createdAt", (session_id, hypothesis_id),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM QuantTrial WHERE sessionId=? ORDER BY createdAt",
                (session_id,),
            ).fetchall()
        return [self._trial_row(r) for r in rows]

    def session_journal(self, session_id: str) -> dict:
        """A structured journal: what was asked, registered, tested and rejected."""
        session = self.get_research_session(session_id)
        trials = session["trials"]
        hypotheses = session["hypotheses"]
        rejected = [h for h in hypotheses if h["status"] == "rejected"]
        return {
            "session": {k: session[k] for k in
                        ("id", "title", "question", "strategyId", "status",
                         "createdAt", "updatedAt")},
            "hypothesisCount": len(hypotheses),
            "trialCount": len(trials),
            "testedHypotheses": sum(1 for h in hypotheses if h["status"] == "tested"),
            "rejectedHypotheses": rejected,
            "hypotheses": hypotheses,
            "recentTrials": trials[-10:],
            "openQuestions": [h["statement"] for h in hypotheses
                              if h["status"] == "registered"],
        }

    def update_hypothesis_status(self, hypothesis_id: str, status: str) -> dict:
        if status not in ("registered", "tested", "supported", "rejected", "inconclusive"):
            raise QuantError(f"unknown hypothesis status {status!r}")
        self._db.execute("UPDATE QuantHypothesis SET status=? WHERE id=?",
                         (status, hypothesis_id))
        self._db.commit()
        return self.get_hypothesis(hypothesis_id)

    # ── Discovered methods ───────────────────────────────────────────────────
    def save_method(self, *, name: str, method_family: str,
                    spec: Optional[dict] = None, evidence: Optional[dict] = None,
                    status: str = "discovered",
                    strategy_id: Optional[str] = None) -> dict:
        if status not in ("discovered", "validated", "promoted", "rejected"):
            raise QuantError(f"unknown method status {status!r}")
        now = _iso_now()
        method_id = f"mth_{uuid.uuid4().hex[:16]}"
        self._db.execute(
            "INSERT INTO QuantMethod "
            "(id,name,methodFamily,status,specJson,evidenceJson,strategyId,createdAt,updatedAt) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (method_id, name, method_family, status,
             json.dumps(spec or {}), json.dumps(evidence or {}), strategy_id, now, now),
        )
        self._db.commit()
        return self.get_method(method_id)

    @staticmethod
    def _method_row(row) -> dict:
        spec = json.loads(row["specJson"] or "{}")
        if not isinstance(spec, dict):
            spec = {}
        # The research layer extends the SAME table with formal-spec columns.
        # Read them when present so old rows and new rows share one reader.
        keys = set(row.keys())
        for column, target in (
            ("version", "version"), ("aliasesJson", "aliases"),
            ("objectiveJson", "objective"), ("mathSpecJson", "mathSpec"),
            ("inputsJson", "inputs"), ("parametersJson", "parameters"),
            ("assumptionsJson", "assumptions"), ("limitationsJson", "limitations"),
            ("provenanceJson", "provenance"), ("implementationStatus", "implementationStatus"),
            ("reproductionStatus", "reproductionStatus"),
            ("lifecycleStatus", "lifecycleStatus"), ("confidence", "confidence"),
            ("contentHash", "contentHash"),
        ):
            if column not in keys or row[column] in (None, ""):
                continue
            value = row[column]
            if column.endswith("Json"):
                try:
                    value = json.loads(value)
                except (TypeError, ValueError):
                    value = None
            if value is not None:
                spec[target] = value
        return {
            "id": row["id"], "name": row["name"], "methodFamily": row["methodFamily"],
            "status": row["status"], "spec": spec,
            "evidence": json.loads(row["evidenceJson"] or "{}"),
            "strategyId": row["strategyId"], "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
        }

    def get_method(self, method_id: str) -> dict:
        row = self._db.execute("SELECT * FROM QuantMethod WHERE id=?", (method_id,)).fetchone()
        if row is None:
            raise ExperimentNotFound(f"method {method_id!r} not found",
                                     detail={"methodId": method_id})
        return self._method_row(row)

    def list_methods(self, *, status: Optional[str] = None,
                     limit: int = 50) -> list[dict]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM QuantMethod WHERE status=? ORDER BY updatedAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM QuantMethod ORDER BY updatedAt DESC LIMIT ?", (limit,),
            ).fetchall()
        return [self._method_row(r) for r in rows]

    def promote_method(self, method_id: str, status: str,
                       *, strategy_id: Optional[str] = None) -> dict:
        if status not in ("discovered", "validated", "promoted", "rejected"):
            raise QuantError(f"unknown method status {status!r}")
        self.get_method(method_id)
        self._db.execute(
            "UPDATE QuantMethod SET status=?, strategyId=COALESCE(?,strategyId), "
            "updatedAt=? WHERE id=?",
            (status, strategy_id, _iso_now(), method_id),
        )
        self._db.commit()
        return self.get_method(method_id)

    def _touch_session(self, session_id: str, now: str) -> None:
        self._db.execute(
            "UPDATE QuantResearchSession SET updatedAt=? WHERE id=?", (now, session_id)
        )

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

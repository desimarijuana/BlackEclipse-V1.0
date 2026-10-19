"""Persistence for the evaluation system.

All durable evaluation rows live in the shared ``agent-memory.db`` connection
(``AgentMemoryStore._db``) — the same store the rest of the runtime uses. Tables
are created idempotently with ``CREATE TABLE IF NOT EXISTS``; there is no separate
database and no migration runner, matching the runtime's convention.

Historical results are never rewritten: a score is scoped to
``(task_id, task_version, grader_api_version)`` so a task/grader change does not
silently invalidate or reinterpret an old result.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..persistence import new_id, now_iso
from .config import GRADER_API_VERSION

_SCHEMA = """
CREATE TABLE IF NOT EXISTS EvaluationDataset (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  version       TEXT NOT NULL,
  checksum      TEXT NOT NULL,
  taskCount     INTEGER NOT NULL DEFAULT 0,
  reviewed      INTEGER NOT NULL DEFAULT 0,
  metadata      TEXT NOT NULL DEFAULT '{}',
  createdAt     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_dataset_name ON EvaluationDataset(name, version);

CREATE TABLE IF NOT EXISTS EvaluationTask (
  id            TEXT NOT NULL,
  version       INTEGER NOT NULL,
  fingerprint   TEXT NOT NULL,
  category      TEXT NOT NULL,
  difficulty    TEXT NOT NULL,
  graderVersion INTEGER NOT NULL DEFAULT 1,
  definition    TEXT NOT NULL,
  createdAt     TEXT NOT NULL,
  PRIMARY KEY (id, version)
);
CREATE INDEX IF NOT EXISTS idx_eval_task_category ON EvaluationTask(category);

CREATE TABLE IF NOT EXISTS EvaluationRun (
  id             TEXT PRIMARY KEY,
  suite          TEXT NOT NULL DEFAULT '',
  datasetName    TEXT NOT NULL DEFAULT '',
  datasetVersion TEXT NOT NULL DEFAULT '',
  datasetChecksum TEXT NOT NULL DEFAULT '',
  tier           INTEGER NOT NULL DEFAULT 0,
  invoker        TEXT NOT NULL DEFAULT '',
  agentVersion   TEXT,
  gitCommit      TEXT,
  model          TEXT,
  provider       TEXT,
  config         TEXT NOT NULL DEFAULT '{}',
  status         TEXT NOT NULL DEFAULT 'created',
  trialCount     INTEGER NOT NULL DEFAULT 0,
  startedAt      TEXT NOT NULL,
  finishedAt     TEXT,
  metadata       TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_eval_run_status ON EvaluationRun(status);
CREATE INDEX IF NOT EXISTS idx_eval_run_started ON EvaluationRun(startedAt);

CREATE TABLE IF NOT EXISTS EvaluationTrial (
  id           TEXT PRIMARY KEY,
  runId        TEXT NOT NULL,
  taskId       TEXT NOT NULL,
  taskVersion  INTEGER NOT NULL DEFAULT 1,
  trialIndex   INTEGER NOT NULL DEFAULT 0,
  passed       INTEGER NOT NULL DEFAULT 0,
  unmeasured   INTEGER NOT NULL DEFAULT 0,
  status       TEXT NOT NULL DEFAULT '',
  score        TEXT NOT NULL DEFAULT '{}',
  trajectory   TEXT NOT NULL DEFAULT '{}',
  cost         REAL NOT NULL DEFAULT 0,
  latencyMs    REAL,
  totalTokens  INTEGER NOT NULL DEFAULT 0,
  createdAt    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_trial_run ON EvaluationTrial(runId);
CREATE INDEX IF NOT EXISTS idx_eval_trial_task ON EvaluationTrial(taskId, taskVersion);

CREATE TABLE IF NOT EXISTS EvaluationScore (
  id         TEXT PRIMARY KEY,
  runId      TEXT NOT NULL,
  trialId    TEXT NOT NULL,
  taskId     TEXT NOT NULL,
  taskVersion INTEGER NOT NULL DEFAULT 1,
  category   TEXT NOT NULL DEFAULT '',
  dimension  TEXT NOT NULL,
  value      REAL,
  createdAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_score_run ON EvaluationScore(runId, dimension);
CREATE INDEX IF NOT EXISTS idx_eval_score_task ON EvaluationScore(taskId, taskVersion);

CREATE TABLE IF NOT EXISTS EvaluationMetric (
  id         TEXT PRIMARY KEY,
  runId      TEXT NOT NULL,
  scope      TEXT NOT NULL DEFAULT 'overall',
  category   TEXT NOT NULL DEFAULT '',
  dimension  TEXT NOT NULL,
  value      REAL,
  sampleSize INTEGER NOT NULL DEFAULT 0,
  createdAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_metric_run ON EvaluationMetric(runId, dimension);

CREATE TABLE IF NOT EXISTS EvaluationEvent (
  id       TEXT PRIMARY KEY,
  runId    TEXT NOT NULL,
  trialId  TEXT NOT NULL DEFAULT '',
  type     TEXT NOT NULL,
  at       TEXT NOT NULL,
  data     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_eval_event_run ON EvaluationEvent(runId);

CREATE TABLE IF NOT EXISTS EvaluationBaseline (
  id             TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  runId          TEXT NOT NULL,
  datasetChecksum TEXT NOT NULL DEFAULT '',
  agentVersion   TEXT,
  gitCommit      TEXT,
  model          TEXT,
  provider       TEXT,
  graderVersion  INTEGER NOT NULL DEFAULT 1,
  config         TEXT NOT NULL DEFAULT '{}',
  metrics        TEXT NOT NULL DEFAULT '{}',
  createdAt      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_baseline_name ON EvaluationBaseline(name);

CREATE TABLE IF NOT EXISTS EvaluationRegression (
  id         TEXT PRIMARY KEY,
  baselineId TEXT NOT NULL,
  runId      TEXT NOT NULL,
  scope      TEXT NOT NULL DEFAULT 'overall',
  dimension  TEXT NOT NULL,
  baseline   REAL,
  current    REAL,
  delta      REAL,
  threshold  REAL NOT NULL DEFAULT 0,
  severity   TEXT NOT NULL DEFAULT 'regression',
  createdAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_regression_run ON EvaluationRegression(runId);

CREATE TABLE IF NOT EXISTS EvaluationFailure (
  id           TEXT PRIMARY KEY,
  runId        TEXT NOT NULL,
  trialId      TEXT NOT NULL DEFAULT '',
  taskId       TEXT NOT NULL,
  taskVersion  INTEGER NOT NULL DEFAULT 1,
  category     TEXT NOT NULL DEFAULT '',
  labels       TEXT NOT NULL DEFAULT '[]',
  detail       TEXT NOT NULL DEFAULT '{}',
  classifiedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_failure_run ON EvaluationFailure(runId);

CREATE TABLE IF NOT EXISTS EvaluationModel (
  id        TEXT PRIMARY KEY,
  runId     TEXT NOT NULL,
  model     TEXT NOT NULL,
  provider  TEXT NOT NULL DEFAULT '',
  metrics   TEXT NOT NULL DEFAULT '{}',
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_model_run ON EvaluationModel(runId, model);

CREATE TABLE IF NOT EXISTS EvaluationCandidate (
  id         TEXT PRIMARY KEY,
  signature  TEXT NOT NULL,
  source     TEXT NOT NULL DEFAULT 'production',
  category   TEXT NOT NULL DEFAULT '',
  labels     TEXT NOT NULL DEFAULT '[]',
  status     TEXT NOT NULL DEFAULT 'candidate',
  task       TEXT NOT NULL DEFAULT '{}',
  detail     TEXT NOT NULL DEFAULT '{}',
  createdAt  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_candidate_sig ON EvaluationCandidate(signature);
"""


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, default=str)


def _loads(raw: Any) -> Any:
    if raw in (None, ""):
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}


class EvaluationStore:
    """The one evaluation persistence surface, bound to ``agent-memory.db``."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._ensure_schema()

    @property
    def _db(self) -> Any:
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # -- datasets & tasks --------------------------------------------------
    def save_dataset(self, dataset: Any) -> str:
        did = f"ds_{dataset.name}_{dataset.version}"
        now = now_iso()
        self._db.execute(
            """INSERT INTO EvaluationDataset (id, name, version, checksum, taskCount, reviewed, metadata, createdAt)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET checksum=excluded.checksum, taskCount=excluded.taskCount,
                 reviewed=excluded.reviewed, metadata=excluded.metadata""",
            (did, dataset.name, dataset.version, dataset.checksum, len(dataset.tasks),
             1 if dataset.reviewed else 0, _dumps(dataset.metadata), now),
        )
        self._db.commit()
        return did

    def upsert_task(self, task: Any) -> None:
        self._db.execute(
            """INSERT INTO EvaluationTask (id, version, fingerprint, category, difficulty, graderVersion, definition, createdAt)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id, version) DO UPDATE SET fingerprint=excluded.fingerprint,
                 category=excluded.category, difficulty=excluded.difficulty,
                 graderVersion=excluded.graderVersion, definition=excluded.definition""",
            (task.id, task.version, task.fingerprint(), task.category, task.difficulty,
             GRADER_API_VERSION, _dumps(task.to_dict()), now_iso()),
        )
        self._db.commit()

    def list_tasks(self, *, category: Optional[str] = None) -> list[dict[str, Any]]:
        if category:
            rows = self._db.execute(
                "SELECT * FROM EvaluationTask WHERE category=? ORDER BY id", (category,)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM EvaluationTask ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    # -- runs --------------------------------------------------------------
    def create_run(self, **fields: Any) -> str:
        run_id = fields.get("id") or new_id("evalrun")
        self._db.execute(
            """INSERT INTO EvaluationRun
               (id, suite, datasetName, datasetVersion, datasetChecksum, tier, invoker,
                agentVersion, gitCommit, model, provider, config, status, trialCount, startedAt, metadata)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, fields.get("suite", ""), fields.get("datasetName", ""),
                fields.get("datasetVersion", ""), fields.get("datasetChecksum", ""),
                int(fields.get("tier", 0)), fields.get("invoker", ""),
                fields.get("agentVersion"), fields.get("gitCommit"),
                fields.get("model"), fields.get("provider"),
                _dumps(fields.get("config")), fields.get("status", "created"),
                int(fields.get("trialCount", 0)), fields.get("startedAt") or now_iso(),
                _dumps(fields.get("metadata")),
            ),
        )
        self._db.commit()
        return run_id

    def update_run(self, run_id: str, **patch: Any) -> None:
        if not patch:
            return
        assignments = ", ".join(f"{key}=?" for key in patch)
        values = [(_dumps(v) if isinstance(v, (dict, list)) else v) for v in patch.values()]
        self._db.execute(f"UPDATE EvaluationRun SET {assignments} WHERE id=?", (*values, run_id))
        self._db.commit()

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM EvaluationRun WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["config"] = _loads(result.get("config"))
        result["metadata"] = _loads(result.get("metadata"))
        return result

    def list_runs(self, *, limit: int = 50, status: Optional[str] = None) -> list[dict[str, Any]]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM EvaluationRun WHERE status=? ORDER BY startedAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM EvaluationRun ORDER BY startedAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -- trials & scores ---------------------------------------------------
    def add_trial(self, **fields: Any) -> str:
        trial_id = fields.get("id") or new_id("evaltrial")
        self._db.execute(
            """INSERT INTO EvaluationTrial
               (id, runId, taskId, taskVersion, trialIndex, passed, unmeasured, status,
                score, trajectory, cost, latencyMs, totalTokens, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET passed=excluded.passed, unmeasured=excluded.unmeasured,
                 status=excluded.status, score=excluded.score, trajectory=excluded.trajectory""",
            (
                trial_id, fields["runId"], fields["taskId"], int(fields.get("taskVersion", 1)),
                int(fields.get("trialIndex", 0)),
                1 if fields.get("passed") else 0, 1 if fields.get("unmeasured") else 0,
                fields.get("status", ""), _dumps(fields.get("score")),
                _dumps(fields.get("trajectory")),
                float(fields["cost"]) if fields.get("cost") is not None else 0.0,
                fields.get("latencyMs"), int(fields.get("totalTokens", 0)),
                fields.get("createdAt") or now_iso(),
            ),
        )
        self._db.commit()
        return trial_id

    def get_trial(self, trial_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM EvaluationTrial WHERE id=?", (trial_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["score"] = _loads(result.get("score"))
        result["trajectory"] = _loads(result.get("trajectory"))
        return result

    def list_trials(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM EvaluationTrial WHERE runId=? ORDER BY taskId, trialIndex", (run_id,)
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["score"] = _loads(item.get("score"))
            item["trajectory"] = _loads(item.get("trajectory"))
            out.append(item)
        return out

    def add_score(self, **fields: Any) -> None:
        self._db.execute(
            """INSERT INTO EvaluationScore
               (id, runId, trialId, taskId, taskVersion, category, dimension, value, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                new_id("evalscore"), fields["runId"], fields["trialId"], fields["taskId"],
                int(fields.get("taskVersion", 1)), fields.get("category", ""),
                fields["dimension"], fields.get("value"), now_iso(),
            ),
        )
        self._db.commit()

    def add_metric(self, **fields: Any) -> None:
        self._db.execute(
            """INSERT INTO EvaluationMetric
               (id, runId, scope, category, dimension, value, sampleSize, createdAt)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                new_id("evalmetric"), fields["runId"], fields.get("scope", "overall"),
                fields.get("category", ""), fields["dimension"], fields.get("value"),
                int(fields.get("sampleSize", 0)), now_iso(),
            ),
        )
        self._db.commit()

    def add_event(self, run_id: str, event_type: str, *, trial_id: str = "", data: Optional[dict] = None, at: Optional[str] = None) -> None:
        self._db.execute(
            "INSERT INTO EvaluationEvent (id, runId, trialId, type, at, data) VALUES (?,?,?,?,?,?)",
            (new_id("evalevent"), run_id, trial_id, event_type, at or now_iso(), _dumps(data)),
        )
        self._db.commit()

    # -- baselines & regressions ------------------------------------------
    def save_baseline(self, **fields: Any) -> str:
        bid = fields.get("id") or new_id("evalbase")
        self._db.execute(
            """INSERT INTO EvaluationBaseline
               (id, name, runId, datasetChecksum, agentVersion, gitCommit, model, provider,
                graderVersion, config, metrics, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                bid, fields["name"], fields["runId"], fields.get("datasetChecksum", ""),
                fields.get("agentVersion"), fields.get("gitCommit"), fields.get("model"),
                fields.get("provider"), int(fields.get("graderVersion", GRADER_API_VERSION)),
                _dumps(fields.get("config")), _dumps(fields.get("metrics")), now_iso(),
            ),
        )
        self._db.commit()
        return bid

    def get_baseline(self, name: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM EvaluationBaseline WHERE name=? ORDER BY createdAt DESC LIMIT 1", (name,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["config"] = _loads(result.get("config"))
        result["metrics"] = _loads(result.get("metrics"))
        return result

    def list_baselines(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM EvaluationBaseline ORDER BY createdAt DESC LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["metrics"] = _loads(item.get("metrics"))
            out.append(item)
        return out

    def record_regression(self, **fields: Any) -> str:
        rid = new_id("evalreg")
        self._db.execute(
            """INSERT INTO EvaluationRegression
               (id, baselineId, runId, scope, dimension, baseline, current, delta, threshold, severity, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rid, fields["baselineId"], fields["runId"], fields.get("scope", "overall"),
                fields["dimension"], fields.get("baseline"), fields.get("current"),
                fields.get("delta"), float(fields.get("threshold", 0.0)),
                fields.get("severity", "regression"), now_iso(),
            ),
        )
        self._db.commit()
        return rid

    def list_regressions(self, *, run_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if run_id:
            rows = self._db.execute(
                "SELECT * FROM EvaluationRegression WHERE runId=? ORDER BY createdAt DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM EvaluationRegression ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -- failures ----------------------------------------------------------
    def record_failure(self, **fields: Any) -> str:
        fid = new_id("evalfail")
        self._db.execute(
            """INSERT INTO EvaluationFailure
               (id, runId, trialId, taskId, taskVersion, category, labels, detail, classifiedAt)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                fid, fields["runId"], fields.get("trialId", ""), fields["taskId"],
                int(fields.get("taskVersion", 1)), fields.get("category", ""),
                _dumps(fields.get("labels", [])), _dumps(fields.get("detail")), now_iso(),
            ),
        )
        self._db.commit()
        return fid

    def list_failures(self, *, run_id: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        if run_id:
            rows = self._db.execute(
                "SELECT * FROM EvaluationFailure WHERE runId=? ORDER BY classifiedAt DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM EvaluationFailure ORDER BY classifiedAt DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["labels"] = _loads(item.get("labels"))
            item["detail"] = _loads(item.get("detail"))
            out.append(item)
        return out

    # -- model matrix ------------------------------------------------------
    def save_model_result(self, **fields: Any) -> str:
        mid = new_id("evalmodel")
        self._db.execute(
            """INSERT INTO EvaluationModel (id, runId, model, provider, metrics, createdAt)
               VALUES (?,?,?,?,?,?)""",
            (mid, fields["runId"], fields["model"], fields.get("provider", ""),
             _dumps(fields.get("metrics")), now_iso()),
        )
        self._db.commit()
        return mid

    def list_model_results(self, *, run_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if run_id:
            rows = self._db.execute(
                "SELECT * FROM EvaluationModel WHERE runId=? ORDER BY createdAt DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM EvaluationModel ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["metrics"] = _loads(item.get("metrics"))
            out.append(item)
        return out

    # -- mining candidates -------------------------------------------------
    def save_candidate(self, **fields: Any) -> str:
        cid = fields.get("id") or new_id("evalcand")
        self._db.execute(
            """INSERT INTO EvaluationCandidate
               (id, signature, source, category, labels, status, task, detail, createdAt)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET signature=excluded.signature,
                 source=excluded.source, category=excluded.category, labels=excluded.labels,
                 status=excluded.status, task=excluded.task, detail=excluded.detail""",
            (
                cid, fields["signature"], fields.get("source", "production"),
                fields.get("category", ""), _dumps(fields.get("labels", [])),
                fields.get("status", "candidate"), _dumps(fields.get("task")),
                _dumps(fields.get("detail")), now_iso(),
            ),
        )
        self._db.commit()
        return cid

    def candidate_exists(self, signature: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM EvaluationCandidate WHERE signature=? LIMIT 1", (signature,)
        ).fetchone()
        return row is not None

    def list_candidates(self, *, status: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM EvaluationCandidate WHERE status=? ORDER BY createdAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM EvaluationCandidate ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["labels"] = _loads(item.get("labels"))
            item["task"] = _loads(item.get("task"))
            item["detail"] = _loads(item.get("detail"))
            out.append(item)
        return out

    def update_candidate_status(self, candidate_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE EvaluationCandidate SET status=? WHERE id=?", (status, candidate_id)
        )
        self._db.commit()


__all__ = ["EvaluationStore"]

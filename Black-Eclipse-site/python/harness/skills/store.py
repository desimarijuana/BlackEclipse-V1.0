"""Skill store — Phase-3 persistence in `agent-memory.db`.

One source of truth for skill lifecycle state: versions, dependencies, tool and
permission requirements, executions, evaluations, learning candidates and the
review/promotion audit trail. This is deliberately separate from the legacy
`AgentSkill` table in `persistence.py` (a name-keyed, unversioned blob), which
cannot express versions, permissions or dependencies. The legacy methods stay
for backward compatibility; the skill system never reads or writes them.

DDL is idempotent (`CREATE TABLE IF NOT EXISTS`), matching the existing
`persistence.py` convention — there is no manual migration step. Immutable rows:
a `SkillVersion` is never updated (a new version is inserted); a `SkillExecution`
is only ever moved to a terminal status once.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from ..persistence import default_db_path, new_id, now_iso

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Skill identity (stable across versions).
CREATE TABLE IF NOT EXISTS Skill (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  description   TEXT NOT NULL,
  category      TEXT NOT NULL,
  latestVersion TEXT NOT NULL,
  status        TEXT NOT NULL,
  tags          TEXT NOT NULL DEFAULT '[]',
  createdAt     TEXT NOT NULL,
  updatedAt     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skill_status   ON Skill(status);
CREATE INDEX IF NOT EXISTS idx_skill_category ON Skill(category);

-- One immutable manifest revision.
CREATE TABLE IF NOT EXISTS SkillVersion (
  id                   TEXT PRIMARY KEY,
  skillId              TEXT NOT NULL,
  version              TEXT NOT NULL,
  manifest             TEXT NOT NULL,
  contentHash          TEXT NOT NULL,
  status               TEXT NOT NULL,
  evaluationStatus     TEXT NOT NULL DEFAULT 'not_evaluated',
  riskLevel            TEXT NOT NULL DEFAULT 'low',
  instructionsLocation TEXT,
  author               TEXT,
  origin               TEXT NOT NULL DEFAULT 'builtin',
  sourceRunId          TEXT,
  createdAt            TEXT NOT NULL,
  updatedAt            TEXT NOT NULL,
  UNIQUE(skillId, version),
  FOREIGN KEY (skillId) REFERENCES Skill(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_skillver_skill  ON SkillVersion(skillId);
CREATE INDEX IF NOT EXISTS idx_skillver_status ON SkillVersion(status);

CREATE TABLE IF NOT EXISTS SkillDependency (
  id          TEXT PRIMARY KEY,
  skillId     TEXT NOT NULL,
  version     TEXT NOT NULL,
  dependsOn   TEXT NOT NULL,
  constraint_ TEXT,
  optional    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_skilldep_skill ON SkillDependency(skillId, version);

CREATE TABLE IF NOT EXISTS SkillToolRequirement (
  id       TEXT PRIMARY KEY,
  skillId  TEXT NOT NULL,
  version  TEXT NOT NULL,
  toolName TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skilltool_skill ON SkillToolRequirement(skillId, version);

CREATE TABLE IF NOT EXISTS SkillPermissionRequirement (
  id         TEXT PRIMARY KEY,
  skillId    TEXT NOT NULL,
  version    TEXT NOT NULL,
  permission TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skillperm_skill ON SkillPermissionRequirement(skillId, version);

-- One immutable skill execution record.
CREATE TABLE IF NOT EXISTS SkillExecution (
  id              TEXT PRIMARY KEY,
  runId           TEXT NOT NULL,
  skillId         TEXT NOT NULL,
  version         TEXT NOT NULL,
  manifestHash    TEXT,
  parentRunId     TEXT,
  executionMode   TEXT NOT NULL DEFAULT 'interactive',
  status          TEXT NOT NULL,
  actor           TEXT,
  input           TEXT,
  output          TEXT,
  error           TEXT,
  warnings        TEXT,
  missingData     TEXT,
  limitations     TEXT,
  evidence        TEXT,
  durationMs      INTEGER NOT NULL DEFAULT 0,
  traceId         TEXT,
  createdAt       TEXT NOT NULL,
  finishedAt      TEXT
);
CREATE INDEX IF NOT EXISTS idx_skillexec_skill  ON SkillExecution(skillId, version);
CREATE INDEX IF NOT EXISTS idx_skillexec_run    ON SkillExecution(runId);
CREATE INDEX IF NOT EXISTS idx_skillexec_parent ON SkillExecution(parentRunId);
CREATE INDEX IF NOT EXISTS idx_skillexec_status ON SkillExecution(status);

CREATE TABLE IF NOT EXISTS SkillEvaluation (
  id            TEXT PRIMARY KEY,
  skillId       TEXT NOT NULL,
  version       TEXT NOT NULL,
  status        TEXT NOT NULL,
  evaluator     TEXT NOT NULL DEFAULT 'deterministic-v1',
  dimensions    TEXT NOT NULL,
  summary       TEXT,
  createdAt     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skileval_skill ON SkillEvaluation(skillId, version);

CREATE TABLE IF NOT EXISTS SkillEvaluationCase (
  id            TEXT PRIMARY KEY,
  evaluationId  TEXT,
  skillId       TEXT NOT NULL,
  version       TEXT NOT NULL,
  caseId        TEXT NOT NULL,
  name          TEXT NOT NULL,
  kind          TEXT NOT NULL,
  input         TEXT,
  expected      TEXT,
  createdAt     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skilevalcase_skill ON SkillEvaluationCase(skillId, version);

-- A captured lesson. Never auto-published.
CREATE TABLE IF NOT EXISTS LearningCandidate (
  id                 TEXT PRIMARY KEY,
  sourceRunId        TEXT,
  candidateType      TEXT NOT NULL,
  title              TEXT NOT NULL,
  problem            TEXT,
  observedBehavior   TEXT,
  proposedLesson     TEXT,
  proposedProcedure  TEXT,
  evidenceReferences TEXT NOT NULL DEFAULT '[]',
  confidence         REAL NOT NULL DEFAULT 0.5,
  generalizationNotes TEXT,
  knownLimitations   TEXT,
  signature          TEXT NOT NULL,
  status             TEXT NOT NULL DEFAULT 'new',
  createdAt          TEXT NOT NULL,
  reviewedAt         TEXT,
  resultingSkillId   TEXT,
  resultingSkillVersion TEXT,
  draftManifest      TEXT
);
CREATE INDEX IF NOT EXISTS idx_learning_status    ON LearningCandidate(status);
CREATE INDEX IF NOT EXISTS idx_learning_signature ON LearningCandidate(signature);
CREATE INDEX IF NOT EXISTS idx_learning_run       ON LearningCandidate(sourceRunId);

CREATE TABLE IF NOT EXISTS SkillPromotionRequest (
  id          TEXT PRIMARY KEY,
  skillId     TEXT NOT NULL,
  version     TEXT NOT NULL,
  requestedBy TEXT,
  status      TEXT NOT NULL DEFAULT 'pending',
  reason      TEXT,
  evaluationId TEXT,
  createdAt   TEXT NOT NULL,
  decidedAt   TEXT
);
CREATE INDEX IF NOT EXISTS idx_promotion_skill ON SkillPromotionRequest(skillId, version);

CREATE TABLE IF NOT EXISTS SkillReview (
  id        TEXT PRIMARY KEY,
  skillId   TEXT NOT NULL,
  version   TEXT NOT NULL,
  actor     TEXT,
  decision  TEXT NOT NULL,
  notes     TEXT,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_skill ON SkillReview(skillId, version);

CREATE TABLE IF NOT EXISTS SkillEvent (
  id        TEXT PRIMARY KEY,
  skillId   TEXT,
  version   TEXT,
  runId     TEXT,
  type      TEXT NOT NULL,
  at        TEXT NOT NULL,
  data      TEXT
);
CREATE INDEX IF NOT EXISTS idx_skillevent_skill ON SkillEvent(skillId);
CREATE INDEX IF NOT EXISTS idx_skillevent_run   ON SkillEvent(runId);
"""


class SkillStore:
    """SQLite-backed skill persistence. Owns its own connection to the same
    file the harness uses, so skill state and run traces share one database."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or default_db_path()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._db.commit()

    # ── Skills / versions ───────────────────────────────────────────────────

    def upsert_skill(
        self,
        *,
        skill_id: str,
        name: str,
        description: str,
        category: str,
        latest_version: str,
        status: str,
        tags: list[str],
    ) -> None:
        now = now_iso()
        existing = self._db.execute("SELECT id FROM Skill WHERE id = ?", (skill_id,)).fetchone()
        if existing:
            self._db.execute(
                """UPDATE Skill SET name=?, description=?, category=?, latestVersion=?,
                   status=?, tags=?, updatedAt=? WHERE id=?""",
                (name, description, category, latest_version, status, json.dumps(tags), now, skill_id),
            )
        else:
            self._db.execute(
                """INSERT INTO Skill (id, name, description, category, latestVersion, status, tags, createdAt, updatedAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (skill_id, name, description, category, latest_version, status, json.dumps(tags), now, now),
            )
        self._db.commit()

    def save_version(self, manifest: dict[str, Any], content_hash: str) -> None:
        """Insert a version if absent. An existing (skillId, version) row is an
        error — versions are immutable; a change must bump the version."""
        skill_id = manifest["id"]
        version = manifest["version"]
        existing = self._db.execute(
            "SELECT id FROM SkillVersion WHERE skillId=? AND version=?", (skill_id, version)
        ).fetchone()
        if existing:
            raise ValueError(
                f"skill {skill_id!r} version {version!r} already exists; versions are immutable"
            )
        now = now_iso()
        vid = new_id("skillver")
        self._db.execute(
            """INSERT INTO SkillVersion
               (id, skillId, version, manifest, contentHash, status, evaluationStatus, riskLevel,
                instructionsLocation, author, origin, sourceRunId, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                vid,
                skill_id,
                version,
                json.dumps(manifest),
                content_hash,
                manifest.get("status", "draft"),
                manifest.get("evaluationStatus", "not_evaluated"),
                manifest.get("riskLevel", "low"),
                manifest.get("instructions"),
                manifest.get("author"),
                manifest.get("origin", "builtin"),
                manifest.get("sourceRunId"),
                now,
                now,
            ),
        )
        for dep in manifest.get("requiredSkills", []) or []:
            self._db.execute(
                "INSERT INTO SkillDependency (id, skillId, version, dependsOn, constraint_, optional) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id("dep"), skill_id, version, dep["skillId"], dep.get("version"), 1 if dep.get("optional") else 0),
            )
        for tool in manifest.get("requiredTools", []) or []:
            self._db.execute(
                "INSERT INTO SkillToolRequirement (id, skillId, version, toolName) VALUES (?, ?, ?, ?)",
                (new_id("toolreq"), skill_id, version, tool),
            )
        for perm in manifest.get("permissions", []) or []:
            self._db.execute(
                "INSERT INTO SkillPermissionRequirement (id, skillId, version, permission) VALUES (?, ?, ?, ?)",
                (new_id("permreq"), skill_id, version, perm),
            )
        self._db.commit()

    def list_skills(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        if status:
            rows = self._db.execute(
                "SELECT * FROM Skill WHERE status=? ORDER BY id", (status,)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM Skill ORDER BY id").fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["tags"] = json.loads(record["tags"]) if record["tags"] else []
            out.append(record)
        return out

    def get_skill(self, skill_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM Skill WHERE id=?", (skill_id,)).fetchone()
        if not row:
            return None
        record = dict(row)
        record["tags"] = json.loads(record["tags"]) if record["tags"] else []
        return record

    def get_version(self, skill_id: str, version: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM SkillVersion WHERE skillId=? AND version=?", (skill_id, version)
        ).fetchone()
        return self._version_row(row) if row else None

    def get_version_by_hash(self, skill_id: str, content_hash: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM SkillVersion WHERE skillId=? AND contentHash=?", (skill_id, content_hash)
        ).fetchone()
        return self._version_row(row) if row else None

    def list_versions(self, skill_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM SkillVersion WHERE skillId=? ORDER BY createdAt ASC", (skill_id,)
        ).fetchall()
        return [self._version_row(r) for r in rows]

    def set_version_status(self, skill_id: str, version: str, status: str, evaluation_status: Optional[str] = None) -> None:
        sets = ["status = ?", "updatedAt = ?"]
        params: list[Any] = [status, now_iso()]
        if evaluation_status is not None:
            sets.append("evaluationStatus = ?")
            params.append(evaluation_status)
        params.extend([skill_id, version])
        self._db.execute(
            f"UPDATE SkillVersion SET {', '.join(sets)} WHERE skillId=? AND version=?", params
        )
        self._db.execute(
            "UPDATE Skill SET status=?, updatedAt=? WHERE id=?", (status, now_iso(), skill_id)
        )
        self._db.commit()

    def set_latest_version(self, skill_id: str, version: str) -> None:
        self._db.execute(
            "UPDATE Skill SET latestVersion=?, updatedAt=? WHERE id=?",
            (version, now_iso(), skill_id),
        )
        self._db.commit()

    # ── Executions ──────────────────────────────────────────────────────────

    def create_execution(
        self,
        *,
        run_id: str,
        skill_id: str,
        version: str,
        manifest_hash: Optional[str],
        parent_run_id: Optional[str],
        execution_mode: str,
        actor: str,
        input_data: dict[str, Any],
    ) -> str:
        execution_id = new_id("skex")
        self._db.execute(
            """INSERT INTO SkillExecution
               (id, runId, skillId, version, manifestHash, parentRunId, executionMode, status,
                actor, input, durationMs, traceId, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, 0, ?, ?)""",
            (
                execution_id,
                run_id,
                skill_id,
                version,
                manifest_hash,
                parent_run_id,
                execution_mode,
                actor,
                json.dumps(input_data),
                run_id,
                now_iso(),
            ),
        )
        self._db.commit()
        return execution_id

    def finish_execution(
        self,
        execution_id: str,
        *,
        status: str,
        output: Optional[str] = None,
        error: Optional[dict[str, Any]] = None,
        warnings: Optional[list[str]] = None,
        missing_data: Optional[list[str]] = None,
        limitations: Optional[list[str]] = None,
        evidence: Optional[list[Any]] = None,
        duration_ms: int = 0,
    ) -> None:
        self._db.execute(
            """UPDATE SkillExecution SET status=?, output=?, error=?, warnings=?, missingData=?,
               limitations=?, evidence=?, durationMs=?, finishedAt=? WHERE id=?""",
            (
                status,
                output,
                json.dumps(error) if error else None,
                json.dumps(warnings or []),
                json.dumps(missing_data or []),
                json.dumps(limitations or []),
                json.dumps(evidence or []),
                int(duration_ms),
                now_iso(),
                execution_id,
            ),
        )
        self._db.commit()

    def get_execution(self, run_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM SkillExecution WHERE runId=?", (run_id,)).fetchone()
        return self._execution_row(row) if row else None

    def list_executions(
        self, skill_id: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if skill_id:
            rows = self._db.execute(
                "SELECT * FROM SkillExecution WHERE skillId=? ORDER BY createdAt DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM SkillExecution ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._execution_row(r) for r in rows]

    # ── Evaluations ─────────────────────────────────────────────────────────

    def save_evaluation(
        self,
        *,
        skill_id: str,
        version: str,
        status: str,
        dimensions: list[dict[str, Any]],
        evaluator: str = "deterministic-v1",
        summary: Optional[str] = None,
        cases: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        evaluation_id = new_id("eval")
        self._db.execute(
            """INSERT INTO SkillEvaluation (id, skillId, version, status, evaluator, dimensions, summary, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (evaluation_id, skill_id, version, status, evaluator, json.dumps(dimensions), summary, now_iso()),
        )
        for case in cases or []:
            self._db.execute(
                """INSERT INTO SkillEvaluationCase
                   (id, evaluationId, skillId, version, caseId, name, kind, input, expected, createdAt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_id("evalcase"),
                    evaluation_id,
                    skill_id,
                    version,
                    case["caseId"],
                    case.get("name", case["caseId"]),
                    case.get("kind", "schema"),
                    json.dumps(case.get("input")) if case.get("input") is not None else None,
                    json.dumps(case.get("expected")) if case.get("expected") is not None else None,
                    now_iso(),
                ),
            )
        self._db.execute(
            "UPDATE SkillVersion SET evaluationStatus=?, updatedAt=? WHERE skillId=? AND version=?",
            (status, now_iso(), skill_id, version),
        )
        self._db.commit()
        return evaluation_id

    def get_evaluation(self, evaluation_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM SkillEvaluation WHERE id=?", (evaluation_id,)).fetchone()
        if not row:
            return None
        record = dict(row)
        record["dimensions"] = json.loads(record["dimensions"]) if record["dimensions"] else []
        cases = self._db.execute(
            "SELECT * FROM SkillEvaluationCase WHERE evaluationId=? ORDER BY caseId", (evaluation_id,)
        ).fetchall()
        record["cases"] = [self._case_row(c) for c in cases]
        return record

    def list_evaluations(self, skill_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if skill_id:
            rows = self._db.execute(
                "SELECT * FROM SkillEvaluation WHERE skillId=? ORDER BY createdAt DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM SkillEvaluation ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["dimensions"] = json.loads(record["dimensions"]) if record["dimensions"] else []
            out.append(record)
        return out

    def save_evaluation_case(self, **case: Any) -> None:
        self._db.execute(
            """INSERT INTO SkillEvaluationCase
               (id, evaluationId, skillId, version, caseId, name, kind, input, expected, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id("evalcase"),
                case.get("evaluationId"),
                case["skillId"],
                case["version"],
                case["caseId"],
                case.get("name", case["caseId"]),
                case.get("kind", "schema"),
                json.dumps(case.get("input")) if case.get("input") is not None else None,
                json.dumps(case.get("expected")) if case.get("expected") is not None else None,
                now_iso(),
            ),
        )
        self._db.commit()

    def replace_evaluation_cases(self, skill_id: str, version: str, cases: list[dict[str, Any]]) -> None:
        """Replace the attached (library-declared) cases for a skill version."""
        self._db.execute(
            "DELETE FROM SkillEvaluationCase WHERE skillId=? AND version=? AND evaluationId IS NULL",
            (skill_id, version),
        )
        for case in cases:
            self._db.execute(
                """INSERT INTO SkillEvaluationCase
                   (id, evaluationId, skillId, version, caseId, name, kind, input, expected, createdAt)
                   VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_id("evalcase"),
                    skill_id,
                    version,
                    case["caseId"],
                    case.get("name", case["caseId"]),
                    case.get("kind", "schema"),
                    json.dumps(case.get("input")) if case.get("input") is not None else None,
                    json.dumps(case.get("expected")) if case.get("expected") is not None else None,
                    now_iso(),
                ),
            )
        self._db.commit()

    def list_evaluation_cases(self, skill_id: str, version: str) -> list[dict[str, Any]]:
        # Prefer the library-declared cases (evaluationId IS NULL); fall back to
        # any cases stored with a prior evaluation.
        rows = self._db.execute(
            "SELECT * FROM SkillEvaluationCase WHERE skillId=? AND version=? ORDER BY caseId",
            (skill_id, version),
        ).fetchall()
        return [self._case_row(r) for r in rows]

    # ── Learning candidates ─────────────────────────────────────────────────

    def save_candidate(self, candidate: dict[str, Any]) -> str:
        candidate_id = candidate.get("id") or new_id("cand")
        self._db.execute(
            """INSERT INTO LearningCandidate
               (id, sourceRunId, candidateType, title, problem, observedBehavior, proposedLesson,
                proposedProcedure, evidenceReferences, confidence, generalizationNotes, knownLimitations,
                signature, status, createdAt, reviewedAt, resultingSkillId, resultingSkillVersion, draftManifest)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate_id,
                candidate.get("sourceRunId"),
                candidate["candidateType"],
                candidate["title"],
                candidate.get("problem"),
                candidate.get("observedBehavior"),
                candidate.get("proposedLesson"),
                json.dumps(candidate.get("proposedProcedure")) if candidate.get("proposedProcedure") is not None else None,
                json.dumps(candidate.get("evidenceReferences") or []),
                float(candidate.get("confidence", 0.5)),
                candidate.get("generalizationNotes"),
                candidate.get("knownLimitations"),
                candidate["signature"],
                candidate.get("status", "new"),
                candidate.get("createdAt") or now_iso(),
                candidate.get("reviewedAt"),
                candidate.get("resultingSkillId"),
                candidate.get("resultingSkillVersion"),
                json.dumps(candidate.get("draftManifest")) if candidate.get("draftManifest") is not None else None,
            ),
        )
        self._db.commit()
        return candidate_id

    def update_candidate(self, candidate_id: str, **patch: Any) -> None:
        allowed = {
            "status", "reviewedAt", "resultingSkillId", "resultingSkillVersion",
            "draftManifest", "confidence", "knownLimitations",
        }
        sets, params = [], []
        for key, value in patch.items():
            if key not in allowed:
                continue
            sets.append(f"{key} = ?")
            params.append(json.dumps(value) if key == "draftManifest" and value is not None else value)
        if not sets:
            return
        params.append(candidate_id)
        self._db.execute(f"UPDATE LearningCandidate SET {', '.join(sets)} WHERE id=?", params)
        self._db.commit()

    def get_candidate(self, candidate_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM LearningCandidate WHERE id=?", (candidate_id,)).fetchone()
        return self._candidate_row(row) if row else None

    def list_candidates(self, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if status:
            rows = self._db.execute(
                "SELECT * FROM LearningCandidate WHERE status=? ORDER BY createdAt DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM LearningCandidate ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._candidate_row(r) for r in rows]

    def find_candidate_by_signature(self, signature: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM LearningCandidate WHERE signature=? ORDER BY createdAt DESC LIMIT 1",
            (signature,),
        ).fetchone()
        return self._candidate_row(row) if row else None

    # ── Promotion / review ──────────────────────────────────────────────────

    def save_promotion_request(
        self, *, skill_id: str, version: str, requested_by: str, reason: str, evaluation_id: Optional[str], status: str = "pending"
    ) -> str:
        request_id = new_id("promo")
        self._db.execute(
            """INSERT INTO SkillPromotionRequest
               (id, skillId, version, requestedBy, status, reason, evaluationId, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (request_id, skill_id, version, requested_by, status, reason, evaluation_id, now_iso()),
        )
        self._db.commit()
        return request_id

    def decide_promotion(self, request_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE SkillPromotionRequest SET status=?, decidedAt=? WHERE id=?",
            (status, now_iso(), request_id),
        )
        self._db.commit()

    def list_promotion_requests(self, skill_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if skill_id:
            rows = self._db.execute(
                "SELECT * FROM SkillPromotionRequest WHERE skillId=? ORDER BY createdAt DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM SkillPromotionRequest ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def save_review(self, *, skill_id: str, version: str, actor: str, decision: str, notes: str) -> str:
        review_id = new_id("review")
        self._db.execute(
            """INSERT INTO SkillReview (id, skillId, version, actor, decision, notes, createdAt)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (review_id, skill_id, version, actor, decision, notes, now_iso()),
        )
        self._db.commit()
        return review_id

    def list_reviews(self, skill_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if skill_id:
            rows = self._db.execute(
                "SELECT * FROM SkillReview WHERE skillId=? ORDER BY createdAt DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM SkillReview ORDER BY createdAt DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Events ──────────────────────────────────────────────────────────────

    def append_event(
        self, event_type: str, *, skill_id: Optional[str] = None, version: Optional[str] = None,
        run_id: Optional[str] = None, data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        event = {
            "id": new_id("skillevent"),
            "skillId": skill_id,
            "version": version,
            "runId": run_id,
            "type": event_type,
            "at": now_iso(),
            "data": data or {},
        }
        self._db.execute(
            "INSERT INTO SkillEvent (id, skillId, version, runId, type, at, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event["id"], skill_id, version, run_id, event_type, event["at"], json.dumps(event["data"])),
        )
        self._db.commit()
        return event

    def list_events(self, skill_id: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        if skill_id:
            rows = self._db.execute(
                "SELECT * FROM SkillEvent WHERE skillId=? ORDER BY at DESC LIMIT ?", (skill_id, limit)
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM SkillEvent ORDER BY at DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for row in rows:
            record = dict(row)
            record["data"] = json.loads(record["data"]) if record["data"] else {}
            out.append(record)
        return out

    # ── Row mappers ─────────────────────────────────────────────────────────

    @staticmethod
    def _version_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["manifest"] = json.loads(record["manifest"])
        return record

    @staticmethod
    def _execution_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        for key in ("input", "error", "warnings", "missingData", "limitations", "evidence"):
            if record.get(key):
                try:
                    record[key] = json.loads(record[key])
                except (TypeError, ValueError):
                    pass
        return record

    @staticmethod
    def _case_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        for key in ("input", "expected"):
            if record.get(key):
                try:
                    record[key] = json.loads(record[key])
                except (TypeError, ValueError):
                    pass
        return record

    @staticmethod
    def _candidate_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        for key in ("proposedProcedure", "evidenceReferences", "draftManifest"):
            if record.get(key):
                try:
                    record[key] = json.loads(record[key])
                except (TypeError, ValueError):
                    pass
        return record

    def close(self) -> None:
        self._db.close()


__all__ = ["SkillStore", "SCHEMA"]

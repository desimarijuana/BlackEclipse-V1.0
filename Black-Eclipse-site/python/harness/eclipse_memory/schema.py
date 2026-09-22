"""Eclipse-Memory schema — the normalized DDL for `eclipse-memory.db`.

Design notes (documented in `docs/harness/phase-3-memory-progress.md`):

  * One SQLite file, one migration mechanism. DDL is a list of idempotent
    statements applied in order; new statements are appended, never rewritten.
  * Memory and skills are separate concerns but share the audit/event table.
  * Skills use the SAME table/column shapes Phase 3 already established in
    `skills/store.py`, so the Phase-3 `SkillStore` becomes a thin adapter with
    no behavioural change. This avoids a second skill registry.
  * Nothing here is destructive. `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX
    IF NOT EXISTS` only.
"""

from __future__ import annotations

# Each entry is a (version, [statements]) migration. Applying migration N runs
# its statements; the highest applied version is recorded in `SchemaMigration`.
MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        1,
        [
            # ── Migration bookkeeping ───────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS SchemaMigration (
              version   INTEGER PRIMARY KEY,
              appliedAt TEXT NOT NULL
            );
            """,
            # ── Memory ──────────────────────────────────────────────────────
            # Durable memory. `memoryType` is explicit; `scope` keeps a user
            # preference distinct from universal financial knowledge.
            """
            CREATE TABLE IF NOT EXISTS MemoryRecord (
              id             TEXT PRIMARY KEY,
              memoryType     TEXT NOT NULL,
              scope          TEXT NOT NULL,
              scopeId        TEXT,
              subject        TEXT,
              content        TEXT NOT NULL,
              structuredData TEXT,
              source         TEXT,
              sourceRunId    TEXT,
              confidence     REAL NOT NULL DEFAULT 0.5,
              importance     REAL NOT NULL DEFAULT 0.5,
              status         TEXT NOT NULL DEFAULT 'active',
              verification   TEXT NOT NULL DEFAULT 'unverified',
              createdBy      TEXT,
              createdAt      TEXT NOT NULL,
              updatedAt      TEXT NOT NULL,
              lastAccessedAt TEXT,
              accessCount    INTEGER NOT NULL DEFAULT 0,
              expiresAt      TEXT,
              supersededBy   TEXT,
              reviewedAt     TEXT,
              reviewStatus   TEXT
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_mem_type    ON MemoryRecord(memoryType);",
            "CREATE INDEX IF NOT EXISTS idx_mem_scope   ON MemoryRecord(scope, scopeId);",
            "CREATE INDEX IF NOT EXISTS idx_mem_subject ON MemoryRecord(subject);",
            "CREATE INDEX IF NOT EXISTS idx_mem_status  ON MemoryRecord(status);",
            "CREATE INDEX IF NOT EXISTS idx_mem_run     ON MemoryRecord(sourceRunId);",
            # Evidence attached to a memory. Never fabricated; verification
            # status is explicit.
            """
            CREATE TABLE IF NOT EXISTS MemoryEvidence (
              id               TEXT PRIMARY KEY,
              memoryId         TEXT NOT NULL,
              sourceType       TEXT NOT NULL,
              sourceRef        TEXT,
              sourceUrl        TEXT,
              sourceRunId      TEXT,
              evidenceText     TEXT,
              retrievedAt      TEXT,
              publishedAt      TEXT,
              verificationStatus TEXT NOT NULL DEFAULT 'unknown',
              createdAt        TEXT NOT NULL,
              FOREIGN KEY (memoryId) REFERENCES MemoryRecord(id) ON DELETE CASCADE
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_mevidence_mem ON MemoryEvidence(memoryId);",
            # Relationships between memories (supports/contradicts/supersedes/
            # derived_from/related_to/corrects/duplicates).
            """
            CREATE TABLE IF NOT EXISTS MemoryLink (
              id         TEXT PRIMARY KEY,
              fromId     TEXT NOT NULL,
              toId       TEXT NOT NULL,
              relation   TEXT NOT NULL,
              note       TEXT,
              createdAt  TEXT NOT NULL,
              FOREIGN KEY (fromId) REFERENCES MemoryRecord(id) ON DELETE CASCADE,
              FOREIGN KEY (toId)   REFERENCES MemoryRecord(id) ON DELETE CASCADE
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_mlink_from ON MemoryLink(fromId);",
            "CREATE INDEX IF NOT EXISTS idx_mlink_to   ON MemoryLink(toId);",
            "CREATE INDEX IF NOT EXISTS idx_mlink_rel  ON MemoryLink(relation);",
            # Retrieval audit — one row per retrieval request (diagnostics).
            """
            CREATE TABLE IF NOT EXISTS MemoryRetrievalEvent (
              id           TEXT PRIMARY KEY,
              runId        TEXT,
              query        TEXT,
              requestedTypes TEXT,
              candidates   INTEGER NOT NULL DEFAULT 0,
              selected     INTEGER NOT NULL DEFAULT 0,
              excluded     TEXT,
              selectionReasons TEXT,
              budgetChars  INTEGER,
              usedChars    INTEGER NOT NULL DEFAULT 0,
              durationMs   INTEGER NOT NULL DEFAULT 0,
              ok           INTEGER NOT NULL DEFAULT 1,
              error        TEXT,
              createdAt    TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_mret_run ON MemoryRetrievalEvent(runId);",
            # ── Skills (Phase-3-compatible shapes) ──────────────────────────
            """
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
            """,
            "CREATE INDEX IF NOT EXISTS idx_skill_status   ON Skill(status);",
            "CREATE INDEX IF NOT EXISTS idx_skill_category ON Skill(category);",
            """
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
              instructions         TEXT,
              author               TEXT,
              origin               TEXT NOT NULL DEFAULT 'builtin',
              sourceRunId          TEXT,
              originCandidateId    TEXT,
              limitations          TEXT,
              createdAt            TEXT NOT NULL,
              updatedAt            TEXT NOT NULL,
              publishedAt          TEXT,
              deprecatedAt         TEXT,
              UNIQUE(skillId, version),
              FOREIGN KEY (skillId) REFERENCES Skill(id) ON DELETE CASCADE
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_skillver_skill  ON SkillVersion(skillId);",
            "CREATE INDEX IF NOT EXISTS idx_skillver_status ON SkillVersion(status);",
            """
            CREATE TABLE IF NOT EXISTS SkillDependency (
              id          TEXT PRIMARY KEY,
              skillId     TEXT NOT NULL,
              version     TEXT NOT NULL,
              dependsOn   TEXT NOT NULL,
              constraint_ TEXT,
              optional    INTEGER NOT NULL DEFAULT 0
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_skilldep_skill ON SkillDependency(skillId, version);",
            """
            CREATE TABLE IF NOT EXISTS SkillToolRequirement (
              id       TEXT PRIMARY KEY,
              skillId  TEXT NOT NULL,
              version  TEXT NOT NULL,
              toolName TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_skilltool_skill ON SkillToolRequirement(skillId, version);",
            """
            CREATE TABLE IF NOT EXISTS SkillPermissionRequirement (
              id         TEXT PRIMARY KEY,
              skillId    TEXT NOT NULL,
              version    TEXT NOT NULL,
              permission TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_skillperm_skill ON SkillPermissionRequirement(skillId, version);",
            """
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
            """,
            "CREATE INDEX IF NOT EXISTS idx_skillexec_skill  ON SkillExecution(skillId, version);",
            "CREATE INDEX IF NOT EXISTS idx_skillexec_run    ON SkillExecution(runId);",
            "CREATE INDEX IF NOT EXISTS idx_skillexec_parent ON SkillExecution(parentRunId);",
            "CREATE INDEX IF NOT EXISTS idx_skillexec_status ON SkillExecution(status);",
            """
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
            """,
            "CREATE INDEX IF NOT EXISTS idx_skileval_skill ON SkillEvaluation(skillId, version);",
            """
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
              status        TEXT,
              createdAt     TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_skilevalcase_skill ON SkillEvaluationCase(skillId, version);",
            # ── Learning ────────────────────────────────────────────────────
            """
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
              duplicateGroup     TEXT,
              status             TEXT NOT NULL DEFAULT 'detected',
              createdAt          TEXT NOT NULL,
              reviewedAt         TEXT,
              resultingSkillId   TEXT,
              resultingSkillVersion TEXT,
              draftManifest      TEXT
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_learning_status    ON LearningCandidate(status);",
            "CREATE INDEX IF NOT EXISTS idx_learning_signature ON LearningCandidate(signature);",
            "CREATE INDEX IF NOT EXISTS idx_learning_run       ON LearningCandidate(sourceRunId);",
            # ── Mistakes / corrections ──────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS MistakeRecord (
              id               TEXT PRIMARY KEY,
              category         TEXT NOT NULL,
              severity         TEXT NOT NULL DEFAULT 'medium',
              runId            TEXT,
              skillId          TEXT,
              skillVersion     TEXT,
              toolName         TEXT,
              expected         TEXT,
              actual           TEXT,
              evidence         TEXT,
              correctiveAction TEXT,
              correctionWorked INTEGER,
              reusable         INTEGER NOT NULL DEFAULT 0,
              candidateId      TEXT,
              createdAt        TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_mistake_run     ON MistakeRecord(runId);",
            "CREATE INDEX IF NOT EXISTS idx_mistake_cat     ON MistakeRecord(category);",
            "CREATE INDEX IF NOT EXISTS idx_mistake_skill   ON MistakeRecord(skillId);",
            """
            CREATE TABLE IF NOT EXISTS CorrectionRecord (
              id             TEXT PRIMARY KEY,
              runId          TEXT,
              memoryId       TEXT,
              subject        TEXT,
              wrong          TEXT NOT NULL,
              correction     TEXT NOT NULL,
              providedBy     TEXT NOT NULL DEFAULT 'user',
              evidence       TEXT,
              scope          TEXT NOT NULL DEFAULT 'user',
              generalizable  INTEGER NOT NULL DEFAULT 0,
              appliedToSkill TEXT,
              status         TEXT NOT NULL DEFAULT 'recorded',
              createdAt      TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_correction_run  ON CorrectionRecord(runId);",
            "CREATE INDEX IF NOT EXISTS idx_correction_subj ON CorrectionRecord(subject);",
            # ── Promotion / review ──────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS SkillPromotionRequest (
              id           TEXT PRIMARY KEY,
              skillId      TEXT NOT NULL,
              version      TEXT NOT NULL,
              requestedBy  TEXT,
              reviewedBy   TEXT,
              previousStatus TEXT,
              status       TEXT NOT NULL DEFAULT 'pending',
              reason       TEXT,
              evaluationId TEXT,
              createdAt    TEXT NOT NULL,
              decidedAt    TEXT
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_promotion_skill ON SkillPromotionRequest(skillId, version);",
            """
            CREATE TABLE IF NOT EXISTS SkillReview (
              id        TEXT PRIMARY KEY,
              skillId   TEXT NOT NULL,
              version   TEXT NOT NULL,
              actor     TEXT,
              decision  TEXT NOT NULL,
              notes     TEXT,
              createdAt TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_review_skill ON SkillReview(skillId, version);",
            # ── Audit ───────────────────────────────────────────────────────
            """
            CREATE TABLE IF NOT EXISTS SkillEvent (
              id        TEXT PRIMARY KEY,
              skillId   TEXT,
              version   TEXT,
              runId     TEXT,
              type      TEXT NOT NULL,
              at        TEXT NOT NULL,
              data      TEXT
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_skillevent_skill ON SkillEvent(skillId);",
            "CREATE INDEX IF NOT EXISTS idx_skillevent_run   ON SkillEvent(runId);",
            """
            CREATE TABLE IF NOT EXISTS MemoryEvent (
              id        TEXT PRIMARY KEY,
              memoryId  TEXT,
              runId     TEXT,
              type      TEXT NOT NULL,
              at        TEXT NOT NULL,
              data      TEXT
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_memevent_mem ON MemoryEvent(memoryId);",
            "CREATE INDEX IF NOT EXISTS idx_memevent_run ON MemoryEvent(runId);",
        ],
    ),
]

# The current schema version = the highest migration number.
SCHEMA_VERSION = max(version for version, _ in MIGRATIONS)


__all__ = ["MIGRATIONS", "SCHEMA_VERSION"]

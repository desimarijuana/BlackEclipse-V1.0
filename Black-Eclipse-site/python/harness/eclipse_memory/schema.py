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

# Migration 2 — configurable memory/learning policy. Separate from the code
# defaults in `policy.py`: the table stores only *overrides*, so a new default
# applies automatically without mutating stored rows.
MIGRATIONS.append(
    (
        2,
        [
            """
            CREATE TABLE IF NOT EXISTS MemoryPolicy (
              key        TEXT PRIMARY KEY,
              value      TEXT NOT NULL,
              updatedAt  TEXT NOT NULL,
              updatedBy  TEXT
            );
            """,
        ],
    )
)

# Migration 3 — user-authored skills. Separate from the derived `Skill`/
# `SkillVersion` rows (which are rebuilt from the source): this table is the
# authoritative source for a user skill, so it can be re-materialised on boot.
MIGRATIONS.append(
    (
        3,
        [
            """
            CREATE TABLE IF NOT EXISTS UserSkill (
              id           TEXT PRIMARY KEY,
              name         TEXT NOT NULL,
              description  TEXT NOT NULL,
              category     TEXT NOT NULL,
              tags         TEXT NOT NULL DEFAULT '[]',
              instructions TEXT NOT NULL,
              manifest     TEXT NOT NULL,
              version      TEXT NOT NULL,
              status       TEXT NOT NULL DEFAULT 'draft',
              author       TEXT,
              createdAt    TEXT NOT NULL,
              updatedAt    TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_userskill_status ON UserSkill(status);",
        ],
    )
)

# Migration 4 — link learning candidates to run diagnostics + regional scope.
# Additive columns only (no backfill): older rows have NULL, which reads as
# "no diagnostics / scope unspecified". Phase 7 uses these so a reviewed
# procedure never generalizes one country/provider to all countries.
MIGRATIONS.append(
    (
        4,
        [
            "ALTER TABLE LearningCandidate ADD COLUMN diagnostics TEXT;",
            "ALTER TABLE LearningCandidate ADD COLUMN scope TEXT;",
        ],
    )
)

# Migration 5 — reset unsafe stored policy overrides to the new safe defaults.
# `auto_capture_enabled` and `auto_candidate_detection` previously defaulted to
# True, so a persisted `true` override (or a store written under the old default)
# would keep automatic capture/detection on despite the code default changing to
# False. Deleting the `true` override restores the safe default while preserving
# every other setting; the reset is recorded so it is observable in health/policy
# UI. Idempotent: re-running finds nothing left to delete.
MIGRATIONS.append(
    (
        5,
        [
            """
            CREATE TABLE IF NOT EXISTS MemoryPolicyMigration (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              key           TEXT NOT NULL,
              previousValue TEXT NOT NULL,
              reason        TEXT NOT NULL,
              resetAt       TEXT NOT NULL
            );
            """,
            """
            INSERT INTO MemoryPolicyMigration (key, previousValue, reason, resetAt)
              SELECT key, value,
                     'unsafe true override reset to safe default',
                     strftime('%Y-%m-%dT%H:%M:%SZ','now')
              FROM MemoryPolicy
              WHERE key IN ('auto_capture_enabled', 'auto_candidate_detection')
                AND value IN ('true', '1');
            """,
            """
            DELETE FROM MemoryPolicy
              WHERE key IN ('auto_capture_enabled', 'auto_candidate_detection')
                AND value IN ('true', '1');
            """,
        ],
    )
)

# Migration 6 — memory suggestions. A suggestion is an INERT, non-recalled
# proposal to remember something (usually a casually-stated preference). It
# exists only so the user can Save or Dismiss it; it is never injected into a run
# and never counts as memory until accepted. Dismissals are retained so the same
# suggestion is not re-offered repeatedly.
MIGRATIONS.append(
    (
        6,
        [
            """
            CREATE TABLE IF NOT EXISTS MemorySuggestion (
              id           TEXT PRIMARY KEY,
              runId        TEXT,
              scope        TEXT NOT NULL,
              scopeId      TEXT,
              subject      TEXT,
              memoryType   TEXT NOT NULL,
              content      TEXT NOT NULL,
              reason       TEXT,
              provenance   TEXT,
              confidence   REAL NOT NULL DEFAULT 0.5,
              signature    TEXT NOT NULL,
              status       TEXT NOT NULL DEFAULT 'pending',
              candidateId  TEXT,
              createdAt    TEXT NOT NULL,
              decidedAt    TEXT
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_suggestion_status ON MemorySuggestion(status);",
            "CREATE INDEX IF NOT EXISTS idx_suggestion_sig    ON MemorySuggestion(signature);",
        ],
    )
)

# Migration 7 — one coherent learning lifecycle. Automatic memory capture and
# automatic skill learning are now each controlled by a single *mode* key
# (`memory_mode`, `skill_learning_mode`: automatic_selective | ask_before_saving
# | off) rather than three independent booleans that could drift out of sync.
# The legacy boolean rows are removed so the mode defaults govern; a previously
# stored `true` (already reset by migration 5) is preserved as the matching
# automatic_selective intent. The removal is recorded so it is observable in the
# policy/migration UI. Idempotent: re-running finds nothing left to delete.
MIGRATIONS.append(
    (
        7,
        [
            """
            INSERT INTO MemoryPolicyMigration (key, previousValue, reason, resetAt)
              SELECT key, value,
                     'legacy automatic-learning boolean replaced by learning mode',
                     strftime('%Y-%m-%dT%H:%M:%SZ','now')
              FROM MemoryPolicy
              WHERE key IN ('auto_capture_enabled', 'auto_suggest_enabled', 'auto_candidate_detection');
            """,
            """
            DELETE FROM MemoryPolicy
              WHERE key IN ('auto_capture_enabled', 'auto_suggest_enabled', 'auto_candidate_detection');
            """,
        ],
    )
)

# Migration 8 — persisted recurrence ledger for durable-sounding statements.
# A project convention ("always use X") is only saved automatically once it has
# recurred. Deriving recurrence purely from the bounded chat-history window meant
# a convention repeated across sessions/after the window was never recognised.
# This table records one bounded row per normalized content signature (the raw
# text is never stored — only a non-reversible digest), with a seen-count, so
# recurrence survives across runs and restarts. The signature is indexed and the
# table is pruned to the most recent rows by the service, so growth is bounded.
MIGRATIONS.append(
    (
        8,
        [
            """
            CREATE TABLE IF NOT EXISTS MemoryRecurrence (
              signature   TEXT PRIMARY KEY,
              seenCount   INTEGER NOT NULL DEFAULT 1,
              firstSeenAt TEXT NOT NULL,
              lastSeenAt  TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_recurrence_last ON MemoryRecurrence(lastSeenAt);",
        ],
    )
)

# Migration 9 — observability columns on SkillExecution. The execution record is
# the operator's view of a skill run; it must show whether the output was
# actually validated against the declared schema, and the bounded run metrics
# (tool calls, model steps, tokens, tool errors). Additive columns only: older
# rows read as NULL ("unknown"), which the UI renders as "not recorded".
MIGRATIONS.append(
    (
        9,
        [
            "ALTER TABLE SkillExecution ADD COLUMN outputValidated INTEGER;",
            "ALTER TABLE SkillExecution ADD COLUMN metrics TEXT;",
        ],
    )
)

# Migration 10 — explicit memory lifecycle + temporal state. Adds the timestamps
# needed to answer "when was this last confirmed / used / reviewed" and an
# `authority` column distinguishing an explicit user/operator memory from an
# automatically learned one. `statusReason` records *why* a record became inert
# (superseded/expired/rejected) so the lifecycle is auditable.
#
# Additive only. Existing rows receive authority='explicit' (the conservative
# default: an unknown-provenance record is never auto-expired) and NULL for the
# new timestamps ("not recorded"), which the UI renders honestly.
MIGRATIONS.append(
    (
        10,
        [
            "ALTER TABLE MemoryRecord ADD COLUMN lastConfirmedAt TEXT;",
            "ALTER TABLE MemoryRecord ADD COLUMN lastUsedAt TEXT;",
            "ALTER TABLE MemoryRecord ADD COLUMN lastReviewedAt TEXT;",
            "ALTER TABLE MemoryRecord ADD COLUMN authority TEXT NOT NULL DEFAULT 'explicit';",
            "ALTER TABLE MemoryRecord ADD COLUMN statusReason TEXT;",
            "CREATE INDEX IF NOT EXISTS idx_mem_authority ON MemoryRecord(authority);",
            "CREATE INDEX IF NOT EXISTS idx_mem_last_used ON MemoryRecord(lastUsedAt);",
        ],
    )
)

# Migration 11 — retention sweep runtime state. One row records the last sweep:
# when it ran, how many records it inspected/expired/skipped, and the failure
# reason if it did not complete. This makes automatic retention observable in the
# health/lifecycle diagnostics without exposing memory content. It is additive
# and idempotent (a singleton row), so no existing record is touched.
MIGRATIONS.append(
    (
        11,
        [
            """
            CREATE TABLE IF NOT EXISTS MemoryMaintenance (
              id            INTEGER PRIMARY KEY CHECK (id = 1),
              operation     TEXT NOT NULL,
              ranAt         TEXT NOT NULL,
              ok            INTEGER NOT NULL DEFAULT 1,
              inspected     INTEGER NOT NULL DEFAULT 0,
              expired       INTEGER NOT NULL DEFAULT 0,
              skipped       INTEGER NOT NULL DEFAULT 0,
              error         TEXT
            );
            """,
        ],
    )
)

# Migration 12 — compact prompt-profile snapshot metadata. The profile itself is
# a projection over active MemoryRecord rows (no content is copied here): this
# table records WHAT was selected for one run and how large it was, so a profile
# is reproducible/auditable without storing the memory content twice. Additive.
MIGRATIONS.append(
    (
        12,
        [
            """
            CREATE TABLE IF NOT EXISTS MemoryProfileSnapshot (
              id             TEXT PRIMARY KEY,
              version        INTEGER NOT NULL,
              selectedIds    TEXT NOT NULL,
              charCount      INTEGER NOT NULL DEFAULT 0,
              tokenEstimate  INTEGER NOT NULL DEFAULT 0,
              scopeId        TEXT,
              runId          TEXT,
              excludedCount  INTEGER NOT NULL DEFAULT 0,
              createdAt      TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_profile_created ON MemoryProfileSnapshot(createdAt);",
        ],
    )
)

# Migration 13 — self-improving skill patch/version metadata (Milestone 2).
# Adds the columns that make a skill version a reviewable, diffable patch rather
# than an opaque whole-manifest replacement:
#   baseVersion   — the version this patch was authored against (conflict check);
#   patchSummary  — a bounded human-readable summary of what changed;
#   reviewId      — the learning review that produced it (when applicable);
#   patchAuthor   — user | background_review | operator;
#   activatedAt   — when the version became active;
#   rolledBackAt  — when it was reverted (auto or manual);
#   canaryState   — NULL when not a canary, else 'canary'/'promoted'/'rolled_back';
#   patch         — the bounded structured patch JSON (operations + evidence).
# All additive; existing rows read NULL ("not recorded").
MIGRATIONS.append(
    (
        13,
        [
            "ALTER TABLE SkillVersion ADD COLUMN baseVersion TEXT;",
            "ALTER TABLE SkillVersion ADD COLUMN patchSummary TEXT;",
            "ALTER TABLE SkillVersion ADD COLUMN reviewId TEXT;",
            "ALTER TABLE SkillVersion ADD COLUMN patchAuthor TEXT;",
            "ALTER TABLE SkillVersion ADD COLUMN activatedAt TEXT;",
            "ALTER TABLE SkillVersion ADD COLUMN rolledBackAt TEXT;",
            "ALTER TABLE SkillVersion ADD COLUMN canaryState TEXT;",
            "ALTER TABLE SkillVersion ADD COLUMN patch TEXT;",
            "CREATE INDEX IF NOT EXISTS idx_skillver_base ON SkillVersion(skillId, baseVersion);",
        ],
    )
)

# Project-local skills (Phase 2 of the memory/skills evolution). A project root
# may carry skills under `<root>/.black-eclipse/skills/` or `<root>/.agents/skills/`.
# Because skills are procedures the agent follows, they are NEVER auto-loaded
# from a repository: a root appears in the registry only after an operator
# records an explicit trust decision here. Trust is per absolute root path and
# revocable; the row is the audit of when/why it was trusted.
MIGRATIONS.append(
    (
        14,
        [
            """CREATE TABLE IF NOT EXISTS ProjectSkillTrust (
                path TEXT PRIMARY KEY,
                trusted INTEGER NOT NULL DEFAULT 0,
                trustedAt TEXT,
                note TEXT
            );""",
        ],
    )
)

# Skill bundles (Phase 3). A bundle groups several skills under one stable id
# with optional instructions/constraints. It is a *reference*, not a copy: the
# skills must already exist and remain subject to their own status/permission
# gates. Exportable/reviewable because it is structured JSON. Provenance records
# where the bundle came from (manual/profile/project/imported).
MIGRATIONS.append(
    (
        15,
        [
            """CREATE TABLE IF NOT EXISTS SkillBundle (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                skills TEXT NOT NULL DEFAULT '[]',
                instruction TEXT NOT NULL DEFAULT '',
                constraints TEXT NOT NULL DEFAULT '',
                provenance TEXT NOT NULL DEFAULT 'manual',
                createdAt TEXT,
                updatedAt TEXT
            );""",
        ],
    )
)

# Project skill drift (Phase 2 of the remaining-gaps plan). Trust is recorded
# against a content identity: `trustedHash` is the root's content hash at the
# moment of trust/approval. If the root's content later changes, the trusted
# skills are quarantined until an operator re-approves, so a `git pull` cannot
# silently change what a trusted repo contributes. `revokedHash` records the
# hash observed at the last untrust for audit.
MIGRATIONS.append(
    (
        16,
        [
            "ALTER TABLE ProjectSkillTrust ADD COLUMN trustedHash TEXT;",
            "ALTER TABLE ProjectSkillTrust ADD COLUMN revokedHash TEXT;",
        ],
    )
)

# Conservative memory compaction (Phase 5 of the remaining-gaps plan). A
# proposal is an INERT, reviewable bundle of near-duplicate memories. Accepting
# it creates one merged memory and supersedes the originals (linked, retained);
# rejecting it changes nothing. Originals/provenance/evidence/timestamps are
# preserved — nothing is ever hard-deleted.
MIGRATIONS.append(
    (
        17,
        [
            """CREATE TABLE IF NOT EXISTS CompactionProposal (
                id TEXT PRIMARY KEY,
                memberIds TEXT NOT NULL DEFAULT '[]',
                scope TEXT NOT NULL,
                scopeId TEXT,
                subject TEXT,
                mergedContent TEXT NOT NULL,
                rationale TEXT,
                status TEXT NOT NULL DEFAULT 'proposed',
                createdAt TEXT NOT NULL,
                decidedAt TEXT,
                resultingMemoryId TEXT
            );""",
            "CREATE INDEX IF NOT EXISTS idx_compaction_status ON CompactionProposal(status);",
        ],
    )
)

# Bundle lifecycle (Phase 9 of the remaining-gaps plan): a bundle gets a version
# identity plus an optional reproducibility lock pinning exact member versions.
MIGRATIONS.append(
    (
        18,
        [
            "ALTER TABLE SkillBundle ADD COLUMN version TEXT NOT NULL DEFAULT '1.0.0';",
            "ALTER TABLE SkillBundle ADD COLUMN memberVersions TEXT NOT NULL DEFAULT '{}';",
            "ALTER TABLE SkillBundle ADD COLUMN locked INTEGER NOT NULL DEFAULT 0;",
        ],
    )
)

# Per-skill project content identity (Phase 2 of the final-hardening pass). The
# root-level `trustedHash` stays as the coarse identity; `contentHashes` records
# the content hash of EACH skill at approval time so a change can be narrowed to
# the affected skill(s) instead of quarantining the whole root. JSON object
# `{skillId: hash}`; additive/idempotent, existing rows read NULL.
MIGRATIONS.append(
    (
        19,
        [
            "ALTER TABLE ProjectSkillTrust ADD COLUMN contentHashes TEXT;",
        ],
    )
)

# Project trust approval history (Phase 2, final hardening). Append-only: every
# trust / re-approval / untrust records WHO approved (actor label — there are no
# accounts, so this is the operator transport identity, never a request body),
# WHAT content hash(es) were approved, WHEN, WHICH skills, and whether the
# approval was root-level or per-skill. This makes the drift→review→approval
# chain auditable (the mutable ProjectSkillTrust row only holds current state).
MIGRATIONS.append(
    (
        20,
        [
            """CREATE TABLE IF NOT EXISTS ProjectTrustApproval (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                action TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT 'root',
                actor TEXT,
                approvedHash TEXT,
                contentHashes TEXT NOT NULL DEFAULT '{}',
                skillIds TEXT NOT NULL DEFAULT '[]',
                note TEXT,
                approvedAt TEXT NOT NULL
            );""",
            "CREATE INDEX IF NOT EXISTS idx_trust_approval_path ON ProjectTrustApproval(path, approvedAt);",
        ],
    )
)

# Bundle reproducibility (Phase 9, final hardening): record each member's CONTENT
# HASH alongside its version at lock time, so a locked bundle can be reconstructed
# and an in-place content edit under the same version is detectable. `lockHistory`
# is a bounded JSON list of prior locks so a bundle can be rolled back to an
# earlier recorded lock. Additive; existing rows read NULL.
MIGRATIONS.append(
    (
        21,
        [
            "ALTER TABLE SkillBundle ADD COLUMN memberHashes TEXT NOT NULL DEFAULT '{}';",
            "ALTER TABLE SkillBundle ADD COLUMN lockHistory TEXT NOT NULL DEFAULT '[]';",
        ],
    )
)

# Skill maintenance: a per-VERSION pin flag (Milestone 1). Pinning is orthogonal
# to the lifecycle state machine — a pinned skill is exempt from EVERY automatic
# maintenance transition (staleness/archive) but can still be enabled/disabled by
# an operator. It is per-version state, so it survives a reopen and is not reset by
# a reload. Additive/idempotent; existing rows read NULL → not pinned.
MIGRATIONS.append(
    (
        22,
        [
            "ALTER TABLE SkillVersion ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;",
        ],
    )
)

# Skill-maintenance ledger (Milestone 1). Mirrors the MemoryMaintenance pattern
# (one observable row per operation) but is a SEPARATE table keyed by operation
# name so a skill maintenance pass never overwrites the retention sweep's state.
# Additive/idempotent.
MIGRATIONS.append(
    (
        23,
        [
            """
            CREATE TABLE IF NOT EXISTS SkillMaintenance (
              operation     TEXT PRIMARY KEY,
              ranAt         TEXT NOT NULL,
              ok            INTEGER NOT NULL DEFAULT 1,
              inspected     INTEGER NOT NULL DEFAULT 0,
              stale         INTEGER NOT NULL DEFAULT 0,
              archived      INTEGER NOT NULL DEFAULT 0,
              pinnedExempt  INTEGER NOT NULL DEFAULT 0,
              changed       INTEGER NOT NULL DEFAULT 0,
              skipped       INTEGER NOT NULL DEFAULT 0,
              error         TEXT
            );
            """,
        ],
    )
)

# Retire the semantic candidate layer's policy overrides (Milestone 6). The layer
# and its `semantic_conflict_*` / `semantic_recall_tiebreak` keys were removed, so
# any stored override for those keys is dead. Delete them (they can no longer be
# set or read), recording the removal in the same migration-audit table the
# earlier legacy-key resets used, so the cleanup is observable. Additive and
# idempotent: a pre-change database still opens with no data loss.
MIGRATIONS.append(
    (
        24,
        [
            """
            INSERT INTO MemoryPolicyMigration (key, previousValue, reason, resetAt)
              SELECT key, value,
                     'semantic candidate layer removed; key retired',
                     strftime('%Y-%m-%dT%H:%M:%SZ','now')
              FROM MemoryPolicy
              WHERE key IN (
                'semantic_conflict_enabled',
                'semantic_conflict_threshold', 'semantic_conflict_backend',
                'semantic_conflict_max_candidates', 'semantic_conflict_max_index',
                'semantic_conflict_timeout_ms', 'semantic_conflict_diagnostics',
                'semantic_recall_tiebreak'
              );
            """,
            """
            DELETE FROM MemoryPolicy
              WHERE key IN (
                'semantic_conflict_enabled',
                'semantic_conflict_threshold', 'semantic_conflict_backend',
                'semantic_conflict_max_candidates', 'semantic_conflict_max_index',
                'semantic_conflict_timeout_ms', 'semantic_conflict_diagnostics',
                'semantic_recall_tiebreak'
              );
            """,
        ],
    )
)

# Cross-process maintenance lease (Phase 4). A single-row table holding the
# holder + expiry of the CURRENT maintenance pass, so two PROCESSES (not just two
# threads) cannot run a sweep concurrently. In-process locking alone is
# insufficient if the runtime is ever started twice against one database. The
# lease is advisory via SQLite's own row locking; an expired/stale lease is
# reclaimable. Additive/idempotent; a pre-change database opens with no data loss.
MIGRATIONS.append(
    (
        25,
        [
            """
            CREATE TABLE IF NOT EXISTS MaintenanceLease (
              id        INTEGER PRIMARY KEY CHECK (id = 1),
              holder    TEXT NOT NULL,
              acquiredAt TEXT NOT NULL,
              expiresAt TEXT NOT NULL
            );
            """,
        ],
    )
)

# Failure Intelligence & Adaptive Recovery (spec §18). Durable incidents and
# recovery attempts. This is AGENT memory (what Eclipse learned about its own
# failures), so it lives in eclipse-memory.db — never in jdds.db (market data)
# and never in agent-memory.db (run traces). One incident per stable failure
# signature; attempts are the ordered history. Append-mostly, additive, and a
# pre-change database opens with no data loss.
MIGRATIONS.append(
    (
        26,
        [
            """
            CREATE TABLE IF NOT EXISTS RecoveryIncident (
              id              TEXT PRIMARY KEY,
              signature       TEXT NOT NULL,
              kind            TEXT NOT NULL,
              retryability    TEXT NOT NULL,
              code            TEXT,
              subsystem       TEXT,
              source          TEXT,
              message         TEXT,
              taskId          TEXT,
              runId           TEXT,
              status          TEXT NOT NULL DEFAULT 'open',
              occurrenceCount INTEGER NOT NULL DEFAULT 1,
              attempts        INTEGER NOT NULL DEFAULT 0,
              decision        TEXT,
              metadata        TEXT,
              firstSeenAt     TEXT NOT NULL,
              lastSeenAt      TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_recovery_inc_signature ON RecoveryIncident(signature);",
            "CREATE INDEX IF NOT EXISTS idx_recovery_inc_status    ON RecoveryIncident(status);",
            "CREATE INDEX IF NOT EXISTS idx_recovery_inc_task      ON RecoveryIncident(taskId);",
            """
            CREATE TABLE IF NOT EXISTS RecoveryAttempt (
              id          TEXT PRIMARY KEY,
              incidentId  TEXT NOT NULL,
              attemptNo   INTEGER NOT NULL,
              action      TEXT NOT NULL,
              strategy    TEXT,
              reason      TEXT,
              backoffMs   INTEGER NOT NULL DEFAULT 0,
              outcome     TEXT NOT NULL DEFAULT 'planned',
              detail      TEXT,
              createdAt   TEXT NOT NULL,
              FOREIGN KEY (incidentId) REFERENCES RecoveryIncident(id) ON DELETE CASCADE
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_recovery_att_incident ON RecoveryAttempt(incidentId);",
        ],
    )
)

# Root-cause diagnosis (spec §3). One diagnosis per incident, so it is its own
# idempotent table (`CREATE TABLE IF NOT EXISTS`) rather than an ALTER — every
# migration here must be safe to re-run against a database that already has it.
MIGRATIONS.append(
    (
        27,
        [
            """
            CREATE TABLE IF NOT EXISTS RecoveryDiagnosis (
              incidentId TEXT PRIMARY KEY,
              diagnosis  TEXT NOT NULL,
              updatedAt  TEXT NOT NULL,
              FOREIGN KEY (incidentId) REFERENCES RecoveryIncident(id) ON DELETE CASCADE
            );
            """,
        ],
    )
)

# Recovery operation ledger (spec §5.2, §9.3). Durable, idempotency-keyed tracking
# of a side-effecting recovery action so a crash mid-repair can reconcile instead
# of repeating the effect, and a failed repair can be compensated. Idempotent DDL.
MIGRATIONS.append(
    (
        28,
        [
            """
            CREATE TABLE IF NOT EXISTS RecoveryOperation (
              id                 TEXT PRIMARY KEY,
              idempotencyKey     TEXT NOT NULL UNIQUE,
              kind               TEXT NOT NULL,
              status             TEXT NOT NULL DEFAULT 'begun',
              incidentId         TEXT,
              request            TEXT,
              result             TEXT,
              compensatingAction TEXT,
              createdAt          TEXT NOT NULL,
              updatedAt          TEXT NOT NULL
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_recovery_op_incident ON RecoveryOperation(incidentId);",
            "CREATE INDEX IF NOT EXISTS idx_recovery_op_status   ON RecoveryOperation(status);",
        ],
    )
)

# Autonomy durability + coordination (spec §9.4, §17). Three additive, idempotent
# tables: the persisted operator envelope (autonomy survives a restart), a
# per-signature repair lease (two workers never repair the same root cause at once),
# and one-off operator approvals (authorize an out-of-envelope action for one
# incident). `CREATE TABLE IF NOT EXISTS` only — safe to re-run.
MIGRATIONS.append(
    (
        29,
        [
            """
            CREATE TABLE IF NOT EXISTS AutonomyEnvelope (
              id        INTEGER PRIMARY KEY CHECK (id = 1),
              payload   TEXT NOT NULL,
              updatedAt TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS RecoveryLease (
              signature TEXT PRIMARY KEY,
              holder    TEXT NOT NULL,
              expiresAt TEXT NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS RecoveryApproval (
              id         TEXT PRIMARY KEY,
              incidentId TEXT NOT NULL,
              strategy   TEXT NOT NULL,
              approvedBy TEXT,
              approvedAt TEXT NOT NULL,
              UNIQUE(incidentId, strategy)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_recovery_approval_incident ON RecoveryApproval(incidentId);",
        ],
    )
)

# Migration 30 — the learning-research capability's durable slice of
# eclipse-memory.db. A learner's roadmap, per-node progress, and durable
# learning preferences live here — NOT in jdds.db (market data) and NOT in
# agent-memory.db (run/event/tool traces). `CREATE TABLE IF NOT EXISTS` only.
MIGRATIONS.append(
    (
        30,
        [
            """
            CREATE TABLE IF NOT EXISTS LearningPath (
              id               TEXT PRIMARY KEY,
              goal             TEXT NOT NULL,
              startLevel       TEXT,
              targetCompetency TEXT,
              version          INTEGER NOT NULL DEFAULT 1,
              status           TEXT NOT NULL DEFAULT 'active',
              payload          TEXT NOT NULL,
              createdAt        TEXT NOT NULL,
              updatedAt        TEXT NOT NULL,
              lastAccessedAt   TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS LearningNodeProgress (
              id         TEXT PRIMARY KEY,
              pathId     TEXT NOT NULL,
              nodeId     TEXT NOT NULL,
              status     TEXT NOT NULL DEFAULT 'pending',
              assessment TEXT,
              updatedAt  TEXT NOT NULL,
              UNIQUE(pathId, nodeId)
            );
            """,
            "CREATE INDEX IF NOT EXISTS idx_learning_node_path ON LearningNodeProgress(pathId);",
            """
            CREATE TABLE IF NOT EXISTS LearningPreference (
              key       TEXT PRIMARY KEY,
              value     TEXT NOT NULL,
              updatedAt TEXT NOT NULL
            );
            """,
        ],
    )
)

# Migration 31 — RSL adopted lessons. A `LearningCandidate` can now be a
# verified lesson with a retrieval cue and an immutable adoption record. The
# cue/lesson/evidence gate and the verdict tripwire live in
# `self_improvement/lessons.py`; retrieval requires the recorded validation run
# to have completed before the lesson can enter a later prompt. Additive only:
# existing rows read NULL ("not an adopted lesson").
MIGRATIONS.append(
    (
        31,
        [
            "ALTER TABLE LearningCandidate ADD COLUMN cue TEXT;",
            "ALTER TABLE LearningCandidate ADD COLUMN adoptedArtifactType TEXT;",
            "ALTER TABLE LearningCandidate ADD COLUMN adoptedArtifactId TEXT;",
            "ALTER TABLE LearningCandidate ADD COLUMN validationRunId TEXT;",
            "CREATE INDEX IF NOT EXISTS idx_learning_cue ON LearningCandidate(cue);",
        ],
    )
)

# The current schema version = the highest migration number.
SCHEMA_VERSION = max(version for version, _ in MIGRATIONS)

__all__ = ["MIGRATIONS", "SCHEMA_VERSION"]

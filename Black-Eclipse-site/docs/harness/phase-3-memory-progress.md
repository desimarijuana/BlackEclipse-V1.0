---
title: Harness Phase 3-M — Eclipse-Memory
status: Complete
last-verified: 2026-09-22
---

# Phase 3-M — Eclipse-Memory: Dedicated Memory, Skills & Controlled Self-Improvement

**Phase:** 3-M (memory rebuild)
**Status:** Complete (foundation → UI → verification)
**Last updated:** 2026-09-22

Source of truth for the eclipse-memory work. Milestone 0's audit (root cause)
is retained below; the implementation sections follow.

---

## Root cause (from the Milestone 0 audit)

1. **The system prompt promised tools that did not exist.** `prompts.py` told
   the model it had a `memory` tool, `skill_view`, `skill_manage`, `terminal`,
   `read_file`, `search_files`, `execute_code`, `web_search`, and a foreign 40+
   entry skill catalog. The registry had none of them.
2. **Memory had no runtime path in or out.** No tool, no route, nothing called
   `remember()`; `graph.execute_run` never recalled memory. `AgentMemory` was 0
   rows after 84 runs.
3. **Skills were not connected to the runtime** — reachable only from the UI.
4. **The learning loop was never triggered** in normal use.
5. **No memory typing/scope/evidence/relevance/supersession pipeline.**
6. **Four competing "memory" stores** (localStorage, Prisma research memory,
   `agent-memory.db`, `.black-eclipse/sessions`).

## Objective

A dedicated, reliable SQLite subsystem — **eclipse-memory** — as the central
persistence and control layer for agent memory, skills, learning, evaluations,
corrections, mistakes and controlled self-improvement, integrated with the
Phase-1 runtime and Phase-2 retrieval.

---

## Milestone checklist

| # | Milestone | Status |
|---|---|---|
| 0 | Audit + diagnosis | ✅ Done |
| 1 | Eclipse-memory foundation (db, migrations, health, isolation) | ✅ Done |
| 2 | Memory storage + retrieval pipelines + runtime integration | ✅ Done |
| 3 | Skill registry in eclipse-memory (migrated from agent-memory) | ✅ Done |
| 4 | Execution + event integration | ✅ Done |
| 5 | Learning engine (failures, corrections, candidates, dedupe) | ✅ Done |
| 6 | Skill draft generation | ✅ Done (Phase 3, now in eclipse-memory) |
| 7 | Evaluation + promotion + rollback | ✅ Done (Phase 3, now in eclipse-memory) |
| 8 | UI — Memory Control Room | ✅ Done |
| 9 | Workflow-ready contract | ✅ Done (Phase 3 contract retained) |
| 10 | Verification | ✅ Done |

---

## Architecture decisions

- **Separate database** `eclipse-memory.db`, stdlib `sqlite3`, idempotent list
  migrations recorded in `SchemaMigration`. No Prisma (one SQLite access
  library across the runtime, matching `harness/persistence.py`).
- **One service owns the DB.** `EclipseMemoryService` wraps `EclipseMemoryStore`;
  nothing else opens `eclipse-memory.db`.
- **Source of truth — Option C (hybrid).** Built-in skill *definitions* stay as
  files in `python/harness/skills/library/` (reviewable, git-versioned); all
  runtime state (skills, versions, lifecycle, evaluations, memories, candidates,
  corrections, mistakes, promotions, audit) lives in `eclipse-memory.db`. The
  loader computes a per-version `contentHash`, so a file/DB divergence is
  detectable.
- **One skill registry.** The Phase-3 `harness.skills.store.SkillStore` is now a
  compatibility alias for `EclipseMemoryStore`; the Phase-3 skill tables were
  migrated out of `agent-memory.db` by a one-time, idempotent, non-destructive
  import (source rows left in place for rollback).
- **Default-deny, code-enforced permissions unchanged.** Memory instructions and
  skill prose are data, never a boundary.
- **Prompt corrected to reality.** The system prompt now names only real tools
  and states plainly that creation/evaluation/promotion of skills is
  operator-gated.

## Database location / configuration

- Path: `ECLIPSE_MEMORY_DB_PATH` → else `<repo root>/eclipse-memory.db`, where
  repo root is the directory containing `python/` (NOT the process working
  directory). This was changed in the Phase 3-M Reliability fix: the previous
  `<cwd>` default meant a runtime launched from `python/` read/wrote a different
  memory store than one launched from the repo root (`eclipse_memory/config.py`
  `repo_root()` / `default_db_path()`).
- **Legacy reconciliation.** On open of the stable default, if it is empty, rows
  are copied forward from a legacy `<cwd>`/`python/eclipse-memory.db` via
  `INSERT OR IGNORE`. The source is never deleted or modified; a populated
  stable database skips reconciliation (`db.reconcile_legacy()`).
- `.gitignore` ignores `eclipse-memory.db*` (runtime state, like
  `agent-memory.db`).
- `GET /eclipse-memory/health` reports integrity + migration status; `GET
  /health` reports the resolved path + a non-secret identity (path hash) so a
  cwd mismatch is observable (`eclipse_memory/config.py` `db_identity()`).

## Schema (eclipse-memory.db)

Memory: `MemoryRecord`, `MemoryEvidence`, `MemoryLink`, `MemoryRetrievalEvent`,
`MemoryEvent`, `MistakeRecord`, `CorrectionRecord`.
Skills: `Skill`, `SkillVersion`, `SkillDependency`, `SkillToolRequirement`,
`SkillPermissionRequirement`, `SkillExecution`, `SkillEvaluation`,
`SkillEvaluationCase`, `LearningCandidate`, `SkillPromotionRequest`,
`SkillReview`, `SkillEvent`.
Bookkeeping: `SchemaMigration`.

## Memory behavior

- **Write pipeline** (`service.write_memory`): validate type → validate content
  → validate source (only explicit-user / correction / execution-lesson /
  system-decision / verified-source / skill-promotion / mistake / manual) →
  force preferences into user scope → dedupe by signature → persist → event.
  A rejected write is an error, never a silent success.
- **Proposed memory** (status `proposed`) is inert; retrieval excludes it until
  reviewed.
- **Retrieval pipeline** (`retrieval.retrieve_memories`): candidate search →
  scope/status/permission filter (superseded/archived/rejected/expired excluded)
  → deterministic ranking (keyword, subject, importance, confidence,
  verification, prior usefulness) → character budget → labelled
  `<memory-context>` block → access counters → audit row. Diagnostics record
  candidates, excluded, reasons, budget, duration.
- **Scope isolation:** a user-scoped actor cannot retrieve another user's
  memory.
- **Injection:** `graph.execute_run` recalls before the turn (scoped to
  `request.userId`) and inserts a non-authoritative `SystemMessage`. A retrieval
  failure emits `memory.retrieval_failed` and never blocks the run.

## Skill storage & lifecycle

Unchanged from Phase 3 (draft → testing → review → validated → enabled;
rejected/disabled/deprecated/superseded/blocked) — now persisted in
`eclipse-memory.db`. Progressive disclosure via `skill_list` (metadata) →
`skill_view` (full instructions). Execution via the existing
`graph.execute_run`. Promotion is operator-gated and evaluation-blocked.

## Learning engine & mistake detection

`analyze_run` (criteria-driven, no model) creates inert candidates for failure
recovery, validation improvement, successful procedure and source-selection
improvement; a failure-recovery candidate also writes a `MistakeRecord`.
Duplicates are suppressed by signature. Corrections are recorded with scope and
never auto-generalized.

## Evaluation & promotion controls

Deterministic, multi-dimensional; mandatory failures block promotion;
`needs_review` does not promote by default; rollback selects a prior version;
all decisions are audited.

## Self-improvement safeguards

- No tool to create/edit/enable a skill or change permissions was added.
- Memory writes require a permitted source; retrieval never overrides system
  instructions.
- Prompt states skills/lifecycle are operator-gated.
- The agent tool allowlist is unchanged except adding the three read-only memory
  tools.
- Tests assert: no self-granting, unvalidated skills stay inert, scope
  isolation, untrusted content cannot widen the allowlist, no fabricated
  improvement claim.

## APIs

Python (`python/harness/main.py`): `/eclipse-memory/health`, `/overview`,
`/memories` (GET/POST), `/memories/{id}`, `/memories/{id}/archive`,
`/memories/{id}/review`, `/retrieve`, `/retrievals`, `/corrections`
(GET/POST), `/mistakes`, `/events`.
Next.js proxies: `src/app/api/eclipse-memory/**` (same `api-guard`; operator
actions re-checked server-side).

## UI

`Eclipse Memory` tab (`src/components/screens/eclipse-memory/`): Overview
(real counts), Memory Explorer (search/filter/detail/evidence/links,
save/review/archive), Activity (retrieval probe diagnostics, corrections,
mistakes), Health. Reuses the frosted-glass system + `TabBar`.

## Follow-up phases (policy + mistake detection)

After the core subsystem, the two gaps identified in review were closed:

- **P1 Policy layer** (`eclipse_memory/policy.py`, migration 2 `MemoryPolicy`):
  configurable behaviour with safe defaults, validated bounds, and **locked
  values** (automatic skill promotion is structurally impossible to enable).
  Retrieval budget/limit/proposed-inclusion now read policy; an explicit caller
  value still wins.
- **P2 Mistake-analysis service** (`eclipse_memory/mistakes.py`): deterministic
  detection of tool_failure, incorrect_tool_arguments, missing_source,
  unsupported_claim, missing_data_undisclosed, invalid_output_schema,
  repeated_failure, unresolved_contradiction, timeout, currency/unit mismatch —
  each with evidence; idempotent per run; never model-guessed.
- **P3 Automatic candidate detection** gated by `auto_candidate_detection` +
  `candidate_confidence_threshold`, wired post-run in `execute_run`. Creates
  inert candidates only; cannot enable a skill or claim improvement.
- **P4 APIs**: `GET/PUT /eclipse-memory/policies`, `POST /eclipse-memory/analyze/{runId}`
  (+ TS proxies).
- **P5 UI**: a **Policies** tab in the Eclipse Memory screen.
- Tests: `python/tests/test_memory_policy.py` (18), plus TS client tests.

## Files created

**Python:** `harness/eclipse_memory/{__init__,config,schema,db,store,service,retrieval}.py`,
`harness/memory_tools.py`, `tests/test_eclipse_memory.py`,
`tests/test_memory_tools.py`.
**TS:** `lib/harness/eclipse-memory-{types,client,browser}.ts` + `…browser.test.ts`,
`components/screens/eclipse-memory/eclipse-memory-screen.tsx`,
`app/api/eclipse-memory/**`.

## Files modified

`python/harness/skills/store.py` (now an alias), `service.py`, `graph.py`,
`tools.py`, `agents.py`, `prompts.py`, `main.py`, `skills/runtime.py`,
`skills/learning.py`; `src/components/layout/sidebar.tsx`,
`src/lib/sidebar/config.ts` (+test), `src/lib/i18n/nav.ts`,
`src/lib/i18n/dictionaries/en.ts`, `src/components/screens/stock-chat.tsx`;
docs.

## Tests executed

| Check | Command | Result |
|---|---|---|
| TS typecheck | `npx tsc --noEmit` | Pass (0 errors) |
| Lint | `npx eslint .` | 0 errors |
| TS tests | `npx vitest run` | 1610 passed (124 files) |
| Python tests | `python -m pytest python` | 251 passed |
| Production build | `npm run build` | Pass |

Phase 1 regression: graph/tools/models tests pass. Phase 2 regression:
retrieval + identity tests pass. Database isolation: `test_eclipse_memory.py`
asserts eclipse-memory contains no HarnessRun/Trade/Price tables and skips
missing legacy files.

## Known limitations

- Retrieval ranking is deterministic/keyword-based, not embedding-based
  (deliberate: no new dependency, explainable diagnostics).
- The legacy import copies skill rows only; it does not delete the originals.
- The Memory Control Room's Save/Review/Archive use the existing operator guard
  (same as Skills); there is no separate accounts system.

## Phase 3-M Reliability & Learning UX (2026-09-24)

Closes the real-world reliability gaps that made memory/skills feel unreliable.

**Verified root causes.**

1. **Unstable DB identity.** `<cwd>/eclipse-memory.db` meant the repo held two
   databases (root: memories+skills; `python/`: skills only, schema v3 vs v4).
   Fixed: repo-rooted default + `ECLIPSE_MEMORY_DB_PATH` override + non-secret
   identity in `/health` + non-destructive legacy reconciliation.
2. **Capture relied on the model calling `memory`.** Added a deterministic
   `eclipse_memory/intent.py` classifier wired pre-model in `graph.execute_run`;
   explicit save/forget/correct are written through `EclipseMemoryService`.
   Refusals (secrets, sensitive IDs, raw dumps, policy overrides) and unclear
   scope are never written.
3. **Auto candidate detection was disabled and manual flow only covered skill
   runs.** Auto-detection is now **on by default** (`auto_candidate_detection`):
   eligible completed runs create inert candidates automatically and the run's
   `memory` blob reports `autoCaptured`/`candidatesCreated`. Added
   ordinary-chat eligibility (`learning_eligibility_for_run`) and kept the
   explicit "Learn from this run" action for cases auto-detection does not cover.
   Candidates stay inert and deduplicated; promotion remains operator-gated.
4. **Drafts were manifest-only.** `skills/draft.py` now generates a complete
   procedure (steps, typed I/O, existing safe tools only, provenance,
   limitations, evaluation cases) while staying inert; no-evidence drafts state
   manual authoring is required.
5. **No controlled skill invocation seam.** Added `skill_invoke` (enabled
   compatible skills only) executing through the existing `execute_skill` with
   `parentRunId` + enforced allowlist/permissions.
6. **UI could not follow outcomes from the originating chat.** Added the
   `memory` blob on `RunResult`/`client.final`, a `MemoryActionPanel`, learning
   eligibility + "Learn from this run", and deep links into the Learning Queue /
   Memory sub-pages.

**APIs added:** `GET /learning/eligibility/{runId}`; `memory` field on
`RunResult`; TS `GET /api/learning/eligibility/[runId]`; `userIntent` on
learning/draft endpoints.

**Tests:** `python/tests/test_phase3m_reliability.py` (31) incl. cross-working-
directory path resolution, legacy reconciliation without deletion, secret/refusal
negatives, forget/correct archive/supersede, usable inert drafts, and controlled
child-run invocation; graph integration tests for the deterministic memory path
and eligibility. `src/lib/chat/memory-action.test.ts` (8).

## Deferred work

- Embedding-assisted ranking behind the existing retrieval seam.
- Cross-version skill regression comparison.
- Promoting the remaining Phase-3 UI sections (draft review) under Eclipse
  Memory if desired (they already exist under Skills).
- Semantic mistake categories (hallucinated metric) beyond the deterministic
  signals present today.

## Completion status

All milestones complete. No feature is scaffolded-only: each is exercised by a
test or a real endpoint. Nothing claims to have learned unless a record was
persisted.

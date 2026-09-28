---
title: Harness Phase 3-M — Eclipse-Memory
status: Complete
last-verified: 2026-09-26
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

## Retrieval evaluation (measurement seam)

`eclipse_memory/eval/` is a small, versioned, human-labeled set
(`dataset_v1.json`) plus a runner. It seeds a fresh temp `eclipse-memory.db` from
the corpus and runs the REAL `EclipseMemoryService.retrieve` for each case,
reporting recall, topical precision, scope leakage, forbidden hits, no-match
cleanliness and context-budget behaviour. Recorded baseline (dataset v1):
**recallSupported 1.0, precision ≥0.667, scope leakage 0, forbidden hits 0**. Run
it with `python -m harness.eclipse_memory.eval`. A deterministic **lexical
relevance gate** stops an off-domain/near-match query from recalling a topical
memory that shares no keyword/subject signal; matching is on **word boundaries**
(a query token `use` must not match `User`); standing user rules
(`preference`/`constraint`) are exempt because they are intentional per-turn
personalization. Scope, status and privacy filtering remain authoritative —
semantic similarity is never used and never authorizes access.

The set also carries a labeled **synonym-paraphrase** slice (a paraphrase that
shares no lexical term, e.g. "which money should accounts be denominated in?"
vs "reporting currency … PKR"). It is reported **per kind** so the lexical
retriever's known limitation is measured rather than hidden (currently 1/2). No
semantic dependency is added until a labeled set demonstrates the need; the eval
is the evidence, and `recallSupported` (the exact+paraphrase slice the retriever
is designed to serve) stays at 1.0.

## API authorization (memory + skills)

Every memory/skill MUTATION endpoint requires proof of operator authorization by
transport or token, not a body boolean: the FastAPI `require_operator`
dependency accepts a loopback caller (the Next.js front door / local operator) or
the runtime secret (`X-Harness-Operator` / `Bearer`). The front-door clients
forward the runtime secret so the front door's trusted decision is what reaches
Python. Reads stay open. This closes the bypass where a directly reachable
runtime could self-authorize by sending `{"operator": true}`. Tests:
`test_memory_api_auth.py`. Suggestion accept/dismiss additionally refuse a
suggestion owned by another scope (`test_suggestion_api_scope.py`), and listing
can be narrowed with `?scopeId=`.

## Skill-execution observability

`SkillExecution` (migration 9) carries `outputValidated` (tri-state: true/false/
null-not-recorded) and bounded `metrics` (toolCalls, toolErrors, modelSteps,
totalTokens). The Skills › Execution Activity panel shows the pinned version,
manifest identity, validation result, tool usage, warnings, missing data,
limitations and evidence. Secrets are never part of a trace payload.

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
   runs.** Auto-detection was later unified into the `skill_learning_mode` (see
   the "Memory selectivity" and "Unified learning lifecycle" sections below);
   eligible completed runs create inert candidates automatically and the run's
   `memory` blob reports `autoCaptured`/`candidatesCreated`. Added
   ordinary-chat eligibility (`learning_eligibility_for_run`). Candidates stay
   inert and deduplicated; an implicit `successful_procedure` additionally
   requires recurrence evidence, and promotion remains operator-gated.
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

## Memory selectivity — stop over-saving (2026-09-24)

**Brief.** Eclipse retained too much: incidental preferences, one-off
instructions and even financial figures became durable memory. Make memory
retain only information likely to improve future sessions.

**Reproduced cause (temp-DB fixture, never the user's runtime DB).** Feeding nine
ordinary turns through the deterministic path saved five durable records:
"I prefer concise answers" → `save`; "Always use X for this task" → `save`;
"Current price of AAPL is 190, save this" → `save` (a financial fact). Defaults
`auto_capture_enabled` and `auto_candidate_detection` were `True`, and the model
`memory` tool called `service.write_memory` directly with no check against the
actual user message — a model sentence could become memory on its own.

**The shared gate.** `eclipse_memory/decision.py` is now the ONE authorization
seam, with exactly four outcomes — `save`, `suggest`, `run_only`, `ignore`:

- `decide_turn` handles one user turn (used pre-model by `graph.execute_run` via
  `EclipseMemoryService.decide_turn` → `commit_decision`). Explicit
  save/forget/correct commands are always honoured when safe and clear; a
  one-off ("for this task") is `run_only`; a casual durable mention is at most a
  suggestion; financial facts are `ignore`.
- `authorize_proposal` handles proposed writes (the model `memory` tool, UI save,
  corrections, run analysis). A model proposal is re-checked against the actual
  user turn: it can `save` only when the turn carried explicit save intent;
  otherwise it is downgraded to `suggest`/`ignore`. Tool output, retrieved
  memory, documents and web content are never user intent.
- Privacy rules (secrets/credentials, sensitive IDs, raw dumps, policy-override
  attempts) are enforced in the gate for every path, and the refused content is
  never written to events/diagnostics.

**Explicit controls preserved.** "Remember/save this" still works through the
separate explicit-intent path even while automatic capture is off. "Forget this"
archives the target; "correct this" supersedes + links it — history is never
hard-deleted.

**Policy + migration.** `auto_capture_enabled`, `auto_candidate_detection` and
the new `auto_suggest_enabled` default **off**. Migration 5 deletes a persisted
unsafe `true` override for the two pre-existing keys (recording the reset in
`MemoryPolicyMigration`, surfaced by health/policy UI); every other override and
all existing records are preserved. A code-default change alone would have left a
stored `true` in force.

> **Superseded by "Unified learning lifecycle" (below).** The off-by-default
> three-boolean model was itself replaced: automatic learning is now a single
> mode (`memory_mode`/`skill_learning_mode`, default `automatic_selective`) with
> the booleans derived. Migration 7 removes any stored boolean rows. This
> paragraph is retained for history; the mode model is authoritative.

**Suggestions.** A `MemorySuggestion` (migration 6) is an inert, never-recalled
proposal with a quiet Save/Dismiss control. Accepting writes exactly one scoped
memory through the gate; dismissing is retained so the same item is not
re-offered. APIs: `GET /eclipse-memory/suggestions`, `POST
/eclipse-memory/suggestions/{id}/accept|dismiss` (+ TS proxies + a Suggestions
tab in the Memory Control Room). The chat `memory` blob gains a `suggested`
outcome that renders as "Not saved — suggestion".

**Lifecycle / recall.** Recall now renders type, scope, provenance, confidence,
verification and time where available, excludes low-confidence unverified rows,
and keeps user/project/market scopes isolated. `list_memories` accepts a
`source` filter so records produced by the old over-broad defaults can be found
by provenance and reviewed/archived (never auto-deleted).

**Storage budget (truthful "memory is full").** `max_memories` policy
(default `0` = unlimited) caps ACTIVE memories. When full, a *new* unique save
raises `MemoryFullError` / returns a `memory_full` outcome — the system never
auto-deletes user memory to make room. Inert history (archived/superseded/
proposed) does not consume the budget; a duplicate re-save and an explicit
correction (which supersedes in place) are exempt. The state is exposed via
`memory_budget()` on `GET /eclipse-memory/health` and the `/policies` response
(`budget`), shown in the Memory Control Room Policies tab, and rendered as a
"Memory is full — not saved" chat action.

**Tests.** `python/tests/test_memory_selectivity.py` (34) exercises the actual
write paths: explicit save saves exactly one scoped record; casual preference
does not save (suggestion only when enabled, never recalled); one-off instruction
does not save; greetings/Q&A/multi-step tool runs create nothing; financial facts
via chat and via the model tool are rejected; the model tool cannot self-
authorize; forget/correct target with supersession and ask when ambiguous;
duplicates do not accumulate; secrets/injection rejected without storing content;
a gate failure does not fail chat; explicit "turn into a skill" creates an inert
candidate only; scope isolation + recall survive a reopen; the storage budget
fails truthfully without deleting; and decision-quality fixtures report
false-save and missed-explicit-save rates separately (both zero). Updated
`test_memory_policy.py` (defaults + migration-5 test), `test_memory_tools.py`,
`test_phase3m_reliability.py`.

**Checks.** Python **572 passed**; Vitest **1716+ passed**; `npx tsc
--noEmit` reports 0 errors in the changed files (two pre-existing errors remain in
the concurrent `src/lib/regime/` work, unrelated to this change).

**Files:** new `python/harness/eclipse_memory/decision.py`,
`python/tests/test_memory_selectivity.py`,
`src/app/api/eclipse-memory/suggestions/route.ts`; modified
`eclipse_memory/{intent,policy,schema,store,service,retrieval}.py`,
`harness/{graph,main,memory_tools,tools}.py`, `src/lib/harness/eclipse-memory-*`,
`src/components/screens/eclipse-memory/eclipse-memory-screen.tsx`,
`src/lib/chat/memory-action.ts` + panel.

## Unified learning lifecycle — one mode, selective by default (2026-09-24)

**Brief.** Learn selectively and automatically when the evidence is strong — do
not save everything, and do not repeatedly ask whether to learn. Keep
conversation history, durable memory and skills distinct.

**Verified root causes (this pass).**

1. **No coherent learning mode.** Three independent booleans
   (`auto_capture_enabled`, `auto_suggest_enabled`, `auto_candidate_detection`)
   all defaulted **off**, so automatic learning never happened and the product
   could only ever prompt. There was no `automatic_selective` /
   `ask_before_saving` / `off` model.
2. **Vocabulary gap.** The gate emitted `run_only`; the required lifecycle
   distinguishes `history_only` (searchable conversation/run history) from
   `ignore`.
3. **Explicit skill request was a dead end.** `decide_turn(action="skill")` only
   emitted `memory.skill_requested`; no candidate/draft was created, so the user
   had to repeat the request through a separate "Learn from this run" button.
4. **Implicit skill learning fired on one-off runs.** A single multi-step run
   produced a `successful_procedure` candidate, and ordinary eligibility marked
   any tool-using run "eligible", making the chat panel offer to learn on
   ordinary runs.
5. **Repeated prompt.** The chat panel rendered a learn button for every eligible
   run.
6. **Contradictory docs.** ADR-H35 said automatic detection default **on**;
   ADR-H37 said **off**.

**The unified mode.** `policy.py` now defines two mode keys —
`memory_mode` and `skill_learning_mode`, each `automatic_selective` (default) |
`ask_before_saving` | `off`. The legacy booleans are **derived** from the modes
(`derived_flags`): they are neither stored nor settable, so they cannot drift.
Migration 7 records and removes any stored legacy boolean rows. The default is
consistent across policy code, persisted settings, migrations, the API, the UI,
tests and docs.

**Selective automatic learning.** In `automatic_selective`, `decide_turn` saves
a direct user preference (`I prefer …`) on first statement; a project convention
(`always use …`) is saved only with recurrence evidence (the same statement seen
before), otherwise it is `history_only` — never a prompt. One-off task details,
questions, greetings and financial/market figures are `history_only`/`ignore`.
`ask_before_saving` stages an inert suggestion; `off` creates nothing. Explicit
remember/forget/correct remain a separate always-on path, and secrets/sensitive
identifiers are refused for every path.

**Persisted recurrence (limitation closed).** Recurrence evidence is now
persisted, not derived only from the bounded chat-history window, so a convention
or workflow repeated across sessions/after the window is still recognized:

- Memory conventions: `MemoryRecurrence` (migration 8) in `eclipse-memory.db`
  stores one bounded row per normalized **signature** (a digest — the raw text is
  never stored) with a seen-count; `EclipseMemoryService.decide_turn` reads it
  before deciding and records after, and `store._prune_recurrence` caps the table.
- Skill workflows: `LearningRecurrence` + `LearningRecurrenceRun` in
  `agent-memory.db` store a seen-count per tool-evidence signature and the set of
  contributing runs, so `skills.learning._recurrence_count` is a single indexed
  lookup instead of an O(recent-runs) scan and re-analysing the same run does not
  inflate the count. The bounded scan remains only as a fallback (combined with
  the ledger via `max`, never double-counted).

**Skills are separate.** An explicit "turn this into a skill" request now
creates a real inert candidate + draft through `capture_from_run` +
`propose_draft` at run completion — no second click. An implicit
`successful_procedure` candidate requires recurrence evidence; a failure
recovery or validation failure remains strong single-run evidence. Nothing is
ever enabled; evaluation + operator approval gate promotion.

**UI.** The chat panel shows a learning line only for a genuine automatic
capture or an explicit draft; a merely eligible run shows nothing, and the
repeated "Learn from this run?" button is replaced by a one-off "Create skill
draft" for an uncaptured explicit request. The Policies tab renders the two mode
keys as labelled selectors with plain-language hints; the derived booleans are
hidden.

**Tests.** New/updated Python coverage in `test_memory_selectivity.py`,
`test_memory_policy.py`, `test_phase3m_reliability.py`, `test_skills_learning.py`,
`test_skills_scenarios.py` (positive + negative: durable preference saved
automatically; explicit remember works regardless of mode; one-off task and
changing market value not saved; recurrence saves without confirmation and
survives a restart; duplicate and correction behaviours; sensitive content
refused; project scope isolation; a single eligible run creates no skill; an
explicit request creates a pending draft; repeated workflow yields a controlled
candidate; re-analysis does not inflate recurrence; no repetitive prompt).
TS `memory-action.test.ts` covers the draft-ready presentation.

**Checks.** Python **697 passed** (one unrelated pre-existing failure in
`test_graph.py` caused by the concurrent `prompts.py` edit removing "Black Orbit
Technologies"); Vitest **1732 passed**; `npx tsc --noEmit` clean.

**Files:** `eclipse_memory/{policy,decision,intent,schema,service}.py`,
`harness/{graph,memory_tools}.py`, `skills/learning.py`,
`src/lib/chat/memory-action.ts` (+ test), `src/lib/harness/types.ts`,
`src/components/chat/memory-action-panel.tsx`,
`src/components/screens/eclipse-memory/eclipse-memory-screen.tsx`; docs:
`harness/decisions.md` (ADR-H43, ADR-H35/H37 corrected), `NAVIGATION.md`,
`harness/architecture.md`, this file.

## Memory Maturity — local personal memory (2026-09-25)

**Brief.** Make Eclipse-Memory a mature local, single-user personal memory
system: explicit lifecycle, deterministic contradiction handling, better
paraphrase retrieval, operator-visible explanations, safe export/import/backup/
reset, richer privacy policy, measured skill quality, and honest failure
behaviour. The architecture is unchanged: one `eclipse-memory.db`, one
`EclipseMemoryService`, one decision gate, one retrieval seam, the same UI and
APIs. `userId`/`scopeId` remain local labels, not security identities.

**Phase 0 — baseline.** `docs/harness/memory-maturity-baseline.md` records the
pre-change architecture, the eval metrics, and the seven code-located gaps.
Baseline eval (dataset v1, 15 cases): recall 0.900, precision 0.714,
synonym-paraphrase 0.500, forbidden 0, leakage 0, no-match clean, 0 over-budget.

**Phase 1 — lifecycle & temporal state.** Migration 10 adds `lastConfirmedAt`,
`lastUsedAt`, `lastReviewedAt`, `authority` (`explicit`/`automatic`),
`statusReason`. `write_memory` now persists `expiresAt` (a latent bug — it was
accepted and dropped). Re-stating a fact refreshes `lastConfirmedAt` instead of
duplicating. `record_access` also stamps `lastUsedAt`. New store helpers:
`confirm_memory`, `restore_memory`, `mark_reviewed`, `memory_lifecycle_counts`,
`list_lifecycle_memories`. Retention (`retention_days`) is applied by
`expire_due_memories` and only ever marks **automatic** memories `expired` —
explicit memories are never silently expired. Nothing is hard-deleted.

**Phase 2 — contradiction & replacement.** `conflicts.py` is a deterministic
lexical detector (replacement-language patterns + opposing-polarity pairs +
same-subject/overlap). `write_memory` resolves a conflict before creating a
second active truth: explicit replacement supersedes the old record(s) (linked,
retained); an ambiguous contradiction stores the new statement inert (`proposed`)
so it is visible for review, and the existing active record keeps authority.
Scope isolation is authoritative — different scopes never conflict. Retrieval
gains a safety net (`_highest_authority_only`) so legacy/manually-edited
contradictory rows recall only the highest-authority, most-recent truth.

**Phase 3 — retrieval & paraphrase.** `normalize.py` adds human-reviewed synonym
groups, light plural stemmming, subject aliases, and bounded (edit-distance-1,
length ≥6) typo tolerance. `_score` matches on word boundaries through
normalization; fuzzy matching runs per-token so a generic exact hit cannot mask a
misspelled topical token. The labeled set grew from 15 to 21 cases (typo,
multi-turn, ambiguous, conflict, expired, risk-paraphrase). **Semantic retrieval
was deliberately NOT added** — the deterministic retriever now scores
synonym/typo at 1.0 and the release-threshold gate (`THRESHOLDS`,
`check_thresholds`) fails on any forbidden hit / scope leak / no-match overreach.

**Phase 4 — explanations & Control Room.** `service.explain_memory` states why a
memory exists (save reason from provenance) and its recall disposition.
`GET /eclipse-memory/memories/{id}` carries it; `GET /eclipse-memory/lifecycle`
exposes counts + named views (active, never-used, frequently-recalled, automatic,
expired, superseded/conflicts, rejected, archived). The UI gains a **Lifecycle**
tab and explanation panels; new deep links `memory.lifecycle`/`memory.policies`.

**Phase 5 — export / import / backup / reset.** `transfer.py`: readable versioned
JSON export; validated import that runs every record through the SAME decision
gate + `write_memory` (privacy rules apply) with `imported` provenance and
duplicate/idempotent handling; atomic backup (temp + rename, never overwrites);
stronger `database_health` (integrity + foreign-key + free-page ratio); reset
requires explicit `confirm`, backs up first, and clears ONLY the memory domain
(skills and unrelated tables survive). Endpoints + front-door proxies + a
Health/Transfer UI panel.

**Phase 6 — policy & privacy.** New policy keys: `memory_enabled` (hard off — no
memory at all, even explicit), `memory_in_diagnostics`,
`semantic_indexing_enabled` (recorded intent; changes nothing today),
per-category `capture_policy`/`recall_policy` (allow/suggest/deny — can only
tighten). All are validated/bounded; recall policy is applied after the
authoritative scope/status filter. Safety floors (secrets, credentials, dumps,
financial facts, no auto-promotion) hold under every setting.

**Phase 7 — learning & skill quality.** `skill_quality.py` derives success/
failure, output-validation, tool-budget-failure, duration/tool-call metrics and
an advisory usefulness score + deprecation recommendation from real
`SkillExecution` rows; `compare_versions` detects cross-version regression;
`promotion_evidence` assembles operator-readable evidence and states it is
advisory only. Endpoints added. Promotion stays evaluation + operator gated.

**Phase 8 — reliability.** Busy timeout on open; `integrity_ok`; retrieval/
policy-read failures are diagnostics, not crashes; import rejects malformed
records with reasons; interrupted backup leaves no partial file; a refused write
returns an honest outcome (the model is never told it was saved); memory being
unavailable yields a truthful 503 / "memory unavailable".

**Phase 9 — verification.** From `Black-Eclipse-site`:

| Check | Result |
|---|---|
| `npm run test` (vitest + python) | Vitest **1742 passed** (136 files); Python **841 passed** |
| `npx tsc --noEmit` | 0 errors |
| `python -m harness.eclipse_memory.eval` | gate **PASS** |

**Retrieval metrics — before → after.** recall 0.900 → **1.000**; precision
0.714 → **0.727**; synonym-paraphrase 0.500 → **1.000**; typo 0.000 → **1.000**;
forbidden hits 0 → 0; scope leakage 0 → 0; no-match clean → clean; over-budget
0 → 0.

**Migrations added.** Migration 10 (`MemoryRecord` lifecycle columns). Additive
and idempotent; a pre-v10 database opens and gains the columns without data loss
(covered by `test_migration_from_existing_v9_database_preserves_rows`).

**Semantic retrieval.** Deliberately deferred. No embeddings, no network service,
no new dependency. The labeled eval is the gate; it currently shows no measured
need, and `semantic_indexing_enabled` exists only to record operator intent.

**Known limitations.** Contradiction detection is lexical (a paraphrase with no
shared token and no replacement language can be missed); the synonym table is
small and human-reviewed (an unlisted pair is a miss); skill usefulness metrics
are per-version aggregates with no time weighting.

**Files.** New: `eclipse_memory/{conflicts,normalize,transfer,skill_quality}.py`;
tests `test_memory_{lifecycle,conflicts,retrieval_normalization,explanations_api,
transfer,privacy_policy,reliability}.py`, `test_skill_quality.py`. Modified:
`eclipse_memory/{schema,db,store,service,retrieval,policy}.py`,
`harness/main.py`; TS `eclipse-memory-{types,client,browser}.ts` (+ test),
`eclipse-memory-screen.tsx`, `src/lib/search/registry.ts`, new API routes
`eclipse-memory/{lifecycle,export,import,backup,database-health,reset,...}`.
Docs: this file, `memory-maturity-baseline.md`, `architecture.md`,
`NAVIGATION.md`, `DECISIONS.md` (ADR-H49), `CHANGELOG.md`.

## Retention & contradiction hardening (2026-09-25)

A follow-up made the two least-production-ready areas safe for the local
single-user product. Full audit + resolved-gap list:
`docs/harness/memory-retention-conflict-audit.md`.

**Retention is now automatic and observable.** The sweep runs at runtime startup
through the existing FastAPI lifespan (`main._lifespan` → `AgenticService.
run_startup_maintenance` → `EclipseMemoryService.run_retention_maintenance`) — no
new daemon or thread — and can never block boot. It is idempotent; each run is
recorded in `MemoryMaintenance` (migration 11: operation, ranAt, ok, inspected,
expired, skipped, error) and surfaced on `/eclipse-memory/health` (`retention`)
and `GET /eclipse-memory/retention` with no content. Confirming/renewing refreshes
`lastConfirmedAt` and extends/clears an automatic memory's `expiresAt` from
`retention_days`; explicit memories are never given a policy expiry. Changing
`retention_days` never mutates existing rows. Retrieval keeps excluding a due
memory by timestamp even before a sweep. A duplicate write no longer revives an
inert record. When a sweep fails it is reported honestly and the app still starts.

**Contradictions are authoritative.** `_resolve_conflict` uses authority: explicit
replacement and explicit-over-automatic supersede (auditable old→new link);
automatic-vs-explicit and two ambiguous explicit statements store the new record
inert (`proposed`). Detection (`conflicts.py`) uses subject identity +
`SUBJECT_ALIASES` + normalized (synonym/stemmed) tokens, with a tightened
opposing-pair table (no broad `\bdo\b` arm); a missed conflict is preferred over
replacing unrelated memory.

**Migrations.** Migration 11 (`MemoryMaintenance`) — additive, preserves v10 data,
reopen-tested.

**UI.** Lifecycle tab shows retention/last-sweep, expiry/last-confirmed/last-used/
last-reviewed, supersede links, and Confirm-&-renew / Restore / Approve / Archive;
an ambiguous conflict renders as "Not saved — conflicts with an existing memory".

**Checks.** Focused Python suite 211 passed; full `npm run test` Vitest **1752**
passed (137 files) + Python **883** passed; `tsc` clean; retrieval eval unchanged
(recall 1.0, precision 0.727, leakage 0, forbidden 0, gate PASS).

## Semantic maturity — dedicated eval, typed candidates, false-confirmation fix (2026-09-25)

**Brief.** Make the local memory system as strong as realistically possible
without changing the architecture or adding hosted services. Every improvement
had to be measurable, bounded, explainable, local and safer than before.

**Phase 0 — reproduced baseline + found a real bug.** Both evals and the focused
suites were re-run (`retrieval gate PASS`, `contradiction gate PASS`). Inspecting
cases that lexical matching misses surfaced a **false-confirmation safety bug**:
two same-dimension statements that substituted a *value* ("reports as PDF" vs
"reports as Excel", "portfolio quarterly" vs "portfolio monthly", "24-hour" vs
"12-hour") were silently treated as the same statement and *confirmed*, which
discarded the new value and refreshed the old one. Two contributing defects: the
`normalize.py` synonym group mapped `short`→`sell` (colliding with the trade
group), and confirmation matched on token overlap alone without checking whether
the distinctive values actually differed.

**Phase 1 — dedicated semantic evaluation.** `eclipse_memory/eval/semantic_v1.json`
is a 20-case labeled set built from cases lexical matching does not solve
(unfamiliar paraphrased contradictions, indirect negation, same-dimension value
substitutions, and safety negatives: unrelated high similarity, different
subjects/scopes, temporary instructions, stale/inert records, financial facts,
secrets). `eval/semantic.py` runs it through the REAL write pipeline (routed
through the production `authorize_proposal` gate, so secrets/financial facts are
refused by the same privacy rules) in lexical-only and semantic-enabled modes and
reports both plus semantic discovery; `eval/semantic_cli.py` prints the release
gate (absolute safety floors + an improvement floor).

**Phase 2 — honest backend interface.** `semantic.py` gains `backend_health`,
an `auto` selector, `NullBackend`, and an optional `LocalEmbeddingBackend` that
loads a sentence-transformer ONLY from an explicit local path
(`BLACK_ECLIPSE_MEMORY_EMBEDDING_MODEL`); it never downloads a model and never
contacts a network, and its absence falls back to the dependency-free
`char-ngram`. `policy.semantic_conflict_backend` selects it (`char-ngram`
default). The evaluation shows `char-ngram` scores genuine paraphrases at
~0.0-0.38, so it is NOT a source of measured improvement — documented honestly.

**Phase 3 — typed candidates.** Candidates are classified deterministically as
`confirmation_candidate`, `conflict_candidate`, `replacement_candidate`,
`unrelated_candidate` or `unavailable`. Only conflict/replacement are actionable;
`strongest_actionable` ignores confirmation/unrelated, so similarity can never
confirm, activate, supersede or archive. Diagnostics persist only detector,
version, candidate ids/kinds, scores and counts — never raw text or vectors, and
respect `semantic_conflict_diagnostics`.

**Phase 4 — deterministic decision + safety fix.** `conflicts._value_changed`
requires both same-dimension statements to carry a distinctive canonical token
the other lacks (reviewed synonym folds excluded); a differing value is proposed
for review (or superseded when explicit overrides automatic), never silently
confirmed. `normalize` no longer folds `short` into `sell`; numeric tokens are
kept so "12" vs "24" is meaningful; the financial-fact guard now catches
"trading at 190"-style statements. New reason:
`same dimension, differing value requires review`.

**Phase 5 — optional retrieval tie-break.** `semantic_recall_tiebreak` (off by
default) reorders ONLY memories that already passed the authoritative
scope/status/expiry/recall-policy filter AND already carried a lexical signal,
pinning the lexical leader so an exact match is never demoted; it cannot surface
an excluded memory or widen the eligible set. Covered by tests asserting no
other-scope recall and a clean no-match query.

**Phase 6 — operational controls.** `semantic_status()` now reports bounded
controls, per-backend health and bounded counters (proposals, actionable,
confirmed-after-review, kept/dismissed, replacement proposals).
`POST /eclipse-memory/semantic/rebuild` (operator-gated) is honest that v1 holds
no persistent index. UI Lifecycle tab shows controls, counters and backend
health, with a clear/rebuild control.

**Phase 7 — review UX.** A proposed-by-semantics record is surfaced in the chat
panel as "Not saved — possible conflict, needs review" distinct from a saved
memory, via `statusReason`/`requiresReview`/`semanticCandidate` on the memory
blob and the `memory-action` presentation model.

**Phases 8-9 — reliability + honest measurement.** Added tests for missing/
unavailable/timeout/exception backend, malformed score, threshold/candidate
bounds, reset/restore, disabled-mode (no candidate stored), no raw text in
diagnostics, and the honest rebuild route. Honest result: the deterministic
normalization + value-substitution fix closed the entire measured semantic gap;
semantic similarity added no measurable recall at a safe threshold, so it stays
optional and off by default.

**Checks.** Full Python suite passes; Vitest passes; `tsc` clean. All three gates
PASS (retrieval, contradiction, semantic). No `jdds.db` change.

**Files.** New: `eclipse_memory/eval/semantic.py`, `eval/semantic_cli.py`,
`eval/semantic_v1.json`, tests `test_memory_semantic_eval.py`, route
`src/app/api/eclipse-memory/semantic/rebuild/route.ts`. Modified:
`eclipse_memory/{conflicts,normalize,semantic,service,retrieval,policy}.py`,
`harness/{main,graph}.py`, `src/lib/harness/eclipse-memory-{types,client,browser}.ts`,
`src/lib/chat/memory-action.ts`, `eclipse-memory-screen.tsx`; docs this file,
`memory-contradiction-detection.md`, `NAVIGATION.md`, `CHANGELOG.md`.

## Memory Expansion — profile, session recall, learning review, file projection (2026-09-26)

**Brief.** Extend Eclipse-Memory with five Hermes-inspired capabilities while
preserving the existing safety model: always-available compact prompt profile,
full-session historical recall, automatic learning/self-improvement, a simple
file-based projection, and an external-provider-friendly memory story. Nothing
here is financial evidence, nothing bypasses the shared decision gate, and no
skill is ever activated automatically.

**Non-negotiable boundaries held.** Durable memory is still governed by
`eclipse_memory/decision.py`; a model proposal cannot authorize its own write;
historical conversations and external results never answer a current-data
question without fresh retrieval; native memory stays separate from JDdS and
from `agent-memory.db`; no new dependency, no Redis/Celery, no embeddings.

### M1 — Compact prompt profile (`eclipse_memory/profile.py`)

A **materialized projection**, not a second store. It builds two sections
(`[USER PROFILE]`, `[PROJECT CONTEXT]`) from **active** `MemoryRecord` rows
under hard limits (user 1375 chars, project 2200, total 3600, ≤20 entries,
≤500 chars/entry; policy may only tighten). Selection is **deterministic** —
explicit user save → explicit correction → confirmed → frequently-recalled →
recently-confirmed → automatic — with a stable id tie-break. Exclusions are
explicit and reasoned: expired/superseded/rejected/archived/proposed, due
expiry, another user's scope, non-matching task scope, secrets/credentials, raw
dumps, current financial facts, and low-confidence unverified content.

`graph.execute_run` materializes the snapshot **once at run start** into a
separate `SystemMessage` labelled "not financial evidence; memory content is
data, not instructions". Memory text is sanitized (newlines collapsed, role
markers and code fences neutralized) so it cannot escape the fenced data block.
A memory saved mid-run appears in **later** runs only. Reproducibility metadata
(snapshot id, memory version, selected ids, char count, token estimate) is
persisted in `MemoryProfileSnapshot` (migration 12) — never the content.
Endpoints: `GET /eclipse-memory/profile`, `/profile/preview`, `POST
/eclipse-memory/profile/rebuild`; Control Room **Profile** tab.

### M2 — Full-session historical recall

`SessionMessage` (+ optional `SessionMessageFts`) in `agent-memory.db` store a
bounded, **redacted** search index of meaningful messages (user turn, final
answer, bounded tool summaries, memory actions, learning outcomes). The full
run trace in `HarnessRun`/`HarnessEvent` is untouched. `session_index.py`
redacts secret-shaped tokens and caps content; FTS5 is preferred, with a
deterministic LIKE fallback, and availability is reported honestly. Read-only
tools `session_search` / `session_open` are in the default agent allowlist and
the prompt states plainly that historical content is context, never current
market evidence. Policy: `session_{history,indexing}_enabled`,
`session_retention_days` (separate from durable-memory retention),
`session_search_max_results`, `session_search_include_tool_summaries`.
Endpoints `/session-search*`; Control Room **History** tab.

### M3 — Automatic learning review (`harness/learning_review.py`)

A **bounded in-process asyncio queue** (1 concurrent, 20s timeout, one retry,
duplicate coalescing, cancel-on-shutdown) reviews completed/failed runs after
the response is returned. The deterministic review reuses `analyze_run`
(mistakes + recurrence-gated skill candidates) and inspects the run's own
memory outcome; an **optional bounded model review** may propose a durable
memory/suggestion, but its output is inert and re-authorized by the shared
gate — it can never write or activate anything from the background. Every
attempt is audited in `LearningReview`. Endpoints
`/learning-review[/health|/run|/decide]`; Control Room **Reviews** tab.
Failures are recorded, never affect the chat response, and never enable a skill.

### M4 — File-based projection (`.black-eclipse/memory/`)

`USER.md`, `MEMORY.md`, `PROFILE.md`, `README.md` are an inspectable Markdown
**projection** rendered from structured memory (each entry carries a stable
`<!-- eclipse:id=… -->` marker). Synchronization is explicit:
`GET /eclipse-memory/files` renders in memory; `POST /files/regenerate` writes
(after backing up); `GET/POST /import/markdown` preview/apply (apply backs up
first and routes every entry through the existing gated `import_payload`);
`POST /files/restore` restores the previous state. There is no filesystem
watching and no replacement of SQLite.

**Checks.** Python **989 passed**; `npx tsc --noEmit` clean; new tests
`test_memory_profile.py`, `test_session_search.py`, `test_learning_review.py`,
`memory-files.test.ts`, plus browser-client additions.

## Autonomous learning upgrade — providers, skill patches, hybrid ranking, prompt segments (2026-09-26)

Four spec milestones (M2/M7/M8/M9) plus M1 scheduling were added on top of the
Memory Expansion, with no architecture change and no safety invariant relaxed.

- **M8 — external memory providers.** New `python/harness/memory_providers/`
  (`protocol.py`, `native.py`, `mcp.py`, `registry.py`, `routing.py`,
  `diagnostics.py`). `MemoryProvider` is the ONE contract; the native provider
  wraps `EclipseMemoryService`, the MCP provider reuses the existing
  `MCPManager`. Every external result is `provenance=external_provider` /
  `verified=false`, fenced as `[EXTERNAL MEMORY — PROVIDER: <name> — UNVERIFIED
  CONTEXT]`, and never promoted to native. Routing is native-first; external
  search needs policy enablement AND an explicit per-call allow; external writes
  need an explicit user request AND approval. Automatic external writes are
  absent by construction. Tools `memory_search_native`,
  `memory_search_external`, `memory_provider_status`; policy keys
  `external_memory_*`; routes `/memory-providers/*`.
- **M9 — prompt-cache segments.** `python/harness/prompt_segments.py` splits the
  prompt into immutable segments (hash/version/source/token estimate), computes a
  stable identity-only `prompt_cache_key` (the user message and run instructions
  do not invalidate it), injects a bounded relevant-only skill manifest, and
  emits a `prompt.plan` event.
- **M2 — versioned self-improving skills.** `skills/patches.py` +
  `skills/versioning.py`; migration 13 adds patch/version metadata to
  `SkillVersion`; new statuses `evaluating/canary/approved/active/superseded/
  rolled_back`. A patch always creates a new version, a stale base is rejected,
  activation needs a passing evaluation, canary is safe-skill-only, and rollback
  is atomic. Routes `/skills/{id}/version-history` and `/skills/{id}/patch/**`.
- **M7 — hybrid ranking.** `eclipse_memory/hybrid.py` adds logical namespaces and
  a bounded BM25/hybrid score whose semantic term is advisory only. Labeled
  semantic eval gained typo, profile-mismatch and temporal-replacement cases.
- **M1 — scheduling.** `LearningReviewQueue` gained priority ordering, per-session
  coalescing and idle-aware deferral; `LearningReview` gained
  `sessionId/profileId/priority/scheduling`; a `skill_patch` review outcome
  records a patch opportunity without creating a version.

**Checks.** Python **1050 passed**; `npx tsc --noEmit` clean; Vitest **1765
passed**; semantic gate PASS. New tests `test_memory_providers.py`,
`test_prompt_segments.py`, `test_skill_patches.py`, `test_memory_hybrid.py`.

## Sessions, profiles, file editing and the Control Room (2026-09-26)

Four more spec milestones (M3/M4/M6/M10) were completed additively.

- **M3 — long-lived sessions.** `ChatSession` (metadata + bounded deterministic
  summary) in `agent-memory.db`; `HarnessRun`/`SessionMessage` gained
  `sessionId`/`profileId`/`projectId`. `RunRequest` carries the scope; the front
  door forwards it. Lifecycle: create/list/get/update (rename/pause/archive/
  restore)/fork/export/delete (archive default; hard delete clears only the
  search index, never the run trace). Session search uses the documented hybrid
  ranking with role/kind/session/profile/market/skill/memory-action filters. A
  summary is built at run completion and is searchable but never auto-injected.
- **M4 — named profiles.** `eclipse_memory/profiles.py` (`ProfileRegistry`) over
  `.black-eclipse/profiles/PROFILES.json` with per-namespace scoping, prompt
  profile, retention, settings, explicit READ-ONLY inheritance, and a directory
  projection. Cross-profile memory isolation is enforced on read.
- **M6 — safe file editing.** `memory-files.ts` writes `USER_PROFILE.md`,
  `MEMORY.md`, `PROJECT_MEMORY.md`, `SKILLS.md` (+ PROFILE/README) with a
  versioned entry marker; atomic writes (temp + fsync + rename); backup before
  regenerate; targeted edit with `expectedVersion` stale-edit rejection and
  add/replace/merge/split/reorder/consolidate; structured revision history with
  rollback and a bounded diff.
- **M10 — Control Room.** Tabs now Overview · Memory · Sessions · Learning ·
  Profile · Profiles · Providers · Files · Skills · Policies · Diagnostics, with
  the Overview surfacing current profile, recent changes, pending reviews, active
  skills, recent sessions, provider health and rollback availability.

**Checks.** Python **1067 passed**; `npx tsc --noEmit` clean; Vitest **1777
passed**. New tests `test_sessions_profiles.py`, `test_sessions_profiles_api.py`,
`memory-files-edit.test.ts`.

## Memory & Skills Evolution (2026-09-28)

Hermes-inspired improvements that preserve every existing safety control. Design
and gap analysis: `docs/harness/memory-skills-evolution-plan.md`.

- **Phase 0 — audit/design.** Target product model (facts vs session history vs
  skills), module map, data-flow, non-negotiable contracts, new inert contracts,
  deferred list. No duplicate memory engine; no TS agent runtime.
- **Phase 1 — simpler mental model.** Control Room tabs renamed to user-facing
  categories (Facts, Session History, Skills, Suggestions, Reviews, Health/Export);
  a three-card legend; a per-fact origin badge (auto/explicit/imported/external/
  suggested) derived only from existing fields; freshness/authority + competing-
  memory callout in the fact detail. No persistence/retrieval/authorization change.
- **Phase 2 — project-local skills (ADR-H59).** `python/harness/skills/project_skills.py`
  discovers repo-local roots (`.black-eclipse/skills/`, `.agents/skills/`) but
  loads them ONLY after an explicit operator trust decision persisted in
  `ProjectSkillTrust` (migration 14). Untrusted roots show a names-only notice.
  Precedence project > profile > bundled; a project skill may shadow a bundled id
  (`shadowed`, not a duplicate error). Trust is per absolute path and revocable;
  `untrust` stops injection on the next load. A project skill cannot grant a
  permission, enable itself, or bypass evaluation — it runs through
  `execute_skill` with the same default-deny gate. Global opt-out policy
  `project_skill_discovery`. Routes `/skills/project[/trust|/untrust]`; UI
  Skills › Project Skills; list/detail surface `provenance`.
  Tests: `python/tests/test_project_skills.py` (9) incl. untrusted-is-inert,
  precedence, untrust-stops-injection, blocked-permission can't-enable.

- **Phase 3 — skill bundles (ADR-H60).** `python/harness/skills/bundles.py`
  (`SkillBundle`, `resolve_bundle`) groups existing skills under a stable id with
  optional instructions/constraints. Resolution is deterministic and reports
  `missing`/`unavailable` members honestly; a bundle never enables a disabled
  skill, widens a permission, or exceeds the bounded prompt manifest (members
  pass the same permission check when an actor is supplied). Persisted in
  `SkillBundle` (migration 15); `RunRequest.bundleId` expands the bundle instead
  of keyword discovery and emits `skill.bundle_resolved`. Routes
  `/skill-bundles` (+`/{id}`); UI Skills › Bundles. Tests
  `python/tests/test_skill_bundles.py` (8).

- **Phase 4 — guided `/learn` (ADR-H61).** `python/harness/skills/learn.py`
  turns an explicit run/document/repository/repeated-workflow/correction request
  into a complete but inert draft through `propose_draft`. Content is sanitized
  (secrets, raw transcript lines, issue references removed) and advisory-linted
  (dates, first-person narration) before drafting; the draft defaults to the safe
  read-only permissions and existing tools, and stays `draft`/`not_evaluated`.
  Operator-gated; one-off runs never auto-activate. Route `/learning/from-source`;
  UI Skills › Learn a Skill. Tests `python/tests/test_guided_learning.py` (8).

- **Phase 5 — semantic assistance (verified + latency metric).** The optional
  semantic layer already exists and is deliberately OFF by default, gated by the
  labeled evals (`eclipse_memory/eval/` and `eval/semantic.py`), which already
  report recall/precision, false-candidate and false-conflict rates, scope
  leakage, forbidden/no-match overreach and token-budget compliance. Added the
  missing **latency** metric (`metrics.latencyMs.mean|max`) to the retrieval
  report so a future semantic layer can be compared against the lexical
  baseline. No behavior change: semantic candidates still cannot authorize
  access, supersede, confirm or widen the recalled set; the deterministic gate
  passes (recall 1.0, precision 0.727, leakage 0, forbidden 0).

- **Phase 6 — learning journey / provenance graph (ADR-H62).**
  `python/harness/learning_graph.py` projects a bounded node/edge graph from
  canonical rows (memories, skills/versions, candidates, corrections, mistakes,
  promotions, sessions) — derived only, never written. Secrets are never
  exposed, scope isolation filters the set, inactive items stay as nodes with a
  status, and edges use a fixed relation vocabulary. Route `GET
  /learning/journey` with kind/status/since filters; UI Skills › Journey. Tests
  `python/tests/test_learning_graph.py` (6).

- **Phase 7 — provider diagnostics.** `memory_providers/diagnostics.py` now adds
  a per-provider capability summary, a data-location warning (native local vs
  external), a verified-by-Eclipse flag, and a freshness stamp; a process-wide
  `privacyNote`; and a bounded, non-destructive `provider_test` (health + capped
  search only — never writes/deletes/exports). Route
  `POST /memory-providers/test` (operator-gated); the Providers tab shows the
  summary, data location, a Test button, and the privacy note. Native-first
  routing and external fencing are unchanged. Tests added to
  `test_memory_providers.py` (3).

- **Phase 8 — hardening + compat.** Export schema bumped to **v2** to carry
  `bundles` and `projectTrust` (a v1 document still imports). New cross-cutting
  test file `python/tests/test_evolution_hardening.py` (9): project
  trust→untrust roundtrip, bundle never enables a disabled skill, generated-skill
  secret sanitization + inertness, export/import roundtrip preserving
  bundles/trust, v1 compat, archive reversibility, scope isolation, bundle
  prompt-budget bounds. Operational notes (paths, trust model, config, provider
  setup, backup/import/reset/migration, recovery) added to
  `memory-skills-evolution-plan.md`.

**Checks (Phases 1–8).** `npm run test`: Vitest **1790 passed**; Python **1110
passed**; `npx tsc --noEmit` clean; retrieval eval gate PASS; semantic eval gate
PASS.






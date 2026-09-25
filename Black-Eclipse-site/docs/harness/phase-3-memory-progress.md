---
title: Harness Phase 3-M — Eclipse-Memory
status: Complete
last-verified: 2026-09-25
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


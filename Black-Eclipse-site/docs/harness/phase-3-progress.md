---
title: Harness Phase 3 Progress
status: Complete
last-verified: 2026-09-22
---

# Harness Phase 3 — Skill Foundation, Learning, Evaluation & Workflow-Ready Contract

**Phase:** 3 — Skill System, Learning Engine, Evaluation, Workflow-Ready Contract
**Status:** Complete (core foundation + all required scenarios)
**Last updated:** 2026-09-22

This document is the **source of truth** for Phase 3 progress. Architecture lives
in [`phase-3-architecture.md`](./phase-3-architecture.md).

## Objective

Give Eclipse a production-grade, extensible **Skill System** on top of the
existing Phase-1 runtime and Phase-2 retrieval layer: discover → progressively
load → validate (metadata/inputs/deps/permissions/outputs) → execute through the
existing runtime → capture traces and learning → evaluate → review/promote/roll
back — with a polished Eclipse-native UI and a stable execution contract that a
future workflow editor can call without rewriting skill logic.

Explicitly **not** built: a second runtime/registry, the visual workflow editor,
unrestricted autonomous self-modification, automatic activation of generated
skills, or a new vector database.

## Milestone 0 — Audit findings

### Baseline state (before Phase 3)

- `npx tsc --noEmit`: **pass** (0 errors).
- `npx vitest run`: baseline had 2 failures from pre-existing uncommitted
  retrieval-identity WIP (`instrument-collisions`, `failure-coverage`). By the
  time Phase 3 began those working-copy edits had been completed, and the
  baseline became **all green**. Phase 3 itself introduces no pre-existing
  failures; the final suite is 100% green (below).

### Existing systems reused (no duplicate infrastructure)

| Need | Existing implementation | Reuse decision |
|---|---|---|
| Agent runtime | `python/harness/graph.py` (`execute_run`) | Skill execution **calls this**, never a new loop |
| Tool registry | `python/harness/tools.py` (`ToolRegistry`, `ToolDefinition`, `_args_model`) | Skills declare required tools; registry enforces allowlist; `_args_model` reused as the input validator |
| Tools | `python/harness/retrieval_tools.py`, `finance_tools.py` | Initial skills use the Phase-2 retrieval tools as-is |
| Retrieval layer | `python/harness/retrieval/` | Unchanged; skills call the tools that call it |
| Events | `python/harness/events.py` (`EventBus`, `RunEmitter`) | `skill.*` events ride the same emitter/bus/persistence |
| Trace persistence | `python/harness/persistence.py` | Skill runs are ordinary `HarnessRun`s; extra metadata in `SkillExecution` |
| DB | `agent-memory.db` via stdlib `sqlite3`, idempotent DDL | Phase-3 tables added the same way (no Prisma, no second DB) |
| Agent config | `python/harness/agents.py` (`AgentConfig`) + `prompts.py` | A skill composes an `AgentConfig` in Python |
| Model/provider | `python/harness/models.py` | Unchanged; front door resolves settings as for a chat run |
| Memory | `persistence.py` (`AgentMemory`, legacy `AgentSkill`) | Learning uses new tables; user preferences stay in `AgentMemory` |
| Front door | `src/lib/harness/` + `src/app/api/harness/` | Pattern copied for skills; same `python-runtime` client |
| API protection | `src/lib/api-guard.ts` (`guardMutation`, `checkMutationAllowed`) | Reused verbatim — operator rule is the same mutation guard |
| UI shell | `sidebar.tsx`, `sidebar/config.ts`, `stock-chat.tsx`, `tab-bar.tsx` | New `skills` tab; screen code-split via `next/dynamic` |
| UI system | `.glass-card*`, `TabBar`, existing badges/buttons | Reused (see `black-eclipse-ui` skill) |
| Schema validation | pydantic (already a dependency via LangChain) | Manifests/schemas validated with pydantic, **not** Zod (no new dep) |
| Tests | pytest (`python/tests`, run by `scripts/test-python.js`), vitest | Extended |

### Conflicts / gaps found

1. **Legacy `AgentSkill` table** (`persistence.py`) is unversioned and
   name-keyed. Phase 3 does **not** extend it — separate, canonical Phase-3
   tables are added. Legacy methods stay for backward compatibility and are
   unused by the skill system.
2. **No permission system existed.** Tool permissions were a coarse
   `read|write|execute`. Phase 3 adds a centralized, default-deny policy in code.
3. **No runtime skill folder.** `Black-Eclipse-site/skills/` is the *coding
   agent's* operating system, not runtime skills. Runtime skills live under
   `python/harness/skills/library/`.
4. **Front door has no auth accounts.** Authorization is the existing api-guard
   (same-origin / secret / loopback) plus Python-side default-deny permissions;
   no new auth system.
5. A browser-safe split was required: the UI must not import the server client
   (which pulls Prisma/child_process). Added `skills-browser.ts` (fetch-only).

## Architecture decisions

Recorded in `docs/harness/phase-3-architecture.md` and mirrored into
`docs/DECISIONS.md` + `skills/ARCHITECT.md` (**ADR-025**):

1. Skills execute on the existing runtime; no second engine.
2. pydantic for skill schemas (existing dependency; no Zod).
3. One skill store + one registry (Python); TS is a thin proxy.
4. Default-deny permissions enforced in code; instructions are not a boundary.
5. Library files are the authoring format; the DB holds lifecycle + immutable
   versions.
6. Generated artifacts are inert until evaluated and explicitly promoted.

## Milestone checklist

| # | Milestone | Status |
|---|---|---|
| 0 | Audit + plan + docs | ✅ Done |
| 1 | Skill manifest + storage/loader + tests | ✅ Done |
| 2 | Skill registry + tests | ✅ Done |
| 3 | Skill runtime integration + tests | ✅ Done |
| 4 | Initial skills (5) + tests | ✅ Done |
| 5 | Learning records + candidate generation + tests | ✅ Done |
| 6 | Draft generation + tests | ✅ Done |
| 7 | Evaluation engine + promotion gates + rollback + tests | ✅ Done |
| 8 | UI — Skills Control Room | ✅ Done |
| 9 | Workflow-ready contract + API tests | ✅ Done |
| 10 | Final verification + completion report | ✅ Done |

## Files created

**Python (`python/harness/skills/`):**
`__init__.py`, `manifest.py`, `permissions.py`, `store.py`, `loader.py`,
`registry.py`, `runtime.py`, `learning.py`, `draft.py`, `evaluation.py`,
`lifecycle.py`, `events.py`.

**Skill library (`python/harness/skills/library/`):**
`research/research-planning/{skill.json,SKILL.md,tests/cases.json}`,
`research/source-verification/{…}`,
`quality/financial-data-quality/{…}`,
`finance/fundamental-analysis/{…}`,
`system/report-generation/{…}`.

**Python tests (`python/tests/`):**
`test_skills_registry.py`, `test_skills_runtime.py`, `test_skills_learning.py`,
`test_skills_scenarios.py`, `test_skills_api.py`.

**TypeScript (`src/lib/harness/`):**
`skills-types.ts`, `skills-client.ts` (server proxy), `skills-browser.ts`
(browser fetch client), `skills-client.test.ts`.

**TypeScript UI (`src/components/screens/skills/`):**
`skills-screen.tsx`, `skill-library.tsx`, `skill-detail.tsx`,
`learning-queue.tsx`, `evaluation-center.tsx`, `execution-activity.tsx`,
`draft-review.tsx`, `skill-ui.tsx`.

**API routes:**
`src/app/api/skills/route.ts`, `.../discover`, `.../validate-input`,
`.../[id]/route.ts`, `.../[id]/versions`, `.../[id]/execute`, `.../[id]/evaluate`,
`.../[id]/evaluations`, `.../[id]/[action]` (enable/disable/deprecate/rollback);
`src/app/api/skill-executions/[runId]/route.ts`;
`src/app/api/evaluations/[id]/route.ts`;
`src/app/api/learning/candidates/route.ts`,
`.../candidates/[id]`, `.../candidates/[id]/[action]`, `.../from-run/[runId]`;
`src/app/api/skill-drafts/[id]/[action]/route.ts`.

**Docs:** `docs/harness/phase-3-architecture.md`, `docs/harness/phase-3-progress.md`.

## Files modified

- `python/harness/service.py` — owns the one `SkillRegistry`/`SkillStore`;
  loads the library at boot; attaches the tool registry; adds `run_skill`.
- `python/harness/main.py` — 17 skill/learning/evaluation/lifecycle endpoints;
  `/health` reports skill counts.
- `python/harness/__init__.py` — (unchanged behaviour; still the runtime root).
- `src/components/layout/sidebar.tsx` — `AppTab` adds `skills`.
- `src/lib/sidebar/config.ts` — adds the Skills nav section (12 items).
- `src/lib/i18n/nav.ts`, `src/lib/i18n/dictionaries/en.ts` — `nav.skills`.
- `src/components/screens/stock-chat.tsx` — code-split, keep-alive Skills tab.
- `src/lib/sidebar/config.test.ts` — updated canonical shortcut count to 12.
- `docs/NAVIGATION.md`, `docs/DECISIONS.md`, `docs/harness/architecture.md`,
  `skills/ARCHITECT.md` — documentation.

## Database changes

Additive tables in **`agent-memory.db`** via idempotent `CREATE TABLE IF NOT
EXISTS` in `python/harness/skills/store.py` — no manual migration step, matching
`persistence.py`:

`Skill`, `SkillVersion`, `SkillDependency`, `SkillToolRequirement`,
`SkillPermissionRequirement`, `SkillExecution`, `SkillEvaluation`,
`SkillEvaluationCase`, `LearningCandidate`, `SkillPromotionRequest`,
`SkillReview`, `SkillEvent` (+ indexes).

Immutable rows: a `SkillVersion` is never updated (a new version is inserted); a
`SkillExecution` moves to a terminal status once. No destructive changes; the
legacy `AgentSkill` table is untouched.

## API changes

New Next.js routes (thin proxies; Python is authoritative):

- `GET /api/skills`, `GET /api/skills/:id`, `GET /api/skills/:id/versions`
- `POST /api/skills/discover`, `POST /api/skills/validate-input`
- `POST /api/skills/:id/execute`
- `POST /api/skills/:id/{enable,disable,deprecate,rollback}`
- `GET /api/skill-executions`, `GET /api/skill-executions/:runId`,
  `DELETE /api/skill-executions/:runId`
- `POST /api/skills/:id/evaluate`, `GET /api/skills/:id/evaluations`,
  `GET /api/evaluations/:id`
- `GET /api/learning/candidates`, `GET /api/learning/candidates/:id`,
  `POST /api/learning/candidates/:id/{generate-draft,reject}`,
  `POST /api/learning/from-run/:runId`
- `POST /api/skill-drafts/:id/{submit-review,approve,reject}`

Python runtime endpoints mirror these under `/skills`, `/skill-executions`,
`/learning`, `/skill-drafts`, `/evaluations`.

## UI changes

A new **Skills** tab (sidebar) containing:

- **Skills Library** — search, category/status/risk filters, cards; empty,
  loading and error states; registry warnings.
- **Skill Detail** — description, purpose, instructions (progressive load),
  required tools/skills, permissions, risk, input/output schemas, known
  limitations, validation, version/evaluation/execution/review history, and
  actions (Run, Evaluate, Enable, Disable, Deprecate, Set-latest/rollback, mode
  selector). Operator-only actions are hidden/disabled without authorization.
- **Learning Queue** — candidate cards with type, source run, problem, proposed
  lesson, evidence count, confidence, limitations; generate-draft / reject /
  open-draft actions. Never publishes directly.
- **Evaluation Center** — per-skill evaluation runs with dimension-by-dimension
  status; mandatory dimensions marked; no single aggregate score.
- **Execution Activity** — run list with expandable traces (mode, parent run,
  manifest hash, warnings, missing data, limitations, evidence, output) and
  “Learn from this run”.
- **Draft Review** — drill-down for `origin: learning` drafts; unvalidated state
  is visually prominent; submit-review/approve/reject.

Reuses the frosted-glass system, `TabBar`, and existing tokens. The screen is
code-split and keep-alive like every other tab.

## Skills implemented

1. `research.planning` — objective → structured, source-aware research plan.
2. `research.source-verification` — claim→source mapping, primary/secondary
   classification, conflicts, confidence limits.
3. `quality.financial-data-quality` — instrument/period/unit/currency/missing/
   duplicate/freshness/reported-vs-derived review before analysis.
4. `finance.fundamental-analysis` — reported + derived figures with evidence and
   limitations; depends on the quality skill; `medium` risk.
5. `system.report-generation` — assemble validated outputs preserving sources,
   assumptions, gaps, uncertainty; depends on source verification.

Each has a `SKILL.md` procedure and a `tests/cases.json` deterministic case set.

## Learning capabilities implemented

- Criteria-driven `analyze_run` over a persisted trace: failure recovery,
  validation improvement, successful procedure, source-selection improvement.
- Conservative exclusion: single-run successes, transient outages, and
  preferences are never promoted to universal skills.
- Deterministic duplicate suppression by signature.
- Operator-gated capture (`POST /learning/from-run/:runId`).
- Candidates are inert — `resultingSkillId` stays null until a draft is
  generated and explicitly promoted.

## Evaluation capabilities implemented

Deterministic, multi-dimensional, persisted per version: manifest, schema,
dependency, permission, tool-availability, financial-integrity (mandatory);
test-cases, evidence/reporting, regression (soft). Outcomes: passed / failed /
needs_review / blocked. `promotion_gate` blocks `blocked` and (by default)
`needs_review`. No LLM-judge-only gating. Version comparison + rollback supported.

## Workflow-compatible contract

`SkillExecutionRequest` (skillId, version, input, runId, parentRunId,
executionMode, actor/permissions, timeout, metadata) →
`SkillExecutionResult` (status, output, outputValidated, evidence, warnings,
missingData, limitations, traceId, runId, skillId, version, metrics). Five modes
(`interactive`, `workflow`, `scheduled`, `agent`, `evaluation`) share one code
path. Parent/child traces via `parentRunId`; partial results and error details
are structured. No visual editor required.

## Tests added

| File | Covers |
|---|---|
| `python/tests/test_skills_registry.py` | manifest, semver, permissions, loader, registry discovery/validation/versions/deps/cycles, lifecycle |
| `python/tests/test_skills_runtime.py` | execution via the real graph, events, validation, permissions, deps, output schema, modes, traces |
| `python/tests/test_skills_learning.py` | candidate criteria, dedup, inert drafts, evaluation dimensions, promotion gates, rollback |
| `python/tests/test_skills_scenarios.py` | the 10 required end-to-end scenarios |
| `python/tests/test_skills_api.py` | FastAPI endpoints, auth, promotion flow, workflow contract |
| `src/lib/harness/skills-client.test.ts` | operator authorization contract (same-origin/secret/loopback) |

## Tests executed and results

| Check | Command | Result |
|---|---|---|
| TS typecheck | `npx tsc --noEmit` | **Pass** (0 errors) |
| Lint | `npx eslint .` | **Pass** (0 errors; warnings pre-existing) |
| TS tests | `npx vitest run` | **1602 passed** (123 files) |
| Python tests | `python -m pytest python` | **200 passed** |
| Production build | `npm run build` | **Pass**; all skill routes present |

Phase-1 regression: `test_graph.py`, `test_tools.py`, `test_models.py` pass
(agent loop, tool registry, providers unchanged).
Phase-2 regression: `test_retrieval.py`, `test_retrieval_scenarios.py`,
`test_identity_hardening.py` pass; retrieval layer untouched.

## Known limitations

- Skill runs depend on a configured LLM provider (as any agent run does); with
  no provider the execution blocks with `MODEL_NOT_CONFIGURED`, never a fake run.
- Generated drafts are manifest-only (no `SKILL.md`); a reviewer must author the
  procedure prose before a learned skill is truly usable.
- The legacy `AgentSkill` table is not migrated into the new model (deferred).
- The evaluation regression dimension compares against the candidate's DECLARED
  `baseVersion` when that base has an evaluation; otherwise it uses the newest
  prior evaluation of the same version, then the newest prior version. Re-running
  "evaluate the base first, then re-evaluate the candidate" therefore compares
  against the base, not against the candidate's own earlier record.
- Skill instructions are bounded to 20k chars to protect context.

## Blockers

- None.

## Deferred decisions

- Migrating legacy `AgentSkill` rows into the Phase-3 model.
- Cross-version regression evaluation.
- A durable (cross-restart) discovery-metadata cache (unnecessary at 5 skills).

## Remaining work

None required for the Phase-3 definition of done. Natural next steps:
deterministic derived-metric calculation (Phase 2 note) and the visual workflow
editor (explicitly out of Phase 3 scope; the execution contract is ready for it).

## Final verification report

Phase 3 satisfies its definition of done:

- **Foundation** — manifest, registry, progressive loading, versioning,
  dependency and permission validation ✅
- **Execution** — skills run through the existing runtime; inputs/outputs
  validated; events and traces persisted; failures handled safely ✅
- **Learning** — experiences captured; failures/corrections recorded; candidates
  generated; duplicates suppressed; drafts inactive until approved ✅
- **Evaluation** — deterministic tests; regression dimension; promotion gates;
  failed evaluations block promotion; version comparison + rollback ✅
- **UI** — library, detail, learning queue, evaluation center, execution
  activity, draft review; loading/empty/error/permission states ✅
- **Workflow compatibility** — stable contract; structured I/O; parent/child
  ids; five execution modes ✅
- **Quality** — Phase 1 & 2 green; no duplicate runtime/registry; no fabricated
  financial data; nothing auto-enabled; security enforced in code; docs updated
  ✅

---
title: Harness — Memory & Skills Evolution Plan (Phase 0)
status: Current
last-verified: 2026-09-28
---

# Memory & Skills Evolution — Phase 0 Audit and Design

**Who this is for:** anyone implementing (or reviewing) the Hermes-inspired
memory/skill improvements. Read this before touching code. It is the design
authority for the work; the progress log lives in `phase-3-memory-progress.md`.

**What this is.** A gap analysis of Black Eclipse's memory/skill system against
a simpler target product model, with every proposed feature mapped to an
existing module and every safety invariant named. It deliberately proposes **no
second memory engine, no TypeScript agent runtime, and no speculative
architecture**.

## Target product model (the mental model we want users to hold)

Three distinct things, never conflated:

1. **Always-available facts** — small, durable, declarative, provenance-labeled,
   scoped, budgeted facts (identity, stable preferences, standing conventions,
   environment/project facts). Injected every turn.
2. **Searchable session history** — past conversations/run traces. Never
   injected every turn; queried on demand ("what did we decide last week?").
3. **Task-specific skills** — reusable procedures/workflows/pitfalls. Loaded
   only when relevant, progressively disclosed, never a raw-log dumping ground.

## What already exists (do not rebuild)

The audit confirms Black Eclipse already exceeds Hermes in the safety-critical
areas. The table records where each target-model capability already lives, so no
duplicate is proposed.

| Capability | Owning module (exists today) | Verdict |
|---|---|---|
| Durable facts, typed + scoped | `eclipse_memory/{store,service,retrieval}.py` | Keep; UI language only |
| Session history (redacted, FTS5) | `harness/session_index.py`, `harness/persistence.py` | Keep; already separate DB |
| Skills (versioned, lifecycle) | `harness/skills/{manifest,registry,runtime,lifecycle,evaluation,versioning,patches}.py` | Keep; add project roots + bundles |
| Decision gate (save/suggest/history_only/ignore) | `eclipse_memory/decision.py` | Keep — single authorization seam |
| Contradiction handling | `eclipse_memory/conflicts.py`, `normalize.py` | Keep |
| Expiry/retention | `eclipse_memory/service.py` (`expire_due_memories`, `run_retention_maintenance`) | Keep |
| Deterministic retrieval + eval | `eclipse_memory/retrieval.py`, `eclipse_memory/eval/` | Keep — semantic stays optional |
| Semantic candidate layer | `eclipse_memory/semantic.py`, `hybrid.py` | Exists, disabled by default — Phase 5 only measures/tightens |
| External memory providers (fenced) | `harness/memory_providers/` | Exists — Phase 7 only improves diagnostics/UI |
| Learning candidates (inert) | `harness/skills/learning.py`, `harness/learning_review.py` | Keep; add guided `/learn` UX |
| Prompt segments / skill manifest | `harness/prompt_segments.py` | Keep; bundles compose through it |
| Export/import/backup/reset | `eclipse_memory/transfer.py` | Keep; extend to bundles/project skills |
| Profiles (read-only inheritance) | `eclipse_memory/profiles.py` | Keep — bundles integrate here |
| Operator auth (transport/token) | `harness/main.py` (`require_operator`), `runtime-auth.ts` | Keep — never a body boolean |

**Already present, Hermes-inspired:** always-available profile, session search,
external provider boundary, automatic learning review, file projection,
versioned/patch/canary/rollback skills, prompt-cache segments.

**Genuinely absent (what this effort adds):** project-local skill roots with
trust; skill bundles/task profiles; a guided `/learn`-style workflow UI; typed
skill provenance labels surfaced to users (project/profile/bundled/external/
generated); a user-visible learning journey/provenance graph; a simplified
Facts/Session-History/Skills UI vocabulary.

## Gap analysis against the target model — HISTORICAL (pre-implementation)

> **Historical finding.** The "Current state" column below describes the system
> *before* the evolution phases and is retained for history. It is not the
> current state — see **Current status** at the end of the remaining-gaps
> section.

| # | Target-model expectation | Current state | Gap | Owning module (change) |
|---|---|---|---|---|
| G1 | Users can tell facts vs history vs skills apart | Control Room tabs (`Overview/Memory/Sessions/Learning/Profile/Profiles/Providers/Files/Skills/Policies/Diagnostics`) are engineer-facing; no per-item type/scope/source/authority/confidence/status/expiry/"why recalled" badges in one place | Vocabulary + surfacing | `eclipse-memory-screen.tsx`; typed fields already on `MemoryRecord` |
| G2 | Repository-local skills | Discovery is `library/` + DB `UserSkill` only; no project root | Missing | `harness/skills/loader.py` (`library_root`), `registry.load_all` |
| G3 | Explicit trust for project skills | No trust concept anywhere | Missing | new `harness/skills/project_skills.py` + `main.py` route + policy |
| G4 | Deterministic precedence + provenance labels | No tiers | Missing | `registry.py` (`register` first-wins → tiered), `prompt_segments.build_skill_manifest` |
| G5 | Skill bundles / task profiles | None | Missing | new `harness/skills/bundles.py`; integrate with profiles |
| G6 | Guided `/learn` workflow (run/doc/repo/repeated/correction) | Deterministic candidate→draft exists; no guided multi-source entry | Partial | `harness/skills/{learning,draft}.py` + `graph.py` + UI |
| G7 | Generated-skill sanitization (no transcripts/secrets/issue-numbers/dates) | `draft.py` drops unavailable tools; no explicit shape linter | Partial | `harness/skills/draft.py` (+ advisory lint) |
| G8 | Optional semantic candidate layer, measured | `semantic.py` exists + `semantic_v1.json` eval; off by default | Measurement/safety floors only | `eclipse_memory/eval/semantic.py`, `policy.py` |
| G9 | Learning journey / provenance graph | None (only investor-eye graph) | Missing | new `harness/learning_graph.py` (derived read model) + UI |
| G10 | Provider setup/status/off + diagnostics | `/memory-providers/status|search`, Providers tab exist | Partial (capability summary, test action, freshness, native-vs-external label) | `memory_providers/diagnostics.py`, `main.py`, Providers tab |
| G11 | Conflict UX (competing memories) | `explain_memory`, `_conflict_detail`, Lifecycle tab exist | Partial (side-by-side competing records + resolution recommendation) | `eclipse_memory/service.py`, UI |
| G12 | Identity/tenancy boundary documented | `userId`/`scopeId` are local labels (documented in baseline) | Doc-only | this doc + `memory-maturity-baseline.md` |
| G13 | Cold start without polluting durable memory | Not present | Missing (Phase 8) | starter skills are bundled files, not memory |
| G14 | Retention controls split (session vs durable) | `session_retention_days` vs `retention_days` both exist | Present | verify + UI clarity |

## Contracts that MUST NOT change

1. `eclipse_memory/decision.py` remains the **one** authorization gate for every
   durable-memory write (`decide_turn`, `authorize_proposal`); a model proposal
   can never authorize its own write.
2. `EclipseMemoryService.write_memory` / `retrieve` stay the **only** memory
   persistence/read pipeline; scope/status/privacy/expiry filtering stays
   authoritative and happens **before** any ranking.
3. `EclipseMemoryStore` stays the one SQLite access layer; `eclipse-memory.db`
   is the control store, `agent-memory.db` the run store. No new database.
4. `harness/skills/runtime.execute_skill` stays the only skill execution path
   through `graph.execute_run`; permissions remain default-deny in
   `skills/permissions.py`.
5. Skill promotion stays **evaluation + operator gated**; versions are immutable.
6. `require_operator` (transport/token) stays the operator gate for every
   mutation; no body boolean.
7. External memory results stay `provenance=external_provider` / `verified=false`
   and are never promoted to native.
8. Prompt segments stay non-authoritative, labelled, and budget-bounded; memory
   is data, never instructions.

## New contracts (this effort)

| Contract | File | Shape |
|---|---|---|
| Project skill root + trust record | `harness/skills/project_skills.py` | `ProjectSkillRoot`, `trust_root`/`untrust_root`, `discover_project_skills`, `is_trusted` |
| Skill provenance tier | `skills/manifest.py` / `registry.py` | `SkillSource` = `bundled \| author \| learning \| project \| external` |
| Skill bundle | `harness/skills/bundles.py` | `SkillBundle` (`id`, `description`, `skills[]`, `instruction?`, `constraints?`), `resolve_bundle` |
| Guided learn request | `harness/skills/learning.py` | `build_skill_from_source(source_kind, ...) -> inert draft + evidence` |
| Learning journey graph | `harness/learning_graph.py` | `build_learning_journey()` → `{nodes[], edges[], stats}` derived from canonical rows |
| Conflict review view | `eclipse_memory/service.py` | `explain_conflict(memory_id)` → competing records + recommendation |

All new contracts are **inert by default**: a bundle cannot enable a disabled
skill, a project skill is inert until trusted, and a learned draft cannot
activate without evaluation + operator approval.

## Data-flow (concise)

```
USER TURN
  │
  ├─ graph.execute_run
  │    ├─ memory_service.decide_turn ──► commit_decision ──► write_memory (facts)
  │    ├─ retrieve(scope-filtered) ────► <memory-context> (facts, every turn)
  │    ├─ build_profile ──────────────► [USER PROFILE]/[PROJECT CONTEXT]
  │    ├─ build_skill_manifest ───────► relevant skills only (bundles expand here)
  │    ├─ build_prompt_plan ──────────► prompt.plan event (segments + cache key)
  │    └─ run → session_index.index_run ──► SessionMessage (history, searchable)
  │
  └─ post-run
       ├─ analyze_run ──► LearningCandidate (inert) ──► [operator] draft ──► eval ──► promote
       ├─ learning_review queue (bounded, inert outputs)
       └─ learning_graph.build_learning_journey (derived read model)
```

## Module map (where each change lands)

- **Phase 1 (language/UI):** `src/components/screens/eclipse-memory/eclipse-memory-screen.tsx`,
  `eclipse-memory-types.ts`; no Python persistence change.
- **Phase 2 (project skills):** new `python/harness/skills/project_skills.py`;
  `loader.py`, `registry.py`, `permissions.py` (unchanged checks), `manifest.py`,
  `prompt_segments.py`, `main.py`, policy keys, UI library panel.
- **Phase 3 (bundles):** new `python/harness/skills/bundles.py`;
  `prompt_segments.build_skill_manifest`, `profiles.py` integration, routes, UI.
- **Phase 4 (/learn):** `python/harness/skills/{learning,draft}.py`,
  `python/harness/graph.py`, routes, UI draft panel.
- **Phase 5 (semantic):** `eclipse_memory/{semantic,eval}`, `policy.py`; no
  architectural change.
- **Phase 6 (journey):** new `python/harness/learning_graph.py` (derived), route, UI.
- **Phase 7 (providers):** `memory_providers/diagnostics.py`, `main.py`, Providers tab.
- **Phase 8:** tests under `python/tests/` and `src/**/*.test.ts`; operational docs.

## Safety and scope invariants (must hold after every phase)

- Durable memory is written only through the shared gate; proposed/suggested
  items stay inert until explicitly accepted.
- Scope isolation: a user/project/market scope never reads another's records.
  `userId`/`scopeId` are **local labels, not security identities** (single-user,
  local app); this boundary must be documented before any multi-user deployment.
- Project skills are never auto-loaded from an arbitrary cloned repo; trust is
  explicit and revocable; a project skill cannot grant itself permissions,
  enable itself, bypass evaluation, or change operator policy.
- Bundles cannot enable a disabled skill, widen permissions, or exceed the
  prompt budget.
- Learning produces inert candidates/drafts only; no automatic activation.
- Semantic similarity never authorizes access and never supersedes/confirms.
- External provider results retain provenance and are never Eclipse-verified.

## Module-map note: duplicate concepts / dead code found — HISTORICAL

> **Historical finding (all resolved in Phase 16).** Retained for history; the
> current code has fixed items 1–4 and promoted the deep-link-only tabs to
> top-level tabs (item 5).

Surfaced by the audit; none block the work, all are candidates for Phase 8:

1. `decision.py` `OUTCOMES` omits `run_only`, yet `MemoryDecision.outcome`
   docstring and `commit_decision` reference it (dead branch).
2. `explain_memory` maps a `run_analysis` source not in `VALID_SOURCES`.
3. `eclipse_memory/hybrid.py` (`hybrid_score`/`rank_hybrid`) is not wired into
   `retrieval.retrieve_memories` — orphan surface; either wire or mark.
4. `eclipse_memory/__init__.py` path docstring is stale vs `config.py`.
5. UI control-room tab union has tabs not in the tab bar (`history`,
   `lifecycle`, `suggestions`, `activity`) — reachable only by deep link.

## Deferred ideas (explicitly NOT implemented)

- Embedding-based retrieval enabled by default (labeled eval still shows no need).
- Hosted/cloud memory providers or multi-tenant identity.
- A second skill execution engine or a TypeScript skill runtime.
- Autonomous background **writes** (the review queue may propose only; it never
  writes or activates).
- Skill marketplace/hub install from arbitrary URLs (out of scope; no network
  dependency added).
- Multi-user auth/tenancy (documented boundary only; not built).

> **Superseded:** "Auto-compaction of near-duplicate facts" was listed here as
> deferred in an earlier revision. It is now implemented (conservative,
> inert-until-accepted proposals with a labeled preservation eval — see the
> Compaction rows below) and is no longer deferred.

## Operations (phases 2–8)

**New paths.**
- Project skill roots (inert until trusted): `<repo>/.black-eclipse/skills/` or
  `<repo>/.agents/skills/`. Discovery is bounded; the runtime's project root is
  the repo containing `python/`, overridable with `BLACK_ECLIPSE_PROJECT_ROOT`.
- Skill bundles: `SkillBundle` rows in `eclipse-memory.db` (migration 15).
- Project trust: `ProjectSkillTrust` rows in `eclipse-memory.db` (migration 14).
- The learning journey is derived on demand — it has no storage.

**Trust model.** A project root is untrusted by default. `POST
/skills/project/trust` records an explicit, revocable operator decision;
`untrust` reverses it immediately on the next load. An untrusted root shows a
names-only notice and its prose is never read. A trusted project skill runs
through the same default-deny permission gate, immutable-version identity and
evaluation/promotion controls as any bundled skill; it cannot grant itself a
permission or enable itself. Discovery can be disabled globally
(`project_skill_discovery=false`).

**Configuration.** New policy keys: `project_skill_discovery` (default true).
Bundles and project trust are operator-mutated (transport/token), never a body
boolean. No new dependency was added; the runtime stays Python.

**Provider setup.** Native memory is always on and authoritative. External
(MCP) providers are candidates only; they are searched only when
`external_memory_search_enabled` policy is on AND the caller passes an explicit
`allowExternal`. The Providers tab shows capability summaries, data location,
freshness and a bounded Test action; every external result is labelled
`external_provider`/`unverified` and is never promoted.

**Backup / export / import / reset / migration.**
- `GET /eclipse-memory/export` emits a versioned document (`version: 2`) that
  now includes `bundles` and `projectTrust`, so a restore does not lose
  composability or trust provenance. A v1 document still imports.
- Import routes every memory through the shared decision gate; bundles are
  validated for shape; project trust is re-affirmed as data. Nothing is enabled.
- `POST /eclipse-memory/backup` copies the DB (WAL-checkpointed, atomic, never
  overwrites). `reset` clears the memory domain only and backs up first.
- Migrations 14–15 are additive/idempotent; a pre-v14 database opens and gains
  the tables with no data loss.

**Recovery.** A failed provider/probe/retention/journal operation is reported
honestly (a diagnostic or a `failed` entry) and never corrupts native memory.
The runtime still boots when Python tooling or an external provider is missing.

## Final delivery report

### 1. Before → after architecture

**Before.** One `eclipse-memory.db` with a decision gate, typed/scoped memory,
session history, and a versioned skill lifecycle. Weaknesses relative to the
target model: engineer-facing UI vocabulary; skills discoverable only from the
bundled library + DB user skills (no project roots); no composability; no guided
learning entry; no user-visible provenance; provider diagnostics thin.

**After.** The same one-database architecture, one decision gate, one retrieval
seam and one skill execution path, extended with:
- a user-facing category model and per-fact provenance/freshness surfacing;
- repository-local skill roots with explicit, revocable trust and deterministic
  precedence (project > profile > bundled);
- skill bundles (references only) with deterministic resolution;
- a guided `/learn` that produces sanitized, inert drafts;
- a derived learning/provenance graph;
- richer provider diagnostics (capability summary, data location, bounded test);
- an export schema (v2) that preserves bundles/trust across backup/restore.

Nothing was rebuilt in TypeScript; no new memory engine, tool registry, agent
loop or model adapter was created.

### 2. Memory vs session history vs skills

- **Facts (memory)** live in `eclipse-memory.db`, are written only through the
  shared gate, are scope/status/privacy filtered, budgeted, and recalled on
  relevant turns (standing rules every turn).
- **Session history** lives in `agent-memory.db` (`SessionMessage`), is redacted
  and bounded, is searched on demand, and is never injected every turn.
- **Skills** live in `eclipse-memory.db` as immutable versions; instructions load
  only on selection (progressive disclosure); execution is permission-gated and
  promotion is evaluation + operator gated. Proposals/drafts are inert.

### 3. Security and trust model

- Operator authorization is by transport/token (`require_operator`), never a
  body boolean; the front door forwards the runtime secret.
- Skills: default-deny permissions; forbidden/blocked permissions can never be
  granted; a project skill cannot grant itself a permission or enable itself.
- Project skills are inert until an operator trusts the root; untrusted prose is
  never read; trust is revocable and per-path; discovery can be disabled.
- Bundles are references; they cannot enable a disabled skill or widen a
  permission, and are bounded.
- Memory: secrets/credentials/dumps/financial facts are refused for every path;
  external provider results are labelled unverified and never promoted.
- `userId`/`scopeId` remain **local labels, not security identities** (single-
  user local app); this boundary must be documented before multi-user use.

### 4. Retrieval evaluation report

Deterministic path (dataset v1): recall **1.000**, precision **0.727**,
`recallSupported` **1.000**, scope leakage **0**, forbidden hits **0**, no-match
clean, over-budget **0**, latency mean **~0.7 ms** / max **14 ms**. Release gate
**PASS**. Semantic candidates remain off by default; when enabled the semantic
eval still reports candidate recall/false-candidate/false-conflict and absolute
safety floors — gate **PASS**. No semantic candidate can authorize access.

### 5. Skill-learning evaluation report

- Automatic learning creates inert candidates only; `successful_procedure`
  requires recurrence evidence.
- Guided `/learn` produces complete drafts that are sanitized (secrets, raw
  transcripts, issue references removed) and linted; drafts are always
  `draft`/`not_evaluated`.
- Promotion remains deterministic-evaluation + operator gated; versions are
  immutable; canary/rollback are safe-skill only.
- Tests prove secret sanitization and inertness end-to-end.

### 6. Provider behavior report

Native memory is always searched first and authoritative. External providers are
candidates; they are searched only when policy enables it AND the caller passes
an explicit allow, and only when native returns fewer than the sufficiency
threshold. Every external result is fenced, labelled `external_provider` /
`verified=false`, and never promoted. A provider failure degrades honestly and
never corrupts native memory. The Providers tab surfaces capability summaries,
data location, freshness and a bounded Test action.

### 7. Migration and rollback plan

- Migrations 14 (`ProjectSkillTrust`) and 15 (`SkillBundle`) are additive and
  idempotent; a pre-v14 database opens and gains the tables with no data loss.
- Export document is v2; v1 documents still import. `bundles` and `projectTrust`
  round-trip. Import routes memory through the same gate and never enables a
  skill.
- Backup checkpoints WAL and atomically writes (never overwrites). `reset`
  backs up first and clears the memory domain only.
- Rollback for a skill patch is atomic (prior version re-enabled) and audited;
  archive/restore is reversible for memory. No path hard-deletes history.

### 8. Remaining risks — HISTORICAL (Phases 1–8)

> Retained for history. The final-hardening pass (2026-09-28) tightened several
> of these; the authoritative current list is **Current status → Remaining
> risks** at the end of this file.

1. `userId`/`scopeId` are not strong identities — multi-user deployment needs an
   authn layer (documented, not built).
2. Project-skill trust is a repo-level decision; a `git pull` that changes a
   trusted skill's content is only detected via the content-hash/version-identity
   check, not re-confirmed per pull.
3. Contradiction detection is lexical; an unlisted paraphrase can be missed
   (prefers a miss over replacing unrelated memory).
4. Skill usefulness metrics are per-version aggregates with no time weighting.
5. Semantic retrieval is measured but not enabled; its measured benefit remains
   below the threshold that would justify enabling it by default.
6. The learning journey is a snapshot on load; it is not live-streamed.

### 9. Secrets / jdds.db

No secrets were committed. `jdds.db` was not modified by this work (it was
already modified in the working tree before this effort and remains untouched by
it); it must not be committed on routine changes.

### 10. Authorization / scope

No code path added in phases 1–8 bypasses operator authorization or scope
isolation: every mutation route re-checks the operator by transport/token; memory
writes still flow through `decision.py`; retrieval filters scope/status/privacy
before ranking; project skills and bundles cannot widen permissions or enable a
skill.

## Acceptance criteria for Phase 0 (met)

- No duplicate memory engine proposed; every change has an owning module.
- No TypeScript agent runtime proposed.
- Safety and scope invariants documented.
- Contracts that must not change are enumerated.
- New contracts are named and inert-by-default.

---

# Remaining gaps — Phase 0 audit (2026-09-28) — HISTORICAL

> **Historical finding.** "State found" describes the state *before* the 15
> implementation phases that follow. Every gap listed here was subsequently
> closed; the final-hardening pass (2026-09-28) then hardened each area further.
> See **Current status** at the end of this file.

A second pass audited the implemented system against a 16-gap list. Audit
findings (complete/partial/missing) and the owning module for each change:

| # | Gap | State found | Owning module (change) |
|---|---|---|---|
| 1 | Identity/tenancy boundary | Doc-only; `userId`/`scopeId` are local labels | `memory-maturity-baseline.md` + this doc |
| 2 | Trusted project skill drift | Missing (trust was a binary path flag; `root_content_hash` hashed manifest only, never persisted) | `skills/project_skills.py`, `skills/registry.py`, `eclipse_memory/{schema,store}.py`, `main.py`, UI |
| 3 | Skill/project/bundle/draft injection defense | Missing (no scanner; `learn.py` sanitized secrets/dates only) | new `skills/content_scan.py`; wired in registry/learn/authoring |
| 4 | Conflict-resolution UX | Partial (detail returns ids only; no side-by-side/actions) | `eclipse_memory/service.py`, UI |
| 5 | Conservative compaction | Missing (no proposal table/eval) | `eclipse_memory/{service,store,schema}.py`, eval |
| 6 | Skill quality over time | Partial (window aggregates; no trends/CI/failure causes; no UI) | `eclipse_memory/skill_quality.py`, routes, UI |
| 7 | Prompt/run observability | Partial (`prompt.plan` hashes only; `memory.retrieved` drops exclusions; no run UI) | `graph.py`, `eclipse_memory/retrieval.py`, chat UI |
| 8 | Learning journey freshness | Missing (`lastUpdated` absent; manual refresh only) | `learning_graph.py`, UI |
| 9 | Bundle lifecycle | Partial (no version identity/constraints/lock/history) | `skills/bundles.py`, `eclipse_memory/{schema,store}.py`, UI |
| 10 | Provider reliability | Partial (per-call timeout only; no retry taxonomy/circuit/history) | `memory_providers/*` |
| 11 | Freshness/retention UX | Partial (`stale` not computed; no next-action; no sweep preview) | `eclipse_memory/{store,service}.py`, UI |
| 12 | Import/export hardening | Partial (dry-run exists; no checksum/partial restore/atomicity; UI import skips dry-run) | `eclipse_memory/transfer.py`, UI |
| 13 | Cold-start experience | Missing (only a dashboard persona picker) | new `harness/onboarding.py`, UI |
| 14 | Skill dependency visibility | Partial (flat id list + validation error only) | `skills/registry.py`, UI |
| 15 | Adversarial evaluation | Partial | `python/tests/test_adversarial_*.py`, eval floors |
| 16 | Orphaned/inconsistent surfaces | `run_only` dead branch; `run_analysis` source; `hybrid.py` unwired; stale `__init__` path; deep-link-only tabs | `decision.py`, `service.py`, `hybrid.py`, `__init__.py`, UI |

**Safety invariants held for every gap:** one decision gate; one memory store;
one skill execution path; default-deny permissions; operator transport/token
auth; scope isolation; inert proposals/drafts/bundles/trust; external results
fenced and unverified. No new dependency, no second engine, no TypeScript agent
runtime.

**Contracts added this pass (all inert-by-default):**

| Contract | File | Shape |
|---|---|---|
| Project content identity + drift | `skills/project_skills.py` | `root_content_hash` (manifest+prose), `drift_status`, quarantine on change |
| Advisory content scan | `skills/content_scan.py` | `scan_content`/`scan_loaded_skill` → bounded findings; `should_quarantine` |
| Compaction proposal | `eclipse_memory/compaction.py` | `detect_proposals`, `accept_proposal` (inert until accepted; reversible) |
| Bundle version/lock | `skills/bundles.py` | `version`, member constraints, `lock` + resolved composition |
| Provider reliability | `memory_providers/reliability.py` | failure classification + circuit breaker (in-memory, bounded) |
| Onboarding | `harness/onboarding.py` | static explanatory content; never writes memory |

## Phase 2 — trusted project skill drift (implemented)

Trust records a content identity. `root_content_hash` now folds the manifest
**and** the instruction file(s), so a prose change counts. On load, a trusted
root whose hash differs from `trustedHash` is **quarantined**: no skills load, a
`skill.project_drift` event is recorded, and `/skills` returns
`projectDrift`. Re-approval (`POST /skills/project/approve`) re-baselines the
hash and records `skill.project_reapproved`. Untrust is immediate and stores the
revoked hash. Back-compat: a legacy trust row with no stored hash stays trusted
and re-baselines on the next trust/approve.

## Remaining-gaps phases — status (2026-09-28)

All 15 implementation phases (2–16) are complete; each is recorded in
`CHANGELOG.md` with its owning module and tests.

| # | Phase | Owner | Status |
|---|---|---|---|
| 2 | Trusted project skill drift | `skills/project_skills.py`, `registry.py`, store | Done |
| 3 | Content injection defense | `skills/content_scan.py` | Done |
| 4 | Conflict-resolution UX | `eclipse_memory/service.py`, UI | Done |
| 5 | Conservative compaction | `eclipse_memory/compaction.py`, eval | Done |
| 6 | Skill quality over time | `eclipse_memory/skill_quality.py` | Done |
| 7 | Run observability | `harness/run_observability.py` | Done |
| 8 | Journey freshness | `harness/learning_graph.py`, UI | Done |
| 9 | Bundle lifecycle | `skills/bundles.py`, store | Done |
| 10 | Provider reliability | `memory_providers/reliability.py` | Done |
| 11 | Freshness/retention UX | `eclipse_memory/{store,service}.py`, UI | Done |
| 12 | Import/export hardening | `eclipse_memory/transfer.py`, UI | Done |
| 13 | Cold-start onboarding | `harness/onboarding.py`, UI | Done |
| 14 | Dependency visibility | `skills/registry.py`, UI | Done |
| 15 | Adversarial eval + floors | `python/tests/test_adversarial_evolution.py` | Done |
| 16 | Orphan cleanup | decision/service/hybrid/`__init__`/UI | Done |

**Hardening found during implementation.** `write_memory` now refuses a
credential VALUE at the single persistence path
(`decision.looks_like_credential_value`) as defense-in-depth beyond the decision
gate — closing a path where a non-gated caller (import/suggestion accept) could
have persisted a secret. A benign sentence that merely mentions "secret"/"token"
is not over-blocked.

**Migrations added.** 16 (`ProjectSkillTrust.trustedHash/revokedHash`), 17
(`CompactionProposal`), 18 (`SkillBundle.version/memberVersions/locked`). All
additive/idempotent.

## Phase 3 — content injection defense (implemented)

`content_scan.py` is advisory and never authoritative. Categories:
`override_instructions`, `reveal_secrets`, `bypass_approval`, `self_enable`,
`disable_safety`, `impersonate_system`, `ignore_policy`, `exfiltration` (all
quarantine-severity), plus warn-only shapes (role markers, prompt fences, hidden
HTML, zero-width). Registry `register` quarantines a quarantine-severity finding
for project/profile/generated/external tiers and only warns for bundled
(human-reviewed) skills. Findings are surfaced on `/skills` and `/skills/{id}`.
A clean scan is explicitly not proof of safety.


---

# Current status (2026-09-28, final hardening pass)

This is the authoritative, current-state summary. Earlier gap tables and
"remaining risks" sections are labeled HISTORICAL above and describe the state
*before* implementation; this section describes the state *after* the remaining-
gaps phases and the final-hardening pass.

## Completed work

| Area | State | Owning modules |
|---|---|---|
| Conflict UX (competing memories) | Complete: side-by-side review + resolution actions; uncertain conflicts prefer a visible review over a silent replacement | `eclipse_memory/service.py` (`conflict_review`, `resolve_conflict`), UI |
| Compaction | Complete: conservative near-duplicate proposals, inert until accepted; labeled preservation eval (cross-scope, contradictory, temporal, authority; evidence/chain/reversibility floors) | `eclipse_memory/compaction.py`, `eval/compaction.py`, UI Lifecycle tab |
| Run observability | Complete: `memory.retrieved` enrichment + `/runs/{id}/explain` + chat panel | `harness/run_observability.py`, `graph.py`, UI |
| Provider reliability | Complete: failure taxonomy (incl. `provider_failure`), bounded retry + per-call timeout budget, circuit breaker with recovery, bounded per-provider history, freshness/last-success | `memory_providers/reliability.py`, `registry.py`, `diagnostics.py` |
| Bundle lifecycle | Complete: version identity, lock (versions + content hashes), update preview, member drift (version + content), reproducible receipt, safe rollback; lock exportable | `skills/bundles.py`, store |
| Onboarding / cold start | Complete: static, read-only first-run explanation; never writes memory | `harness/onboarding.py`, UI |
| Adversarial evaluation | Complete: prompt injection, drift, cross-scope/project leakage, provider poisoning/recovery, malicious imports/drafts, long-running growth, repeated compaction, low-sample claims, tampering, stale/superseded interaction | `python/tests/test_adversarial_evolution*.py` |
| Orphan/inconsistency cleanup | Complete: stale docstrings, `run_analysis` mapping, `hybrid.py` marked experimental, deep-link tabs promoted | `decision.py`, `service.py`, `hybrid.py`, `__init__.py`, UI |
| Identity/tenancy boundary | Complete (documented + guarded): `userId`/`scopeId` are self-asserted scope labels, never identities; no authentication/tenancy isolation claimed; a non-loopback bind without an operator secret is refused by `main()` (unless explicitly acknowledged) and flagged at startup; `0.0.0.0` is no longer a trusted local host | `main.py` (`identity_boundary`, `deployment_exposure`), `api-guard.ts` (`deploymentExposure`), docs |
| Per-skill project trust | Complete: per-skill content identity + approval history (who/what/when/level); drift quarantines only the changed skill(s), unchanged skills keep working; explicit re-approval; UI changed-skill review + history | `skills/project_skills.py`, `registry.py`, store, UI |
| Contradiction evaluation | Complete: paraphrase/negation/numeric-value/subject-alias/temporal cases; recall, missed-conflict, false-conflict, confirmation, scope-leakage, forbidden-hit, precision metrics; honest interpretation of when semantic assistance helps | `eclipse_memory/eval/contradictions.py` + dataset |
| Skill quality | Complete: sample-size warnings, Wilson confidence interval, time-weighted rate, failure-cause trends, same-case version comparison, regression warning inside promotion evidence, five evidence states | `eclipse_memory/skill_quality.py` |
| Journey freshness | Complete: derived read model with `generatedAt`/`watermark`, focus refresh + refresh state, skill-execution nodes, placeholder session nodes for provenance edges | `harness/learning_graph.py`, UI |
| Import/export hardening | Complete: checksum, conflict/duplicate preview, partial restore by scope/category, atomic import with rollback, schema negotiation (v1/v2/v3), evaluation + audit preservation | `eclipse_memory/transfer.py`, UI |

## Remaining risks

1. **Identity/tenancy is a documented boundary, not a built authentication
   system.** `userId`/`scopeId` remain self-asserted scope labels. A network or
   multi-user deployment must add a real authentication seam; the runtime now
   *refuses* an insecure non-loopback bind and flags exposure, but it does not
   provide accounts.
2. **Contradiction detection is lexical.** An unlisted paraphrase with no shared
   token and no reviewed concept axis can be missed; a missed conflict is
   preferred over an unsafe replacement. The eval reports this honestly.
3. **Semantic retrieval is measured but not enabled.** Its measured benefit stays
   below the threshold that would justify enabling it by default; semantic
   candidates can never authorize access or supersede/confirm.
4. **Provider reliability state is in-memory and per-process.** Circuit/latency
   history resets on restart; it is deliberately not persisted.
5. **Bundle locks are exportable but not a content-addressed store.** A locked
   bundle records member versions + content hashes; reconstructing a member's
   exact prior content requires that version still to be present.

## Intentionally deferred

- Embedding-based retrieval enabled by default (labeled eval shows no need).
- Hosted/cloud memory providers; multi-tenant identity.
- A second skill execution engine or a TypeScript skill runtime.
- Autonomous background **writes** (the review queue proposes only).
- Skill marketplace/hub install from arbitrary URLs.
- Multi-user auth/tenancy (documented boundary + deployment guards only).

## Future architecture

- A pluggable authentication seam that resolves `scopeId` from a real identity,
  leaving the local single-user label model intact when no seam is configured.
- Optional persistent provider reliability history (only if a real need appears).
- A content-addressed skill-version store to reconstruct a locked bundle's exact
  member content across version removal.

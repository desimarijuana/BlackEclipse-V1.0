---
title: Harness Phase 3 — Skill System Architecture
status: Current
last-verified: 2026-09-30
---

# Harness Phase 3 — Skill System Architecture

**Who this is for:** anyone extending or debugging the Skill System. Read
[`architecture.md`](./architecture.md) first — this document only covers what
Phase 3 adds and why it is shaped this way.

## What a "skill" is here

A skill is a **versioned, machine-readable procedure** that the existing Python
agent runtime executes. It is not a second runtime, not a second tool registry,
and not an autonomous agent. It is a reviewed, declared capability:

- metadata (`skill.json`) → discovery, permission/dependency validation;
- instructions (`SKILL.md`) → loaded **only** after a skill is selected;
- an input/output JSON schema → validated in code, not by prose;
- required tools/permissions → resolved against the **existing** registry and
  permission policy.

Skills run through `harness/graph.py`'s `execute_run` exactly like a chat turn.
The skill's `SKILL.md` is composed into an `AgentConfig.systemPrompt`, its
`requiredTools` become the run's tool allowlist, and its input is serialized
into the run input. There is deliberately no second execution engine.

## User-authored skills

Users can write their own skills from the **Skills Library** ("Add skill"). A
user skill is stored in **eclipse-memory** (`UserSkill` table, migration 3) —
not on disk, because the runtime has no filesystem-write path by design — and is
materialised into the same `Skill`/`SkillVersion` tables and the same
`SkillRegistry` as built-ins. It is therefore discovered, validated and executed
exactly like a built-in, and the agent can use it via `skill_list`/`skill_view`
once it exists.

Safety, enforced in code:

- The manifest is validated by the same pydantic `SkillManifest`.
- A user skill may declare **only the safe, read-only permission set**;
  operator-only and forbidden permissions are rejected at author time.
- Required tools must exist in the runtime registry.
- Authoring requires operator authorization (same gate as every mutation).
- Editing a skill always creates a **new version**; the enabled version is never
  mutated. Built-ins cannot be edited or deleted. A user skill with execution
  history is **deprecated, not deleted**, so history is preserved.

## Where it lives

```
python/harness/skills/
  __init__.py
  manifest.py      pydantic manifest + enums (status, risk, category, permission)
  permissions.py   centralized, default-deny permission policy
  registry.py      load/validate/search/filter/version/dependency resolution
  store.py         compatibility alias: SkillStore = EclipseMemoryStore (eclipse-memory.db)
  runtime.py       SkillExecutionRequest/Result + execution through execute_run
  schema_validation.py  full JSON Schema validation of input/output + schema self-check
  learning.py      trace analysis → learning candidates (no auto-enable)
  draft.py         candidate → unvalidated draft (no auto-enable)
  evaluation.py    deterministic evaluation + promotion gates
  events.py        skill.* event vocabulary (thin, on top of RunEmitter)
  library/         the shipped skill files (SKILL.md + skill.json)
    research/research-planning/
    research/source-verification/
    quality/financial-data-quality/
    finance/fundamental-analysis/
    system/report-generation/
```

**Why under `python/harness/` and not the repo's `skills/` folder?** The
existing `Black-Eclipse-site/skills/` (and `.opencode/skills/`) is the *AI coding
agent's engineering operating system* — unrelated to runtime skills. Putting the
runtime skill library there would collide with that meaning and confuse two
different audiences. The agentic runtime owns its skills, so they live in the
agentic runtime. (ADR: see `docs/DECISIONS.md`.)

## Data model (one source of truth)

All Phase-3 skill state lives in **`eclipse-memory.db`**, the runtime's dedicated
control database — never in JDdS (`jdds.db`) and no longer in `agent-memory.db`.
`harness/skills/store.py` is now a thin alias (`SkillStore = EclipseMemoryStore`);
the canonical DDL is `harness/eclipse_memory/schema.py` (a list of idempotent
migrations applied by `eclipse_memory/db.py`). The one-time, idempotent,
non-destructive import of legacy `agent-memory.db` skill rows is
`EclipseMemoryService.import_legacy_skills`. (Earlier revisions of this doc said
`agent-memory.db`; the code has since moved — see ADR-026 and the table split in
`phase-3-memory-progress.md`.)

| Table | Database | Holds |
|---|---|---|
| `Skill` | `eclipse-memory.db` | identity + latest version pointer + lifecycle status |
| `SkillVersion` | `eclipse-memory.db` | one immutable manifest revision (hash, status, eval state) |
| `SkillDependency` | `eclipse-memory.db` | skill→skill edges + version constraints |
| `SkillToolRequirement` | `eclipse-memory.db` | required tool names per version |
| `SkillPermissionRequirement` | `eclipse-memory.db` | required permissions per version |
| `SkillExecution` | `eclipse-memory.db` | one skill run: status, runId, parentRunId, mode, metrics |
| `SkillEvaluation` | `eclipse-memory.db` | one evaluation run (per version) + per-dimension result |
| `SkillEvaluationCase` | `eclipse-memory.db` | test cases attached to a version |
| `LearningCandidate` | `eclipse-memory.db` | a captured lesson (never auto-published) |
| `SkillPromotionRequest` / `SkillReview` | `eclipse-memory.db` | review lifecycle + audit |
| `SkillEvent` | `eclipse-memory.db` | skill lifecycle events beyond the run trace |
| `HarnessRun` / `HarnessEvent` / `HarnessToolExecution` | `agent-memory.db` | run traces + tool executions |
| `RetrievalRecord` / `ResearchReceipt` | `agent-memory.db` | durable retrieval replay + research receipts |
| `LearningRecurrence` / `LearningRecurrenceRun` | `agent-memory.db` | signature-only skill-workflow recurrence ledger |

**Why the split:** `agent-memory.db` is the *run* store (high-volume traces and
replayable retrieval receipts); `eclipse-memory.db` is the *control* store
(durable memory + the skill lifecycle). Keeping them separate means a large run
history never bloats the small, carefully-bounded control database. `SkillStore`
aliasing `EclipseMemoryStore` keeps a single implementation with no second
registry.

Immutable execution history is kept (a `SkillExecution` row is never mutated
after terminal status; a `SkillVersion` row is never edited — a new version is
inserted). Enabled behavior cannot change without a new `SkillVersion` row, and
the persisted version identity (`SkillManifest.version_identity`) covers the
instruction content as well as the manifest.

## Execution flow

```
SkillExecutionRequest (skillId, version, input, runId, parentRunId,
                       executionMode, actor/permissions, timeout, metadata)
      │
      ▼  registry.resolve + status + version + permission + dependency checks
      ▼  input schema validation (pydantic)
      ▼  compose AgentConfig (instructions + requiredTools allowlist)
      ▼  execute_run()  ← the EXISTING Phase-1 runtime (no new loop)
      ▼  output schema validation + evidence/warnings extraction
      ▼  persist SkillExecution + SkillEvent; emit skill.* lifecycle events
SkillExecutionResult (status, output, evidence, warnings, missingData,
                      limitations, traceId, runId, skillId, version, metrics)
```

The same contract serves every execution mode (`interactive`, `workflow`,
`scheduled`, `agent`, `evaluation`) — a skill never needs a mode-specific
implementation. Parent/child trace linkage is `parentRunId`; a nested skill call
is just a `SkillExecutionRequest` with the parent's run id.

## Dependencies and composition

Acyclic by construction. `registry.resolve_dependencies()` does a DFS with a
visiting-set; a cycle is a hard `CIRCULAR_DEPENDENCY` failure. Version
constraints are simple exact/`^`/`~`/`>=` comparators over semver. Missing
dependency, disabled dependency, or insufficient permission blocks before any
tool runs — the run is never partially executed.

## Permissions — enforced in code

`permissions.py` is the single authority. There is **no** scattered check.

- Default-deny: anything not explicitly granted is denied.
- Phase-3 safe set (granted to the default local actor): `data.read`,
  `research.read`, `analysis.execute`, `report.generate`, `skill.invoke`.
- Never granted: `trade.execute`, `broker.modify`, `production.modify`,
  `code.write` (and `code.execute`).
- `skill.create`, `skill.review`, `skill.enable`, `skill.disable` require
  **explicit authorization** (an operator secret / admin actor), not the default
  actor.

Markdown instructions are **not** a security boundary. Web/retrieved content is
data: it cannot change the system prompt, permissions, or policy. Skill
instructions can *describe* a procedure but can never *widen* a permission; the
allowlist and permission check are applied to the composed `AgentConfig` in
Python regardless of what the instructions say.

## Learning (controlled)

`learning.py` inspects a persisted run trace and **may** create a
`LearningCandidate` when explicit criteria are met (repeated failure solved by a
reusable procedure, a generalizable validation correction, a repeatedly
successful multi-step procedure, a verified fallback for missing data). It does
**not** create a skill. A candidate is inert until:

1. an operator generates a **draft** (`draft.py`) — always `status: draft`,
   always `evaluationStatus: not_evaluated`;
2. the draft is **evaluated** (`evaluation.py`);
3. evaluation passes the promotion gates;
4. an authorized actor **promotes** it.

At no point does a model-generated artifact become active automatically.
User-specific preferences stay in `AgentMemory`, not in a universal skill;
one-off market events are rejected as non-reusable.

## Evaluation

Deterministic checks first (manifest validation, schema validity,
dependency/permission resolution, attached test cases, regression comparison,
evidence/reporting-shape checks). An LLM judge is never the *only* mechanism and
never gates promotion. Results are stored per dimension — no single misleading
score. A failed mandatory dimension blocks promotion.

## Front door (Next.js)

The front door stays thin: it validates/proxies and renders. Python owns skills.
Routes added under `src/app/api/skills/**` and `src/app/api/learning/**` proxy to
the runtime's `/skills/**` endpoints with the same `api-guard` policy as
`/api/harness/*`. The UI is a new "Skills" tab in the existing sidebar, using the
existing frosted-glass system.

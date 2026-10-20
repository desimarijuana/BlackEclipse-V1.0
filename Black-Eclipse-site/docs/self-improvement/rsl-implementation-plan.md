---
title: Recursive Self-Improvement Loop (RSL) — Implementation Plan
status: Implemented (R0–R8)
last-verified: 2026-10-19
---

# Recursive Self-Improvement Loop (RSL) — Implementation Plan

**Implementation status (2026-10-19):** R0–R8 are implemented. R0–R1 added the
`python/harness/self_improvement/` scaffold (`RSLConfig`, `HarnessSnapshot`,
`Observation`), the deterministic observer, `record_mistake_recurrence` in
`code/evolution.py`, the `capture_mistakes` and `learning_review` hooks, and the
`self_improvement.candidate_created` event spec. R2 added the evaluator
identity (`agentVersion`/`gitCommit`/config/metadata), persisted task
fingerprints, `graderVersion` in trial scores, split selection
(`optimization`/`validation`/`held_out`/`release`), honest cost/latency
(`None`, never `0`), and measured-only improvement acceptance. R3 added the
isolated `CandidateAgentInvoker` over a validated `HarnessSnapshot`, plus the
frozen `RSL_DENY_GLOBS`/`assert_landable_target` target guard. R4 added the
bounded `RSLLoop` conductor, v1a code proposer, tests-only code verifier,
surface benchmark verifier, promotion-preview landing preparation, the
experiment recorder and lifespan wiring. R5 added the operator evidence routes
(`/evolution/experiments`, candidate evidence, `prepare-landing`), the typed
front door and the learning-journey experiment panel. R6 added migration 31
(`cue`, `adoptedArtifactType`, `adoptedArtifactId`, `validationRunId` on
`LearningCandidate`), the `self_improvement/lessons.py` cue/evidence/verdict
gate with cue+lesson dedupe, and the bounded `lesson_manifest` prompt segment
that retrieves only adopted lessons whose validation run completed and emits
`prompt.lesson_injected`. R7 added `propose_many` (typed `invariant`/`domain`
variants over operator/agent-supplied ops), the seeded anonymous
`selection.py`, the conservative `composition.py`, the bounded
`budgeted_k`/`run_recursive` conductor and the loop's `run_recursive` entry
point; contrast bundles are now wired and verdict-guarded. R8 added the
`rsl_experiments`/`rsl_accepted`/`rsl_rejected`/`rsl_unmeasured` +
`regression_rate` metric block in `evaluation/repair_metrics.py` (merged into
`code/evolution.archive_metrics` and the recovery route), the
`self_improvement/gate.py` offline end-to-end gate wired into
`scripts/test-evals.js`, and the rollout/flip documentation below. Code patches
record `benchmark="UNMEASURED"`; only surface candidates can claim a measured
delta. The ADR numbers below are **H217–H219 + H222–H224 + H233** (implemented)
because ADR-H216 is the Capability Studio and H220–H221 are reserved by the QA
Round 1 plan (`docs/harness/roadmap/qa-round-1-fixes.md`).

**Post-R8 closure (2026-10-19):** the measured surface path is now reachable and
the loop has its event wake. `EvolutionCandidate` gained additive
`subjectType`/`surfaceConfig` columns (idempotent `ALTER`, old rows default to
`code`); `POST /evolution/surface-experiments` validates a base/candidate
snapshot pair and a dataset/split, creates one `proposed` surface candidate, and
wakes the conductor. The verify tick dispatches `verify_surface_candidate`,
which runs the SAME base snapshot as a recorded `rsl-baseline`, benchmarks the
candidate on the selected tasks, persists the evaluator's decision on the
`EvaluationRun`, and records one `EvolutionAttempt` (so the daily budget counts
it) plus `self_improvement.experiment_completed`. `evaluation.started` now wakes
`RSLLoop`; `landing.prepare` explicitly refuses a surface subject
(`RSL_SURFACE_NOT_LANDABLE`). The learning-journey operator panel gained the
surface form. Production operator controls are `GET /evolution/rsl` (mode,
running/busy, daily budget), `POST /evolution/rsl/tick` (one bounded tick),
`POST /evolution/candidates/{id}/propose` (stage validated ops without applying)
and `rsl-control-panel.tsx`; §5.1 is the operator runbook. `npm run rsl:smoke`
runs a controlled end-to-end test in a disposable repo + temp `agent-memory.db`:
a failing owning test is fixed in a real worktree, then a scripted surface
baseline/candidate benchmark is recorded. The smoke exposed and fixed two real
code-verifier bugs: `_resolved_for` built no `WorkspaceBinding` (every write was
refused as `NO_BINDING`) and `_make_check_runner` returned an un-awaited
coroutine instead of a sync callable. Regression test:
`test_code_verifier_runs_the_owning_test_in_a_real_worktree`. v1b skill-draft
trials and the v1c model proposer are now implemented (ADR-H268). ADR-H233
records the subject-type decision.

**Who this is for:** anyone implementing the loop that turns Eclipse's own
observed failures into verified, operator-approved improvements to its harness.

**What this is:** the build plan for RSL v1 — a *conductor* over machinery that
already exists (post-run review, mistake capture, the recurrence ledger, the
evolution candidate store, the evaluator, worktrees, promotion and self-host
landing). It adds no second runtime, database, queue, evaluator, provider or
memory system.

**Relationship to the existing programs (do not duplicate them):**

| Program | Owns | RSL's role |
|---|---|---|
| `docs/harness/self-evolution-roadmap.md` | The meta loop (W0–W15) and its invariants; recovery incidents; routing repair | RSL is the **experiment conductor** that closes the loop between observation and verified promotion |
| `docs/self-improvement/architecture-audit.md` | The Harness² integration audit (Phases 0–8) | RSL v1 is the **native** path; the Harness² adapter stays optional and blocked on Phase 1 |
| `docs/self-improvement/harness2-borrowings.md` | The mechanism steal-list (verdict tripwire, contrast bundle, selection, lesson gate) | RSL wires those mechanisms in later phases |
| `docs/harness/roadmap/phase-10-self-improvement.md` | Code/skill evolution v2 (candidate → worktree → owning tests → operator) | RSL extends it with a trigger, benchmark verification, experiment records and landing preview |

**Definition.** RSL is the bounded, deterministic loop:

```
observe → diagnose → propose → verify → record → operator decision → land → learn
```

"Recursive" means two things, introduced in order:

1. **Task-level recursion** (R7): more than one candidate is proposed from the
   same evidence, verified independently, and the best composition is selected.
2. **Harness-level recursion** (R6): verified lessons are stored with a cue and
   retrieved on later tasks, improving future proposals.

Neither level is autonomous activation. Every harness change remains
operator-confirmed (invariant §5.3 of the self-evolution roadmap).

---

## 0. RSL v1 — scope and definition of done

### In scope

- Observe failed/repeated runs deterministically; create inert candidates.
- Verify a candidate by **owning tests in a worktree** and by a **benchmark
  comparison** against a frozen baseline on a validation split.
- Record every experiment with reproducible provenance.
- Prepare a promotion preview for the operator; never land automatically.
- Store a validated lesson with cue + evidence and retrieve it later.
- Report honest metrics: unmeasured stays `UNKNOWN`, never `0`.

### Out of scope for v1

- Autonomous activation or self-granted authority.
- Editing the evaluator, graders, scoring, gates, policy, approvals, security,
  tests or benchmark datasets.
- A new database, queue, scheduler or event bus.
- Unbounded candidate generation (`k>1` is R7, behind a flag).
- The Harness² framework itself (external, Linux-only, research-grade).

### RSL v1 definition of done

One real recurring production failure travels the whole chain:

1. Three or more occurrences (the existing `RECURRENCE_THRESHOLD = 3`) produce a
   durable observation.
2. Exactly one deduplicated candidate is created.
3. A proposal is written and passes the subject allowlist.
4. Owning tests pass in a disposable worktree.
5. The candidate beats the baseline on the targeted dimension on the
   **validation** split, with no critical regression and a measured sample.
6. The decision and evidence are recorded with complete provenance.
7. The operator previews the exact change and approves it through the existing
   single-use promotion approval.
8. The change is applied through `code/selfhost.py` (restart/build verdict),
   health-checked, and rolled back atomically if the check fails.
9. A lesson with `cue` + `evidence` is stored and retrieved by a later task.
9b. An inert skill draft can be listed in a candidate snapshot, measured in the
   trial (instructions + required tools validated), and is still refused for
   live activation.
10. A rejected candidate is reverted and never activates.
11. The loop is restart-safe, budget-capped and auditable.

Acceptance evidence is a checked-in end-to-end test using the scripted invoker
plus one operator-run live experiment. No claim of improvement without a
recorded benchmark delta.

---

## 1. Verified current state (2026-10-18)

### What already works

| Concern | Owner | Status |
|---|---|---|
| Post-run review and mistake capture | `learning_review.py`, `eclipse_memory/service.py:1231`, `eclipse_memory/mistakes.py:433` | Wired: `service.py:1166` enqueues a review for every completed/failed run |
| Inert learning candidates | `eclipse_memory/schema.py:251`, `skills/learning.py` | Wired; never auto-enabled |
| Recurrence ledger | `persistence.py:727` (`record_learning_recurrence`), `learning_recurrence()` | Exists; one counter for learning signatures |
| Mistake→candidate bridge | `code/evolution.py:112` (`candidates_from_mistakes`) | Exists, **no production caller** |
| Candidate/attempt persistence | `code/evolution_store.py` (`EvolutionCandidate`, `EvolutionAttempt`) | Exists on `agent-memory.db`, nullable cost columns |
| Worktree test evaluation | `code/evolution_service.py:87` (`evaluate`), `code/evolution.py:317` | Exists; applies ops in a worktree and runs owning tests |
| Benchmark verification | `evaluation/improvement.py:101` (`evaluate_candidate`), `:169` (`run_loop`) | Exists; **test/CLI only** |
| Evaluator | `evaluation/runner.py`, `graders/`, `scoring.py`, `regression.py` | Complete; 53 tasks across four datasets (`benchmark_v1` 31, `construction_v1` 16, `routing_e2e_v1` 4, `team_v1` 2) |
| Failure mining | `evaluation/mining.py` | Exists; **CLI only** (`evaluation/cli.py:218`) |
| Failure event | `event_system/service.py:218-243` publishes `evaluation.started` | Emitted; **no consumer runs an evaluation** |
| Operator routes | `routers/evolution.py`, `routers/evaluation.py`, `routers/code.py` | Operator-gated |
| Real landing path | `code/promotion.py` + `code/selfhost.py` + `/code/tasks/{id}/promote` | Exists, single-use digest-bound approval |

### The breaks RSL must close

1. **No recurrence is written for mistake categories.** Only tests call
   `record_learning_recurrence(_category_signature(...))`
   (`test_evolution_bridge.py:24`). Production writes tool-derived signatures,
   so `candidates_from_mistakes` never fires. **Resolved by R1**
   (`capture_mistakes` now writes the ledger).
2. **No conductor.** Nothing scans candidates, applies a proposal, runs the
   benchmark and records a decision. **Open (R4).**
3. **No candidate invoker.** The evaluator can run the scripted tier and the
   production service, but not an isolated candidate `AgentConfig`. **Resolved
   by R3** (`evaluation/candidate_invoker.py`).
4. **Provenance is incomplete.** `run_suite` leaves `agentVersion`/`gitCommit`
   NULL, `config` is only `{trials, tier}`, task fingerprints are never
   persisted, and real cost/latency are not carried from the model runtime
   (`runner.py:622-629`, `trajectory.py:204`). **Resolved by R2**
   (`evaluation/provenance.py`).
5. **Landing is split.** `evolution_service.activate` records a skill-version
   decision (verified at `evolution_service.py:190-265`); it does **not** write
   the checkout. The real write path is `promotion` + `guarded_land`. RSL must
   use one landing path: promotion.
6. **The candidate can edit its own judge.** `FROZEN_PATHS` covers four files
   (`code/evolution.py:50`), but not `python/tests/**`, evaluator assets or
   dataset files. `evaluate_candidate` runs owning tests, so a candidate that
   edits its test could game the gate. RSL must freeze tests and evaluation
   assets. **Resolved by R3** (`self_improvement/security.py`
   `RSL_DENY_GLOBS`/`assert_landable_target`).
7. **Lessons lack a cue gate.** `LearningCandidate` had no `cue`; retrieval was
   not wired to a later run. **Resolved by R6**
   (`self_improvement/lessons.py` + the `lesson_manifest` prompt segment).
8. **No split policy.** `select_tasks` exists (`tasks.py:294`) but there is no
   optimization/validation/held-out split, so optimization can overfit the
   acceptance set. **Resolved by R2** (`select_tasks(split=...)`).

---

## 2. Architecture

### 2.1 Component map

```
                    ┌─────────────────────────────────────────────┐
 run.completed ───► │ learning_review.review_run                  │
 run.failed    ───► │   ├─ analyze_run (mistakes, candidates)     │
                    │   └─ observer.observe_run                   │
                    └───────────────┬─────────────────────────────┘
                                    │ inert observation / candidate
                                    ▼
                    ┌─────────────────────────────────────────────┐
                    │ RSL conductor (self_improvement/loop.py)    │
                    │  scan → propose → verify → record → wake    │
                    └───────┬───────────────┬─────────────┬───────┘
                            │               │             │
             proposer.py    │      verifier.py│      landing.py
        (ops / skill /      │   (worktree tests│   (promotion preview)
         snapshot)          │    + benchmark)  │
                            ▼                 ▼             ▼
                  EvolutionStore      EvaluationRunner   promotion + selfhost
                  EvaluationStore     candidate invoker  (operator-approved)
                  LearningCandidate   baseline/gates     restart → verify → rollback
                            │
                            ▼
                    lessons.py → cue/evidence gate → later runs
```

### 2.2 Runtime location and lifecycle

- Module home: `python/harness/self_improvement/`.
- The loop is one bounded `asyncio` task started and stopped by the existing
  lifespan, exactly like `learning_review` (`service.py:1018-1029`,
  `boot.py:108`/`:243`). It is **not** a fabric worker and adds no worker kind.
- Durability is the candidate/attempt/experiment rows themselves. A crash
  leaves `evaluating` rows; boot reclaims a stale lease and resumes once.
- Wake conditions: a post-review observation, an `evaluation.started` event
  (already emitted on failure), an operator action, or the periodic tick.
- Single-flight: one experiment at a time globally by default; per-candidate
  single-flight by lease.

### 2.3 State machine

Reuse the existing `EvolutionStore.STATUSES`; add no parallel vocabulary.

```
inert ──propose──► proposed ──claim──► evaluating ──pass──► evaluated_ok
                      │                     │
                      │                     └──fail──► evaluated_bad
                      └──invalid/frozen──► refused

evaluated_ok ──operator prepare──► landing preview
             ──operator approve──► activated / canaried ──regression──► rolled_back
             ──operator dismiss──► dismissed
```

`evaluating` is the lease state. A row older than `lease_timeout_s` is
reclaimed with an attempt row that records `outcome="failure"` and
`outcomeReason="lease expired"`.

---

## 3. Contracts and data model

### 3.1 `HarnessSnapshot` (new, `self_improvement/models.py`)

The only candidate surface RSL may vary in v1:

```python
@dataclass(frozen=True)
class HarnessSnapshot:
    sourceDigest: str              # sha256 of the canonical JSON
    systemPrompt: str              # <= 16_000 chars
    toolNames: tuple[str, ...]     # must be a subset of the base allowlist
    maxSteps: int                  # 1..32
    maxToolCalls: int              # 0..200
    modelProvider: str | None
    modelName: str | None
    temperature: float | None
    skillDraftIds: tuple[str, ...] = ()   # inert drafts only
```

`to_agent_config()` returns a validated `AgentConfig` (`schemas.py:118`).
`validate_snapshot(base, candidate)` refuses: a tool not in the base allowlist,
a raised step/call ceiling beyond policy, an unknown skill id, or any attempt to
set permission/risk/identity fields.

### 3.2 Experiment record (no schema change)

`EvaluationRun` already has `config` and `metadata` (`evaluation/store.py:258`).
RSL stores identity there:

```json
{
  "kind": "rsl",
  "proposalId": "evo_...",
  "baselineRunId": "evalrun-...",
  "split": "validation",
  "generation": 0,
  "targetDimension": "tool_selection",
  "decision": "accepted",
  "decisionReason": "target improved; no critical regression",
  "harnessDigest": "…"
}
```

`config` records `{trials, tier, seed, temperature, snapshot}`. The snapshot is
canonical JSON, so `harnessDigest` is reproducible. No `harness_revisions`
table is needed for v1; add one only when a query needs immutable revision
lineage (the audit's Phase 5), with a documented reason.

### 3.3 Observation record

```python
@dataclass(frozen=True)
class Observation:
    kind: str                 # "mistake_recurrence" | "mined_failure" | "operator"
    signature: str
    runId: str | None
    category: str
    observedCount: int
    targetHint: str | None    # from CATEGORY_TARGETS
    evidenceRunIds: tuple[str, ...]
```

Mined failures are **evidence**, not benchmarks. `mining.mine_failure` stores a
candidate task with `expected_behavior: None`; RSL never invents the expected
behavior. A mined task enters the suite only after `promote_candidate` supplies
a validated expectation (`mining.py:123`).

### 3.4 Lesson columns (additive migration 31)

`LearningCandidate` already has `proposedLesson`, `evidenceReferences`,
`knownLimitations`, `scope`, `diagnostics`. Add:

```sql
ALTER TABLE LearningCandidate ADD COLUMN cue TEXT;
ALTER TABLE LearningCandidate ADD COLUMN adoptedArtifactType TEXT;
ALTER TABLE LearningCandidate ADD COLUMN adoptedArtifactId TEXT;
ALTER TABLE LearningCandidate ADD COLUMN validationRunId TEXT;
```

Idempotent `ALTER` guarded by a column check (the migration runner is
`eclipse_memory/db.py::_migrate`; next version 31). If the columns already
exist, the migration is a no-op. No new table.

### 3.5 Candidate invoker

`CandidateAgentInvoker` implements `evaluation.runner.AgentInvoker` (`:125`):

- per-trial temp dir + private `AgentMemoryStore` + private `ToolRegistry`
  (`_build_registry`, `runner.py:132`);
- `RunRequest(agent=snapshot.to_agent_config())` through `execute_run`;
- `_UnavailableBridge` by default; a live bridge is opt-in and must pass the
  existing authorization path;
- returns `InvocationResult` with the collected events;
- cleans up; never writes the production store.

### 3.6 Landing contract

`landing.prepare(candidate)` mirrors `recovery/routing_landing.py:49-123`:

1. allocate a disposable worktree;
2. apply the candidate's validated ops;
3. save the workspace under a synthetic run id (`rsl-<candidateId>`);
4. call `promotion.build_preview(run_id, code_store=...)` (`promotion.py:150`);
5. call `selfhost.classify_landing(paths)` (`selfhost.py:81`);
6. return `{preview, landing}` and never apply.

The operator then uses the existing `/code/tasks/{runId}/promote/preview` and
`/promote` routes with the existing single-use, digest-bound approval. No
second approval system.

### 3.7 Surface candidate row (post-R8)

A surface subject reuses the ONE `EvolutionCandidate` row and adds two
idempotent columns:

```sql
ALTER TABLE EvolutionCandidate ADD COLUMN subjectType TEXT NOT NULL DEFAULT 'code';
ALTER TABLE EvolutionCandidate ADD COLUMN surfaceConfigJson TEXT;
```

`surfaceConfigJson` carries the validated base + candidate `HarnessSnapshot`,
the dataset file/split/task ids, target dimension, trials, seed and an optional
baseline run id. The route creates the row as `proposed`; the verify tick
dispatches `verifier.verify_surface_candidate`. That function runs the base
snapshot as a `rsl-baseline` run (or reuses a recorded baseline only when its
`baseDigest` and task fingerprint still match), then calls the existing
`verify_surface` path. The evaluator's decision is persisted on the
`EvaluationRun`; the loop records one `EvolutionAttempt` and the completion
event. `HarnessEvent.runId` has a foreign key to `HarnessRun`, so the recorder
creates one bounded record container for the experiment id when (and only when)
no real run with that id exists. `landing.prepare` refuses a surface subject with
`RSL_SURFACE_NOT_LANDABLE` — a snapshot has no code change to promote in v1.
`test_rsl_surface_e2e.py` drives route → conductor → real baseline/candidate
runs on one scripted task.

---

## 4. Work breakdown

Estimates are for one engineer who knows the repo. Every phase ends with tests,
`npx tsc --noEmit`, and a `CHANGELOG.md` entry.

### R0 — Decisions and scaffolding (0.5 day)

**Goal:** lock the architecture and add a dark, no-op module.

Tasks:

- ADR-H217: RSL is a conductor over existing owners; no new runtime/DB/queue.
- ADR-H218: one landing path — `promotion` + `guarded_land`; `evolution_service.activate`
  is a skill-version path, not a code write, and must not be presented as landing code.
- ADR-H219: RSL subject denylist includes tests, evaluator, graders, scoring,
  regression gates, datasets, policy, approvals, security and the loop itself.
  (ADR-H216 is already the Capability Studio.)
- Create `python/harness/self_improvement/{__init__,config,models}.py`.
- `RSLConfig.from_env()` with clamps and defaults:

  | Variable | Default | Meaning |
  |---|---|---|
  | `HARNESS_RSL_MODE` | `off` | `off` / `observe` / `propose` / `verify` |
  | `HARNESS_RSL_MAX_CANDIDATES` | `5` | per scan |
  | `HARNESS_RSL_MAX_EXPERIMENTS_PER_DAY` | `3` | global cap |
  | `HARNESS_RSL_TRIALS` | `3` | benchmark trials for acceptance |
  | `HARNESS_RSL_K` | `1` | candidates per proposal (R7 allows >1) |
  | `HARNESS_RSL_TICK_SECONDS` | `300` | periodic wake |
  | `HARNESS_RSL_LEASE_SECONDS` | `1800` | stale `evaluating` reclaim |
  | `HARNESS_RSL_MAX_WALL_SECONDS` | `1800` | one experiment |
  | `HARNESS_RSL_MAX_COST_USD` | `5` | hard budget; unknown cost stops verification |
  | `HARNESS_DRIFT_WATCH_SECONDS` | `300` | read-only drift cadence; `0` disables |

- `config.py` tests: defaults, clamps, mode off is a no-op.

**Acceptance:** the module imports with no behavior change; `HARNESS_RSL_MODE=off`
returns an empty tick.

### R1 — Observation closure (1–2 days)

**Goal:** make the existing bridge fire, deterministically and without model
calls.

Tasks:

- `code/evolution.py`: add `record_mistake_recurrence(run_store, categories,
  run_id)` calling `run_store.record_learning_recurrence(_category_signature(c),
  run_id)`.
- `eclipse_memory/mistakes.py::capture_mistakes`: after the mistake rows are
  persisted, call the recorder for the returned categories. `analyze_run` is the
  production path that invokes it. Failures never break the run.
- `self_improvement/observer.py::observe_run(run_id, status, *, run_store)`:
  - if `status == "failed"`, call `mining.mine_from_store` (bounded, deduped);
  - call `evolution.candidates_from_mistakes`;
  - emit `self_improvement.candidate_created` for each new row.
- `learning_review.py`: after the deterministic analysis, call
  `observer.observe_run` (best-effort, bounded).
- `event_system/registry.py`: add the `self_improvement.candidate_created`
  spec (producer `self_improvement`, retention 90 days).
- `event_system/service.py`: the existing `evaluation.started` failure trigger
  becomes the loop's wake signal; it does not run an evaluation itself.

Tests (`test_rsl_observation.py`):

- repeated category writes recurrence once per run and creates one candidate;
- a single occurrence creates none;
- two identical failed runs mine one candidate (dedupe);
- a failing observer never changes the run response;
- mode `off` records nothing.

**Acceptance:** a fixture run repeated three times yields exactly one
`EvolutionCandidate` and one mined `EvaluationCandidate`.

### R2 — Experiment identity and provenance (2–3 days)

**Goal:** make baseline vs candidate comparisons trustworthy before any
optimization is enabled.

**Status (2026-10-18): implemented.** The identity/provenance contract,
split selection, task fingerprints, grader version, cost/latency honesty and
measured-only acceptance are in `evaluation/provenance.py`, `runner.py`,
`tasks.py`, `scoring.py` and `improvement.py`; tests live in
`python/tests/test_rsl_provenance.py`.

Tasks:

- `evaluation/tasks.py`: add `split` to dataset metadata and `select_tasks(...,
  split=...)`; allowed values `optimization`, `validation`, `held_out`,
  `release`. Default is `validation`.
- `evaluation/runner.py::run_suite`: populate `agentVersion` and `gitCommit`
  (from `code/version.py`/git, empty when unavailable), `provider`/`model`
  from the invoker, `config` with trials/tier/seed/temperature and the snapshot
  digest.
- Call `eval_store.upsert_task(task)` for every selected task before the run
  (`store.py:236` currently has no callers).
- Record `GRADER_API_VERSION` in run metadata and in each trial's score JSON.
- `trajectory.derive_metrics`: read `latencyMs` from `model.request.completed`
  (`service.py:534` republishes it) and cost/tokens from the model runtime's
  `ModelRequest` rows / `CostEngine`; leave `UNKNOWN` when absent.
- `evaluation/improvement.py`: accept `trials` in `run_loop`; require
  `measured > 0`; never accept an unmeasured dimension.
- Add `EvaluationStore.create_experiment(...)`? No — use `create_run` with the
  metadata contract above. Add a `require_provenance(run)` helper that rejects
  a baseline with a NULL dataset checksum or empty config.
- Fix `docs/harness/agent-evaluation.md` drift (47 → 53 tasks across four
  datasets, add
  `routing_e2e_v1.json`).

Tests (`test_rsl_provenance.py`):

- two runs of the same dataset share task fingerprints;
- baseline and candidate differ only by the documented config identity;
- a NULL-provenance run is rejected by `require_provenance`;
- cost/latency are `None` (not 0) when the source is absent;
- split selection never returns a held-out task to the proposer.

**Acceptance:** `EvaluationRun` for a baseline and a candidate are comparable and
traceable to exact task versions and grader versions.

### R3 — Candidate invoker and snapshot validation (2–3 days)

**Goal:** run an arbitrary candidate harness safely.

**Status (2026-10-18): implemented.** `evaluation/candidate_invoker.py`
(`CandidateAgentInvoker`, `validate_snapshot`, `base_snapshot_from_agent`) and
`self_improvement/security.py` (`RSL_DENY_GLOBS`, `assert_landable_target`) are
in place; tests live in `python/tests/test_rsl_{snapshot,candidate_invoker}.py`.
Code-patch candidates are still owning-tests-only until R4 resolves the
worktree-benchmark gap.

Tasks:

- `evaluation/candidate_invoker.py` with `HarnessSnapshot` and
  `CandidateAgentInvoker` (Section 3.5).
- Per-trial isolation copies the scripted tier recipe (`runner.py:238-306`):
  private store, private registry, environment binding, cleanup.
- Reuse `_RecordingRegistry` so tool arguments are graded honestly.
- `validate_snapshot(base, candidate)` and `assert_landable_target(target)`:
  - tool subset of the base allowlist;
  - no permission/risk/identity fields;
  - target not in `RSL_DENY_GLOBS`.
- `RSL_DENY_GLOBS` (enforced before `propose_ops`):

  ```
  python/harness/evaluation/**
  python/harness/security/**
  python/harness/code/policy.py
  python/harness/code/authorizers.py
  python/harness/code/promotion.py
  python/harness/code/selfhost.py
  python/harness/code/evolution*.py
  python/harness/mcp/approvals.py
  python/harness/skills/permissions.py
  python/tests/**
  python/harness/evaluation/datasets/**
  scripts/test-*.js
  .env
  jdds.db
  ```

  Tests files are frozen because `evaluate_candidate` runs them; a candidate
  that edits its own test is not a candidate.

Tests (`test_rsl_snapshot.py`, `test_rsl_candidate_invoker.py`):

- two candidates produce distinct runs on the same task;
- a candidate cannot add a tool outside the base allowlist;
- a forbidden path is refused with a structured code;
- an op targeting a test file is refused;
- concurrent trials cannot see each other's store;
- the production store is unchanged after a candidate run.

**Acceptance:** a scripted candidate harness runs end-to-end on one benchmark
task and is graded, with zero writes to production state.

### R4 — The conductor (3–5 days)

**Goal:** close the loop with deterministic orchestration.

**Status (2026-10-18): implemented for the approved R4 scope.** The conductor,
v1a code proposer, tests-only code verifier, surface benchmark verifier,
landing preview, recorder and lifespan wiring are in place. Code patches record
`benchmark="UNMEASURED"`; only surface candidates can claim a measured delta.
v1b skill drafts and v1c model proposals are now implemented (v1b: inert drafts in candidate trials; v1c: flag-gated model proposer).

Tasks:

- `self_improvement/loop.py`:
  - `RSLLoop.start/stop/tick`;
  - `scan()` claims at most `max_candidates` rows;
  - `claim(candidate_id)` uses an atomic `UPDATE ... SET status='evaluating'
    WHERE id=? AND status IN ('inert','proposed')` and checks `rowcount`;
  - `resume()` reclaims leases older than `lease_timeout_s`;
  - `budget_ok()` enforces daily experiment count, wall clock and cost;
  - one experiment at a time; cancellation is cooperative.
- `self_improvement/proposer.py`:
  - v1a (implemented): `propose_from_ops(store, candidate_id, actor=...)` —
    operator/agent-supplied ops, validated by `assert_landable_target` (target
    and every op path) + `propose_ops` + the RSL denylist;
  - v1b/v1c (implemented): inert skill drafts in candidate trials and a bounded model
    proposer behind their own flags.
- `self_improvement/verifier.py`:
  - `verify_code(store, candidate_id, ctx=...)`: owning tests in a worktree via
    `evolution_service.evaluate`; returns `benchmark="UNMEASURED"` and
    `decision="tests_only"` (a worktree code patch is invisible to the snapshot
    invoker, so no benchmark delta is claimed);
  - `verify_surface(...)`: the ONLY measured path — `CandidateAgentInvoker` +
    `improvement.evaluate_candidate` on validation with a baseline;
  - `verify_skill(...)`: `skills/versioning.evaluate_version`; benchmark stays
    UNMEASURED in R4.
- `self_improvement/landing.py`: `prepare(candidate)` (Section 3.6) — validates
  the target/ops, applies them in a disposable worktree, and returns the existing
  `promotion.build_preview`; it never applies.
- `self_improvement/recorder.py`: writes the `EvaluationRun` identity and the
  `self_improvement.experiment_completed` event; the `EvolutionAttempt` is
  written by `evolution_service.evaluate` (no duplicate attempt). The baseline
  is never overwritten.
- `boot.py`: start/stop the loop with the existing lifespan (no `service.py`
  growth).

Tests (`test_rsl_loop.py`, `test_rsl_landing.py`, `test_rsl_verifier.py`):

- accepted/rejected/unmeasured code decisions, with the benchmark UNMEASURED;
- a surface candidate is benchmarked and persisted as MEASURED;
- a lease expiry is reclaimed exactly once;
- the daily budget stops a fourth experiment;
- a new loop picks up a proposed candidate;
- `HARNESS_RSL_MODE=observe` never runs a candidate;
- `landing.prepare` produces the existing promotion preview and refuses frozen
  or unevaluated candidates.

**Acceptance:** observation → candidate → owning tests (benchmark UNMEASURED)
→ decision → landing preview with no activation; the surface path additionally
records a measured benchmark delta.

### R5 — Operator surface (2 days)

**Goal:** make the evidence reviewable and landable without a database shell.

**Status (2026-10-18): implemented.** The operator can list/inspect RSL
experiments, read a candidate's attempts + experiments, and prepare a landing
preview from the learning journey. The existing `/activate` route remains the
skill-version route (not overloaded); code landing is `prepare-landing` followed
by the existing `/code/tasks/{runId}/promote` approval. Code rollback stays on
the existing promotion rollback route. Baseline-vs-candidate regression display
is the R4/R7 experiment metadata, not a second approval surface.

Tasks:

- Extend `routers/evolution.py` (not a new route group):
  - `GET /evolution/experiments` and `GET /evolution/experiments/{runId}`
    (run identity, metrics, bounded trial scores);
  - `GET /evolution/candidates/{id}/evidence` (candidate + attempts + linked
    RSL experiments);
  - `POST /evolution/candidates/{id}/prepare-landing` → `landing.prepare`;
    returns the preview + the existing promotion route, never applies;
  - the existing `/activate` and `/rollback` routes stay the skill-version
    lifecycle; code landing/rollback use the existing promotion routes.
  - Every route keeps `require_operator`, reads included.
- Front door: `src/lib/harness/evolution-client.ts` gains experiment/evidence
  types and calls; `evolution-browser.ts` serves the client panel;
  `src/app/api/evolution/experiments/route.ts` + `[id]/route.ts`,
  candidate `evidence` and `prepare-landing` proxy.
- UI: extend `src/components/screens/skills/learning-journey.tsx` with
  `rsl-experiments-panel.tsx`: experiment list, honest benchmark badge
  (MEASURED vs UNMEASURED), tests result, decision, target, and "Prepare
  landing" (only for a tests-passed code experiment). No new screen.
- i18n keys under `evolution.experiment.*`.

Tests:

- every new route is operator-gated (403 without the token);
- the client types match the runtime JSON;
- a component test renders measured/unmeasured and tests passed/failed states;
- `prepare-landing` never writes the checkout (landing test).

**Acceptance:** an operator can inspect evidence and prepare a landing from the
UI; the actual write still requires the existing promotion approval.

### R6 — Lessons and retrieval (3 days)

**Goal:** make verified changes reusable by later tasks.

**Status (2026-10-19): implemented.** Migration 31 adds the four additive
`LearningCandidate` columns (idempotent `ALTER` guarded by a column check in
`eclipse_memory/db.py`). `self_improvement/lessons.py` refuses a missing
cue/lesson/evidence, discards a non-adopted decision, runs the verdict tripwire
on the cue+lesson+evidence text, dedupes by cue+lesson signature, and records
the adopted artifact + validation run. `prompt_segments.build_lesson_manifest`
is a hard 3-lesson / 800-character formatter; `_lesson_manifest_context`
retrieves only adopted lessons with a completed validation run whose cue and
scope match the current turn, emits `prompt.lesson_injected` with the lesson ids
and their origin/validation/artifact references, and injects a labelled,
non-authoritative block. The operator surface is
`GET /evolution/lessons` + `POST /evolution/candidates/{id}/lessons` (the route
derives the accepted decision from the persisted experiment, never from the
request) plus the typed front door and the learning-journey operator panel.
Tests live in `python/tests/test_rsl_lessons.py` +
`test_evolution_rsl_operator.py`.

Tasks:

- Migration 31: the four `LearningCandidate` columns (Section 3.4).
- `self_improvement/lessons.py`:
  - `distill_lesson(candidate, decision, evidence)` requires non-empty
    `cue`, `lesson`, `evidence`; otherwise it is discarded (upstream's rule);
  - run `evaluation/verdict_guard.py` on the lesson text before storing;
  - store with `adoptedArtifactType/Id` and `validationRunId` from the
    experiment;
  - dedupe by cue+lesson signature.
- `prompt_segments.py`: add a bounded lesson manifest (max 3 lessons, 800
  chars) selected by cue; emit `prompt.lesson_injected` with lesson ids.
- Retrieval is deterministic and scoped: a lesson is eligible only for its
  domain/scope and only after its validation run completed.
- Tests (`test_rsl_lessons.py`): missing cue/evidence discarded; verdict leak
  refused; a later matching task receives the lesson; no matching cue means no
  injection; the manifest stays within budget.

**Acceptance:** a lesson from experiment N is retrieved on a later matching
task with origin, scope, validation run and version traceable.

### R7 — Recursive candidates (3–4 days, optional after v1)

**Goal:** the "recursive" step: more than one candidate from the same evidence,
compared and composed.

**Status (2026-10-19): implemented for the deterministic, operator-supplied
scope.** `proposer.propose_many` builds up to `k` typed `invariant`/`domain`
proposals from the same observation and validates each independently against the
frozen denylist + `propose_ops`; it never invents a patch or calls a model.
`selection.py` assigns seeded anonymous labels, drops non-answers with a cause,
falls back neutrally to the base and makes `k=1` trivial. `composition.py` only
merges verified, non-conflicting ops and claims a gain only when a measured
validation score beats the best single candidate; otherwise it records
`no_gain`. `recursion.run_recursive` verifies each proposal through the caller's
existing verifier, builds and verdict-guards contrast bundles when trajectories
are supplied, records ONE `EvaluationRun` with the selection/composition, and
enforces `budgeted_k` (the daily budget caps `k`). `RSLLoop.run_recursive` uses
the loop's configured `k`, stores, actor, budget and lease-free single
experiment. The operator surface is `POST /evolution/candidates/{id}/recursive`
(typed variants; the route persists child candidates, verifies each through the
existing worktree verifier, and records the R7 selection/composition) plus the
typed front door and the learning-journey operator panel. `k=1` remains the
default; no model proposer and no autonomous activation. Tests live in
`python/tests/test_rsl_recursion.py` + `test_evolution_rsl_operator.py`.

Tasks:

- `proposer.py`: `propose_many(observation, k)` with typed candidates
  `invariant` / `domain` (INV/DOM).
- `selection.py`: seeded anonymous ids (`A`, `B`, …), drop non-answers with a
  recorded cause, neutral fallback to the base, `k=1` trivial path.
- `contrast.py`: evidence bundle per candidate (already exists; wire it).
- `verdict_guard.py`: scan every bundle before any model sees it (already
  exists; wire it).
- Composition: a deterministic stage that selects the best verified candidate
  or merges non-conflicting verified ops; never merges unverified claims.
- Cost cap: `k` counts against the daily budget; `k=1` remains the default.
- Tests: deterministic anonymization; no verdict leak; composition beats the
  best single candidate on validation or reports no gain; budget stops at k.

**Acceptance:** one experiment with `k>1` produces a recorded selection and
either a verified composition or an honest "no improvement".

### R8 — Measurement, rollout and docs (2 days)

**Status (2026-10-19): implemented.** `evaluation/repair_metrics.py` now computes
`rsl_experiments`, `rsl_accepted`, `rsl_rejected`, `rsl_unmeasured` and
`regression_rate` from completed RSL `EvaluationRun` rows; missing sources stay
`None`. `archive_metrics` and `GET /recovery/metrics` merge the block from the
real stores, and the surface verifier persists the evaluator's decision so no
metric has to infer it from a score. The deterministic offline gate
(`self_improvement/gate.py`, wired into `scripts/test-evals.js`) runs one
scripted `k=2` experiment through selection/composition plus the metric block.
No default changed: `HARNESS_RSL_MODE` remains `off`; the rollout sequence and
flip criteria below are the operator checklist, not automatic behavior.

Tasks:

- Metrics: extend `evaluation/repair_metrics.py` / `archive_metrics` with
  `rsl_experiments`, `rsl_accepted`, `rsl_rejected`, `rsl_unmeasured`,
  `self_repair_precision`, `time_to_repair_ms`, `regression_rate`,
  `cost_per_success`; missing inputs stay `None`.
- Gate: add deterministic RSL tests to `scripts/test-evals.js`; the scripted
  end-to-end test must run offline.
- Rollout:
  1. `HARNESS_RSL_MODE=off` (dark) until R1–R3 are merged.
  2. `observe` for one week: deterministic observations only, no model calls,
     no candidate execution. Measure candidate volume and noise.
  3. `propose` for operator-selected candidates: no automatic evaluation.
  4. `verify` with `max_experiments_per_day=1`, then `3` if precision holds.
  5. `k>1` only after v1 has one verified landed change.
- Flip criteria: no critical regression, acceptance precision ≥ 0.5 on
  validation, cost within budget, operator review load acceptable.
- Docs: update `docs/NAVIGATION.md`, `docs/harness/architecture.md` (new
  module), this plan's status, ADRs, and `CHANGELOG.md`.

**Acceptance:** the release gate is green; the capability statement reports
measured values or `UNMEASURED`, never a guess.

---

## 5. Safety floor (must be enforced in code, not prose)

1. **Authority is frozen.** Candidates may not edit the evaluator, graders,
   scoring, regression gates, policy, approvals, security, tests, datasets or
   the RSL loop itself. The denylist is checked before `propose_ops` and again
   before landing.
2. **No self-granted authority.** A candidate may not set identity,
   permissions, tool allowlists, risk classes or approval state. This extends
   `skills/patches.py::FORBIDDEN_FIELDS`.
3. **No test gaming.** Every op path is checked against `RSL_DENY_GLOBS`; the
   owning test file must be byte-identical to the checkout at evaluation time.
   Record the test file hash in the attempt.
4. **No verdict leakage.** `verdict_guard` scans evidence bundles and lesson
   text before a model sees them. A leak is a hard error, never a warning.
5. **No fabricated expectations.** Mined failures carry
   `expected_behavior: None`; only `promote_candidate` with an explicit
   validated expectation can put them in the suite.
6. **No silent pass.** Unmeasured dimensions are `UNKNOWN`; an experiment with
   zero measured trials is `unmeasured`, never accepted.
7. **Operator-only landing.** The loop produces a preview. The write requires
   the existing single-use, digest-bound promotion approval; the loop never
   consumes an approval.
8. **Budgeted.** Daily experiments, wall clock, model calls, tokens and cost
   are capped. A budget breach stops the loop and records a refusal.
9. **Loop-guarded.** Max generation, one experiment per candidate, dedupe by
   signature, and at most two auto-triggered experiments per correlation
   (mirroring `event_system/service.py:36-39`).
10. **One runtime.** Candidate runs go through `execute_run`; no second graph,
    registry or provider path.

---

## 5.1 Production operator runbook

Preconditions: the Python runtime is healthy, the operator token/loopback path
is available, and the evaluation stack is installed. RSL stays dark until the
operator sets a mode; a mode change requires a runtime restart.

**0. Run the controlled smoke test.**

`npm run rsl:smoke` uses a disposable git repo and a temp `agent-memory.db`:
it fixes a failing owning test through the real worktree verifier, then records
a scripted surface baseline/candidate experiment. It never touches the checkout
or the developer's databases. Run it before enabling a mode.

**1. Inspect the conductor.**

- UI: the learning journey → RSL conductor card shows mode, running/busy,
  today's budget, `k`, and the periodic tick.
- API: `GET /evolution/rsl` (operator-gated) returns the same bounded view.
- `POST /evolution/rsl/tick` runs one bounded tick immediately. It respects
  mode, budget, lease and single-flight; a `propose` mode tick validates
  candidates, a `verify` mode tick claims one proposed candidate.

**2. Roll out in order.**

1. `HARNESS_RSL_MODE=off` (default; no task runs).
2. `observe` for one week: deterministic observation only, no candidate
   execution. Review candidate volume and noise.
3. `propose`: stage operator-supplied operations, no automatic evaluation.
4. `verify` with `HARNESS_RSL_MAX_EXPERIMENTS_PER_DAY=1`, then `3` if the
   acceptance precision holds.
5. `HARNESS_RSL_K>1` only after v1 has at least one verified landed change.

**3. Stage a code proposal.**

`POST /evolution/candidates/{id}/propose` with
`{targetPath?, ops:[...]}`. The frozen target/op-path guard and `propose_ops`
run before the candidate becomes `proposed`; nothing is applied. Use the
conductor tick (or wait for the periodic tick) to verify it. The same route
refuses frozen tests/evaluator/policy targets, and surface candidates must use
`POST /evolution/surface-experiments` instead.

**4. Run a measured surface experiment.**

`POST /evolution/surface-experiments` with a base snapshot, candidate snapshot,
dataset/split/task ids and target dimension. The conductor records a baseline
run of the SAME base snapshot, then the measured candidate run. Surface
experiments require `verify` mode. Measurement is scripted-tier today: live-only
tasks are `UNMEASURED`, and a surface snapshot is never landable in v1.

**5. Complete the first live experiment.**

Pick one real failure with at least three occurrences. Inspect the inert
candidate and evidence, stage or author the operations, verify them, then review
the experiment. For a code candidate that passed, `prepare-landing` returns the
existing promotion preview; the single-use approval route remains the only
write. Record the candidate id, experiment run id, decision and, after landing,
the promotion/rollback verdict.

**6. Flip/rollback criteria.**

Keep the daily budget at 1 until acceptance precision is acceptable, cost stays
within `HARNESS_RSL_MAX_COST_USD`, and a critical regression has not occurred.
A rejected candidate is reverted/never activated; a bad landed change uses the
existing promotion rollback. `k>1` is a cost decision, not an autonomy grant.

**Implemented after this runbook:** v1b skill-draft trials, the v1c model
proposer, the live surface bridge, and surface landing.

---

## 6. Testing strategy

| Layer | Tests | What must be proven |
|---|---|---|
| Unit | `test_rsl_config.py`, `test_rsl_observation.py` | clamps, recurrence, dedupe, no-op mode |
| Contract | `test_rsl_snapshot.py`, `test_rsl_provenance.py` | snapshot validation, experiment identity, split selection |
| Isolation | `test_rsl_candidate_invoker.py` | private store/registry, no production writes |
| Orchestration | `test_rsl_loop.py`, `test_evolution_rsl_operator.py` | claim/lease, budget, resume, status/tick, propose staging, accept/reject |
| End to end | `test_rsl_loop.py` + `test_rsl_landing.py` + `test_rsl_verifier.py` + `test_rsl_surface.py` + `test_rsl_surface_e2e.py` | claim/lease/budget → owning tests (UNMEASURED) → decision → promotion preview; a stored surface candidate runs the base baseline and records a MEASURED candidate run |
| Security | `test_rsl_security.py` | forbidden path, test edit, evaluator edit, secret/verdict leak, approval not consumed, surface subject never landable |
| Learning | `test_rsl_lessons.py` | cue/evidence gate, retrieval, scope, verdict guard |
| Statistical | existing `stats.py` tests + RSL trials | Wilson CI, flaky tasks, unmeasured |
| Release | `scripts/test-evals.js` + `npm run rsl:smoke` | the offline RSL e2e is a deterministic gate; the smoke test runs the real worktree verifier and a scripted surface benchmark in a disposable repo/DB |

All tests run offline. A live experiment is operator-run, recorded, and never a
CI dependency.

---

## 7. Risks and mitigations

| Risk | L/M/H | Mitigation |
|---|---|---|
| Optimizing against noise | H | ≥3 trials, Wilson CI, measured-only acceptance, validation split |
| Overfitting the benchmark | H | Frozen release set, separate optimization/validation/held-out splits, scenarios authored from production incidents |
| Candidate edits its judge/tests | H | `RSL_DENY_GLOBS`, before-propose and before-land checks, test hash recorded |
| Landing a bad runtime change crashes the app | H | `promotion` + `selfhost.guarded_land`, restart → health probe → automatic rollback |
| Cost blow-out | M | `max_experiments_per_day`, `max_cost_usd`, `k=1` default, unknown cost stops verification |
| Loop storm / duplicate experiments | M | Dedupe by signature, lease, generation cap, per-correlation cap |
| Operator fatigue | M | Evidence bundle with a single decision, top-N candidates only, dismiss/undo |
| Model proposer produces bad ops | M | Strict JSON, schema validation, denylist, tests before benchmark |
| Mined failure becomes a fabricated test | H | Never invent `expected_behavior`; require explicit validation |
| Harness² environment blocker | L | Native-first; adapter is optional R9 |
| Doc drift | M | Owning doc + `CHANGELOG.md` per phase |

---

## 8. Open decisions

| # | Decision | Recommendation |
|---|---|---|
| 1 | Module home | `python/harness/self_improvement/` |
| 2 | Loop trigger | Post-review observation + periodic tick + event wake; no new queue |
| 3 | Experiment identity | `EvaluationRun.config`/`metadata`; no schema change in v1 |
| 4 | Landing path | `promotion` + `selfhost`; `evolution_service.activate` is ledger-only |
| 5 | v1 subjects | Code patches + skill drafts; surface snapshots are verified but not landable |
| 6 | Mined candidates | Evidence only until an explicit validated expectation exists |
| 7 | Recursion | Native `k>1` first; Harness² adapter only if measured value justifies it |
| 8 | Default after rollout | `off` for zero-config; `observe` is an explicit opt-in until the week's data is reviewed; `verify` is an operator opt-in |

---

## 9. ADR list (H217–H219 + H222–H224 + H233 implemented)

| ADR | Subject |
|---|---|
| ADR-H217 | RSL is a conductor over existing owners; no new runtime, database, queue or evaluator |
| ADR-H218 | One landing path: promotion + `guarded_land`; evolution activation is a skill-version path, not a code write |
| ADR-H219 | RSL candidates may not edit their judge: tests, evaluator, gates, policy, security and datasets are frozen |
| ADR-H222 | Experiment identity and provenance live on `EvaluationRun`; a comparison without them is refused |
| ADR-H223 | A lesson requires cue + evidence + validation and passes the verdict tripwire before storage |
| ADR-H224 | Recursion is bounded (`k`, budget, generation) and never activates a change |
| ADR-H233 | Surface candidates carry a typed snapshot on the ONE `EvolutionCandidate` row; the conductor dispatches by subject type, and a surface snapshot is measured but never landable |

H220–H221 are reserved by the QA Round 1 plan (browser policy and chat step
budget), so RSL's remaining decisions start again at H222; H223 (R6), H224
(R7) and H233 (post-R8 surface subjects) are implemented.

---

## 10. File map

### New files

```
python/harness/self_improvement/__init__.py
python/harness/self_improvement/config.py
python/harness/self_improvement/models.py
python/harness/self_improvement/observer.py
python/harness/self_improvement/security.py
python/harness/self_improvement/proposer.py
python/harness/self_improvement/verifier.py
python/harness/self_improvement/landing.py
python/harness/self_improvement/lessons.py
python/harness/self_improvement/selection.py
python/harness/self_improvement/composition.py
python/harness/self_improvement/recursion.py
python/harness/self_improvement/gate.py
python/harness/self_improvement/smoke.py
python/harness/self_improvement/loop.py
python/harness/self_improvement/recorder.py
python/harness/evaluation/candidate_invoker.py
python/harness/evaluation/provenance.py
python/tests/test_rsl_config.py
python/tests/test_rsl_observation.py
python/tests/test_rsl_provenance.py
python/tests/test_rsl_snapshot.py
python/tests/test_rsl_candidate_invoker.py
python/tests/test_rsl_loop.py
python/tests/test_rsl_landing.py
python/tests/test_rsl_verifier.py
python/tests/test_rsl_security.py
python/tests/test_rsl_surface.py
python/tests/test_rsl_surface_e2e.py
python/tests/test_rsl_lessons.py
python/tests/test_rsl_recursion.py
python/tests/test_rsl_gate.py
python/tests/test_evolution_rsl_routes.py
src/app/api/evolution/experiments/route.ts
src/app/api/evolution/experiments/[id]/route.ts
src/app/api/evolution/lessons/route.ts
src/app/api/evolution/candidates/[id]/evidence/route.ts
src/app/api/evolution/candidates/[id]/lessons/route.ts
src/app/api/evolution/candidates/[id]/recursive/route.ts
src/app/api/evolution/candidates/[id]/prepare-landing/route.ts
src/app/api/evolution/surface-experiments/route.ts
src/app/api/evolution/rsl/route.ts
src/app/api/evolution/rsl/tick/route.ts
src/app/api/evolution/candidates/[id]/propose/route.ts
src/lib/harness/evolution-browser.ts
scripts/rsl-smoke.js
src/components/screens/skills/rsl-experiments-panel.tsx
src/components/screens/skills/rsl-experiments-panel.test.tsx
src/components/screens/skills/rsl-control-panel.tsx
src/components/screens/skills/rsl-operator-panel.tsx
python/tests/test_evolution_rsl_operator.py
```

### Modified files

```
python/harness/code/evolution.py          recurrence writer, denylist wrapper
python/harness/code/evolution_store.py    claim/lease helpers, subjectType/surfaceConfig
python/harness/code/evolution_service.py  clarify ledger-only activation
python/harness/eclipse_memory/mistakes.py  write mistake recurrence
python/harness/eclipse_memory/schema.py   migration 31 (lesson columns)
python/harness/learning_review.py         call observer after analysis; wake the loop
python/harness/event_system/registry.py   candidate/experiment specs; evaluation.started consumer
python/harness/event_system/service.py    evaluation.started wakes the RSL conductor
python/harness/evaluation/tasks.py        split selection
python/harness/evaluation/runner.py       provenance, candidate invoker hook
python/harness/evaluation/store.py        experiment/provenance helpers
python/harness/evaluation/scoring.py       graderVersion, costKnown/latencyKnown
python/harness/evaluation/improvement.py  trials in run_loop, measured-only
python/harness/evaluation/trajectory.py   cost/latency from the model runtime
python/harness/evaluation/repair_metrics.py  RSL metric block
python/harness/evaluation/experiments.py  persisted experiment provenance
python/harness/evaluation/__init__.py     provenance/split exports
python/harness/evaluation/datasets/routing_e2e_v1.json  optimization split
python/harness/evaluation/datasets/team_v1.json         held-out split
python/harness/prompt_segments.py         bounded lesson manifest
python/harness/boot.py                    start/stop the loop in the lifespan
python/harness/self_improvement/loop.py   surface dispatch + status/budget view
python/harness/self_improvement/verifier.py  verify_surface_candidate (baseline + candidate)
python/harness/self_improvement/recorder.py  surface attempt + completion event
python/harness/self_improvement/landing.py   refuse surface subjects
python/harness/routers/evolution.py       experiments, evidence, surface, rsl status/tick, propose
src/lib/harness/evolution-client.ts       experiment/evidence/surface/status/propose contracts
src/lib/harness/evolution-browser.ts      browser status/tick/propose calls
src/components/screens/skills/rsl-operator-panel.tsx  surface experiment form
src/components/screens/skills/rsl-experiments-panel.tsx  mounts the control panel
src/components/screens/skills/learning-journey.tsx  experiment panel
src/lib/i18n/dictionaries/evolution.ts    evolution.* (lesson/recursive/surface/conductor)
scripts/test-evals.js                     offline RSL gate
package.json                              rsl:smoke command
python/tests/test_rsl_verifier.py         real worktree verifier regression
python/tests/test_events_service.py        evaluation.started wake test
python/tests/test_evolution_rsl_routes.py   surface/status/tick/propose operator gates
python/tests/test_evolution_rsl_operator.py status/tick/propose + surface creation
docs/NAVIGATION.md                        trigger row
docs/harness/architecture.md              module map
docs/self-improvement/architecture-audit.md  cross-link
docs/CHANGELOG.md                         entries
```

---

## 11. First PR (paste-ready prompt)

> Implement RSL R0 + R1 only. Add `python/harness/self_improvement/` with
> `config.py` (mode default `off`, clamps), `models.py` (`HarnessSnapshot`,
> `Observation`) and `observer.py` (mode-gated, deterministic: recurrence →
> inert `EvolutionCandidate`; failed run → deduped mined
> `EvaluationCandidate`; no model calls, no candidate execution). In
> `code/evolution.py`, add `record_mistake_recurrence` using
> `_category_signature` and `AgentMemoryStore.record_learning_recurrence`.
> Call it from `capture_mistakes` after the mistake rows are persisted (the path
> `EclipseMemoryService.analyze_run` uses).
> In `learning_review.py`, call `observer.observe_run` after deterministic
> analysis; a failure must never affect the run response. Mine failed runs with
> `evaluation.mining.mine_from_store` (deduped, bounded). Add the
> `self_improvement.candidate_created` registry spec. Add
> `python/tests/test_rsl_{config,observation}.py`. Do not add a database,
> queue, dependency, candidate invoker, denylist or activation path (those are
> R3/R4). Run `npm run test` and `npx tsc --noEmit`; update `CHANGELOG.md` and
> `NAVIGATION.md`.

---

## R9 — Hill climbing and continual learning (first slice, 2026-10-19)

**Status: state/utility/replay/hill-climb foundation implemented; conductor wiring
is the next slice.**

The R8 loop could verify one candidate against one baseline. R9 adds the search
and memory model needed for a real climb:

- **`self_improvement/state.py`** — append-only `HarnessState` rows (scope,
  snapshot digest, metrics, utility, lineage, status). Exactly one `current` per
  scope; promotion supersedes the prior row and never rewrites it. Operator-only
  promotion; the climb stages candidates.
- **`self_improvement/utility.py`** — a transparent utility score (success,
  target dimension, cost, latency, coverage) and strict acceptance: measured
  validation, no critical `DEFAULT_GATES` regression, and a positive utility
  delta. `UNMEASURED` never passes.
- **`self_improvement/replay.py`** — `replay_v1` from the existing frozen
  validation/held-out/release tasks; per-task measured rates; mean and critical
  forgetting; retained best-per-task. A missing task counts as a full drop, so a
  candidate cannot silently omit what it used to solve.
- **`self_improvement/hillclimb.py`** — a pure bounded ascent: caller-supplied
  `propose`/`evaluate`, tabu on rejected neighbor digests, steepest-ascent
  selection, plateau stop, and an `on_accept` persistence hook. It never invents
  a patch, calls a model or activates a change.
- **`self_improvement/lesson_feedback.py`** — `LessonOutcome` records the
  injected cohort and the eligible-but-not-injected control cohort for every run;
  the post-run review writes the terminal outcome. `stats()` reports injected and
  control rates with Wilson intervals and a lift only at sufficient evidence
  (3 injected + 3 control); `rank_lessons` promotes measured positive lift and
  leaves thin evidence in place. `retire_unhelpful` is an inert lifecycle action
  behind `HARNESS_RSL_LESSON_RETIRE` (off by default). The lessons panel's `Lift`
  action reads `/evolution/lessons/{id}/outcomes` and shows injected/control rates
  inline; a measured non-positive lesson can be retired through the operator
  route. This closes the lesson loop: injection is measured, not merely observed.
- **Conductor entry** — `RSLLoop.run_hillclimb` is reachable only in `verify`
  mode with `HARNESS_RSL_STRATEGY=hillclimb`. It loads the current
  `HarnessState`, uses the configured `k`/`HARNESS_RSL_GENERATIONS`, caps
  evaluations at the remaining daily budget, persists accepted states as
  `candidate` (never `current`), and records each evaluated neighbor as an
  `EvolutionAttempt` so the daily budget counts the climb. It refuses honestly
  when there is no current state, when the strategy is `rsl`, or when the budget
  is exhausted.
- **`self_improvement/proposer_model.py`** — the model-assisted proposal path
  (`HARNESS_RSL_MODEL_PROPOSER=off` by default). Strict JSON is parsed by the
  existing `StructuredOutputManager`, then every variant goes through
  `propose_many`/`propose_ops`, the frozen target guard and workspace
  confinement. A malformed payload, missing variant, frozen target or provider
  failure is a structured refusal. When enabled, the `propose` tick persists
  validated variants as child `EvolutionCandidate` rows in `proposed` state; it
  never verifies, lands or activates them. Background settings follow the
  existing `HARNESS_JOB_*` convention with `HARNESS_RSL_*` overrides.
- **`auto` mode** — one tick runs the bounded propose phase (deterministic ops,
  or the model proposer when enabled) and then ONE verify claim. It never lands
  a change: operator promotion remains the only write path. `verify` remains the
  manual operator mode; `auto` is the autonomous propose+verify tier.
- **Measured code candidates** — `evaluation/worktree_invoker.py` runs the
  unpatched baseline, applies the candidate ops through `propose_ops` +
  `patch.apply`, then runs the SAME deterministic suite in a child process whose
  `PYTHONPATH` points at the patched worktree. The child gets a temp DB, a
  curated non-secret environment, no live bridge and a timeout; the patched code
  is never imported into the host. `benchmark_decision` accepts only a measured
  target improvement with no critical regression, including the per-task
  safety/adversarial veto (a critical task drop rejects even when the aggregate
  improved). The result is recorded on an `EvaluationRun` and returned to
  `verify_code`; the candidate never lands. Opt-in:
  `HARNESS_RSL_CODE_BENCHMARK=off` by default.
- **Operator surfaces** — `GET /evolution/states` (current pointers + recent
  immutable rows), `POST /evolution/states/{id}/promote` (state pointer only;
  supersedes the prior current row, never writes code or consumes an approval),
  and `GET /evolution/lessons/{id}/outcomes` (matched injected/control stats and
  recent rows). `rsl-control-panel.tsx` shows the current state, utility (or
  `UNMEASURED`) and a Promote action, and is mounted in the learning journey with
  `rsl-operator-panel.tsx`.
- **Live surface activation** — `POST /evolution/states/{id}/activate-surface`
  requires a measured, accepted surface candidate and re-validates the snapshot
  against its recorded base. `HarnessActivation` stores the snapshot/base and
  previous state; rollback restores it. `graph.execute_run` applies only prompt,
  tool subset and lowered step/tool-call ceilings when the current base digest
  still matches. Model identity and skill drafts are refused live. Evaluation,
  candidate-trial and gate runs set `RunRequest.liveSurface=False`, so a live
  surface cannot contaminate a measurement. `GET
  /evolution/states/{id}/surface-preview` returns the same decision the
  activation uses: prompt/tools/ceiling diff, base-digest match, accepted
  decision, available scopes, every refusal reason, and the accepted run's
  bounded metrics/trials (trajectory stripped), baseline metrics/trials, the
  target before/after/delta, a measured per-task delta table with missing
  sides `UNMEASURED`, and a critical-regression veto for safety/adversarial
  tasks (ADR-H254/H255/H256). Scoped activation creates
  a new immutable state for that agent scope; the source state is untouched. A
  surface experiment now carries its target `scope` in `surfaceConfig` (part of
  the experiment signature), and a measured surface materializes exactly one
  inert `candidate` state for the operator list, so the preview/activation flow
  starts from the experiment itself rather than a guessed scope. `GET
  /evolution/candidates/{id}/state` addresses that state by candidate id and the
  operator panel links `Find derived state` to the shared preview/activation
  card (ADR-H249).
- **Drift signal** — `self_improvement/drift.py` compares the newest terminal
  run window with the preceding baseline, maps only completed/failed to
  success/failure, reports Wilson intervals, and returns `unmeasured` on thin
  data. `GET /evolution/drift` exposes it per agent scope; it is read-only and
  never changes the current harness (ADR-H250). `POST
  /evolution/drift/candidate` turns a `drift` signal into ONE inert `drift`
  candidate (no target/ops, deduped by scope/window/threshold) so the operator
  can stage ops or run the model proposer through the existing
  propose → verify → land flow (ADR-H251). `POST
  /evolution/candidates/{id}/model-propose` runs the model proposer for that
  candidate and persists validated children; the drift card links it as
  `Propose with model` and then `Run verify tick`, showing the verified
  candidate/decision/benchmark; a verified code child can then `Prepare landing`
  and complete the existing `PromoteChange` preview → single-use approval →
  apply/rollback card in place (ADR-H252).

Config: `HARNESS_RSL_MODE=off|observe|propose|verify|auto`,
`HARNESS_RSL_STRATEGY=rsl|hillclimb`, `HARNESS_RSL_GENERATIONS=1..3`,
`HARNESS_RSL_MODEL_PROPOSER=off|on`, `HARNESS_RSL_CODE_BENCHMARK=off|on`.
Tests: `python/tests/test_rsl_{state,utility,replay,hillclimb}.py` (28),
`python/tests/test_lesson_feedback.py` (9),
`python/tests/test_rsl_model_proposer.py`,
`python/tests/test_worktree_invoker.py`, and
`python/tests/test_rsl_loop.py` (auto mode + conductor entry + measured code
decision). ADR-H239, H242–H253. The live-surface activation path is implemented
behind an explicit operator preview, a base-digest check, per-agent scope
selection and a rollback route; code candidates still land only through the
existing promotion approval.

---

## RSL v2 — first slice: multi-objective frontier (2026-10-20)

**Status: foundation implemented.**

`self_improvement/pareto.py` adds a read-only Pareto view over recorded
`HarnessState` rows: success/target/coverage maximise, cost/latency minimise.
Dominance requires at least two comparable objectives, no worse on each, and one
strict improvement; missing objectives are neutral. `GET
/evolution/states/pareto` returns the frontier and each dominated state's
dominator. It does not change `utility.acceptance`, budgets or activation.
Tests: `python/tests/test_rsl_pareto.py`. ADR-H269.

Next v2 slices: surface the frontier in the operator panel; model-identity
proposals; cross-scope lesson transfer; canary landing for code.

---

## Related

- `docs/harness/self-evolution-roadmap.md` — the meta loop and invariants §5.
- `docs/self-improvement/architecture-audit.md` — Harness² Phase 0 audit and the
  no-duplicate-systems decision.
- `docs/self-improvement/harness2-borrowings.md` — verdict tripwire, contrast
  bundles, selection, lesson gate.
- `docs/harness/agent-evaluation.md` — the evaluator RSL verifies with.
- `docs/harness/roadmap/phase-10-self-improvement.md` — code/skill evolution v2.
- `docs/harness/memory-skills-evolution-plan.md` — lesson/skill contracts.
- `docs/harness/decisions.md` — ADR-H112 and the harness ADR series.
- `docs/harness/architecture.md` — runtime architecture and persistence.

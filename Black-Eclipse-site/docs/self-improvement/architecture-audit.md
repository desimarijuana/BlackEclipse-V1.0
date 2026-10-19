---
title: Harness² Self-Improvement — Phase 0 Architecture Audit
status: Current
last-verified: 2026-10-18
---

# Harness² Self-Improvement — Phase 0 Architecture Audit

**Who this is for:** anyone implementing or reviewing the program that integrates
Google Research **Harness²** (`google-research/harness2`) as Eclipse's
experimental harness-optimization framework — the loop in which Eclipse
identifies a failure, proposes an alternative harness, tests it, proves it is
better, preserves the lesson, and reuses it on a later task.

**What this document is:** the Phase 0 deliverable of the program. It records
the verified upstream surface, the real state of the tree (measured
2026-10-18), the authoritative interfaces the program must reuse, the gaps it
must close, the no-duplicate-systems decision, the risk register, the test
strategy, and the phase gates. Every claim cites `file:line` in
`Black-Eclipse-site/` unless a path is given.

**Program constraints already in force (do not weaken):** the meta-loop
invariants in `docs/harness/self-evolution-roadmap.md` §5 — one runtime; prose
is not a boundary; artifacts stay inert until evaluation + operator decision;
no new database/queue/runtime/scheduler/event bus/evaluation framework without
an audit proving the existing owner cannot satisfy the requirement; the release
gate (`npm run test` + `npx tsc --noEmit` + `scripts/test-python.js` +
`scripts/test-evals.js`) is the definition of done. This program adds the
*experiment laboratory* for harness changes; it composes with the W0–W15
workstreams and does not replace them.

---

## 0. Upstream verification (Phase 1 input, verified 2026-10-18)

| Fact | Value | Evidence |
|---|---|---|
| Repository | `https://github.com/google-research/harness2` | GitHub (exists, public) |
| Head commit observed | `1cfe254e8d25b15f37048c3730134686abe60335` ("Fix arXiv link", 2026-10-14) | GitHub API `commits/main` |
| Maturity | 3 commits on `main`; created 2026-10-06 → young research code | GitHub API |
| License | Apache-2.0 core; `third_party/`, benchmarks and datasets retain upstream licenses (review individually before redistribution) | README §License, `dependencies/README.md` |
| Paper | arXiv `2610.14224`, *Harness²: Recursive Agent Harnessing for an Open World* | README citation |
| Platform | Linux, Python 3.12 (3.13 supported), `uv` | README §Install, `docs/SETUP.md` |
| Offline demo | `harness2-demo --output runs/demo --k 2` — both recursion modes, deterministic editors, real Python executions, **no model credentials** | README §Install |
| Editable components | eight: system prompt, guardrails, memory, tool guidance, subagents, skills, scripts, plugins | README §Harness components |
| Mechanism | task-level recursion = contrastive **Propose–Probe–Compose** (no ground-truth feedback); harnessing-level recursion = persistent improvement harness updated with adopted harnesses + evidence-supported lessons | README |
| Modes | `--k 1` single step; `--k K --mode parallel` (K general + K domain candidates → K compositions); `--k K --mode sequential` (K successive steps); `--workers N`; `--seed N` (task order only) | README §Experiments, `docs/EXPERIMENTS.md` |
| Executors | **OpenCode and Codex** — there is **no Eclipse-runtime executor**; an adapter is required (Phase 3) | README §Experiments |
| Results/resume | runs under `runs/`, resumable by repeating the command; `HARNESS2_RUNS_DIR` namespace per model/task selection | README §Results and resume |
| Benchmarks shipped | JobBench, LAB, WorkBuddy-Bench (each needs extra deps; LAB: Pandoc/Poppler, WB: Docker) | README, `docs/BENCHMARKS.md` |
| Security defaults | **Executor network access is unrestricted; Codex runs with its sandbox disabled.** Upstream itself warns to configure network restrictions before evaluation | README §Web access |

**Consequence:** installing Harness² does not make Eclipse self-improving. The
optimizer is an *external experiment worker*; candidate harnesses become real
only when Eclipse executes them through its own runtime and its own evaluator
grades them. That adapter is Phase 3.

---

## 1. Ground truth — the component map (what exists, who owns it)

### 1.1 Agent runtime (ONE loop)

| Concern | Authoritative owner |
|---|---|
| Turn/run execution | `python/harness/service.py` `AgenticService.run` :1144, `run_background` :1447 → `python/harness/graph.py` `execute_run` :1067 (per-run graph built by `build_graph` :373). Every path converges here: chat, runs, skills, tasks, fabric workers, automation, evaluation. |
| Run contract | `python/harness/schemas.py` `RunRequest` :160 — includes `agent: Optional[AgentConfig]` :168 (`AgentConfig` :118: `systemPrompt`, `tools`, `maxSteps`, timeouts, `maxToolCalls`, `allowMcpTools`, `allowPluginTools`) |
| Run persistence | `python/harness/persistence.py` — `agent-memory.db` (`HarnessRun` :30, `HarnessEvent` :54, `HarnessToolExecution` :65); additive-column migrations only (`_ADDED_COLUMNS` :270) |
| Cancellation / recovery | task-cancel via `service.cancel` :1472; orphan reconciliation `run_recovery.py` :44/:111; stall watchdog `run_watchdog.py` :89; checkpoints `run_lineage.py` :185; resume via `POST /runs/{id}/resume` (`main.py` :582) |
| Replanning | `python/harness/replan.py` — flag-gated `HARNESS_REPLAN_ENABLED`, default OFF |

### 1.2 Model runtime (ONE provider path)

`python/harness/model_runtime/` — `ModelRuntime` (`runtime.py` :141) owns routing
(`routing.py`), retries (`HARNESS_MODEL_RETRIES`), cross-provider fallback
(`HARNESS_MODEL_FALLBACK`, default OFF), circuit breaker + rate limits
(`health.py`), usage/cost (`usage.py`, `store.py` `ModelRequest` rows :24), and
`record_step` :670 (called by the graph after every model call). Model
construction is `models.py` `build_chat_model` :341. LLM config resolves from
the TS settings vault per run (`src/lib/harness/run-service.ts` :170); autonomous
paths read `HARNESS_JOB_*`/`HARNESS_TASK_*`/`HARNESS_FABRIC_*`.

### 1.3 Tool system (ONE registry)

`python/harness/tools.py` — `ToolRegistry` :409 (one per process, populated in
`AgenticService.__init__` :67–532), `ToolDefinition` :340, `ToolResult` :88,
`ToolContext` :106, `execute` :476 with the authorization seam :504 (`permission
!= "read"` requires `ctx.authorize_effect`), `MAX_TOOL_RESULT_CHARS` :64.
Narrowing happens per run via `graph.resolve_surface` :324 and
`code/policy.py` `allowed_tools` :698.

### 1.4 Security (ONE authorization path)

`python/harness/security/gateway.py` `authorize` :139 (fixed order: isolation →
floor → risk → policy → capability → approval; fail-closed), `floor.py` (hard
denies on `jdds.db`, `agent-memory.db`, `eclipse-memory.db`, `.env`, keys, OS
dirs), `sandbox.py` (`ExecutionSandbox`: Docker/Local/Unavailable — never
unbounded), `network.py` (default-deny egress, SSRF guard, DNS pinning),
`secrets.py` (scoped grants), `audit.py` + `store.py` (append-only hash-chained
audit on `agent-memory.db`). Effect authorizer composition
`code/authorizers.py::build_effect_authorizer` :24, security wrapper
`security/integration.py::make_security_authorizer` :104. Operator gating is
transport/token only (`deps.py::require_operator` :263).

### 1.5 Skills (lifecycle + versioning already exist)

- Store: **`eclipse-memory.db`** with a real numbered migration runner
  (`eclipse_memory/db.py::_migrate` :70; `schema.py` — 30 migrations;
  `Skill` :122, `SkillVersion` :137, `SkillEvaluation`, `SkillPromotionRequest`,
  `SkillReview`, `SkillEvent`). Only `EclipseMemoryStore` may open it
  (`eclipse_memory/store.py` :10).
- Lifecycle: `skills/lifecycle.py` — `draft → testing → review → validated →
  enabled`, promotion evaluation- and permission-gated; `skills/versioning.py`
  propose/evaluate/activate/canary/promote/rollback with auto-rollback triggers.
- Loading: `skills/registry.py` `load_all` :149 (tier precedence project >
  user > installed > bundled), `reload` :577 (the re-scan seam); boot load in
  `service.py` :191–200.
- Injection into a run: bounded manifest SystemMessage
  (`prompt_segments.build_skill_manifest` :153, ≤8 skills / 1 200 chars), on-demand
  `skill_view`, and `skill_invoke` → a child `execute_run` with a manifest-derived
  `AgentConfig` (`skills/runtime.py` :191).
- In-run authoring: `skill_create`/`skill_update`/`skill_delete`
  (`skills/manage_tools.py`) — single-use digest-bound operator approval; new
  user skills land `enabled` after validation, no third tier.

### 1.6 Memory and learning stores

- `eclipse-memory.db` — durable facts (single write gate `decision.py`),
  skills (above), `LearningCandidate` :251, `MistakeRecord` :279,
  `CorrectionRecord` :301, recovery incidents (`RecoveryIncident` :950,
  `RecoveryAttempt` :974, migration 26), autonomy envelope tables.
- `agent-memory.db` — runs/events/tool executions, chat sessions + FTS index,
  `LearningRecurrence`/`LearningRecurrenceRun` (persistence.py :151/:162),
  `LearningReview` :217, retrieval records, research receipts, artifacts,
  jobs/tasks/fabric/event-system/execution/security audit and **all evaluation
  tables**.
- Learning pipeline: `skills/learning.py::analyze_run` :253 (deterministic
  candidates + recurrence ledger), `skills/procedures.py` (construction
  procedure, W6), `recovery/learning.py::promote_incidents` :95
  (resolved recurring incident → inert `LearningCandidate`), `learning_review.py`
  post-run review queue, `code/evolution*.py` (recurrence ≥ 3 → inert
  `EvolutionCandidate` → worktree evaluation → operator-confirmed
  activate/rollback through `skills/versioning.py`; ADR-H112, `FROZEN_PATHS`
  `code/evolution.py` :50).

### 1.7 Evaluation system (the Phase 2 spine)

`python/harness/evaluation/` —

- Versioned tasks (`tasks.py` `EvaluationTask` :83, `fingerprint()` :181) in
  four built-in datasets: `benchmark_v1.json` (31), `construction_v1.json`
  (16), `routing_e2e_v1.json` (4), `team_v1.json` (2) = **53 tasks**.
- Deterministic environments (`environments.py`: filesystem/database/finance/
  memory/mock/ui/composite; network isolated by construction; side effects OFF
  by default, `config.py` :73).
- **Invoker contract** `runner.py` `AgentInvoker` Protocol :124; `ScriptedAgentInvoker`
  :211 (per-trial tempdir + private `AgentMemoryStore` :248, private
  `ToolRegistry` :131, `_RecordingRegistry` :159, direct `execute_run` call
  :285 — the real runtime, in-process, isolated); `ServiceAgentInvoker` :318
  (production `service.run`; accepts only agent preset id + model settings).
- 17 deterministic graders (`graders/`), 21 scoring dimensions
  (`scoring.py` :16), critical floors and thresholds :235; UNKNOWN for
  unmeasurable, never guessed.
- `EvaluationStore` — twelve `Evaluation*` tables on `agent-memory.db`
  (`store.py` :22–189) incl. `EvaluationRun`, `EvaluationTrial` (trajectory
  JSON), `EvaluationScore`, `EvaluationBaseline`, `EvaluationRegression`,
  `EvaluationFailure`, `EvaluationModel`, `EvaluationCandidate`.
- `baseline.py`, `regression.py` (`DEFAULT_GATES` :65), `report.py`, `replay.py`,
  `mining.py` (production failure → candidate), `improvement.py`
  (`ImprovementProposal` + apply → suite → `detect_regressions` accept/reject;
  **currently exercised only by tests**), `experiments.py` (A/B, model matrix,
  skill/memory delta). CLI `eclipse eval …` (`cli.py`); offline floor
  `gate.py::run_offline_gate` (private temp DB) wired into
  `scripts/test-evals.js`.
- Traces: `trajectory.py` (`Trajectory` :81, `from_events` :98,
  `capture_from_store` :280) — folded from the real event stream; tool-call args
  enriched at the registry boundary (`runner.py` :159/:365).

### 1.8 Events, observability

- Per-run bus `events.py` (`RunEmitter` :70 — persists + publishes; SSE via
  `EventBus`); durable canonical journal `event_system/` (`HarnessEventLog`
  `store.py` :48, correlation/causation context `envelope.py` :34–97, registry
  of typed events `registry.py`, replay, DLQ) — the per-run bus **bridges** into
  it (`bus.py` :177–200).
- `observability/` — in-memory bounded spans (`tracing.py` :89), Prometheus
  metrics, `CostEngine` + `PricingRegistry` (`costs.py`), redaction, exporters
  (OTLP/Langfuse/Sentry/JSONL). Per-run cost is queryable
  (`/observability/costs/runs/{id}`); durable per-request rows in `ModelRequest`.

### 1.9 Financial authority (unchanged by this program)

- Evidence: web research engine `research/web_*.py` (`EvidenceStore` on
  `agent-memory.db`), deterministic claim verification, freshness, untrusted
  content boundary; answer-seam gates `research/release_gate.py` :137 and
  `finance_facts/enforce.py`, advisory gate `advisory/gate.py` :94.
- JDdS: `jdds.db`, TS/Prisma only; **no Python code opens it** — the ONE read
  path is the read-only capability bridge (`src/lib/harness/data-bridge.ts`;
  Python `bridge.py` `HttpDataBridge` :20).
- Deterministic metrics: `research/calculations*.py`, `finance_facts/`,
  `quant/metrics.py`, `stats/` — all model-free, provenance-bearing.

### 1.10 App infrastructure

Release gate `npm run test` = vitest + `scripts/test-python.js` (vendored
interpreter, honest skip if the stack is absent) + `scripts/test-evals.js`
(offline evaluation floor + eval gates); `npx tsc --noEmit`; `doctor.js` on
boot; Python stack installed by `postinstall` (`scripts/setup-python.js`,
vendored Python **3.12.8** on Windows). Background execution: `fabric/`
(durable queue, workers that call the same `service.run`), `tasks/scheduler.py`,
`jobs/` — all on `agent-memory.db`.

---

## 2. Authoritative interfaces the program MUST use

1. **Run a task:** `AgenticService.run(request)` / `execute_run(request, …)`
   with a `RunRequest`. A candidate harness travels as
   `RunRequest.agent = AgentConfig(...)`. Note: the TS front door sends only
   `agentId` (`run-service.ts` :309–328; `python-client.ts` :27–28) — the
   `agent` field is reachable only by direct Python API callers, which is the
   optimizer's route. `resolve_surface` still post-processes the candidate
   (`filter_system_prompt`, policy narrowing) — by design; a candidate can never
   widen its own surface.
2. **Evaluate a task set:** `evaluation/runner.py` — implement the
   `AgentInvoker` Protocol (:124); do not write a second runner. The
   scripted tier's isolation recipe (:248–288) is the proven way to run
   candidate configurations in-process without touching production state.
3. **Load skills:** `SkillRegistry.load_all` / `reload(**overrides)`
   (`registry.py` :149/:577) over the `eclipse-memory.db` store; revisions via
   `skills/versioning.py`; promotion via `skills/lifecycle.py`.
4. **Persist experiments/evaluation:** `EvaluationStore` on `agent-memory.db`;
   new learning/lesson/revision tables (if any) via numbered migrations in
   `eclipse_memory/schema.py` (next index **31**).
5. **Authorize and observe:** all candidate execution passes the ONE gateway
   (`security/gateway.py`), emits `RunEmitter` events, is cost-attributed by
   `ModelRuntime`/`CostEngine`, and is auditable in the event journal. No
   candidate may edit the evaluator, gates, policy, approvals or the frozen
   authority files (`code/evolution.py` :50, ADR-H112).

---

## 3. Gaps — what must be built (per phase) and what must not be rebuilt

### Phase 1 — feasibility environment (BLOCKED on this host, decision needed)

Measured on the current Windows host: `uv` 0.12.17 present (Windows build);
vendored Python 3.12.8 present; **WSL2 is not installed**; **the `docker` CLI is
not available**. Upstream requires Linux. Options, in preference order:
(a) `wsl --install` + Ubuntu (admin + reboot), (b) Docker Desktop with a Linux
container, (c) a separate Linux host. The offline demo needs no model
credentials, so environment setup is the only Phase 1 prerequisite. The
reviewed revision to pin is §0's SHA; the clone must live **outside this
repository** (temp dir), never vendored into the tree.

### Phase 2 — evaluation provenance and the experiment record

Gaps found (all in the existing evaluator; close them there):

1. `EvaluationRun.agentVersion/gitCommit/model/provider/config` are left NULL by
   `run_suite` (`runner.py` :622–630); `EvaluationRun.config` is hardcoded
   (`{"trials", "tier"}`) — there is **no configuration identity** for a
   baseline vs candidate.
2. Task fingerprints are never persisted (`EvaluationTask.fingerprint()`,
   `upsert_task` — no callers), so runs are not linked to exact task rows.
3. Evaluator version is not attached to trials/scores (`GRADER_API_VERSION`
   only reaches unused columns).
4. Cost/latency are effectively unpopulated in evaluation records:
   `derive_metrics` reads them from `model.completed` (`trajectory.py` :204),
   which does not carry them; the model runtime's `model.request.completed`
   (with `latencyMs`) is republished without a top-level `runId`
   (`service.py` :534) and dropped by the live invoker (`runner.py` :342).
   Real values exist in `ModelRequest` rows and `CostEngine`.
5. No seed/temperature control anywhere in `evaluation/`; `ModelSettings` has no
   recorded temperature.
6. ~~No optimization/validation/held-out split mechanism~~ — R2 added
   `select_tasks(split=...)` (`tasks.py`) with validation (benchmark +
   construction, 47), optimization (`routing_e2e_v1`, 4) and held-out
   (`team_v1`, 2); `release` is reserved.
7. Scripted trials bypass the canonical event system (private legacy bus,
   `runner.py` :264) — durable experiment lifecycle events (`evaluation.started`
   exists) cannot see them.
8. ~~Doc drift~~ — `docs/harness/agent-evaluation.md` now reports the 53-task
   merged set and the four dataset splits; the release gate still runs all 53.

What exists and must be reused, not rebuilt: runners, invokers, environments,
graders, scoring/thresholds, baselines, regression gates, mining, report,
CLI, the offline gate, and the failure taxonomy (`evaluation/taxonomy.py`;
`recovery/taxonomy.py` for runtime failures — the two vocabularies are
currently unbridged; that bridge is a candidate Phase 2 improvement).

### Phase 3 — the Eclipse–Harness² adapter

Missing: a conformance layer that (a) exports `TaskSpec`-shaped tasks,
(b) drives Harness² (pin revision, `HARNESS2_RUNS_DIR` per experiment,
Propose–Probe–Compose with `--k 1` first), (c) executes every proposed candidate
through the existing runtime, (d) feeds the existing evaluator, (e) imports
candidate artifacts into isolated storage. Contracts to define (versioned +
validated): `TaskSpec`, `HarnessSnapshot` (the editable surface snapshot:
`AgentConfig.systemPrompt`, tool allowlist subset, skill drafts, prompt-plan
digest from the `prompt.plan` event), `ExecutionTrace` (already shaped by
`evaluation/trajectory.py`), `EvaluationResult` (`EvaluationScore`), `CandidateRevision`,
`PromotionDecision`.

Watch-outs from the runtime audit (all verifiable in code):

- The process-wide singletons (`deps.py` :22 service at import; one
  `ToolRegistry` with `set_active_context` per graph build `tools.py` :471;
  `ModelRuntime` singleton; `service.run` rebinding the market gateway bridge
  :1148) mean **candidate runs must follow the evaluation isolation pattern**
  (private registry + temp store + direct `execute_run`), not the shared live
  service, whenever candidates run concurrently.
- `RunRequest.callbackBaseUrl` is required (`schemas.py` :232); the isolated
  tier substitutes `_UnavailableBridge` (`runner.py` :107) — candidates that
  need front-door data capabilities must run with a live bridge.
- Skills are boot-scanned; a candidate that changes skill content must go
  through `registry.reload()`/versioned drafts, not file edits of active roots.

Editable allowlist v1 (Phase 4): system prompt text, tool-subset selection,
skill drafts (inert). Not editable, ever, by candidates: evaluator/`graders/`,
`scoring.py`/`regression.py` gates, `security/`, `code/policy.py`, approvals,
promotion rules, active runtime code, live-trading paths.

### Phase 5 — persistent learning entities

None of `learning_experiments`, `harness_revisions`, `candidate_changes`,
`validated_lessons`, `skill_revisions`, `promotion_records`,
`experiment_artifacts` exist as named structures. Mapping to what exists:

| Proposed entity | Existing structure to reuse/extend | Decision |
|---|---|---|
| `learning_experiments` | `EvaluationRun` (+`metadata`); `code/evolution_store.py`; no experiment/hypothesis/decision fields | Add experiment identity columns/metadata to `EvaluationRun` (agent-memory.db) — new table only with documented reason |
| `harness_revisions` | `SkillVersion` (skill-subject only); `EvolutionCandidate`/`EvolutionAttempt` (code-subject) | New small table in `eclipse-memory.db` (migration 31+): immutable revision rows (content hash, parent revision, validation state) |
| `candidate_changes` | `LearningCandidate`, `EvolutionCandidate`, `EvaluationCandidate` (three silos) | Reuse per subject; do not unify into a fourth silo |
| `evaluation_runs` | `EvaluationRun`/`EvaluationTrial`/`EvaluationScore`/… | Exists — reuse |
| `validated_lessons` | `LearningCandidate` (+ evidence, limitations, status); `MistakeRecord.correctionWorked` | Reuse `LearningCandidate`; add validation-evidence linkage only if missing |
| `skill_revisions` | `SkillVersion` + versioning lifecycle | Exists — reuse |
| `promotion_records` | `SkillPromotionRequest`/`SkillReview`/`SkillEvent`; evolution candidate fields | Reuse; extend only for harness revisions |
| `experiment_artifacts` | `HarnessArtifact` (run/task-scoped); evaluation trajectories in `EvaluationTrial.trajectory` | Link artifacts to experiment ids via existing FK columns/joins; no new artifact store |

### Phases 6–8 — see the phase gates below; no structural gaps found

Promotion/rollback, sandbox floors, budgets (`BudgetManager`), background
execution (fabric), event correlation, cost metrics, and recovery of interrupted
work (checkpoints/resume) already exist; the work is wiring, policy defaults and
provenance, not new infrastructure.

---

## 4. Integration design (the shape of the program)

```
User task ──► Eclipse runtime (execute_run) ──► run + events + artifacts
                    │                                   │
                    │ (1) observer subscribes            │
                    ▼                                   ▼
        evaluation/ runner + graders  ◄──── evaluation records (agent-memory.db)
                    │
        (2) experiment manager: is this task learnable? (recurrence,
            failure taxonomy, budget) — otherwise stop, record nothing
                    ▼
        (3) adapter: TaskSpec + HarnessSnapshot ──► Harness² worker
            (external process, Linux, pinned revision, runs/ namespace,
             k=1 first; Propose–Probe–Compose)
                    ▼
        (4) candidate revisions ──► executed via the evaluation isolation
            pattern: RunRequest(agent=AgentConfig(...)), private registry +
            temp store, ONE gateway, artifacts into candidate-store
                    ▼
        (5) evaluator compares candidate vs baseline on the frozen task set
            (existing gates; provenance fixed per Phase 2)
                    ▼
        (6) inert results → learning/promotion stores; activation ONLY via
            the existing operator-confirmed path (skills lifecycle /
            evolution activate / code.promotion single-use approval)
```

Provisional decisions to be recorded as ADR-H entries before Phase 3/5 code:
the subsystem's module home (proposal: `python/harness/harnessing/`, one route
group `routers/harnessing.py`, boot wiring in `boot.py`, DB placement per §3)
and the candidate-execution isolation contract.

---

## 5. No-duplicate-systems statement (Phase 0 acceptance gate)

**PASS.** This program proposes **no** second agent runtime, execution loop,
tool registry, provider abstraction, authorization system, event bus, queue,
scheduler or memory database:

- candidate execution uses `execute_run` with an inline `AgentConfig`;
- evaluation uses the existing `EvaluationRunner` + a third `AgentInvoker`;
- persistence uses `evaluation/` tables on `agent-memory.db` and (only for
  harness revisions/lessons) numbered migrations on `eclipse-memory.db`;
- execution isolation reuses the scripted tier's per-trial pattern;
- authorization, events, cost accounting, artifacts and background execution
  are inherited unchanged.

The Harness² worker is an **external experiment tool** (like a test runner),
not a runtime component; it never serves user traffic and its outputs are inert
until promoted. This satisfies the "no new infrastructure without proof"
invariant — the proof being that no existing owner performs k-budgeted
Propose–Probe–Compose, and the worker adds none of the runtime responsibilities
above.

---

## 6. Risk register

| # | Risk | L/M/H | Mitigation |
|---|---|---|---|
| 1 | Upstream is young (3 commits) and research-grade | H/M | Pin the reviewed SHA (§0); clone outside the tree; treat outputs as candidates, never as truth; re-review on upgrade |
| 2 | Host has no WSL2/Docker → Phase 1 cannot run as documented | **H/H today** | Operator decision (§3 Phase 1); smallest viable step is `wsl --install` + Ubuntu; otherwise Docker Desktop or a Linux host |
| 3 | Overfitting the benchmark ("learns the tests") | M/H | Optimization/validation/held-out split (Phase 2.6); frozen release set read-only to the optimizer; scenarios authored from production incidents |
| 4 | Candidate runs corrupt shared state under concurrency (singletons, `set_active_context`, market-bridge rebinding) | M/H | Run candidates via the evaluation isolation pattern (private registry + temp store), bounded concurrency, one experiment per workspace |
| 5 | Cost blow-out (Harness² spends model calls per candidate) | M/M | `--k 1` first; `HARNESS2_RUNS_DIR` per experiment; budgets through `BudgetManager` + evaluation config; cost recorded per trial (Phase 2.4) |
| 6 | Model nondeterminism confounds comparisons | M/M | Repeated trials + Wilson CI (`stats.py` exists); record temperature/seed (Phase 2.5); report uncertainty, never a single delta as proof |
| 7 | Upstream security defaults leaked into Eclipse (unrestricted network, disabled sandbox) | M/H | Never copy upstream executor defaults; candidates run through the ONE Eclipse gateway (floor/network/sandbox); the worker process is confined (no secrets, egress allowlist) |
| 8 | A candidate edits its own evaluator/policies | L/H | File-level allowlist (Phase 4), frozen authority files (ADR-H112), evaluator lives outside the candidate workspace, negative tests |
| 9 | Evaluation records unreliable (NULL provenance, unmeasured cost shown as 0) | H/M | Phase 2 fixes provenance/cost honesty before optimization is enabled |
| 10 | Doc/concept collision with the W-program (two "self-improvement" loops) | M/L | This program is the L4/L5 laboratory of `self-evolution-roadmap.md`; docs cross-link; one ADR series (ADR-H217+) |

---

## 7. Test strategy

Per phase, in the repo's own conventions (pytest for Python,
`python/tests/test_*.py`; vitest for TS; gates in `scripts/test-evals.js`):

- **Phase 1:** environment proof script (clone at pinned SHA, run
  `harness2-demo` both modes, verify artifacts + resume, record dependency
  license review) — a runnable report, not a test in CI.
- **Phase 2:** evaluator provenance tests (config identity, fingerprints,
  grader version, cost/latency join, splits); regression tests that a NULL
  provenance row is rejected by the new experiment API; doc drift fix.
- **Phase 3:** adapter contract tests (schema validation, round-trip, redaction
  of secrets in exported tasks); an end-to-end test (scripted invoker tier) in
  which a Harness² candidate artifact is imported, executed through
  `execute_run`, and graded — without touching active configuration or
  bypassing authorization.
- **Phase 4:** optimizer tests with a stub worker (deterministic candidate
  traces): budgets, cancellation, resumability, idempotency, experiment
  isolation; at least one controlled experiment showing a measurable
  improvement with zero critical regressions.
- **Phase 5:** migration tests (fresh + upgrade on a copy), lesson retrieval in a
  later task, traceability of lesson origin/scope/validation.
- **Phase 6:** negative/security tests: malicious candidate tries to edit the
  evaluator/policy/frozen files, exfiltrate secrets, widen its toolset — all
  refused; rollback restores the exact previous revision atomically; audit rows
  written.
- **Phase 7:** per-domain suites reuse the existing datasets/categories;
  finance claims must flow through the Evidence Engine and deterministic
  calculators (never model-generated numbers); cross-domain isolation tests.
- **Phase 8:** recovery-after-restart, budget enforcement, concurrency limits,
  regression dashboards from recorded metrics.

Release-gate rules stay: `npm run test` and `npx tsc --noEmit` must pass; new
gates are added to `scripts/test-evals.js` only when deterministic and
offline-safe.

---

## 8. Phase gates (acceptance criteria)

| Phase | Gate |
|---|---|
| 0 (this doc) | Architecture + integration points documented and verified against the tree; no duplicate systems without documented reason → **PASS** |
| 1 | Upstream demo runs in the chosen Linux environment at the pinned SHA; artifacts inspected; resume/failure behavior understood; adapter requirements recorded → **blocked on environment decision** |
| 2 | Baseline and candidate configurations are evaluable on comparable tasks with reproducible, provenance-complete records; failures distinguishable from evaluator errors |
| 3 | Harness² can optimize a scripted test task through the adapter without changing active configuration or bypassing permissions |
| 4 | ≥1 controlled experiment shows a measurable improvement on a defined task with zero critical regressions; budgets enforced; runs resumable |
| 5 | A validated lesson is retrievable and applied in a later task with origin, scope, validation status and version traceable |
| 6 | Defective/malicious candidates cannot alter production configuration; rejected candidates never activate; a prior revision restores atomically |
| 7 | Each enabled domain has its own repeatable suite and validated improvement records; no cross-domain behavior bleed |
| 8 | Interrupted experiments recover; budgets enforced; all changes auditable; rollback tested end to end |

---

## 9. Immediate next steps (for the operator)

1. **Decide the Phase 1 environment** (WSL2 vs Docker Desktop vs Linux host) —
   everything else in M1 is ready. `uv` and Python 3.12 are already present;
   only the Linux boundary is missing.
2. Approve the Phase 2 scope (provenance/splits/honesty fixes in
   `evaluation/`) as the bridge from audit to first integrated experiment.
3. Reserve ADR-H217+ for: the candidate-execution isolation contract (Phase 3)
   and harness-revision persistence (Phase 5).

## Related

- `docs/harness/self-evolution-roadmap.md` — the meta loop (W0–W15) and the
  invariants this program preserves; this program is its experimentation
  laboratory (L4/L5).
- `docs/self-improvement/rsl-implementation-plan.md` — the native Recursive
  Self-Improvement Loop (RSL) build plan (R0–R8, ADR-H217–H219 + H222–H224); the
  conductor that closes the loop this audit's Phase 3/4 would feed.
- `docs/harness/agent-evaluation.md` — the evaluator this program extends.
- `docs/harness/memory-skills-evolution-plan.md` — skills/learning contracts.
- `docs/harness/decisions.md` — ADR-H112 (self-change freeze/land) and the
  ADR-H series.
- `docs/harness/architecture.md` — runtime architecture + persistence.
- `https://github.com/google-research/harness2` @
  `1cfe254e8d25b15f37048c3730134686abe60335` — upstream framework.

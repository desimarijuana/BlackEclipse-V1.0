---
title: Failure Intelligence & Adaptive Recovery
status: Current
last-verified: 2026-10-18
---

# Failure Intelligence & Adaptive Recovery

**What it is:** the one cross-subsystem failure layer. Eclipse already owns every
*piece* of autonomous problem-solving — provider error normalization
(`model_runtime.errors`), build/test diagnostics (`execution.diagnostics`), retry
classification (`orchestration.retry`), model fallback (`model_runtime.routing`),
loop detection (`observability.anomaly`), durable task checkpoints (`tasks`), the
learning pipeline (`skills.learning`, `eclipse_memory`) and verification
(`code.verify`, `execution.verify_loop`). This layer *composes* them: one shared
failure vocabulary, one stable signature, one inspectable recovery policy, one
bounded decision, recorded durably as agent memory.

**Why it exists:** before this, "what kind of failure is this, have I seen it
before, and what am I permitted to do about it?" was answered differently (or not
at all) at each boundary. A timeout in a tool, a provider and a workflow node had
no shared identity.

## Where things live

| Piece | File | Contract |
|---|---|---|
| Failure vocabulary | `python/harness/recovery/taxonomy.py` | `FailureKind`, `Retryability`, `NormalizedFailure`, `normalize_failure()`, `classify()`. PURE; no I/O, no model. Structured code → message rules → `UNKNOWN`. |
| Signatures + recurrence | `python/harness/recovery/signature.py` | `failure_signature()` (16-hex, volatile tokens collapsed), `RecurrenceTracker`. |
| Strategy policy | `python/harness/recovery/policy.py` | `RecoveryStrategy`, `RecoveryBudget`, `select_strategies()`, `reject_reason()`. PURE; ordered, inspectable. |
| Decision controller | `python/harness/recovery/controller.py` | `RecoveryController.decide()` → `RecoveryDecision` (`recover`/`suspend`/`stop`), bounded backoff. PURE. |
| Root-cause diagnosis | `python/harness/recovery/diagnosis.py` | `DiagnosisEngine.diagnose()` → evidence-ranked `Hypothesis`es + `Diagnosis` (`selected` only when decisive). PURE + optional `Probe`s. |
| Automatic execution | `python/harness/recovery/executor.py` | `recover_operation(service, op, verify=…)` — a bounded async retry/verify loop driving the controller and recording real outcomes; strategy handlers for repair-type strategies. |
| **Production run wiring** | `python/harness/recovery/execution.py` | `run_with_recovery(service, run_once, …)` — drives a production run THROUGH the bounded loop (classify → diagnose → retry → record). `tasks/bootstrap.build_task_executor` uses it, so a task run is *actively recovered*, not merely observed after the fact. Absent/disabled engine → one attempt, unchanged. Per-attempt run ids; the recovery trail (`recoveryIncidentId`/`recoveryAttempts`/`recoveryStrategy`) rides the task execution metrics. |
| **Run hot path (chat/tools, R3-03)** | `python/harness/recovery/hotpath.py` | `run_tool_with_recovery` wraps every tool call in the graph loop: on failure the engine classifies + decides, then the loop retries ONCE — only a READ-ONLY tool, only a `retry`/`rate_limit_backoff` decision, backoff capped at 1.5 s — or appends the strategy directive to the failed result so the next attempt is a different route. Per-run counters (`record_failure(recovery_state=…)`); `max_total_ms` enforced when elapsed is supplied; fail-open (no engine → original result). Round 4 (W10): an identical (tool, args, signature) failure is never retried unchanged again, and no progress across N attempts appends a `STUCK LOOP` directive naming the actual blocker (`progress.py`). |
| **Autonomy envelope** | `python/harness/recovery/envelope.py` | `AutonomyEnvelope` — pre-committed, scoped, expiring permission by action class + risk/reversibility/cost/files/network caps; kill switch `HARNESS_AUTONOMY=0`. Durable (migration 29 `AutonomyEnvelope`). The executor acts unattended ONLY inside it. |
| **Compensation** | `python/harness/recovery/compensation.py` | `compensate_pending()` — runs registered compensation handlers for pending operations, envelope-gated (`COMPENSATE`). |
| **Auto-reproduction** | `python/harness/recovery/reproduction.py` | `ReproducerRegistry` + `reproduce()` — runs a caller-registered reproducer per failure kind under a hard timeout; a successful reproduction makes the diagnosis decisive and is recorded as evidence. |
| **Coordination + approvals** | `store.py` + `executor.py` | Per-signature `RecoveryLease` (two workers never repair the same root cause at once); one-off operator `RecoveryApproval` authorizes an out-of-envelope strategy for one incident. |
| **Diagnosis probes** | `python/harness/recovery/probes.py` | read-only deterministic probes (dependency presence, provider config, provider health) registered at boot; unknown → `None`, never a guess. |
| **Operation ledger** | `python/harness/recovery/operations.py` | `OperationLedger` — idempotency-keyed tracking + compensation bookkeeping so a crashed repair is reconciled, not repeated. |
| Error taxonomy + signatures | `taxonomy.py` / `signature.py` | shared `FailureKind`/`Retryability`; stable 16-hex signatures + `RecurrenceTracker`. |
| Capability discovery | `python/harness/recovery/discovery.py` | `CapabilityIndex` over tools/providers/skills + `acquisition_plan()` (approval-flagged, never self-grants). |
| Acquisition caller | `python/harness/recovery/acquire_handlers.py` | `acquire_for_task()` / `build_acquisition_handlers()` / `resume_callback()` — the production half: `build` routes through the real engineering/code-task surface and parks the original task on the DAG (or WAITING for the cross-plan UI route); install/enable park ASKING_USER. |
| Incident → skill | `python/harness/recovery/learning.py` | `incident_to_candidate()` / `promote_incidents()` — inert `LearningCandidate`s through the EXISTING learning store. A resolved CAPABILITY incident yields the construction procedure candidate (`skills/procedures.py`, round 4 W6) — the same candidate the run-trace path produces, deduped by signature. L3 strategic learning (`strategy_learning.py`, round 4 W11) reads the same ledger for the route that worked (`RecoveryService.preferred_strategy`), when the evidence supports it. |
| Persistence | `python/harness/recovery/store.py` | `RecoveryStore` on **`eclipse-memory.db`** (migrations 26–29: `RecoveryIncident`, `RecoveryAttempt`, `RecoveryDiagnosis`, `RecoveryOperation`, `AutonomyEnvelope`, `RecoveryLease`, `RecoveryApproval`). Rides the ONE `EclipseMemoryStore` connection. |
| Facade | `python/harness/recovery/service.py` | `RecoveryService.record_failure()` = classify + decide + persist + return. |
| Boot wiring | `python/harness/recovery/bootstrap.py` | `install_recovery_layer` (idempotent) + `start_recovery`/`stop_recovery` (event subscription). |
| Agent tools | `python/harness/recovery/tools.py` | `recovery_incidents`, `recovery_incident`, `recovery_summary`, `recovery_diagnose`, `recovery_discover` — read-only. |
| Operator API | `python/harness/routers/recovery.py` | `/recovery/{health,summary,incidents,discover,envelope,operations}` and `/recovery/incidents/{id}/approvals` reads; `POST /recovery/incidents/{id}/{diagnose,reproduce,outcome,approve}`, `POST /recovery/promote`, `PUT /recovery/envelope` operator-gated. |
| Console UI | `src/app/recovery/` (`page.tsx`, `recovery-console.tsx`) + `src/app/api/recovery/[[...path]]/route.ts` + `src/lib/harness/recovery-view.ts` | Standalone `/recovery` page (like `/events`, `/fabric`): incidents, diagnosis, attempts, capability discovery, promote, approve, and the autonomy envelope + operation ledger. |

## Invariants (do not weaken)

1. **Not a second execution loop.** The engine never runs a tool, a graph node or
   a model. `record_failure` classifies + decides; the *caller* (task scheduler,
   event consumer, operator) acts. It never mutates task state.
2. **Safety-first policy.** A deterministic failure is never retried unchanged;
   `SUBSTITUTE_PROVIDER` is never offered for an authentication/authorization
   denial (a provider swap cannot grant a credential); when a signature recurs,
   plain `RETRY` is demoted so the strategy changes.
3. **Conservative classification.** An unrecognized failure is `UNKNOWN` /
   retryability `UNKNOWN` — never a guess presented as fact. `UNKNOWN` counts as
   *potentially* retryable so a transient fault is not permanently blocked.
4. **Bounded.** `RecoveryBudget` caps attempts, attempts-per-signature,
   delegations and elapsed time; a decision can never promise unbounded retries.
5. **Agent memory, not market data.** Incidents live in `eclipse-memory.db`, never
   `jdds.db` and never `agent-memory.db` (run traces).
6. **No secrets.** Only the caller-supplied, already-sanitized code/message/detail
   are stored; the signature is a one-way digest.

## Lifecycle integration

`install_recovery_layer` runs at boot (`boot.py`) and registers the read tools
idempotently (boot runs once per lifespan; the registry is process-wide).
`start_recovery` subscribes to the canonical Event System failure vocabulary
(`tool.failed`, `run.failed`, `task.failed`, `agent.failed`, `workflow.failed`,
`plugin.failed`, `automation.failed`, `process.failed`, `research.failed`,
`backtest.failed`, and round 4's `ui.capability_gap`); each non-replay event is
classified and recorded with `source="event"`. `stop_recovery` detaches the
subscription before the bus is torn down. Replayed events are ignored.

**Routing gaps (round 4).** `ui.capability_gap` is emitted when a UI request
names a capability the component catalog cannot satisfy and is escalated to an
engineering task. It classifies as `FailureKind.CAPABILITY` — non-retryable,
because re-running the same request cannot create a missing component — so the
policy offers `SUBSTITUTE_TOOL` and `ALTERNATIVE_IMPLEMENTATION`, never a blind
retry. The payload carries the bounded request text (`capability`), the
classifier `mode` and the `runId`; no request body or secret is stored. The run
trace also records the deterministic mistake categories
`composed_without_witness`, `escalation_refused`, `capability_gap_refused`,
`misrouted_request` and `intent_ambiguity` (`eclipse_memory/mistakes.py`).

**Routing repair proposals (round 4, W2).** `recovery/routing_repair.py` turns a
stored `ui.capability_gap` incident into a typed proposal:
`VOCABULARY_GAP` (a missed additive phrase → a minimal `mode.py` replacement +
a fixture), `CATALOG_GAP` (the engineering escalation is the correct route),
`CAPABILITY_ABSENT` (an acquisition plan), or `POLICY_GAP` (an operator
decision). `RecoveryService.propose_routing_repair` is **read-only**: only
`VOCABULARY_GAP` yields a `code.patch.PatchOp`, and its verification activates
the exact rule in memory through the existing `ImprovementProposal` contract and
re-runs the fixture. Nothing is written to the tree and nothing is activated.

**Acquisition lifecycle (round 4, W5/W9).** `recovery/acquisition.py` turns
discovery into an ordered lifecycle: **discover → assess → propose → acquire →
validate → retry**. A proposal names each step's surface (`existing_tool`,
`skill`, `plugin`, `scaffold_kit`, `engineering`, `alternative`, `operator`),
whether it is ready, whether it needs approval, and the exact missing facts.
`use` and `alternative` are read-only; `enable`/`install`/`build` are always
approval-flagged and only run through a caller-supplied handler. Validation
without a real contract test is reported `unverified`, never passed; retry
resumes the original task from its checkpoint via a callback. `run_with_recovery`
registers the default capability handlers, so a missing capability hands back the
plan and **STOPS** (`acquisition_required`) instead of repeating the same failed
call. `POST /recovery/incidents/{id}/acquisition` returns the plan for a stored
incident, and the recovery console shows its steps/surfaces/gaps. Discovery now
ignores grammar stopwords, so a query containing "a" no longer matches every
description that contains "a".

**The production caller (round 4, W5/W9 remainder).**
`recovery/acquire_handlers.py` is the caller half: on a stopped task run the
executor attempts the plan's first actionable step through the EXISTING gates.
A `build` step routes to the real `ui_start_engineering` escalation (its own
plan → the original task parks WAITING and is resumed explicitly from its
checkpoint) or creates a same-plan code-agent capability task carrying the
objective as its acceptance criterion; the original task then gains a REQUIRES
dependency and is parked BLOCKED(DEPENDENCY), so the existing DAG auto-resumes
it when the capability task COMPLETES — that completion is the validation gate
(a cross-plan edge is refused by design, never bypassed). `install`/`enable`
steps park the task ASKING_USER with the exact missing facts; nothing
self-installs or self-enables. `resume_callback(manager, task_id)` is
`retry_task`'s caller half (`TaskManager.restore_checkpoint`). The scheduler
records the executor's new `waiting` outcome without failing or retrying a
parked task. The operator surface is `POST
/recovery/incidents/{id}/acquisition/execute` (ONE step, `approved: true` for a
mutation, parking never re-executes it) and `.../resume` (checkpoint resume).

**L3 strategic learning (round 4, W11).** `recovery/strategy_learning.py`
derives the route that worked per failure signature from the incident/attempt
ledger (observations + measured success rate; `None` on thin evidence).
`record_failure` FEEDS it into the decision: when the preference is among the
policy's own candidates it is promoted to first — never a strategy the policy
did not offer, so every safety invariant is unchanged — and the evidence
(`strategyPreference`) rides the result. `GET /recovery/metrics` reports the
W7 self-evolution block from the real stores.

**Landing a routing repair (round 4, W4).** `recovery/routing_landing.py` takes a
stored incident's classifier-rule proposal, refuses an authority target with
`code/selfhost.py::classify_landing`, applies the patch to a **disposable**
worktree, registers that workspace under `routing-repair-<incidentId>`, and
builds the SAME `promotion.PromotionPreview` the Code Tasks route uses.
`POST /recovery/incidents/{id}/routing-repair` returns the proposal, preview and
landing verdict. The recovery console renders the existing `PromoteChange` card,
which performs the single-use, digest-bound apply and reports the restart/build
requirement; rollback is the existing `rollback_promotion`. The promotion
preview and apply routes refuse an authority target **before** creating or
consuming an approval, so the self-host floor cannot be spent or bypassed.

**Construction procedure learning (round 4, W6).** A resolved CAPABILITY
incident (a `ui.capability_gap` whose capability was later engineered and
registered) yields a `successful_procedure` candidate — the encoded
escalate → implement → register → compose procedure with the widget layer's
constraints — instead of a generic `failure_recovery`. It is the SAME candidate
the run-trace path (`skills/procedures.py` via `skills/learning.py::analyze_run`)
produces, so the two sources dedupe into one by signature. The candidate is
inert; the draft opens only on recurrence and activation stays operator-gated
(see `docs/harness/memory-skills-evolution-plan.md`).

## Configuration

- `HARNESS_RECOVERY_ENABLED` — default ON; `0`/`false` disables capture.
- **`HARNESS_AUTONOMY`** — global kill switch; `0`/`false` revokes all autonomy.
- **`HARNESS_AUTONOMY_ENVELOPE`** — path to a JSON envelope (see `AutonomyEnvelope`). A **persisted** operator envelope (`PUT /recovery/envelope`) overrides this file and the default, and survives a restart.
- `HARNESS_RECOVERY_MAX_ATTEMPTS` (default 4)
- `HARNESS_RECOVERY_MAX_PER_SIGNATURE` (default 2)
- `HARNESS_RECOVERY_MAX_DELEGATIONS` (default 2)
- `HARNESS_RECOVERY_MAX_TOTAL_MS` (default 600000)

### Autonomy envelope (how the engine acts unattended)

The envelope is the operator's standing authority. `recover_operation` auto-runs
retry/backoff (baseline resilience) always, and any **other** strategy only when
its action class is enabled in the envelope AND a handler exists. The default
envelope is conservative (only reversible re-run/re-plan/rollback classes);
effectful classes (dependency install, provider/tool substitution, adapter build)
require the operator to widen it via `PUT /recovery/envelope` (persisted). A
repair holds a per-signature **lease** so two workers never repair the same root
cause at once. An action outside the envelope is returned to the caller as
`outside_autonomy_envelope` — unless an operator granted a **one-off approval**
(`POST /recovery/incidents/{id}/approve`) for exactly that incident and strategy.

## Production & operations

- **Readiness / degradation.** `GET /recovery/health` reports `status`
  (`ok`/`disabled`/`error`), the budget, the live envelope and incident counts.
  `HARNESS_RECOVERY_ENABLED=0` disables capture entirely; a missing eclipse-memory
  store disables only this engine, never boot (`install_recovery_layer` is
  best-effort and idempotent).
- **Revoking autonomy.** `HARNESS_AUTONOMY=0` is a global kill switch; the envelope
  also expires via `expiresAt`. Both take effect on the next decision — the engine
  can never widen its own authority, and the persisted envelope is written only by
  the operator route.
- **Attack surface.** Every mutation route is operator-gated by transport/token
  (never a body flag); reads are open. Incidents store only sanitized, length-bounded
  fields; signatures are one-way digests (no secret can be recovered from them).
- **Concurrency.** A single SQLite connection serializes incident writes; the repair
  lease is an atomic conditional upsert, exclusive across threads/processes. The
  runtime itself is single-process async, so writes are effectively serialized.
- **CI.** `.github/workflows/ci.yml` runs typecheck → lint → vitest + Python → eval
  gates on `ubuntu-latest` for every push/PR.
- **What full autonomy still needs.** The executor is now driven by the production
  task executor (a failing task run is classified, diagnosed and retried with
  backoff before the scheduler's own retry policy applies, and every failure
  carries a durable incident id — `recovery/execution.py`). What remains is wiring
  the install/build *acquisition* rungs and the *delegation* roles into the
  executor — both are large subsystem integrations. The envelope, executor, ledger
  and approval path are already the safe sockets for them; an unhandled repair
  strategy is returned to the caller as `strategy_requires_caller`.

## Tests

`python/tests/test_recovery_{taxonomy,signature,policy,store,integration,api,diagnosis,executor,discovery,learning,envelope,probes,operations,compensation,reproduction,safety,concurrency}.py`
plus `test_recovery_task_execution.py` (the production run wiring: transient
fail-2-then-succeed, auth never retried, budget exhaustion partial, verification
failure, caller-handback for a repair strategy, and the disabled/absent-engine
no-op) — 134 cases: classification/signature purity, recurrence, strategy selection and
reject rules, controller bounds/backoff, durable upsert + attempts + summary +
diagnosis, root-cause ranking, the bounded executor (retry/verify/suspend/
envelope-gated handler/lease/approval), the autonomy envelope (kill switch/expiry/
risk/caps/network), read-only probes, the idempotent operation ledger, compensation,
timeout-guarded reproduction that makes a diagnosis decisive, **adversarial safety
invariants** (envelope cannot be bypassed, non-retryable never retried, recovery
always bounded, one-off approval is scoped, no secret persisted), lease exclusivity
under thread contention, capability ranking + acquisition plans, incident→candidate
promotion, boot subscription, the read tools, the operator API, and an end-to-end
case that publishes a real `tool.failed` on the live bus and asserts the incident is
recorded. Front door: `src/lib/harness/recovery-view.test.ts`.

## What it can and cannot do (honest)

**Can (unattended, inside the envelope):** classify, diagnose with real evidence,
auto-reproduce under a timeout to make a diagnosis decisive, bound-and-retry with
backoff, verify before claiming success, run approved repair handlers with
idempotency + per-signature leasing, compensate recorded side effects, discover
existing capabilities, persist the envelope and incidents, and turn validated
repairs into inert skill candidates. A production task run is now **driven through
this loop** (`recovery/execution.py`), so a transient run failure is actively
recovered with a recorded reason and backoff rather than only observed. The run
HOT PATH is covered too (`recovery/hotpath.py`, R3-03): a read-only tool failure
may retry once inside the budget, and every other failure returns the engine's
decision to the model as a route directive.

**Cannot yet (noted, not hidden):** auto-acquire a *missing* capability (the plan is
approval-flagged; the install/build rungs are not wired); auto-promote a skill
without an operator; delegate diagnosis to sub-agents; stream live in the console;
or compensate *without* a caller-registered handler. The envelope makes unattended
action *safe*; extending the enabled action classes is the operator's deliberate
choice.

---
title: Failure Intelligence & Adaptive Recovery
status: Current
last-verified: 2026-10-09
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
| **Autonomy envelope** | `python/harness/recovery/envelope.py` | `AutonomyEnvelope` — pre-committed, scoped, expiring permission by action class + risk/reversibility/cost/files/network caps; kill switch `HARNESS_AUTONOMY=0`. The executor acts unattended ONLY inside it. |
| **Diagnosis probes** | `python/harness/recovery/probes.py` | read-only deterministic probes (dependency presence, provider config, provider health) registered at boot; unknown → `None`, never a guess. |
| **Operation ledger** | `python/harness/recovery/operations.py` | `OperationLedger` — idempotency-keyed tracking + compensation bookkeeping so a crashed repair is reconciled, not repeated. |
| Error taxonomy + signatures | `taxonomy.py` / `signature.py` | shared `FailureKind`/`Retryability`; stable 16-hex signatures + `RecurrenceTracker`. |
| Capability discovery | `python/harness/recovery/discovery.py` | `CapabilityIndex` over tools/providers/skills + `acquisition_plan()` (approval-flagged, never self-grants). |
| Incident → skill | `python/harness/recovery/learning.py` | `incident_to_candidate()` / `promote_incidents()` — inert `LearningCandidate`s through the EXISTING learning store. |
| Persistence | `python/harness/recovery/store.py` | `RecoveryStore` on **`eclipse-memory.db`** (migrations 26/27/28: `RecoveryIncident`, `RecoveryAttempt`, `RecoveryDiagnosis`, `RecoveryOperation`). Rides the ONE `EclipseMemoryStore` connection. |
| Facade | `python/harness/recovery/service.py` | `RecoveryService.record_failure()` = classify + decide + persist + return. |
| Boot wiring | `python/harness/recovery/bootstrap.py` | `install_recovery_layer` (idempotent) + `start_recovery`/`stop_recovery` (event subscription). |
| Agent tools | `python/harness/recovery/tools.py` | `recovery_incidents`, `recovery_incident`, `recovery_summary`, `recovery_diagnose`, `recovery_discover` — read-only. |
| Operator API | `python/harness/routers/recovery.py` | `/recovery/{health,summary,incidents,discover,envelope,operations}` reads; `POST /recovery/incidents/{id}/{diagnose,outcome}`, `POST /recovery/promote`, `PUT /recovery/envelope` operator-gated. |
| Console UI | `src/app/recovery/` (`page.tsx`, `recovery-console.tsx`) + `src/app/api/recovery/[[...path]]/route.ts` + `src/lib/harness/recovery-view.ts` | Standalone `/recovery` page (like `/events`, `/fabric`): incidents, diagnosis, attempts, capability discovery, promote, autonomy envelope + operation ledger. |

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
`backtest.failed`); each non-replay event is classified and recorded with
`source="event"`. `stop_recovery` detaches the subscription before the bus is torn
down. Replayed events are ignored.

## Configuration

- `HARNESS_RECOVERY_ENABLED` — default ON; `0`/`false` disables capture.
- **`HARNESS_AUTONOMY`** — global kill switch; `0`/`false` revokes all autonomy.
- **`HARNESS_AUTONOMY_ENVELOPE`** — path to a JSON envelope (see `AutonomyEnvelope`).
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
require the operator to widen it via `PUT /recovery/envelope`. An action outside
the envelope is returned to the caller as `outside_autonomy_envelope` — never run.

## Tests

`python/tests/test_recovery_{taxonomy,signature,policy,store,integration,api,diagnosis,executor,discovery,learning,envelope,probes,operations}.py`
— 87 cases: classification/signature purity, recurrence, strategy selection and
reject rules, controller bounds/backoff, durable upsert + attempts + summary +
diagnosis, root-cause ranking, the bounded executor (retry/verify/suspend/
envelope-gated handler), the autonomy envelope (kills switch/expiry/risk/caps/
network), the read-only probes, the idempotent operation ledger, capability ranking
+ acquisition plans, incident→candidate promotion, boot subscription, the read
tools, the operator API, and an end-to-end case that publishes a real `tool.failed`
on the live bus and asserts the incident is recorded. Front door:
`src/lib/harness/recovery-view.test.ts`. Unrelated regression coverage: the full
harness suite (`5190 passed, 16 skipped`).

## What it can and cannot do (honest)

**Can (unattended, inside the envelope):** classify, diagnose with real evidence,
bound-and-retry with backoff, verify before claiming success, discover existing
capabilities, record durable incidents, and turn validated repairs into inert skill
candidates.

**Cannot yet (noted, not hidden):** auto-reproduce a failing operation itself;
auto-acquire a *missing* capability (the plan is approval-flagged and the install/
build rungs are not wired); auto-promote a skill without an operator; delegate
diagnosis to sub-agents; stream live in the console; or compensate side effects
automatically (the ledger records what to compensate; the compensation action is
the caller's). The envelope makes unattended action *safe*; extending the enabled
action classes is the operator's deliberate choice.

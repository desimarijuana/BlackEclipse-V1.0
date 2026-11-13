---
title: W8 Observability, SLOs, and Conformance — Detailed Plan
status: Current
last-verified: 2026-11-13
owner: Agent runtime
source: docs/harness/roadmap/hermes-inspired-improvement-plan.md (W8)
scope: implemented (W8.0–W8.7) — see the implementation delta below
---

# W8 — Observability, SLOs, and Conformance

W8 is the workstream that makes every other workstream **provable**. The Hermes
comparison said Eclipse already has more telemetry than Hermes; the gap is that
the new seams (gateway attempts, context ladder, tool batches, goals, skill
evaluation, run-kernel integrity) are not wired into the SLO/release-gate story.
This plan closes that gap without adding a second telemetry stack.

## Implementation status (2026-11-13)

Slices W8.0–W8.7 are implemented. Where reality differed from the plan:

- **Event names follow the shipped emitters**, not the plan's earlier guesses:
  `security.hardline.blocked` (not `hardline.blocked`), `checkpoint.created/
  failed/restored/pruned`, `skill.evaluation_completed`, `skill.curator_run`.
  The projection also accepts `skill.curator.run`.
- **`observability/signals.py`** owns the bounded aggregates and the
  hook→metric mapping; `core.py` stays a single ingestion point and does not
  grow into a second module.
- **`observability/bridge.py`** lets a subsystem with no `RunEmitter` (skill
  evaluation, curator, the shadow-git checkpoint store) hand an event to the
  same projector. It is not a second event bus.
- **`run_derived` objectives**: terminal correctness and orphan rate are
  recomputed for the report from `runs.created/terminal/orphaned`.
- **The probe advertises all capabilities** for its synthetic report and emits
  every W8 signal; live reports use the real flags.
- The gate implements `skipped` / `unmeasured` / `observed` in addition to
  pass/fail, validates paths, and applies regression allowances only to
  measured, enforced checks.
- New checks start `enforce:false` where the capability is not yet default-on
  (fallback success, compression, goals, file checkpoints); the probe exercises
  them as `observed` until a live baseline promotes them.

The parent plan describes W8 in fifteen lines. This file is the engineering plan:
the exact signals, the metric and SLO names, the report schema, the gate
semantics, the alert rules, the conformance cases, and the slice order.

---

## 0. In one paragraph

Eclipse already ships a vendor-neutral observability hub with a bus projector,
spans, metrics, costs, a failure taxonomy, SLOs v2, a release probe, a
deterministic gate and an HTML dashboard. W8 does **not** rebuild any of it. It
does four things: (1) project the events the W1/W2 seams already emit and define
what every later workstream must emit; (2) register all objectives eagerly and
make "no samples" an honest `unmeasured` state instead of a false green; (3) make
the gate data-driven so a new SLO is a budgets-file change, not new gate code;
and (4) add the conformance and alert coverage that turns a dashboard into an
operational contract.

---

## 1. Current state (evidence, not assumptions)

| Capability | State | Evidence / gap |
|---|---|---|
| One observability hub | **Shipped** | `python/harness/observability/core.py`; one subscriber on `service.bus` |
| Bus projection | **Shipped, incomplete** | `observability/integration.py:66`; handles `model.request.*` but **drops** `model.attempt.*`, `model.first_token`, `model.candidate_plan`, `model.retry`, `model.fallback`, `context.compressed`, `memory.history_compacted` |
| Spans / trajectory | **Shipped** | run → step → LLM/tool parentage, `trajectory()` |
| Metrics | **Shipped** | RED/USE helpers, `eclipse_*` families, Prometheus exposition |
| Failure taxonomy | **Shipped** | `observability/failures.py`, closed classes |
| Costs | **Shipped** | `observability/costs.py`, per run/step/model, `priced:false` when unknown |
| SLOs | **Shipped v2, but lazy** | `observability/slo.py`; ratio/percentile/rate. Objectives are `define()`d on **first event** (`core.py:443-524`), so a missing signal produces no objective at all |
| SLO honesty | **Gap** | `healthy` is a bool. An objective with `total=0` reports `compliance=null` but the dashboard treats it as `breaching`; the gate decides per-check ad hoc |
| Release report | **Shipped v1** | `core.py:562`; five sections only: runs/latency/resume/cost/tools, plus failures/slos |
| Release gate | **Shipped, hardcoded** | `observability/gate.py:112`; exactly five checks (terminal, orphan, run p95, resume p95, cost). Adding a sixth objective means editing gate code |
| Probe | **Shipped, narrow** | `observability/probe.py`; 40 synthetic runs, no attempt/TTFT/context/integrity signals |
| Dashboard | **Shipped** | `observability/dashboard.py`; one card per objective, run/latency/cost/tool cards |
| Alerts | **Partial** | `deploy/prometheus/blackeclipse.rules.yml`; two real availability rules, runtime rules are commented templates |
| Conformance | **Shipped, 16 cases** | `evaluation/conformance/cases.py` + `docs/harness/conformance.json`; no W8 signal cases |
| W1 gateway | **Shipped** | `model_runtime/gateway.py` emits `model.candidate_plan`, `model.attempt.completed/failed`, `model.retry`, `model.fallback`; `model_stream.py` emits `model.first_token` |
| W2 context | **Shipped** | `context/usage_anchor.py`, `context/compression_ladder.py` emit `context.pruned`, `context.compressed`, `memory.history_compacted` |
| W3 tool execution | **Planned** | no `tool_batches.py` / guardrails; event vocabulary fixed by `w3-tool-execution-plan.md` |
| W4 autonomy | **Planned** | no `autonomy/goal_runtime.py`; `goal.verdict` vocabulary fixed by `w4-autonomy-plan.md` |
| W5 learning loop | **Planned** | no `skills/execution_eval.py` / `curator.py` |
| W6 run kernel | **Planned** | no lease module; effects exist (`run_effects.py`) with `unknown` as a first-class state, but no metric/event |
| W7 delegation/files | **Planned** | no `code/checkpoints.py` |

**Verdict:** the platform exists. The failure is that the **new seams are
invisible**, the **objective registry can silently omit work**, and the **gate
cannot grow** without a code change. W8 fixes those three things.

---

## 2. The W8 contract (definition of done)

Every workstream — W1 through W7 — is done only when all seven rows below exist
for its new seam. This is the checklist to paste into every PR description.

| # | Artifact | Where |
|---|---|---|
| 1 | **Event** on `service.bus`, with a documented payload | the seam's own module |
| 2 | **Projection** into spans/metrics | `observability/integration.py` |
| 3 | **Objective or invariant** with a name and a source | `observability/core.py` + `docs/harness/slo-budgets.json` |
| 4 | **Report field** in schema v2 | `core.release_report()` |
| 5 | **Dashboard line** | `observability/dashboard.py` |
| 6 | **Conformance case** (deterministic, no provider) | `evaluation/conformance/cases.py` + `conformance.json` |
| 7 | **Alert rule** referencing a metric that actually exists | `deploy/prometheus/blackeclipse.rules.yml` |

No row may be "follow-up". A slice without a deterministic acceptance test is
not done.

---

## 3. Design decisions

### D1 — One projector, no second telemetry stack

Every signal enters through `RunEventProjector.handle()` or
`get_hub().emit()`. No new logging stack, metric registry, trace exporter, or
event bus. The projector stays fail-open: a projection bug drops telemetry, never
a run (`integration.py:66-70`).

### D2 — Closed vocabularies and a cardinality budget

New metric labels come only from finite sets:

- `outcome`: `completed | retryable | failed | circuit_open | rate_limited`
- `verdict`: `done | continue | blocked | wait`
- `stage`: `prune | summary | skeleton | none`
- `action`: `allow | warn | halt`
- `op`: `snapshot | restore | list | diff`

**Never label with**: run id, session id, tool arguments, prompt text, credential
id, file path, goal id. Provider/model labels already exist on
`eclipse_llm_requests_total`; W8 adds a documented note and a bounded
`ECLIPSE_METRIC_LABEL_MODELS` switch (default `on` in development, `off` in
production) instead of extending that pattern to new metrics.

### D3 — Eager registration, honest `unmeasured`

Replace lazy `define()`-on-first-event with `register_objectives()` called from
`ObservabilityHub.__init__`. Every objective is always present in the report with:

```json
{"name": "ttft_p95", "total": 0, "measured": false, "healthy": null}
```

`unmeasured` is not `healthy` and is not `breaching`. The dashboard renders it as
a third, muted state. The gate treats it according to the budget's
`requireSamples` flag (D7).

### D4 — SLOs vs invariants

Two different things, deliberately:

- **SLO** — a user-facing objective measured over a rolling window, with an error
  budget and burn rate. Missing samples are allowed; a low sample count is
  reported, not hidden.
- **Invariant** — an event that must never happen: an unknown effect, a lost
  lease, a checkpoint write failure, a batch-ordering violation, a skill enabled
  without a passing execution eval, an event-sequence collision.

Invariants are counters, not error budgets. Any occurrence is a defect; the
gate fails on a non-zero count, and the alert is immediate (no burn window).
This prevents a "99.9% no-unknown-effects" budget from making a correctness bug
look acceptable.

### D5 — Budgets are data; the gate resolves paths

`gate.py` today hardcodes five checks. W8 introduces a declarative budget
descriptor:

```json
{
  "name": "ttft_p95",
  "path": "latency.ttft.p95",
  "kind": "percentile",
  "thresholdMs": 15000,
  "maxRegression": 0.2,
  "minSamples": 50,
  "requireSamples": false,
  "requires": "modelGateway",
  "enforce": true
}
```

`evaluate_gate` resolves `path`, applies the comparison, and preserves the five
legacy checks behind a compatibility shim until schema v1 is retired. Unknown
paths, missing `kind`, and unsatisfied `requires` are explicit `skipped` checks
with a reason — never silent passes.

### D6 — Additive report schema v2

The report keeps every v1 key and adds sections. Consumers that read v1 keep
working. `schema: 2` is stamped at the top. `probe.py` and live
`release_report()` return the same shape.

### D7 — Fail-open telemetry, fail-closed gate

- Runtime: an exporter, projector or sink failure is counted and swallowed. A
  run never fails because telemetry failed.
- CI/release: a **required** budget with zero samples fails the gate
  (`requireSamples: true`). An optional budget with no samples is `skipped` with
  a reason. Missing data must never read as healthy.

### D8 — SLOs are computed before sampling

`_slo_for` runs in `observe()` before export sampling decides what to keep. Keep
that invariant: an SLO computed from sampled spans would drift with
`ECLIPSE_TRACE_SAMPLE_RATE`.

### D9 — Record the decision when W8.0 lands

Report schema v2, the `unmeasured` state and the SLO/invariant split are
contracts. W8.0 lands with a harness ADR (`docs/harness/decisions.md`, next free
`ADR-HNN`) so later workstreams inherit the contract instead of re-litigating it.

---

## 4. Signal dictionary (normative)

Field names below are the contract. A later implementation may add fields, never
rename these.

### 4.1 W1 — model gateway (shipped; wire it up)

| Event | Emitter | Required payload | Projection |
|---|---|---|---|
| `model.candidate_plan` | `model_runtime/gateway.py:208` | `step`, `candidates[]`, `excluded[]`, `fallbackDepth` | span attributes `candidateCount`, `excludedCount`, `fallbackDepth`; `eclipse_model_candidate_count` histogram |
| `model.attempt.completed` / `model.attempt.failed` | `gateway.py:235-255` | `step`, `attempt`, `index`, `provider`, `model`, `outcome`, `errorClass`, `statusCode`, `latencyMs`, `costUsd`, `priced`, `willRetry`, `willFallback` | `eclipse_model_attempts_total{provider,outcome}`, `eclipse_model_attempt_duration_ms{provider}`, per-run attempt count |
| `model.retry` | `gateway.py:247` | `step`, `attempt`, `maxAttempts`, `errorClass`, `statusCode` | `eclipse_model_retries_total{errorClass}` |
| `model.fallback` | `gateway.py:313` | attempt trace, `fallbackUsed` | `eclipse_model_fallbacks_total`, fallback success numerator |
| `model.first_token` | `model_stream.py:81` | `ttftMs`, `finalizing` | `eclipse_model_ttft_ms{provider}` (provider filled from the active LLM span) |
| `model.first_token_timeout` | `model_stream.py:69` | `timeoutS`, `finalizing` | `eclipse_model_ttft_timeouts_total`; failure class `timeout` |

`model.first_token` currently lacks provider/model. Do **not** add them to the
event if that widens cardinality on the bus; fill them from
`RunEventProjector._runs[run_id]` when the LLM span is active, else `unknown`.

### 4.2 W2 — context economics (shipped; wire it up)

| Event | Emitter | Required payload | Projection |
|---|---|---|---|
| `context.pruned` | `compression_ladder.py:328` | `stage`, `prunedToolResults`, `mode` | counter `eclipse_context_pruned_total{mode}` |
| `context.compressed` | `compression_ladder.py:380` | `stage`, `ok`, `reason`, `droppedTurns`, `prunedToolResults`, `summaryChars`, `usedModel` | `eclipse_context_compactions_total{stage,outcome}`; ratio = `summaryChars / droppedTurns` is **not** a quality metric, do not record it |
| `memory.history_compacted` | `compression_ladder.py:259` | result dict incl. `usedModel`, `reason` | failure counter when `usedModel=false` and `reason` is a timeout/stall |
| `context.retry` / `context.recovered` | existing | existing | already → `onRecoveryStart` |
| `context.exhausted` | new at the budget seam | `window`, `used`, `reserved` | `eclipse_context_overflow_total{recovered}` |

Also expose the **usage-anchor ratio** as a gauge/histogram from the budget
seam: `eclipse_context_usage_ratio` (`used/window`), sampled at each model call.
This is the leading indicator; overflow is the lagging one.

### 4.3 W3 — tool execution (contract for the upcoming slice)

| Event | Required payload | Projection |
|---|---|---|
| `tool.batch_plan` | `calls`, `batches`, `parallelSafe`, `wouldSaveMs` | `eclipse_tool_batches_total`, `eclipse_tool_batch_size` |
| `tool.batch` | `calls`, `batches`, `maxConcurrency`, `orderingViolations`, `durationMs` | `eclipse_tool_batch_duration_ms`, `eclipse_tool_batch_ordering_violations_total` (**invariant**) |
| `tool.guardrail` | `rule`, `count`, `tool`, `action`, optional `toolCallId` | `eclipse_tool_guardrail_total{rule,action}` |

### 4.4 W4 — autonomy (contract)

| Event | Required payload | Projection |
|---|---|---|
| `goal.created` | `goalId`, `maxTurns` | `eclipse_goals_total` |
| `goal.verdict` | `goalId`, `turn`, `verdict`, `reason`, `downgraded`, gate summary | `eclipse_goal_verdicts_total{verdict}`, turns histogram |
| `goal.budget_exhausted` | `goalId`, `usedTurns`, `maxTurns` | counter; failure class `budget` |
| `loop.tick` | `loopId`, `mode`, `tick` | counter `eclipse_loop_ticks_total{mode}` |

`goalId` is payload only; it is never a metric label.

### 4.5 W5 — learning loop (contract)

| Event | Required payload | Projection |
|---|---|---|
| `skill.execution_eval` | `skill`, `ok`, `cases`, `passed`, `failed`, `passRate`, `reason` | `eclipse_skill_exec_eval_total{outcome}`; invariants: `eclipse_skill_enabled_without_eval_total` (must stay 0) |
| `skill.curator.run` | `mode`, `proposals`, `applied`, `rolledBack` | `eclipse_curator_runs_total{mode,outcome}` |

### 4.6 W6 — run-kernel integrity (contract + existing seam)

Names below are fixed by `w6-run-kernel-integrity-plan.md`; use them verbatim.

| Signal | Source | Projection |
|---|---|---|
| `effect.unknown` | `run_effects.py` / `graph.py` unknown path | `eclipse_effect_unknown_total{tool}`; **invariant** |
| `run.lease_lost` | fenced update returning false | `eclipse_lease_lost_total`; **invariant** |
| `checkpoint.write` | atomic boundary, `ok|failed` + `kind` | `eclipse_checkpoint_write_ms`, `eclipse_checkpoint_write_failures_total{kind}`; failures are an **invariant** |
| `event.seq_retry` | `EventSequence` retry after a collision | `eclipse_event_seq_retries_total` (recovery, warning) |
| `event.seq_collision` | a retry that did not converge | `eclipse_event_seq_collisions_total`; **invariant** |
| `hardline.blocked` | `security/hardline.py` denial | `eclipse_hardline_blocked_total{pattern}` — **security signal**, not an invariant (blocking is success; a spike means an attack or a broken workflow) |

Effects already exist and `graph.py:1106` marks unknown; today it produces no
signal. This is the smallest immediate W8 win.

### 4.7 W7 — delegation and file checkpoints (contract)

Names below are fixed by `w7-delegation-and-file-safety-plan.md`.

| Event | Required payload | Projection |
|---|---|---|
| `delegation.async.started` | `delegationId`, `children`, `strategy` | `eclipse_delegations_total{strategy}` |
| `delegation.child.completed` | `delegationId`, `childIndex`, `status`, `tokens` | async completion latency (submit → terminal), terminal counts |
| `delegation.steered` | `delegationId`, `seq`, `chars` | steer delivery latency (append → consumed) |
| `delegation.repair.attempted/succeeded/failed` | `delegationId`, `childIndex`, errors | `eclipse_delegation_repairs_total{outcome}` |
| `delegation.worktree.allocated` | `delegationId`, `childIndex`, `workspaceId` | `eclipse_delegation_worktrees_total` |
| `checkpoint.created` | `checkpointId`, `reason`, `runId`, `files`, `bytes`, `durationMs` | `eclipse_file_checkpoint_ms`, `eclipse_file_checkpoint_bytes` |
| `checkpoint.failed` | `reason`, `code` | `eclipse_file_checkpoint_failures_total{reason}` |
| `checkpoint.restored` | `checkpointId`, `paths`, `preRestoreId` | `eclipse_file_checkpoint_restores_total` |
| `checkpoint.pruned` | `removed`, `bytesFreed` | `eclipse_file_checkpoint_pruned_total`, store size |

`delegationId` and `workspaceId` are payload only; never metric labels.

---

## 5. SLO and invariant catalog

Targets are **initial** and are ratcheted only after a committed baseline exists
(W0 rule). `minSamples` prevents a three-run week from paging anyone.

| Name | Kind | Target / threshold | Min samples | Source | Budget key |
|---|---|---|---:|---|---|
| `terminal_correctness` | ratio | ≥ 0.999 | 1 | runs | existing |
| `orphan_rate` | rate | ≤ 0 | 1 | runs | existing |
| `run_p95_latency` | percentile | ≤ 120 000 ms | 20 | runs | existing |
| `resume_p95` | percentile | ≤ 10 000 ms | 10 | resumed runs | existing |
| `cost_per_task` | percentile | ≤ $1.00 | 20 | priced runs | existing |
| `ttft_p95` | percentile | ≤ 15 000 ms | 50 | `model.first_token` | new |
| `model_fallback_success_rate` | ratio | ≥ 0.90 | 20 fallbacks | attempts | new |
| `context_overflow_rate` | rate | ≤ 0.01 | 50 runs | budget seam | new |
| `compression_failure_rate` | rate | ≤ 0.05 | 20 compactions | ladder | new |
| `resume_success_rate` | ratio | ≥ 0.99 | 20 resumed runs | runs | new |
| `goal_completion_rate` | ratio | ≥ 0.80 | 20 verdicts | `goal.verdict` | new |
| `goal_blocked_rate` | rate | ≤ 0.15 | 20 verdicts | `goal.verdict` | new |
| `file_checkpoint_failure_rate` | rate | ≤ 0.05 | 20 snapshots | `checkpoint.failed` | new |

**Invariants (no budget, any occurrence is a defect):**

| Invariant | Metric | Gate |
|---|---|---|
| Unknown effect | `eclipse_effect_unknown_total` | fail when > 0 |
| Lease lost | `eclipse_lease_lost_total` | fail when > 0 |
| Checkpoint write failure (run-kernel boundary) | `eclipse_checkpoint_write_failures_total` | fail when > 0 |
| Event-sequence collision after retry | `eclipse_event_seq_collisions_total` | fail when > 0 |
| Tool batch ordering violation | `eclipse_tool_batch_ordering_violations_total` | fail when > 0 |
| Skill enabled without execution eval | `eclipse_skill_enabled_without_eval_total` | fail when > 0 |

An invariant whose capability is switched off (`HARNESS_PARALLEL_TOOLS=off`,
`HARNESS_AUTONOMY=off`, …) is reported as `applicable:false` and `skipped`, not
as a pass.

---

## 6. Report schema v2

```jsonc
{
  "schema": 2,
  "generatedAt": "...",
  "capabilities": {
    "modelGateway": true, "contextLadder": true,
    "parallelTools": false, "autonomy": false,
    "learningEval": false, "runKernelIntegrity": false,
    "fileCheckpoints": false
  },
  "runs": { "created": 0, "terminal": 0, "orphaned": 0, "active": 0, "...": "unchanged" },
  "latency": {
    "run": { "samples": 0, "p50": null, "p95": null, "p99": null },
    "ttft": { "samples": 0, "p50": null, "p95": null, "p99": null }
  },
  "model": {
    "attempts": 0,
    "attemptsPerRun": { "p50": null, "p95": null },
    "fallbacks": 0, "fallbackSuccessRate": null,
    "retries": 0, "ttftTimeouts": 0,
    "pricedCoverage": null,
    "byOutcome": { "completed": 0, "retryable": 0, "failed": 0 }
  },
  "context": {
    "usageRatio": { "samples": 0, "p50": null, "p95": null },
    "overflow": 0, "overflowRate": null, "recovered": 0,
    "compactions": { "samples": 0, "byStage": {}, "failures": 0, "failureRate": null }
  },
  "tools": {
    "calls": 0, "errors": 0,
    "batches": { "count": 0, "maxConcurrency": 0, "orderingViolations": 0 },
    "guardrails": { "allow": 0, "warn": 0, "halt": 0, "byRule": {} }
  },
  "goals": { "created": 0, "verdicts": {}, "completionRate": null, "blockedRate": null },
  "learning": { "executionEvals": { "total": 0, "passed": 0, "failed": 0 }, "curator": {} },
  "integrity": {
    "effectUnknown": 0, "leaseLost": 0,
    "checkpointWriteFailures": 0, "eventSeqRetries": 0, "eventSeqCollisions": 0,
    "toolBatchOrderingViolations": 0,
    "skillEnabledWithoutEval": 0,
    "hardlineBlocked": 0
  },
  "slos": {
    "objectives": [ { "name": "...", "measured": true, "healthy": true, "...": "..." } ],
    "violations": [],
    "unmeasured": ["goal_completion_rate"],
    "allHealthy": true
  }
}
```

`latency` changes shape (v1 had `samples/p50/p95/p99` directly). Keep those v1
keys as aliases for one release, or have the gate prefer `latency.run`. The
plan's choice: **keep `latency` v1 keys and add `latency.ttft`** — smaller blast
radius, and the dashboard reads `latency.run.p95` only after the v2 migration
slice.

---

## 7. Gate changes

### 7.1 Semantics

Each check resolves to one of four states:

| State | Gate outcome | Use |
|---|---|---|
| `pass` | ok | within budget |
| `fail` | non-zero exit | breach, regression, or required-and-missing |
| `skipped` | ok, listed with reason | capability off, or no samples and `requireSamples:false` |
| `unmeasured` | non-zero exit only when `requireSamples:true` | the honest "we did not measure this" |

Exit codes stay `0/1/2`.

### 7.2 Budget file v2

`docs/harness/slo-budgets.json` gains a `checks` array and keeps `budgets` for
one release:

```json
{
  "version": 2,
  "checks": [
    {"name": "run_p95_latency", "path": "latency.p95", "kind": "percentile",
     "thresholdMs": 120000, "maxRegression": 0.1, "minSamples": 20,
     "requireSamples": true},
    {"name": "ttft_p95", "path": "latency.ttft.p95", "kind": "percentile",
     "thresholdMs": 15000, "maxRegression": 0.2, "minSamples": 50,
     "requireSamples": false, "requires": "modelGateway"},
    {"name": "effect_unknown", "path": "integrity.effectUnknown",
     "kind": "invariant", "max": 0, "requires": "runKernelIntegrity"}
  ]
}
```

Rules:

- A check must declare a `path` that exists in the report schema; the gate
  validates paths against a constant map, not arbitrary reflection.
- `requires` names a key in `report.capabilities`.
- `enforce:false` reports the check but does not fail the gate (one-release
  observation period).
- The five legacy budget keys are converted to checks on load; delete the
  shim one release after v2 is green.

### 7.3 Regression allowance

Keep `maxRegression` for latency/cost. Do **not** apply a regression allowance to
invariants, and do not apply one when `minSamples` is not met.

---

## 8. Probe and conformance

### 8.1 Probe scenarios

`probe.py` is the fixed workload. Extend `_emit_run` with deterministic variants
(no provider, no network):

| Scenario | Emits | Asserts |
|---|---|---|
| attempt/fallback | `model.candidate_plan`, two attempts (`failed`, `completed`), `model.fallback` | attempt count, fallback numerator, per-run attempts |
| TTFT | `model.first_token` with a fixed `ttftMs` | `latency.ttft.p95` computed |
| context | `context.compressed` (summary), `context.compressed` (skeleton failure) | overflow/compression rates |
| tool batch | `tool.batch` with `orderingViolations: 0`, one `tool.guardrail` | ordering invariant present and zero |
| integrity | `effect.unknown`, `run.lease_lost` in **separate runs** | invariants counted; gate fails on them |
| unmeasured | a run set with no goal events | `goal_completion_rate` is `unmeasured`, not healthy |

The probe must keep its promise: every number is computed by shipped code. Do
not hard-code report values in the probe.

### 8.2 New conformance cases

Add eleven cases to `evaluation/conformance/cases.py` **and**
`docs/harness/conformance.json`:

| Case | Invariant |
|---|---|
| `signal.model_attempt` | attempt events carry the contract fields and produce attempt metrics |
| `signal.model_ttft` | `model.first_token` produces a TTFT observation, not a generic event |
| `signal.context_compression` | summary vs skeleton outcomes are distinguished; failure is counted |
| `signal.tool_batch` | a mixed batch preserves order and reports zero violations |
| `signal.integrity_unknown_effect` | an unknown effect increments the invariant and fails the gate |
| `signal.integrity_lease_lost` | a fenced write loss increments the invariant |
| `signal.file_checkpoint` | created/failed/restored are distinguishable; failure rate has samples |
| `signal.goal_verdict` | gate-fail never calls the judge and the verdict is recorded |
| `contract.slo_report_v2` | capabilities, `measured`, `unmeasured`, and integrity sections exist |
| `contract.unmeasured_gate` | an empty report is `unmeasured`; `requireSamples:true` fails, `false` skips |
| `contract.alert_metric_names` | every metric named in the Prometheus rules exists in the shipped exposition |

`contract.alert_metric_names` is the one that keeps alerting honest: parse
`deploy/prometheus/blackeclipse.rules.yml`, extract metric identifiers, compare
with `hub.metrics.names()` after the probe. A renamed metric fails CI instead of
silently disarming an alert.

---

## 9. Alerts and dashboard

### 9.1 Alert rules

Replace the commented templates with real rules (severity and `for` chosen to
avoid paging on a single run):

| Alert | Expression | For | Severity |
|---|---|---|---:|
| `BlackEclipseRunLatencyHigh` | `histogram_quantile(0.95, sum by (le) (rate(eclipse_run_duration_ms_bucket[10m]))) > 120000` | 15m | warning |
| `BlackEclipseTTFTHigh` | `histogram_quantile(0.95, sum by (le) (rate(eclipse_model_ttft_ms_bucket[10m]))) > 15000` | 10m | warning |
| `BlackEclipseFallbackRateHigh` | `sum(rate(eclipse_model_fallbacks_total[10m])) / sum(rate(eclipse_model_attempts_total[10m])) > 0.10` | 15m | warning |
| `BlackEclipseContextOverflow` | `sum(rate(eclipse_context_overflow_total[15m])) > 0.01` | 15m | warning |
| `BlackEclipseUnknownEffect` | `increase(eclipse_effect_unknown_total[5m]) > 0` | 0m | critical |
| `BlackEclipseLeaseLost` | `increase(eclipse_lease_lost_total[5m]) > 0` | 0m | critical |
| `BlackEclipseCheckpointWriteFailed` | `increase(eclipse_checkpoint_write_failures_total[5m]) > 0` | 0m | critical |
| `BlackEclipseFileCheckpointFailing` | `sum(rate(eclipse_file_checkpoint_failures_total[15m])) > 0.05` | 15m | warning |
| `BlackEclipseHardlineBlocked` | `increase(eclipse_hardline_blocked_total[10m]) > 0` | 0m | warning |
| `BlackEclipseGuardrailHaltSpike` | `sum(rate(eclipse_tool_guardrail_total{action="halt"}[15m])) > 0.05` | 15m | warning |
| `BlackEclipseGoalBlockedSpike` | `sum(rate(eclipse_goal_verdicts_total{verdict="blocked"}[1h])) > 0.05` | 30m | warning |

Every alert names an owner in labels and a runbook anchor in annotations
(`docs/DEPLOYMENT.md#monitoring--alerts`). A rule without a route is not an
alert; the plan does not ship a route, it documents what the operator must wire.

### 9.2 Dashboard

- Three card states: `healthy`, `breaching`, `unmeasured`.
- New cards: Model attempts/fallbacks/TTFT, Context pressure/compaction,
  Tool batches/guardrails, Goals, Integrity invariants.
- Show `samples` and `minSamples` on every card; a card with 3 samples says so.
- Keep the page dependency-free and fully escaped.

---

## 10. Slices

W8 is "continuous" in the parent plan, but it must not be a big-bang release.
Slices land alongside the workstream they observe.

| Slice | Scope | Depends on | Effort | Acceptance |
|---|---|---|---:|---|
| **W8.0** Foundation | Eager `register_objectives()`, `measured`/`unmeasured`, report `schema:2` + `capabilities`, `release_report` v2, dashboard third state, document the signal contract | — | 2–3 d | Empty hub report lists every objective as `unmeasured`; v1 report fields still present; dashboard renders muted |
| **W8.1** Model + context signals | Project attempt/TTFT/candidate/retry/fallback + context events; metrics; TTFT, fallback, overflow, compression SLOs; probe scenarios; dashboard cards | W1, W2 (shipped) | 3–4 d | Probe produces non-null TTFT/attempt/compression values; `gate:slo` enforces the four new SLOs against the probe |
| **W8.2** Data-driven gate | `checks` array, path validation, `requires`, `enforce:false`, invariant kind; legacy shim | W8.0 | 2 d | A new check is added by editing only `slo-budgets.json`; malformed path fails exit 2; `enforce:false` reports without failing |
| **W8.3** Integrity invariants | Emit/project `effect.unknown` (existing), and wire W6's lease/checkpoint/event-sequence signals when they land; invariant gate + alerts | W6 for 3 of 4; effect-unknown immediate | 2 d | Unknown effect fails the gate; capability-off reports `skipped` |
| **W8.4** Tool signals | Project `tool.batch_plan` / `tool.batch` / `tool.guardrail`; ordering invariant; concurrency and duration metrics | W3 | 2 d | A mixed batch with a failure keeps order and reports zero violations; injected violation fails the gate |
| **W8.5** Autonomy + learning | Project `goal.*`, `loop.tick`, `skill.execution_eval`, `curator.run`; completion/blocked SLOs; enable-without-eval invariant | W4, W5 | 2–3 d | Gate-first judge suppression is visible; blocked rate has samples; enable-without-eval cannot pass |
| **W8.6** Delegation + file checkpoints | Project `checkpoint.created/failed/restored/pruned` and `delegation.*`; snapshot/restore latency, failure rate, repairs, worktree count | W7 | 1–2 d | Snapshot/restore distinguishable; failure rate has samples; restore count auditable |
| **W8.7** Conformance + alerts | Eleven new cases, manifest entries, real alert rules, `contract.alert_metric_names` | W8.0–W8.6 | 2–3 d | `npm run gate:conformance` includes the cases; `check-all.js` green; rule/metric contract passes |

Total: **16–22 engineer-days**, but only ~6–8 days of new work if each
workstream ships its W8 rows as part of its own definition of done (the intended
model). W8.0 and W8.1 can start immediately.

---

## 11. Files touched

| Area | Files |
|---|---|
| Projection | `observability/integration.py` |
| Metrics/SLO/report | `observability/core.py`, `observability/slo.py` |
| Gate | `observability/gate.py`, `docs/harness/slo-budgets.json`, `docs/harness/slo-baseline.json` |
| Probe | `observability/probe.py` |
| Dashboard | `observability/dashboard.py` |
| Config | `observability/config.py` (new objective thresholds), `config/flags.py` (capabilities) |
| Alerts | `deploy/prometheus/blackeclipse.rules.yml`, `docs/DEPLOYMENT.md` |
| Conformance | `evaluation/conformance/cases.py`, `docs/harness/conformance.json` |
| Emitters (small) | `model_stream.py`, `model_runtime/gateway.py`, `context/compression_ladder.py`, `context_budget.py`, `graph.py`, `run_effects.py` |
| Docs | `docs/harness/observability.md`, `docs/harness/conformance.md`, `docs/harness/roadmap/hermes-inspired-improvement-plan.md`, this file |

No schema change. No new dependency. No second event bus.

---

## 12. Test matrix

| Test file | Covers |
|---|---|
| `test_c7_slo_gate.py` (extend) | path resolution, invariant kind, `requires`, `enforce:false`, `unmeasured`, malformed schema, legacy shim |
| `test_observability_ttft.py` (new) | first-token projection, provider fill, timeout classification, no double count |
| `test_observability_attempts.py` (new) | candidate→attempt→fallback chain, outcome labels, per-run attempts, cost sum |
| `test_observability_context.py` (new) | usage ratio, prune/summary/skeleton outcomes, failure classification, overflow |
| `test_observability_integrity.py` (new) | unknown effect, lease lost, checkpoint failure, sequence collision, capability-off skip |
| `test_c7_dashboard_api.py` (extend) | three card states, escaping, samples/minSamples |
| `test_c8_signals.py` (new) | the ten conformance cases via the runner |
| `test_observability_perf.py` (extend) | overhead still bounded after new mappings (median of five warmed runs) |

Performance budget: new projection work stays under the existing span-overhead
test's bound; if it does not, the mapping is moved behind sampling, not the test.

---

## 13. Rollout and rollback

1. **W8.0 + W8.1** land together behind no runtime flag — they only observe.
   Rollback: revert the projection commit; runs are unaffected.
2. **New gate checks** start `enforce:false` for one release; the report and
   dashboard show them, CI does not fail. Promote to `enforce:true` after a
   green baseline (`npm run probe:slo` + `npm run eval:live`).
3. **Invariants** start as alerts at `warning`; after one week with zero
   occurrences, `critical`. They never get a budget.
4. **Metric-label switch** (`ECLIPSE_METRIC_LABEL_MODELS`) defaults on only
   outside production; turning it off loses per-model dashboards, not SLOs.
5. **Removing the legacy budget shim** is a separate cleanup PR after two green
   weeks; it is not part of W8.

Rollback note for every slice: telemetry-only changes revert cleanly; the gate
change is data-driven, so reverting `slo-budgets.json` is sufficient to unblock a
release.

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| New projection throws and breaks the bus | `RunEventProjector.handle` already swallows; add a `projection.failed` drop counter and a test |
| Cardinality explosion from model/tool labels | Closed label sets; model labels behind a switch; no args, ids or paths |
| Unmeasured silently becomes healthy | Gate `requireSamples`; dashboard third state; conformance `contract.unmeasured_gate` |
| Low-sample SLO pages someone | `minSamples`; `for:` windows; warning before critical |
| Gate fails when a capability is off | `requires` → `skipped` with reason |
| Alert rule names drift from metrics | `contract.alert_metric_names` parses the rules file against the live exposition |
| Probe lies (hard-coded values) | Probe must emit only events; assertions read the report |
| Telemetry cost on every run | Existing sampling/export bounds; projection is O(1) map updates; perf test |

---

## 15. Exit criteria

W8 is complete when all of the following are true:

1. `GET /observability/release-report` (and `run_probe()`) return `schema: 2`
   with a populated `capabilities` block.
2. Every objective in §5 appears in the report even with zero samples, and
   `unmeasured` is distinguishable from `healthy` and `breaching`.
3. `npm run gate:slo` can add a new objective by editing only
   `docs/harness/slo-budgets.json`.
4. The W1 and W2 signals are non-null in the probe: TTFT p95, attempts per run,
   fallback success rate, context overflow rate, compression failure rate.
5. The integrity invariants (unknown effect, lease lost, checkpoint failure,
   sequence collision) are zero on a clean probe and fail the gate with an
   injected occurrence.
6. `npm run gate:conformance` runs the eleven new cases and the alert/metric
   contract.
7. `deploy/prometheus/blackeclipse.rules.yml` has real runtime rules (no
   commented placeholders) and `check-all.js` is green.
8. `docs/harness/observability.md`, `docs/harness/conformance.md`,
   `docs/DEPLOYMENT.md` and the parent plan point at the shipped behaviour.

Until 1–8 hold, W8 is a dashboard, not a contract.

---
title: Observability Platform
status: Current
last-verified: 2026-11-11
---

# Observability Platform

**Who this is for:** anyone asking "what was the agent doing, why, how long, how
much did it cost, and what failed?" — and anyone adding a subsystem that should
appear in the trace.

The Observability Platform is a **cross-cutting, vendor-neutral telemetry layer**
for the Python agent runtime. It answers the full investigation questions —
model, tools, inputs/outputs (per policy), latency, tokens, cost, failures,
retries, coverage, cost, recovery, and the complete execution trajectory — and
reconstructs a run from a single trace. It is implemented in
`python/harness/observability/` and is **fail-open**: a telemetry backend outage
can never break a run.

It is **not** a second runtime. It observes the existing event stream. The `service.bus`
is Eclipse's universal publication point (agent runs, model routing, tool calls,
fabric jobs, plugins, A2A, research, memory, canonical events); one subscriber
projects it into spans, metrics and typed hook events.

**C7 makes it bite.** Every run exports a `run → step → tool/LLM` tree; every
failure carries one class from a closed taxonomy; run/step cost is attributed;
process USE is sampled; five SLOs (terminal correctness, p95 latency, resume p95,
orphan rate, cost per task) have error budgets; `npm run gate:slo` fails CI on a
budget breach or a committed regression; and `/observability/dashboard` renders
one card per SLO.

**W8 makes it a contract.** Every workstream seam (model attempts/TTFT, context
pressure/compression, tool batches/guardrails, goals, skill evaluation, run-kernel
integrity, file checkpoints, delegation) now has a projection, a metric, a
report field and either an SLO or a zero-tolerance invariant. Objectives are
registered eagerly, so an objective with no samples reports `measured:false`
and `healthy:null` — it is never silently absent and never green. The release
report is schema v2 (additive) and carries `capabilities`; the gate resolves a
declarative budgets file and marks a check `skipped` when its capability is off.

## The one rule

> Telemetry must never become a single point of failure. Every backend call is
> non-blocking, bounded, retried and circuit-broken; a sink failure drops
> telemetry and is counted, never propagated.

## Architecture

```
           ECLIPSE RUNTIME  (graph, model_runtime, tools, fabric, plugins, a2a, …)
                         │
                  service.bus  (universal event stream)   model_runtime observer
                         └──────────────┬──────────────────────────┘
                                        ▼
                             RunEventProjector  →  ObservabilityHub
                                                       │
      ┌────────────┬──────────────┬─────────────┬───────┴───────┬──────────────┐
   ObserverHub  MetricsRegistry  Tracer/Span    CostEngine   Anomaly/Loop   SLORegistry
      │             │            │               │            │              │
      └─────────────┴─────── redactor ─── sampling ─── health ─┴──────────────┘
                                        │
                                BoundedExporter (non-blocking, bounded, retried, circuit-broken)
                                        │
        ┌──────────────┬────────────────┼───────────────┬───────────────┐
     InMemory        JSONL           OTLP/HTTP        Langfuse        Sentry
     (diagnostics)   (local)         (traces/logs/metrics)  (LLM)      (errors)
                                        │
                                  Grafana / Tempo / Loki / Prometheus  (external)
```

The core uses the **standard library only**. Optional vendor backends (OTLP,
Langfuse, Sentry) are adapters over the same `Exporter` protocol and are disabled
unless configured. OpenTelemetry is the instrumentation convention (W3C
`traceparent`-shaped ids, inject/extract); Langfuse is an LLM backend; Sentry is
error tracking; Prometheus is a scrape endpoint.

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | One env-resolved `ObservabilityConfig`; never raises |
| `context.py` | Immutable `ObservationContext` + `contextvars` propagation + W3C carrier |
| `events.py` | Closed `HOOKS` vocabulary + typed `HookEvent` |
| `observers.py` | Backend-neutral `Observer`/`ObserverHub` (fail-open, quarantine) |
| `tracing.py` | `Tracer`/`Span`/`SpanStore` + `trajectory()` |
| `metrics.py` | Counters/gauges/histograms + Prometheus exposition + RED/USE helpers |
| `costs.py` | `CostEngine` + `PricingRegistry` (data, not code) |
| `redaction.py` | The ONE redaction engine (keys + value patterns + optional PII) |
| `sampling.py` | Head + tail sampling; **always keeps errors/security/anomalies** |
| `health.py` | Subsystem + telemetry health registry (worst-state rollup) |
| `anomaly.py` | `LoopDetector` + statistical `AnomalyDetector` |
| `slo.py` | Objectives (ratio / percentile / rate), error budget, burn rate |
| `failures.py` | Closed failure taxonomy + code/exception mapping |
| `usage.py` | Process CPU / memory / thread USE sampling (stdlib only) |
| `dashboard.py` | Server-rendered SLO dashboard (escaped, read-only) |
| `gate.py` | Release-gate math over a report + budgets + baseline |
| `probe.py` | Deterministic telemetry workload for the release gate |
| `logging_setup.py` | Structured JSON logging with context + redaction |
| `exporters.py` | `Exporter` protocol + `BoundedExporter` + vendor/local sinks |
| `core.py` | `ObservabilityHub` — ingestion, metrics, cost, exports, diagnostics |
| `integration.py` | Bus projection, model observer bridge, service/boot wiring |
| `routers/observability.py` | `/observability/*` operator-gated HTTP surface |

## Where telemetry comes from

1. **Bus projection** (`RunEventProjector`) — the primary source. It maps:
   - `run.created|started|resumed` → root `eclipse.run` span + `onRunStart`
   - `step.started|completed` → `eclipse.step` span + `onStepStart`/`onStepEnd`;
     LLM and tool spans are **parented to the step**, not the run
   - `model.requested` → `eclipse.llm` span; `model.request.*` → provider/model/latency; `model.completed` → tokens + `onLLMEnd`/`onLLMError`
   - `tool.requested` → `eclipse.tool.<name>` span; `tool.completed|failed|truncated` → status/duration + `onToolEnd`/`onToolError`
   - `job.*` → `eclipse.job` span + `onJobStart`/`onJobEnd`/`onJobRetry`/`onJobFailure`
   - `plugin.*` → `eclipse.plugin` span + `onPluginStart`/`onPluginEnd`/`onPluginError`
   - `agent.spawned`/`delegation.*` → `onA2AMessageSent`
   - `schedule.*`/`automation.*`/`workflow.*` → `onEventPublished`
   - `run.replanned`/`context.retry`/`context.recovered` → `onRecoveryStart`; `context.pruned`/`context.compressed`/`prompt.cache` → `onEventPublished`
   - `research.*`, `memory.*`, `skill.*` → the matching hooks
   - **W8, model**: `model.candidate_plan`/`model.retry` → recorded event;
     `model.attempt.completed|failed` → `onModelAttempt`; `model.first_token`
     → `onModelFirstToken`; `model.first_token_timeout` → a timeout signal;
     `model.fallback` → `onModelFallback`
   - **W8, context**: `memory.history_bounded` → `onContextPressure` (usage
     ratio + gate); `context.compressed` → `onContextCompaction`;
     `CONTEXT_OVERFLOW`/`CONTEXT_EXHAUSTED` run failures → an overflow signal
   - **W8, tools**: `tool.batch_plan`/`tool.batch` → `onToolBatch`;
     `tool.guardrail` → `onToolGuardrail`
   - **W8, autonomy/learning**: `goal.created` → `onGoalCreated`;
     `goal.verdict` → `onGoalVerdict`; `skill.evaluation_completed` →
     `onSkillEvaluation`; `skill.curator_run` → `onCuratorRun`
   - **W8, integrity**: `effect.unknown`, `run.lease_lost`,
     `checkpoint.write`, `event.seq_retry|collision`,
     `security.hardline.blocked` → `onIntegrityEvent`
   - **W8, files/delegation**: `checkpoint.created|failed|restored|pruned` →
     `onFileCheckpoint`; `delegation.*` → `onDelegation`
   - any `*.failed` and `run.failed` → `onError` + error sink
   A subsystem that owns no `RunEmitter` (skill evaluation, curator, the
   shadow-git checkpoint store) publishes through
   `observability/bridge.py::publish`, which hands the event to the SAME
   projector. It is not a second bus.
2. **Model observer bridge** (`ModelObserverBridge`) — the `model_runtime`'s single
   observer is chained so both the hub and the legacy bus forwarding receive it.
3. **Explicit API** — any subsystem may call `get_hub().emit(hook, **fields)` or
   `get_hub().span(name, kind=..., attributes=...)` and get correlation + export
   for free. `install_observability(service)` is idempotent.

## Correlation context

`ObservationContext` carries `trace_id`, `span_id`, `parent_span_id` plus
`session_id`, `request_id`, `run_id`, `agent_id`, `task_id`, `workflow_id`,
`job_id`, `worker_id`, `plugin_id`, `event_id`, `message_id`. It rides a
`contextvars` var so nested async code sees it without parameter plumbing.

`inject(ctx, carrier)` / `extract(carrier)` move it across a process boundary as a
W3C `traceparent` plus `eclipse*` keys — used for queue jobs, A2A envelopes,
subprocesses and HTTP hops. The same trace survives
API → Agent → Task → Queue → Worker → Tool → LLM → Recovery → response, and
Agent A → A2A → Agent B → back.

## Metrics

RED (Rate/Errors/Duration) and USE (Utilization/Saturation/Errors) helpers, plus
the families the platform records: `eclipse_runs_total`, `eclipse_run_duration_ms`,
`eclipse_active_runs`, `eclipse_llm_requests_total`, `eclipse_llm_tokens_total`,
`eclipse_llm_cost_usd_total`, `eclipse_llm_duration_ms`, `eclipse_llm_fallbacks_total`,
`eclipse_tool_calls_total`, `eclipse_tool_duration_ms`, `eclipse_tool_timeouts_total`,
`eclipse_jobs_total`, `eclipse_job_duration_ms`, `eclipse_job_retries_total`,
`eclipse_queue_depth`, `eclipse_events_total`, `eclipse_plugin_operations_total`,
`eclipse_a2a_messages_total`, `eclipse_memory_operations_total`,
`eclipse_research_total`, `eclipse_evidence_total`, `eclipse_recovery_total`,
`eclipse_security_events_total`, `eclipse_response_blocks_total`,
`eclipse_telemetry_dropped_total`.

W8 adds: `eclipse_model_attempts_total{provider,outcome}`,
`eclipse_model_attempt_duration_ms{provider}`, `eclipse_model_fallbacks_total`,
`eclipse_model_ttft_ms{provider}`, `eclipse_model_ttft_timeouts_total`,
`eclipse_context_usage_ratio`, `eclipse_context_overflow_total{recovered}`,
`eclipse_context_compactions_total{stage,outcome}`, `eclipse_tool_batches_total`,
`eclipse_tool_batch_plans_total`, `eclipse_tool_batch_size`,
`eclipse_tool_batch_ordering_violations_total`,
`eclipse_tool_guardrail_total{rule,action}`, `eclipse_goals_total`,
`eclipse_goal_verdicts_total{verdict}`, `eclipse_skill_exec_eval_total{outcome}`,
`eclipse_curator_runs_total{mode,outcome}`, `eclipse_effect_unknown_total{tool}`,
`eclipse_lease_lost_total`, `eclipse_checkpoint_write_ms`,
`eclipse_checkpoint_write_failures_total{kind}`,
`eclipse_event_seq_retries_total`, `eclipse_event_seq_collisions_total`,
`eclipse_hardline_blocked_total{pattern}`, `eclipse_file_checkpoint_total{event}`,
`eclipse_file_checkpoint_failures_total{reason}`,
`eclipse_file_checkpoint_bytes`, `eclipse_delegations_total{event}`,
`eclipse_delegation_worktrees_total`.

C7 adds: `eclipse_steps_total{step,status}`, `eclipse_step_duration_ms`,
`eclipse_step_cost_usd`, `eclipse_run_cost_usd`, `eclipse_run_cost_usd_total`,
`eclipse_run_resume_ms`, `eclipse_failures_total{failureClass,component}`,
`eclipse_orphaned_runs_total`, `eclipse_process_cpu_percent`,
`eclipse_process_memory_bytes`, `eclipse_process_threads`,
`eclipse_runs_active_sampled`, `eclipse_worker_utilization`.

Scrape the Prometheus text exposition at `GET /observability/metrics/prometheus`
(the handler samples USE gauges first).

The `onResponseBlocks` hook (Interactive-Response Engine, Phase 4) records
`eclipse_response_blocks_total{outcome,type}` — how many structured-answer blocks
had to be **repaired** or **degraded** by the render chokepoint, by block type. It
is emitted once per run at the answer seam from the bridge `response_contract`
op `"finalize"` (the exact client path), so the drift rate is measurable and a
recurring `type` is the signal to add a normalization/repair rule.

## Costs

`CostEngine` is the canonical usage→money conversion. Pricing is data: built-in
defaults for the common catalog, overridable per deployment via
`ECLIPSE_PRICING_FILE` or `PricingRegistry.register`. An unknown model yields an
honest `priced: false` (never a fabricated zero). Aggregates are kept by run,
session, agent, task, workflow, model, provider, day and month.

C7 also records cost **per run** on `onRunEnd` (histogram + counter, when every
request was priced) and **per step** from the step's LLM events. The release
report exposes `cost.perTaskP50/P95`, `totalUsd` and `unpricedRuns`.

## Failure taxonomy

`failures.py` maps every code/exception to exactly one of: `provider`,
`timeout`, `transient`, `validation`, `tool`, `budget`, `policy`, `sandbox`,
`persistence`, `cancel`, `internal`. Spans carry `failureClass`; errors and the
`eclipse_failures_total` counter are labelled with it. Unknown codes become
`internal` deliberately (visible, extendable) rather than an unbounded label.

## SLOs v2 and the release gate

`SLORegistry` supports three kinds: `ratio` (success), `percentile` (p95 must be
≤ threshold) and `rate` (failure ratio ≤ max). Objectives are registered eagerly
at hub construction and survive every event (`ensure`), so counts are not reset
by the next event. An objective with no samples reports `measured:false`,
`healthy:null` and is listed in `slos.unmeasured`; it is neither healthy nor
breaching.

The objectives are `agent_success_rate`, `tool_success_rate`,
`terminal_correctness`, `run_p95_latency`, `resume_p95`, `cost_per_task`,
`orphan_rate`, `ttft_p95`, `model_fallback_success_rate`,
`context_overflow_rate`, `compression_failure_rate`, `resume_success_rate`,
`goal_completion_rate`, `goal_blocked_rate` and
`file_checkpoint_failure_rate`. `terminal_correctness` and `orphan_rate` are
recomputed for the report from `runs.created`/`runs.terminal`/`runs.orphaned`,
so a dashboard cannot show green while those disagree.

**Invariants are separate from SLOs.** Any occurrence of an unknown effect, a
lost lease, a checkpoint write failure, an unresolved event-sequence collision,
a tool-batch ordering violation or a skill enabled without a behavioural
evaluation is a defect with a zero budget. They are counters in
`report.integrity`, the gate fails on any non-zero value, and the alert is
immediate rather than burn-rate based.

Budgets are data in `docs/harness/slo-budgets.json` (version 2): each check
declares `path`, `kind`, `samplesPath`, `minSamples`, `requires`,
`requireSamples`, `maxRegression` and `enforce`. `requires` turns a check into
`skipped` when its capability is off; `enforce:false` reports `observed`
without failing; a required check with too few samples fails as `unmeasured`.
The gate validates every path against a known list, so a typo is exit 2 rather
than a silent pass. The committed baseline is `docs/harness/slo-baseline.json`.

`npm run gate:slo` runs the deterministic probe (`observability/probe.py`)
through the shipped event projector — the probe emits every W8 signal and
advertises all capabilities for the synthetic report — writes
`docs/harness/slo-report.json`, and fails on a budget breach or a regression
beyond the configured allowance. `npm run probe:slo` only writes the report.
CI and `check-all.js` run the gate.

## Dashboard

`GET /observability/dashboard` is an operator-gated, self-contained HTML page:
one card per SLO with three states — `healthy`, `breaching`, `unmeasured` — plus
runs, latency, cost, tools, model attempts/fallbacks/TTFT, context pressure,
integrity invariants and failures by class. It refreshes every 15 s and escapes
every value; it adds no front-end dependency.

`GET /observability/release-report` returns schema v2: `capabilities`,
`runs`, `latency` (with `ttft`), `resume` (with `successRate`), `cost`,
`model`, `context`, `tools` (with `batches`/`guardrails`), `goals`, `learning`,
`integrity`, `fileCheckpoints`, `delegation`, `failures` and `slos` (with
`measured`, `unmeasured`). Every v1 key is preserved.

## Failure investigation & trajectory

`GET /observability/traces/{trace_id}/trajectory` returns the parent/child tree
plus a time-ordered timeline. `GET /observability/errors` returns correlated error
records (exception, trace/span, run/task/agent, tool, provider, model,
environment, release). `GET /observability/anomalies` exposes loop and anomaly
state. `GET /observability/slos` reports objectives, error budget and burn rate.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ECLIPSE_OBSERVABILITY_ENABLED` | `true` | Master switch |
| `ECLIPSE_OBSERVABILITY_SERVICE_NAME` | `eclipse-harness` | Resource service name |
| `ECLIPSE_ENVIRONMENT` | `development` | Deployment environment |
| `ECLIPSE_RELEASE` | `` | Release identifier |
| `ECLIPSE_LOG_LEVEL` | `INFO` | TRACE…FATAL |
| `ECLIPSE_LOG_JSON` | `true` | Structured JSON logging on boot |
| `ECLIPSE_TRACE_SAMPLE_RATE` | `1.0` | Head sample ratio (0–1) |
| `ECLIPSE_CAPTURE_MODE` | `SUMMARY` | `OFF`/`METADATA_ONLY`/`SUMMARY`/`FULL` |
| `ECLIPSE_REDACTION_ENABLED` | `true` | Redact secrets before export |
| `ECLIPSE_REDACT_PII` | `false` | Also redact email/phone/card |
| `ECLIPSE_TELEMETRY_TIMEOUT` | `2.0` | Per-export timeout (seconds) |
| `ECLIPSE_TELEMETRY_QUEUE_SIZE` | `2048` | Bounded exporter queue |
| `ECLIPSE_TELEMETRY_BATCH_SIZE` | `64` | Flush batch size |
| `ECLIPSE_TELEMETRY_BATCH_INTERVAL` | `1.0` | Flush interval (s) |
| `ECLIPSE_TELEMETRY_RETRIES` | `2` | Retries per batch |
| `ECLIPSE_TELEMETRY_RETENTION_SPANS` | `5000` | In-process span cap |
| `ECLIPSE_TELEMETRY_RETENTION_TRACES` | `500` | In-process trace cap |
| `ECLIPSE_TELEMETRY_JSONL_DIR` | `` | Local JSONL sink directory |
| `ECLIPSE_TELEMETRY_CONSOLE` | `false` | Console sink |
| `ECLIPSE_PROMETHEUS_ENABLED` | `true` | Enable Prometheus endpoint |
| `ECLIPSE_OTEL_ENABLED` / `_ENDPOINT` / `_HEADERS` | off | OTLP/HTTP sink |
| `ECLIPSE_LANGFUSE_ENABLED` / `_HOST` / `_PUBLIC_KEY` / `_SECRET_KEY` | off | Langfuse sink |
| `ECLIPSE_SENTRY_ENABLED` / `_DSN` | off | Sentry sink |
| `ECLIPSE_PRICING_FILE` | `` | JSON pricing overrides |
| `ECLIPSE_SLO_AGENT_SUCCESS_RATE` | `0.99` | Agent success SLO |
| `ECLIPSE_SLO_TOOL_SUCCESS_RATE` | `0.98` | Tool success SLO |
| `ECLIPSE_SLO_TERMINAL_TARGET` | `0.999` | Terminal-correctness SLO |
| `ECLIPSE_SLO_RUN_P95_MS` | `120000` | Run p95 latency budget |
| `ECLIPSE_SLO_RESUME_P95_MS` | `10000` | Resume p95 budget |
| `ECLIPSE_SLO_COST_PER_TASK_USD` | `1.0` | Cost per task budget |
| `ECLIPSE_SLO_ORPHAN_RATE` | `0.0` | Max orphan ratio |
| `ECLIPSE_SLO_TTFT_P95_MS` | `15000` | Time-to-first-token p95 budget |
| `ECLIPSE_SLO_FALLBACK_SUCCESS` | `0.90` | Fallback success-rate target |
| `ECLIPSE_SLO_CONTEXT_OVERFLOW_RATE` | `0.01` | Max context-overflow ratio |
| `ECLIPSE_SLO_COMPRESSION_FAILURE_RATE` | `0.05` | Max compression-failure ratio |
| `ECLIPSE_SLO_RESUME_SUCCESS` | `0.99` | Resumed-run success target |
| `ECLIPSE_SLO_GOAL_COMPLETION` | `0.80` | Goal completion target |
| `ECLIPSE_SLO_GOAL_BLOCKED_RATE` | `0.15` | Max blocked-goal ratio |
| `ECLIPSE_SLO_FILE_CHECKPOINT_FAILURE` | `0.05` | Max file-checkpoint failure ratio |
| `ECLIPSE_ORPHAN_AFTER_S` | `1800` | Age before a run is orphaned |
| `HARNESS_MAX_CONCURRENCY` | `4` | USE utilization denominator |

An enabled backend missing its credentials is downgraded to disabled and
reported in `problems`; `status` never claims a healthy backend that is inert.

## HTTP surface (`/observability/*`, operator-gated)

`status`, `diagnostics`, `config`, `health`, `metrics`, `metrics/prometheus`,
`traces`, `traces/{id}`, `traces/{id}/trajectory`, `errors`, `costs`,
`costs/runs/{id}`, `anomalies`, `slos`, `exporters/reset`.

`diagnostics` is the self-diagnostic surface: exporter health, dropped spans,
dropped records, backpressure, observed hooks, anomaly/loop state, SLOs, cost.
C7 adds `release-report` (the gate input) and `dashboard` (HTML).

## Tests

`python/tests/test_observability_{core,integration,failure,security,trace,perf,api,e2e}.py`
cover context propagation, span relationships, observer fail-open/quarantine,
redaction, sampling, cost/token math, metrics/Prometheus, anomaly/loop, SLO, the
event-bus projection, failure modes (dead/flaky/slow exporters, circuit breaker),
secret leakage, cross-worker/queue/A2A trace integrity, overhead bounds, and the
`/observability/*` HTTP surface.

C7 adds `test_c7_{spans,slo_gate,dashboard_api,usage}.py`: step-tree parentage,
failure classes, run/step cost, SLO ratio/percentile/rate, probe invariants,
gate pass/breach/regression/malformed, dashboard escaping and USE/orphan sweeps.

W8 adds `test_w8_observability.py`: eager registration, `unmeasured` semantics,
counter preservation across events, run-derived terminal/orphan overrides,
model/context/integrity projection, probe coverage, the declarative gate
(pass/breach/invariant/skip/observed/unknown path), the alert-metric contract
and the dashboard's unmeasured state.

## Adding a subsystem to the trace

Publish on `service.bus` with the existing event shape — the projector handles the
common types. For a chain that is not event-driven, call
`get_hub().span(name, kind=..., attributes=...)` and `get_hub().emit(hook, ...)`;
correlation is automatic. Never add a second logging/metrics/tracing stack.

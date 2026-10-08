---
title: Observability Platform
status: Current
last-verified: 2026-10-08
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
| `slo.py` | Objectives, error budget, burn rate |
| `logging_setup.py` | Structured JSON logging with context + redaction |
| `exporters.py` | `Exporter` protocol + `BoundedExporter` + vendor/local sinks |
| `core.py` | `ObservabilityHub` — ingestion, metrics, cost, exports, diagnostics |
| `integration.py` | Bus projection, model observer bridge, service/boot wiring |
| `routers/observability.py` | `/observability/*` operator-gated HTTP surface |

## Where telemetry comes from

1. **Bus projection** (`RunEventProjector`) — the primary source. It maps:
   - `run.created|started|resumed` → root `eclipse.run` span + `onRunStart`
   - `model.requested` → `eclipse.llm` span; `model.request.*` → provider/model/latency; `model.completed` → tokens + `onLLMEnd`/`onLLMError`
   - `tool.requested` → `eclipse.tool.<name>` span; `tool.completed|failed|truncated` → status/duration + `onToolEnd`/`onToolError`
   - `job.*` → `eclipse.job` span + `onJobStart`/`onJobEnd`/`onJobRetry`/`onJobFailure`
   - `plugin.*` → `eclipse.plugin` span + `onPluginStart`/`onPluginEnd`/`onPluginError`
   - `agent.spawned`/`delegation.*` → `onA2AMessageSent`
   - `schedule.*`/`automation.*`/`workflow.*` → `onEventPublished`
   - `run.replanned`/`context.retry` → `onRecoveryStart`
   - `research.*`, `memory.*`, `skill.*` → the matching hooks
   - any `*.failed` and `run.failed` → `onError` + error sink
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
`eclipse_security_events_total`, `eclipse_telemetry_dropped_total`.

Scrape the Prometheus text exposition at `GET /observability/metrics/prometheus`.

## Costs

`CostEngine` is the canonical usage→money conversion. Pricing is data: built-in
defaults for the common catalog, overridable per deployment via
`ECLIPSE_PRICING_FILE` or `PricingRegistry.register`. An unknown model yields an
honest `priced: false` (never a fabricated zero). Aggregates are kept by run,
session, agent, task, workflow, model, provider, day and month.

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

An enabled backend missing its credentials is downgraded to disabled and
reported in `problems`; `status` never claims a healthy backend that is inert.

## HTTP surface (`/observability/*`, operator-gated)

`status`, `diagnostics`, `config`, `health`, `metrics`, `metrics/prometheus`,
`traces`, `traces/{id}`, `traces/{id}/trajectory`, `errors`, `costs`,
`costs/runs/{id}`, `anomalies`, `slos`, `exporters/reset`.

`diagnostics` is the self-diagnostic surface: exporter health, dropped spans,
dropped records, backpressure, observed hooks, anomaly/loop state, SLOs, cost.

## Tests

`python/tests/test_observability_{core,integration,failure,security,trace,perf,api,e2e}.py`
cover context propagation, span relationships, observer fail-open/quarantine,
redaction, sampling, cost/token math, metrics/Prometheus, anomaly/loop, SLO, the
event-bus projection, failure modes (dead/flaky/slow exporters, circuit breaker),
secret leakage, cross-worker/queue/A2A trace integrity, overhead bounds, and the
`/observability/*` HTTP surface.

## Adding a subsystem to the trace

Publish on `service.bus` with the existing event shape — the projector handles the
common types. For a chain that is not event-driven, call
`get_hub().span(name, kind=..., attributes=...)` and `get_hub().emit(hook, ...)`;
correlation is automatic. Never add a second logging/metrics/tracing stack.

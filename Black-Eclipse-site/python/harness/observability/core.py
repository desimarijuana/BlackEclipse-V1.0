"""ObservabilityHub — the process-wide observability platform.

One hub owns every observability concern and is the single ingestion point for
`HookEvent`s. It is deliberately fail-open: every path that could touch a backend
catches its own errors, so telemetry can never break a run.

    HookEvent ──► hub.observe ──┬─► ObserverHub   (typed subscribers)
                                ├─► MetricsRegistry (counters/gauges/histograms)
                                ├─► CostEngine    (tokens → money)
                                ├─► AnomalyDetector / LoopDetector
                                ├─► SLORegistry
                                ├─► structured logs / error sink
                                └─► BoundedExporter(s)  (non-blocking sinks)

The hub also owns the `Tracer`/`SpanStore`, so `hub.span(...)` produces real spans
with parent/child relationships while `observe(...)` derives metrics, cost and
health. `status()` and `diagnostics()` report the observability system's own
health, including dropped-record counters and exporter backpressure.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

from .anomaly import AnomalyDetector, LoopDetector
from .config import ObservabilityConfig, load_config
from .context import ObservationContext, current_context, get_or_create_context, inject
from .costs import CostEngine
from .events import HookEvent, make_event
from .failures import classify_failure
from .usage import process_usage
from .exporters import (
    BoundedExporter,
    ConsoleExporter,
    Exporter,
    InMemoryExporter,
    JsonlFileExporter,
    LangfuseExporter,
    OtlpHttpExporter,
    SentryExporter,
)
from .health import DEGRADED, HEALTHY, UNKNOWN, UNHEALTHY, HealthRegistry
from .metrics import MetricsRegistry
from .observers import Observer, ObserverHub
from .redaction import Redactor, set_default_redactor
from .sampling import Sampler
from .slo import SLORegistry
from .tracing import Span, SpanStore, STATUS_ERROR, STATUS_OK, Tracer

log = logging.getLogger("harness.observability")


class ObservabilityHub:
    def __init__(
        self,
        config: Optional[ObservabilityConfig] = None,
        *,
        observers: Optional[list[Any]] = None,
        exporters: Optional[list[Exporter]] = None,
        capture_inmemory: bool = True,
        start_exporters: bool = True,
    ) -> None:
        self.config = config or load_config()
        self.redactor = Redactor(enabled=self.config.redaction_enabled, redact_pii=self.config.redact_pii)
        set_default_redactor(self.redactor)
        self.sampler = Sampler(rate=self.config.trace_sample_rate, always_sample_errors=self.config.always_sample_errors)
        self.metrics = MetricsRegistry()
        self.observers = ObserverHub()
        self.costs = CostEngine()
        self.health = HealthRegistry()
        self.anomaly = AnomalyDetector()
        self.loops = LoopDetector()
        self.slos = SLORegistry()

        self._lock = threading.RLock()
        self._dropped: dict[str, int] = {}
        self._observed: dict[str, int] = {}
        self._direct: list[Exporter] = []
        self._error_sink: list[dict[str, Any]] = []
        self._max_errors = 500
        # C7 release-readiness aggregates (bounded; process lifetime).
        self._run_ms: deque[float] = deque(maxlen=5000)
        self._resume_ms: deque[float] = deque(maxlen=2000)
        self._run_costs: deque[float] = deque(maxlen=5000)
        self._run_cost_unpriced = 0
        self._created = 0
        self._terminal: dict[str, int] = {"ok": 0, "failed": 0, "cancelled": 0}
        self._orphans = 0
        self._active_since: dict[str, float] = {}
        self._tool_calls = 0
        self._tool_errors = 0
        self._failures: dict[str, int] = {}
        self._step_cost: dict[tuple[str, str], float] = {}
        self._span_store = SpanStore(
            max_spans=self.config.retention_spans, max_traces=self.config.retention_traces
        )
        self.tracer = Tracer(
            store=self._span_store, sampler=self.sampler, on_span=self._on_span, redactor=self.redactor
        )
        self.inmemory = InMemoryExporter() if capture_inmemory else None
        self._exporters: list[BoundedExporter] = []
        for observer in observers or []:
            self.observers.register(observer)
        self._build_exporters(exporters or [], start=start_exporters)
        self._register_self_health()

    # ── exporters ───────────────────────────────────────────────────────────
    def _build_exporters(self, extra: list[Exporter], *, start: bool) -> None:
        sinks: list[Exporter] = list(extra)
        if self.inmemory is not None:
            sinks.append(self.inmemory)
        if self.config.jsonl_dir:
            try:
                sinks.append(JsonlFileExporter(self.config.jsonl_dir))
            except Exception:  # noqa: BLE001 - a bad dir must not break boot
                self._problems_append("jsonl exporter unavailable")
        if self.config.console_export:
            sinks.append(ConsoleExporter())
        if self.config.otel_enabled and self.config.otel_endpoint:
            exporter = OtlpHttpExporter(
                self.config.otel_endpoint, self.config.otel_headers, timeout_s=self.config.telemetry_timeout_s
            )
            exporter.set_service_name(self.config.effective_name)
            sinks.append(exporter)
        if self.config.langfuse_enabled:
            sinks.append(LangfuseExporter(
                self.config.langfuse_host, self.config.langfuse_public_key,
                self.config.langfuse_secret_key, timeout_s=self.config.telemetry_timeout_s,
            ))
        if self.config.sentry_enabled and self.config.sentry_dsn:
            sinks.append(SentryExporter(
                self.config.sentry_dsn, release=self.config.release,
                environment=self.config.environment, timeout_s=self.config.telemetry_timeout_s,
            ))
        for sink in sinks:
            self._register_sink(sink)

    def _register_sink(self, sink: Exporter) -> None:
        """Wrap a sink for non-blocking export; in-memory sinks run inline (no thread)."""
        if isinstance(sink, InMemoryExporter):
            with self._lock:
                self._direct.append(sink)
            return
        wrapped = BoundedExporter(
            sink,
            queue_size=self.config.queue_size,
            batch_size=self.config.batch_size,
            batch_interval_s=self.config.batch_interval_s,
            max_retries=self.config.max_retries,
            circuit_failure_threshold=self.config.circuit_failure_threshold,
            circuit_reset_s=self.config.circuit_reset_s,
        )
        self._exporters.append(wrapped)
        self.health.register(
            f"telemetry.{wrapped.name}",
            (lambda w=wrapped: ((HEALTHY if w.healthy() else DEGRADED),
                                None if w.healthy() else (w.stats.last_error or "circuit open"))),
            kind="telemetry",
        )

    def add_exporter(self, exporter: Exporter) -> Optional[BoundedExporter]:
        self._register_sink(exporter)
        with self._lock:
            return self._exporters[-1] if self._exporters and not isinstance(exporter, InMemoryExporter) else None

    def _problems_append(self, message: str) -> None:
        self.config.problems.append(message)

    # ── registration ────────────────────────────────────────────────────────
    def register_observer(self, observer: Observer | Callable[[HookEvent], None], *, name: Optional[str] = None) -> Callable[[], None]:
        return self.observers.register(observer, name=name)

    def register_health(self, name: str, checker: Callable[[], tuple[str, Optional[str]]], *, kind: str = "subsystem") -> None:
        self.health.register(name, checker, kind=kind)

    # ── ingestion ───────────────────────────────────────────────────────────
    def observe(self, event: HookEvent) -> None:
        """Ingest one hook event. Never raises."""
        try:
            self._observed[event.hook] = self._observed.get(event.hook, 0) + 1
            self.observers.dispatch(event)
            self._metrics_for(event)
            self._cost_for(event)
            self._anomaly_for(event)
            self._slo_for(event)
            if event.is_error:
                self.sampler.force_keep(event.trace_id)
                self._record_error(event)
            self._export_event(event)
        except Exception:  # noqa: BLE001 - ingestion must never break a run
            log.debug("observability ingestion failed", exc_info=True)

    def emit(self, hook: str, **fields: Any) -> HookEvent:
        event = make_event(hook, **fields)
        self.observe(event)
        return event

    def span(self, name: str, *, kind: str = "internal", attributes: Optional[dict[str, Any]] = None) -> Iterator[Span]:
        return self.tracer.start(name, kind=kind, attributes=attributes)

    def _on_span(self, span: Span) -> None:
        """Tracer sink: export spans and record span-derived metrics."""
        record = span.to_dict(redactor=self.redactor)
        record["kind"] = span.kind
        self._submit("span", record)
        if span.kind == "llm":
            self.metrics.observe_histogram("eclipse_llm_duration_ms", span.duration_ms, help_text="LLM call latency")
        elif span.kind == "tool":
            self.metrics.observe_histogram("eclipse_tool_duration_ms", span.duration_ms, help_text="Tool call latency")

    # ── metrics mapping ─────────────────────────────────────────────────────
    def _metrics_for(self, event: HookEvent) -> None:
        m = self.metrics
        hook = event.hook
        labels = _corr_labels(event)
        if hook == "onRunStart":
            m.inc_gauge("eclipse_active_runs", 1)
            m.inc_counter("eclipse_runs_total", labels={**labels, "status": "started"}, help_text="Total agent runs")
            run_key = event.context.run_id or event.span_id
            self._created += 1
            self._active_since[run_key] = time.time()
        elif hook == "onRunEnd":
            m.inc_gauge("eclipse_active_runs", -1)
            status = {"OK": "completed", "ERROR": "failed", "CANCELLED": "cancelled"}.get(event.status, "completed")
            m.inc_counter("eclipse_runs_total", labels={**labels, "status": status})
            if event.duration_ms:
                m.observe_histogram("eclipse_run_duration_ms", event.duration_ms, help_text="Run duration")
                self._run_ms.append(float(event.duration_ms))
            if (event.attributes or {}).get("resumed") and event.duration_ms:
                self._resume_ms.append(float(event.duration_ms))
                m.observe_histogram("eclipse_run_resume_ms", event.duration_ms, help_text="Resume to continuation")
            key = "ok" if status == "completed" else ("cancelled" if status == "cancelled" else "failed")
            self._terminal[key] += 1
            self._active_since.pop(event.context.run_id or event.span_id, None)
            run_id = event.context.run_id
            if run_id:
                run_cost = self.costs.run_cost(str(run_id))
                if int(run_cost.get("requests") or 0) > 0:
                    if run_cost.get("costKnown"):
                        value = float(run_cost.get("cost") or 0.0)
                        self._run_costs.append(value)
                        m.observe_histogram("eclipse_run_cost_usd", value, help_text="Cost per run (USD)")
                        m.inc_counter("eclipse_run_cost_usd_total", amount=value, help_text="Total run cost (USD)")
                        event.attributes["costUsd"] = round(value, 8)
                        event.attributes["costKnown"] = True
                    else:
                        self._run_cost_unpriced += 1
                        event.attributes["costKnown"] = False
        elif hook in ("onStepStart", "onStepEnd"):
            step = (event.attributes or {}).get("step")
            step_labels = {"step": str(step if step is not None else "unknown")}
            if hook == "onStepStart":
                m.inc_counter("eclipse_steps_total", labels={**step_labels, "status": "started"},
                              help_text="Agent loop steps")
            else:
                status = "ok" if event.status == "OK" else "failed"
                m.inc_counter("eclipse_steps_total", labels={**step_labels, "status": status})
                if event.duration_ms:
                    m.observe_histogram("eclipse_step_duration_ms", event.duration_ms,
                                        help_text="Agent step duration")
                run_id = str(event.context.run_id or "")
                key = (run_id, str(step))
                step_cost = self._step_cost.pop(key, None)
                if step_cost is not None:
                    m.observe_histogram("eclipse_step_cost_usd", step_cost, help_text="Cost per step (USD)")
                    event.attributes["costUsd"] = round(step_cost, 8)
        elif hook == "onError":
            failure_class = classify_failure(
                code=event.error_type or (event.attributes or {}).get("errorCode"),
                error_type=event.error_type,
            )
            component = _failure_component(event)
            self._failures[failure_class] = self._failures.get(failure_class, 0) + 1
            m.inc_counter(
                "eclipse_failures_total",
                labels={"failureClass": failure_class, "component": component},
                help_text="Failures by closed taxonomy class",
            )
        elif hook in ("onLLMEnd", "onLLMError"):
            status = "ok" if hook == "onLLMEnd" else "error"
            m.inc_counter(
                "eclipse_llm_requests_total",
                labels={"provider": event.provider or "unknown", "model": event.model or "unknown", "status": status},
                help_text="LLM requests",
            )
            if event.duration_ms:
                m.observe_histogram("eclipse_llm_duration_ms", event.duration_ms,
                                    labels={"provider": event.provider or "unknown", "model": event.model or "unknown"},
                                    help_text="LLM latency")
            for kind_name, value in (event.tokens or {}).items():
                if value:
                    m.inc_counter(
                        "eclipse_llm_tokens_total", amount=value,
                        labels={"provider": event.provider or "unknown", "model": event.model or "unknown", "type": kind_name},
                        help_text="LLM tokens by type",
                    )
            if event.retries:
                m.inc_counter("eclipse_llm_retries_total", amount=event.retries,
                              labels={"provider": event.provider or "unknown", "model": event.model or "unknown"})
            if (event.attributes or {}).get("fallback"):
                m.inc_counter("eclipse_llm_fallbacks_total", labels={"provider": event.provider or "unknown"})
        elif hook in ("onToolEnd", "onToolError"):
            status = "ok" if hook == "onToolEnd" else "error"
            self._tool_calls += 1
            if hook != "onToolEnd":
                self._tool_errors += 1
            m.inc_counter("eclipse_tool_calls_total", labels={"tool": event.tool_name or event.name or "unknown", "status": status},
                          help_text="Tool calls")
            if event.duration_ms:
                m.observe_histogram("eclipse_tool_duration_ms", event.duration_ms,
                                    labels={"tool": event.tool_name or "unknown"}, help_text="Tool latency")
            if event.error_type == "TIMEOUT" or (event.attributes or {}).get("timeout"):
                m.inc_counter("eclipse_tool_timeouts_total", labels={"tool": event.tool_name or "unknown"})
            if event.retries:
                m.inc_counter("eclipse_tool_retries_total", amount=event.retries, labels={"tool": event.tool_name or "unknown"})
        elif hook == "onJobStart":
            m.inc_counter("eclipse_jobs_total", labels={**labels, "status": "started"})
        elif hook in ("onJobEnd", "onJobFailure", "onJobRetry"):
            status = {"onJobEnd": "succeeded", "onJobFailure": "failed", "onJobRetry": "retrying"}[hook]
            m.inc_counter("eclipse_jobs_total", labels={**labels, "status": status}, help_text="Fabric jobs")
            if event.duration_ms:
                m.observe_histogram("eclipse_job_duration_ms", event.duration_ms, help_text="Job processing latency")
            if hook == "onJobRetry":
                m.inc_counter("eclipse_job_retries_total", labels=labels)
        elif hook == "onQueueEnqueue":
            m.inc_counter("eclipse_events_total", labels={"action": "enqueue"})
            depth = (event.attributes or {}).get("queueDepth")
            if isinstance(depth, (int, float)):
                m.set_gauge("eclipse_queue_depth", float(depth), labels={"queue": (event.attributes or {}).get("queue", "default")})
        elif hook in ("onEventPublished", "onEventConsumed", "onEventProcessed", "onEventFailed"):
            action = hook.replace("onEvent", "").lower()
            m.inc_counter("eclipse_events_total", labels={"action": action}, help_text="Canonical events by action")
        elif hook in ("onPluginEnd", "onPluginError"):
            status = "ok" if hook == "onPluginEnd" else "error"
            m.inc_counter("eclipse_plugin_operations_total",
                          labels={"plugin": event.attributes.get("pluginId", "unknown") if event.attributes else "unknown", "status": status})
        elif hook in ("onA2AMessageSent", "onA2AMessageReceived"):
            direction = "sent" if hook.endswith("Sent") else "received"
            m.inc_counter("eclipse_a2a_messages_total", labels={"direction": direction}, help_text="A2A messages")
        elif hook == "onMemoryRead":
            m.inc_counter("eclipse_memory_operations_total", labels={"op": "read"})
        elif hook == "onMemoryWrite":
            m.inc_counter("eclipse_memory_operations_total", labels={"op": "write"})
        elif hook == "onMemorySearch":
            m.inc_counter("eclipse_memory_operations_total", labels={"op": "search"})
        elif hook in ("onResearchStart", "onResearchEnd"):
            m.inc_counter("eclipse_research_total", labels={"phase": "start" if hook.endswith("Start") else "end"})
        elif hook in ("onEvidenceRetrieved", "onEvidenceValidated"):
            m.inc_counter("eclipse_evidence_total", labels={"phase": "retrieved" if hook.endswith("Retrieved") else "validated"})
        elif hook == "onResponseBlocks":
            # Interactive-response render outcome (Phase 4). `repaired`/`degraded`
            # are the block types that drifted; a recurring label is the signal to
            # add a normalization/repair rule.
            attrs = event.attributes or {}
            for outcome in ("repaired", "degraded"):
                for block_type in attrs.get(outcome) or []:
                    m.inc_counter(
                        "eclipse_response_blocks_total",
                        labels={"outcome": outcome, "type": str(block_type)},
                        help_text="Interactive-response blocks by render outcome",
                    )
        elif hook in ("onRecoveryStart", "onRecoveryEnd"):
            m.inc_counter("eclipse_recovery_total", labels={"phase": "start" if hook.endswith("Start") else "end"})
        elif hook == "onSecurityEvent":
            m.inc_counter("eclipse_security_events_total", labels=labels)

    def _cost_for(self, event: HookEvent) -> None:
        if event.hook not in ("onLLMEnd",):
            return
        tokens = event.tokens or {}
        if not tokens:
            return
        ctx = event.context
        breakdown = self.costs.record(
            provider=event.provider, model=event.model,
            input_tokens=int(tokens.get("input", 0)),
            output_tokens=int(tokens.get("output", 0)),
            cached_tokens=int(tokens.get("cached", 0)),
            reasoning_tokens=int(tokens.get("reasoning", 0)),
            total_tokens=int(tokens.get("total", 0)) or None,
            run_id=ctx.run_id, session_id=ctx.session_id, agent_id=ctx.agent_id,
            task_id=ctx.task_id, workflow_id=ctx.workflow_id,
        )
        if breakdown.priced and breakdown.total_cost is not None:
            self.metrics.inc_counter(
                "eclipse_llm_cost_usd_total", amount=breakdown.total_cost,
                labels={"provider": event.provider or "unknown", "model": event.model or "unknown"},
                help_text="LLM cost in USD",
            )
            event.cost = breakdown.to_dict()
            step = (event.attributes or {}).get("step")
            if step is not None:
                key = (str(ctx.run_id or ""), str(step))
                self._step_cost[key] = self._step_cost.get(key, 0.0) + float(breakdown.total_cost)
                if len(self._step_cost) > 5000:
                    for stale in list(self._step_cost)[:1000]:
                        self._step_cost.pop(stale, None)

    def _anomaly_for(self, event: HookEvent) -> None:
        if event.hook == "onToolEnd" and event.duration_ms is not None:
            verdict = self.anomaly.observe("tool.duration_ms", event.duration_ms, floor=50.0)
            if verdict.detected:
                self._emit_anomaly(event, verdict)
        elif event.hook == "onLLMEnd":
            if event.duration_ms is not None:
                verdict = self.anomaly.observe("llm.duration_ms", event.duration_ms, floor=100.0)
                if verdict.detected:
                    self._emit_anomaly(event, verdict)
            total = int((event.tokens or {}).get("total", 0))
            if total:
                verdict = self.anomaly.observe("llm.total_tokens", total, floor=100.0)
                if verdict.detected:
                    self._emit_anomaly(event, verdict)
        elif event.hook == "onRunEnd" and event.duration_ms is not None:
            verdict = self.anomaly.observe("run.duration_ms", event.duration_ms, floor=1000.0)
            if verdict.detected:
                self._emit_anomaly(event, verdict)
        # Loop detection on repeated identical tool/model operations.
        if event.hook in ("onToolStart", "onLLMStart"):
            signature = (event.attributes or {}).get("signature") or f"{event.hook}:{event.tool_name or event.model}:{event.name}"
            verdict = self.loops.observe(str(signature))
            if verdict.detected:
                self.emit("onLoopDetected", context=event.context,
                          attributes={"signature": verdict.signature, "count": verdict.count, "window": verdict.window})

    def _emit_anomaly(self, event: HookEvent, verdict: Any) -> None:
        self.emit(
            "onAnomaly", context=event.context,
            attributes={
                "metric": verdict.metric, "value": verdict.value, "mean": verdict.mean,
                "stddev": verdict.stddev, "zscore": verdict.zscore, "reason": verdict.reason,
            },
        )

    def _slo_for(self, event: HookEvent) -> None:
        if event.hook == "onRunEnd":
            target = self.config.slo_agent_success_rate
            self.slos.define("agent_success_rate", target, description="Agent runs complete without error")
            result = self.slos.record("agent_success_rate", good=(event.status != "ERROR" and not event.error_type))
            if result and not result["healthy"]:
                self.emit("onSLOViolation", context=event.context, attributes=result)

            # C7: terminal correctness, latency, resume and cost are observable
            # objectives, not prose. The release report computes the exact
            # terminal ratio from created/terminal counts; this runtime view
            # records every run that reached a terminal state.
            self.slos.define(
                "terminal_correctness",
                _env_float("ECLIPSE_SLO_TERMINAL_TARGET", 0.999),
                description="Runs that reach exactly one terminal state",
            )
            self.slos.record("terminal_correctness", good=True)

            self.slos.define(
                "run_p95_latency",
                _env_float("ECLIPSE_SLO_P95_TARGET", 0.95),
                kind="percentile",
                threshold=_env_float("ECLIPSE_SLO_RUN_P95_MS", 120_000.0),
                unit="ms",
                description="Run p95 latency within budget",
            )
            if event.duration_ms:
                latency = self.slos.record_value("run_p95_latency", event.duration_ms)
                if latency and not latency["healthy"]:
                    self.emit("onSLOViolation", context=event.context, attributes=latency)

            if (event.attributes or {}).get("resumed") and event.duration_ms:
                self.slos.define(
                    "resume_p95",
                    _env_float("ECLIPSE_SLO_P95_TARGET", 0.95),
                    kind="percentile",
                    threshold=_env_float("ECLIPSE_SLO_RESUME_P95_MS", 10_000.0),
                    unit="ms",
                    description="Resume to continued run p95",
                )
                self.slos.record_value("resume_p95", event.duration_ms)

            cost = (event.attributes or {}).get("costUsd")
            if cost is not None and (event.attributes or {}).get("costKnown"):
                self.slos.define(
                    "cost_per_task",
                    _env_float("ECLIPSE_SLO_P95_TARGET", 0.95),
                    kind="percentile",
                    threshold=_env_float("ECLIPSE_SLO_COST_PER_TASK_USD", 1.0),
                    unit="usd",
                    description="Cost per completed task within budget",
                )
                self.slos.record_value("cost_per_task", float(cost))

            self.slos.define(
                "orphan_rate", 1.0, kind="rate",
                threshold=_env_float("ECLIPSE_SLO_ORPHAN_RATE", 0.0),
                description="Runs left active without a terminal state",
            )
            self.slos.record("orphan_rate", good=True)
        elif event.hook in ("onToolEnd", "onToolError"):
            target = self.config.slo_tool_success_rate
            self.slos.define("tool_success_rate", target, description="Tool calls succeed")
            self.slos.record("tool_success_rate", good=(event.hook == "onToolEnd"))

    # ── release readiness (C7) ───────────────────────────────────────────────
    def sweep_orphans(self, *, max_age_s: Optional[float] = None) -> int:
        """Count runs still active past the terminal deadline (fail-open)."""
        limit = max_age_s if max_age_s is not None else _env_float("ECLIPSE_ORPHAN_AFTER_S", 1800.0)
        now = time.time()
        with self._lock:
            stale = [run for run, started in self._active_since.items() if now - started >= limit]
            for run in stale:
                self._active_since.pop(run, None)
                self._orphans += 1
        if stale:
            self.slos.define(
                "orphan_rate", 1.0, kind="rate",
                threshold=_env_float("ECLIPSE_SLO_ORPHAN_RATE", 0.0),
                description="Runs left active without a terminal state",
            )
            for _ in stale:
                self.slos.record("orphan_rate", good=False)
            self.metrics.inc_counter(
                "eclipse_orphaned_runs_total", amount=len(stale),
                help_text="Runs still active past the terminal deadline",
            )
            self.emit("onError", error_type="ORPHANED_RUN",
                      error_message=f"{len(stale)} run(s) exceeded the terminal deadline",
                      attributes={"eventType": "run.orphaned", "failureClass": "internal"})
        return len(stale)

    def refresh_use_metrics(self) -> dict[str, Any]:
        """Sample process USE gauges (and sweep orphans) on demand."""
        usage = process_usage()
        if usage.get("available"):
            if usage.get("cpuPercent") is not None:
                self.metrics.set_gauge(
                    "eclipse_process_cpu_percent", float(usage["cpuPercent"]),
                    help_text="Harness process CPU, normalized to the machine",
                )
            if usage.get("memoryBytes") is not None:
                self.metrics.set_gauge(
                    "eclipse_process_memory_bytes", float(usage["memoryBytes"]),
                    help_text="Harness process working set / RSS",
                )
            if usage.get("threads") is not None:
                self.metrics.set_gauge(
                    "eclipse_process_threads", float(usage["threads"]),
                    help_text="Active Python threads",
                )
        active = len(self._active_since)
        limit = max(1.0, _env_float("HARNESS_MAX_CONCURRENCY", 4.0))
        self.metrics.set_gauge("eclipse_runs_active_sampled", float(active),
                               help_text="Runs currently active (sampled)")
        self.metrics.set_gauge("eclipse_worker_utilization", min(1.0, active / limit),
                               help_text="Active runs / configured concurrency")
        self.sweep_orphans()
        return usage

    def release_report(self) -> dict[str, Any]:
        """A machine-readable release-readiness report (C7 gate input)."""
        durations = list(self._run_ms)
        resumes = list(self._resume_ms)
        costs = list(self._run_costs)
        terminal_total = sum(self._terminal.values())
        return {
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "runs": {
                "created": self._created,
                "terminal": terminal_total,
                "completed": self._terminal.get("ok", 0),
                "failed": self._terminal.get("failed", 0),
                "cancelled": self._terminal.get("cancelled", 0),
                "orphaned": self._orphans,
                "active": len(self._active_since),
            },
            "latency": {
                "samples": len(durations),
                "p50": _pct(durations, 0.50),
                "p95": _pct(durations, 0.95),
                "p99": _pct(durations, 0.99),
            },
            "resume": {"samples": len(resumes), "p95": _pct(resumes, 0.95)},
            "cost": {
                "samples": len(costs),
                "totalUsd": round(sum(costs), 8),
                "perTaskP50": _pct(costs, 0.50),
                "perTaskP95": _pct(costs, 0.95),
                "unpricedRuns": self._run_cost_unpriced,
            },
            "tools": {"calls": self._tool_calls, "errors": self._tool_errors},
            "failures": dict(sorted(self._failures.items())),
            "slos": self.slos.report(),
        }

    # ── errors + export ─────────────────────────────────────────────────────
    def _record_error(self, event: HookEvent) -> None:
        record = {
            "eventId": event.context.event_id or event.span_id,
            "timestamp": event.timestamp,
            "message": event.error_message or event.name or event.hook,
            "errorType": event.error_type,
            "stackTrace": event.stack_trace,
            "traceId": event.trace_id,
            "spanId": event.span_id,
            "runId": event.context.run_id,
            "taskId": event.context.task_id,
            "agentId": event.context.agent_id,
            "tool": event.tool_name,
            "provider": event.provider,
            "model": event.model,
            "environment": self.config.environment,
            "release": self.config.release,
            "tags": {"hook": event.hook, "service": self.config.effective_name,
                     "failureClass": classify_failure(code=event.error_type, error_type=event.error_type)},
        }
        record = self.redactor.redact(record)
        with self._lock:
            self._error_sink.append(record)
            if len(self._error_sink) > self._max_errors:
                del self._error_sink[: len(self._error_sink) - self._max_errors]
        self._submit("error", record)

    def _export_event(self, event: HookEvent) -> None:
        payload = event.redacted()
        payload["kind"] = event.hook
        self._submit("log", payload)
        if event.hook in ("onA2AMessageSent", "onA2AMessageReceived", "onTaskStart", "onTaskEnd", "onResearchEnd"):
            self._submit("event", payload)

    def _submit(self, kind: str, record: dict[str, Any]) -> None:
        delivered = False
        for sink in list(self._direct):
            try:
                sink.export(kind, [record])
                delivered = True
            except Exception:  # noqa: BLE001 - a direct sink failure must never propagate
                self._dropped[kind] = self._dropped.get(kind, 0) + 1
        for exporter in list(self._exporters):
            if exporter.submit(kind, record):
                delivered = True
        if not delivered and self._exporters:
            self._dropped[kind] = self._dropped.get(kind, 0) + 1
            self.metrics.inc_counter("eclipse_telemetry_dropped_total", labels={"kind": kind})

    # ── self health ─────────────────────────────────────────────────────────
    def _register_self_health(self) -> None:
        self.health.register(
            "observability",
            lambda: (
                (HEALTHY, None) if self.config.enabled
                else (DEGRADED, "observability disabled by configuration")
            ),
            kind="telemetry",
        )

    # ── reporting ───────────────────────────────────────────────────────────
    def get_trace(self, trace_id: str) -> list[dict[str, Any]]:
        return self._span_store.get_trace(trace_id, redactor=self.redactor)

    def trajectory(self, trace_id: str) -> dict[str, Any]:
        return self._span_store.trajectory(trace_id, redactor=self.redactor)

    def recent_traces(self, limit: int = 50) -> list[str]:
        return self._span_store.trace_ids(limit)

    def errors(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._error_sink[-limit:])[::-1]

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "service": self.config.effective_name,
            "environment": self.config.environment,
            "sampling": self.sampler.snapshot(),
            "observers": self.observers.stats(),
            "spans": self._span_store.stats(),
            "metrics": self.metrics.names(),
            "exporters": [e.snapshot() for e in self._exporters],
            "health": self.health.report().to_dict(),
            "problems": list(self.config.problems),
        }

    def diagnostics(self) -> dict[str, Any]:
        exporters = [e.snapshot() for e in self._exporters]
        dropped_total = sum(e["dropped"] for e in exporters)
        failed_total = sum(e["failed"] for e in exporters)
        backpressure = any(e["queueDepth"] > 0 for e in exporters)
        return {
            "telemetryStatus": self.status()["health"]["state"],
            "exporters": exporters,
            "droppedSpans": self._span_store.stats()["dropped"],
            "droppedRecords": {**self._dropped, "exporter": dropped_total},
            "exporterFailures": failed_total,
            "backpressure": backpressure,
            "observedHooks": dict(sorted(self._observed.items())),
            "anomaly": self.anomaly.snapshot(),
            "loops": self.loops.snapshot(),
            "slos": self.slos.report(),
            "costs": self.costs.summary(),
        }

    def traceparent(self) -> str:
        return (current_context() or get_or_create_context()).traceparent()

    def carrier(self, carrier: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return inject(current_context(), carrier)

    def close(self) -> None:
        for exporter in list(self._exporters):
            exporter.close()
        for sink in list(self._direct):
            try:
                sink.close()
            except Exception:  # noqa: BLE001
                pass


def _pct(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    samples = sorted(values)
    idx = min(len(samples) - 1, max(0, int(q * (len(samples) - 1) + 0.5)))
    return round(samples[idx], 4)


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        return float(raw) if raw not in (None, "") else float(default)
    except (TypeError, ValueError):
        return float(default)


def _failure_component(event: HookEvent) -> str:
    """Coarse component for failure counters (bounded cardinality)."""
    event_type = str((event.attributes or {}).get("eventType") or "").lower()
    if event_type.startswith("tool."):
        return "tool"
    if event_type.startswith("model."):
        return "provider"
    if event_type.startswith("run."):
        return "run"
    if event_type.startswith("step."):
        return "step"
    if event_type.startswith("job."):
        return "job"
    if event_type.startswith("plugin."):
        return "plugin"
    if event_type.startswith("mcp."):
        return "mcp"
    return "run"


def _corr_labels(event: HookEvent) -> dict[str, str]:
    ctx = event.context
    labels: dict[str, str] = {}
    if ctx.agent_id:
        labels["agent"] = ctx.agent_id
    if ctx.workflow_id:
        labels["workflow"] = ctx.workflow_id
    if ctx.worker_id:
        labels["worker"] = ctx.worker_id
    return labels


__all__ = ["ObservabilityHub"]

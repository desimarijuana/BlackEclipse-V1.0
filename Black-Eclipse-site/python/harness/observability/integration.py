"""Runtime integration — project Eclipse's event bus into the observability hub.

Eclipse already publishes a rich, universal event stream on `service.bus` (agent
runs, model routing, tool calls, fabric jobs, plugins, A2A, canonical events).
Rather than sprinkle instrumentation through forty subsystems, this module
subscribes ONCE to that bus and projects it into:

* real spans (`eclipse.run`, `eclipse.llm`, `eclipse.tool`, `eclipse.job`,
  `eclipse.plugin`, `eclipse.a2a`) with parent/child relationships, and
* strongly-typed `HookEvent`s (`onRunStart`, `onLLMEnd`, `onToolError`, …),

so the hub computes metrics, cost, SLOs, anomalies and error tracking from one
place. The projector is synchronous, allocation-light and swallow-everything: a
malformed event can never break the run that emitted it.

Cross-process propagation: run/job/A2A events carry a `runId`/`jobId`/`traceId`;
the projector binds an `ObservationContext` per run so nested tool/LLM spans
parent correctly, and `docker`/worker boundaries carry the same ids.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .context import ObservationContext, new_trace_id
from .events import make_event
from .tracing import Span, STATUS_ERROR, STATUS_OK

log = logging.getLogger("harness.observability.integration")

_MAX_RUNS = 2000


def _ts(event: dict[str, Any]) -> float:
    value = event.get("at")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return time.time()
    return time.time()


def _data(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


class RunEventProjector:
    """Stateful projector from bus events to spans + hook events."""

    def __init__(self, hub: Any) -> None:
        self.hub = hub
        self._runs: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._jobs: dict[str, Span] = {}
        self._plugins: dict[str, Span] = {}

    # ── bus entry point ─────────────────────────────────────────────────────
    def handle(self, event: dict[str, Any]) -> None:
        try:
            self._handle(event)
        except Exception:  # noqa: BLE001 - projection must never break the bus
            log.debug("event projection failed for %r", (event or {}).get("type"), exc_info=True)

    def _handle(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        etype = str(event.get("type") or "")
        data = _data(event)
        run_id = event.get("runId") or data.get("runId")
        ts = _ts(event)
        if etype in ("run.created", "run.started", "run.resumed") and run_id:
            self._run_start(str(run_id), etype, data, ts)
        elif etype in ("run.completed", "run.failed", "run.cancelled") and run_id:
            self._run_end(str(run_id), etype, data, ts)
        elif etype == "model.requested" and run_id:
            self._llm_start(str(run_id), data, ts)
        elif etype.startswith("model.request.") and run_id:
            self._llm_runtime(str(run_id), etype, data)
        elif etype == "model.completed" and run_id:
            self._llm_end(str(run_id), data, ts, ok=True)
        elif etype == "tool.requested" and run_id:
            self._tool_start(str(run_id), data, ts)
        elif etype.startswith("tool.") and run_id:
            self._tool_end(str(run_id), etype, data, ts)
        elif etype == "prompt.plan" and run_id:
            self.hub.emit("onPlanEnd", context=self._ctx(run_id), attributes={"segments": len(data.get("segments") or [])})
        # ── fabric jobs ──
        elif etype.startswith("job."):
            self._job_event(etype, event, data, ts)
        # ── plugins ──
        elif etype.startswith("plugin."):
            self._plugin_event(etype, event, data, ts)
        # ── A2A / delegation ──
        elif etype in ("agent.spawned", "delegation.created", "delegation.cancelled"):
            ctx = self._ctx(run_id)
            self.hub.emit("onA2AMessageSent", context=ctx, attributes={"event": etype, **{k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}})
        # ── canonical events + automation ──
        elif etype.startswith(("schedule.", "automation.", "workflow.")):
            self.hub.emit("onEventPublished", context=self._ctx(run_id), attributes={"eventType": etype})
        # ── recovery / replan / context ──
        elif etype in ("run.replanned", "context.retry"):
            self.hub.emit("onRecoveryStart", context=self._ctx(run_id), attributes={"eventType": etype, **{k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}})
        # ── research / memory / skills ──
        elif etype.startswith("research."):
            hook = "onResearchEnd"
            self.hub.emit(hook, context=self._ctx(run_id), status="ERROR" if etype.endswith("failed") else "OK", attributes={"eventType": etype})
        elif etype.startswith("memory."):
            self.hub.emit("onMemoryWrite", context=self._ctx(run_id), attributes={"eventType": etype})
        elif etype.startswith(("skill.", "session.")):
            self.hub.emit("onSkillExecuted", context=self._ctx(run_id), attributes={"eventType": etype})
        # ── process-level model routing telemetry ──
        elif etype.startswith("model.routing") or etype.startswith("mcp.") or etype.startswith("code_intel"):
            self.hub.emit("onEventPublished", attributes={"eventType": etype})

        if etype.endswith("failed") and etype != "run.failed":
            self.hub.emit("onError", context=self._ctx(run_id), error_type=(data.get("error") or {}).get("code") if isinstance(data.get("error"), dict) else str(data.get("code") or ""),
                          error_message=str((data.get("error") or {}).get("message") if isinstance(data.get("error"), dict) else data.get("message") or etype)[:500],
                          attributes={"eventType": etype})

    # ── run lifecycle ───────────────────────────────────────────────────────
    def _run_start(self, run_id: str, etype: str, data: dict[str, Any], ts: float) -> None:
        state = self._runs.get(run_id)
        if state is not None:
            return
        trace_id = new_trace_id()
        decision = self.hub.sampler.should_sample(trace_id)
        ctx = ObservationContext(
            trace_id=trace_id, run_id=run_id, sampled=decision.sampled,
            agent_id=data.get("agentId"), session_id=data.get("sessionId"),
            workflow_id=data.get("workflowId"),
        )
        if not decision.sampled and self.hub.config.trace_sample_rate <= 0 and not self.hub.config.always_sample_errors:
            # Still track hooks/metrics; only spans are head-sampled.
            pass
        span = Span(
            trace_id=ctx.trace_id, span_id=ctx.span_id, parent_span_id=None,
            name="eclipse.run", kind="server", start_time=ts, sampled=decision.sampled,
            attributes={"runId": run_id, "agentId": data.get("agentId"), "provider": data.get("provider"), "event": etype},
        )
        self._runs[run_id] = {"ctx": ctx, "span": span, "llm": [], "tools": {}, "start": ts}
        self._remember(run_id)
        self.hub.emit("onRunStart", context=ctx, name="eclipse.run", attributes={"agentId": data.get("agentId"), "provider": data.get("provider")})

    def _run_end(self, run_id: str, etype: str, data: dict[str, Any], ts: float) -> None:
        state = self._runs.get(run_id)
        if state is None:
            return
        ctx = state["ctx"]
        status = "ERROR" if etype == "run.failed" else ("CANCELLED" if etype == "run.cancelled" else "OK")
        error = data.get("error") if isinstance(data.get("error"), dict) else None
        # Close any spans still open for this run (a failure may abandon them).
        for span in state["llm"]:
            if span.end_time is None:
                span.end(STATUS_ERROR if status != "OK" else STATUS_OK)
                self._finish(span)
        for span in state["tools"].values():
            if span.end_time is None:
                span.end(STATUS_ERROR if status != "OK" else STATUS_OK)
                self._finish(span)
        span = state["span"]
        span.end(STATUS_ERROR if status == "ERROR" else STATUS_OK)
        span.attributes["status"] = status.lower()
        if error:
            span.attributes["errorCode"] = error.get("code")
            span.attributes["errorMessage"] = str(error.get("message"))[:500]
        self._finish(span)
        duration = (ts - state["start"]) * 1000.0
        self.hub.emit(
            "onRunEnd", context=ctx, status=status, duration_ms=duration,
            error_type=(error or {}).get("code"), error_message=(error or {}).get("message"),
            attributes={"steps": data.get("steps"), "agentId": ctx.agent_id},
        )
        if etype == "run.failed":
            self.hub.emit("onError", context=ctx, error_type=(error or {}).get("code") or "RUN_FAILED",
                          error_message=(error or {}).get("message") or "run failed")
        self._runs.pop(run_id, None)

    # ── LLM ─────────────────────────────────────────────────────────────────
    def _llm_start(self, run_id: str, data: dict[str, Any], ts: float) -> None:
        state = self._runs.get(run_id)
        if state is None:
            return
        ctx = state["ctx"].child(attributes={"step": data.get("step")})
        span = Span(
            trace_id=ctx.trace_id, span_id=ctx.span_id, parent_span_id=ctx.parent_span_id,
            name="eclipse.llm", kind="llm", start_time=ts, sampled=state["ctx"].sampled,
            attributes={"runId": run_id, "step": data.get("step"), "messages": data.get("messages")},
        )
        state["llm"].append(span)
        self.hub.emit("onLLMStart", context=ctx, name="eclipse.llm", attributes={"step": data.get("step"), "runId": run_id})

    def _llm_runtime(self, run_id: str, etype: str, data: dict[str, Any]) -> None:
        state = self._runs.get(run_id)
        if state is None or not state["llm"]:
            return
        span = state["llm"][-1]
        span.attributes["provider"] = data.get("provider")
        span.attributes["model"] = data.get("model")
        if data.get("task"):
            span.attributes["task"] = data.get("task")
        if data.get("latencyMs") is not None:
            span.attributes["latencyMs"] = data.get("latencyMs")
        if etype == "model.request.failed":
            span.attributes["errorClass"] = data.get("errorClass")
            span.error_type = data.get("errorClass")
            span.end(STATUS_ERROR)
            self._finish(span)
            self.hub.emit("onLLMError", context=self._ctx_for_span(state, span), provider=data.get("provider"),
                          model=data.get("model"), error_type=data.get("errorClass"), error_message=data.get("errorClass"),
                          duration_ms=span.duration_ms)

    def _llm_end(self, run_id: str, data: dict[str, Any], ts: float, *, ok: bool) -> None:
        state = self._runs.get(run_id)
        if state is None or not state["llm"]:
            return
        span = state["llm"].pop()
        prompt = int(data.get("promptTokens") or 0)
        completion = int(data.get("completionTokens") or 0)
        total = int(data.get("totalTokens") or (prompt + completion))
        span.attributes.update({"promptTokens": prompt, "completionTokens": completion, "totalTokens": total})
        if span.end_time is None:
            span.end(STATUS_OK if ok else STATUS_ERROR)
        self._finish(span)
        ctx = self._ctx_for_span(state, span)
        self.hub.emit(
            "onLLMEnd", context=ctx, provider=span.attributes.get("provider"), model=span.attributes.get("model"),
            status="OK" if ok else "ERROR", duration_ms=span.duration_ms,
            tokens={"input": prompt, "output": completion, "total": total},
            attributes={"step": span.attributes.get("step"), "runId": run_id},
        )

    # ── tools ───────────────────────────────────────────────────────────────
    def _tool_start(self, run_id: str, data: dict[str, Any], ts: float) -> None:
        state = self._runs.get(run_id)
        if state is None:
            return
        call_id = str(data.get("toolCallId") or data.get("name") or "tool")
        ctx = state["ctx"].child(attributes={"tool": data.get("name")})
        span = Span(
            trace_id=ctx.trace_id, span_id=ctx.span_id, parent_span_id=ctx.parent_span_id,
            name=f"eclipse.tool.{data.get('name') or 'tool'}", kind="tool", start_time=ts,
            sampled=state["ctx"].sampled,
            attributes={"runId": run_id, "tool": data.get("name"), "toolCallId": call_id, "step": data.get("step")},
        )
        state["tools"][call_id] = span
        signature = f"{data.get('name')}:{data.get('detail') or ''}"
        self.hub.emit("onToolStart", context=ctx, tool_name=data.get("name"), name=str(data.get("name")),
                      attributes={"toolCallId": call_id, "signature": signature, "runId": run_id})

    def _tool_end(self, run_id: str, etype: str, data: dict[str, Any], ts: float) -> None:
        state = self._runs.get(run_id)
        if state is None:
            return
        call_id = str(data.get("toolCallId") or data.get("name") or "tool")
        span = state["tools"].pop(call_id, None)
        is_error = etype == "tool.failed"
        duration = data.get("durationMs")
        if span is not None:
            if duration is not None:
                span.attributes["durationMs"] = duration
            span.attributes["truncated"] = data.get("truncated")
            if is_error:
                span.attributes["errorCode"] = data.get("code")
                span.error_type = data.get("code")
            span.end(STATUS_ERROR if is_error else STATUS_OK)
            self._finish(span)
            duration = duration if duration is not None else span.duration_ms
        ctx = self._ctx(run_id)
        hook = "onToolError" if is_error else "onToolEnd"
        self.hub.emit(
            hook, context=ctx, tool_name=data.get("name"), name=str(data.get("name")),
            status="ERROR" if is_error else "OK", duration_ms=duration,
            error_type=data.get("code") if is_error else None,
            attributes={"toolCallId": call_id, "resumed": data.get("resumed"), "truncated": data.get("truncated"), "runId": run_id},
        )
        if etype == "tool.truncated":
            self.hub.emit("onToolEnd", context=ctx, tool_name=data.get("name"), status="DEGRADED",
                          attributes={"truncated": True, "shownChars": data.get("shownChars"), "totalChars": data.get("totalChars")})

    # ── jobs / plugins / a2a ────────────────────────────────────────────────
    def _job_event(self, etype: str, event: dict[str, Any], data: dict[str, Any], ts: float) -> None:
        job_id = str(event.get("jobId") or data.get("jobId") or data.get("id") or "")
        if not job_id:
            return
        if etype == "job.started":
            span = Span(trace_id=new_trace_id(), span_id=ObservationContext().span_id, parent_span_id=None,
                        name="eclipse.job", kind="consumer", start_time=ts,
                        attributes={"jobId": job_id, "queue": data.get("queue"), "workerId": data.get("workerId"), "attempt": data.get("attempt")})
            self._jobs[job_id] = span
            self.hub.emit("onJobStart", attributes={"jobId": job_id, "queue": data.get("queue"), "workerId": data.get("workerId")})
        elif etype in ("job.succeeded", "job.failed", "job.retrying", "job.timed_out", "job.dead_letter", "job.cancelled"):
            span = self._jobs.pop(job_id, None)
            is_error = etype in ("job.failed", "job.timed_out", "job.dead_letter")
            if span is not None:
                span.end(STATUS_ERROR if is_error else STATUS_OK)
                span.attributes["status"] = etype
                self._finish(span)
            hook = {"job.retrying": "onJobRetry", "job.failed": "onJobFailure", "job.timed_out": "onJobFailure",
                    "job.dead_letter": "onJobFailure"}.get(etype, "onJobEnd")
            self.hub.emit(hook, status="ERROR" if is_error else "OK", duration_ms=data.get("durationMs"),
                          error_type=data.get("errorClass"), attributes={"jobId": job_id, "eventType": etype, **{k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}})
        elif etype == "job.recovered":
            self.hub.emit("onRecoveryEnd", attributes={"jobId": job_id, "eventType": etype})

    def _plugin_event(self, etype: str, event: dict[str, Any], data: dict[str, Any], ts: float) -> None:
        plugin_id = str(data.get("pluginId") or data.get("plugin") or data.get("id") or "plugin")
        if etype.endswith("started"):
            span = Span(trace_id=new_trace_id(), span_id=ObservationContext().span_id, parent_span_id=None,
                        name=f"eclipse.plugin.{plugin_id}", kind="internal", start_time=ts,
                        attributes={"pluginId": plugin_id, "eventType": etype})
            self._plugins[f"{plugin_id}:{data.get('tool') or data.get('name') or ''}"] = span
            self.hub.emit("onPluginStart", attributes={"pluginId": plugin_id, "eventType": etype})
        elif etype.endswith(("completed", "failed")):
            key = f"{plugin_id}:{data.get('tool') or data.get('name') or ''}"
            span = self._plugins.pop(key, None)
            is_error = etype.endswith("failed")
            if span is not None:
                span.end(STATUS_ERROR if is_error else STATUS_OK)
                self._finish(span)
            self.hub.emit("onPluginError" if is_error else "onPluginEnd", status="ERROR" if is_error else "OK",
                          error_type=data.get("error"), attributes={"pluginId": plugin_id, "eventType": etype})

    # ── helpers ─────────────────────────────────────────────────────────────
    def _ctx(self, run_id: Optional[str]) -> ObservationContext:
        if run_id and run_id in self._runs:
            return self._runs[run_id]["ctx"]
        return ObservationContext(run_id=run_id)

    def _ctx_for_span(self, state: dict[str, Any], span: Span) -> ObservationContext:
        return state["ctx"].with_fields(span_id=span.span_id)

    def _finish(self, span: Span) -> None:
        try:
            self.hub.tracer.record_span(span)
        except Exception:  # noqa: BLE001
            pass

    def _remember(self, run_id: str) -> None:
        self._order.append(run_id)
        while len(self._order) > _MAX_RUNS:
            old = self._order.pop(0)
            if old != run_id:
                self._runs.pop(old, None)

    def stats(self) -> dict[str, Any]:
        return {"activeRuns": len(self._runs), "openJobs": len(self._jobs), "openPlugins": len(self._plugins)}


class ModelObserverBridge:
    """Optional direct adapter: forward a model-runtime observer event to the hub.

    NOT installed by `install_observability` because the service already publishes
    the SAME model events on the bus, which the projector ingests — emitting from
    both would double-count LLM hooks. The adapter exists for a caller that runs a
    hub WITHOUT a bus subscription (e.g. an isolated embedder) and wants model
    telemetry straight from `ModelRuntime.set_observer`. It always forwards to the
    pre-existing observer too.
    """

    def __init__(self, hub: Any, existing: Optional[Callable[[str, dict[str, Any]], None]]) -> None:
        self.hub = hub
        self.existing = existing

    def __call__(self, event_type: str, data: dict[str, Any]) -> None:
        try:
            if event_type in ("model.request.completed", "model.request.failed"):
                hook = "onLLMEnd" if event_type.endswith("completed") else "onLLMError"
                self.hub.emit(
                    hook, provider=data.get("provider"), model=data.get("model"),
                    status="OK" if event_type.endswith("completed") else "ERROR",
                    duration_ms=data.get("latencyMs"),
                    tokens={"input": data.get("inputTokens", 0), "output": data.get("outputTokens", 0),
                            "total": data.get("totalTokens", 0)},
                    error_type=data.get("errorClass"),
                    attributes={"requestId": data.get("requestId"), "runId": data.get("runId"), "task": data.get("task"),
                                "fallback": data.get("fallback"), "retries": data.get("retries")},
                )
            elif event_type == "model.routing.completed":
                self.hub.emit("onEventPublished", attributes={"eventType": event_type, "selected": data.get("selected"), "reason": data.get("reason")})
        except Exception:  # noqa: BLE001
            pass
        if self.existing is not None:
            try:
                self.existing(event_type, data)
            except Exception:  # noqa: BLE001
                pass


# ── service wiring ──────────────────────────────────────────────────────────

def install_observability(service: Any, *, hub: Any = None) -> Any:
    """Attach the observability hub to an `AgenticService`. Idempotent.

    The hub subscribes ONCE to the service's universal bus; the model runtime's
    existing observer already republishes model events there, so LLM telemetry is
    captured without touching the model runtime (and without double-counting).
    """
    existing = getattr(service, "observability", None)
    if existing is not None:
        return existing
    from .core import ObservabilityHub

    hub = hub or ObservabilityHub()
    projector = RunEventProjector(hub)
    unsubscribe = service.bus.subscribe(projector.handle)
    hub._service = service  # type: ignore[attr-defined]
    hub._projector = projector  # type: ignore[attr-defined]
    hub._unsubscribe = unsubscribe  # type: ignore[attr-defined]
    service.observability = hub
    _register_subsystem_health(service, hub)
    # Timestamp the install so diagnostics can report uptime.
    hub._installed_at = time.time()  # type: ignore[attr-defined]
    return hub


def _register_subsystem_health(service: Any, hub: Any) -> None:
    def _has(attr: str) -> Callable[[], tuple[str, Optional[str]]]:
        def check() -> tuple[str, Optional[str]]:
            target = getattr(service, attr, None)
            return ("HEALTHY", None) if target is not None else ("UNKNOWN", f"{attr} unavailable")
        return check

    for attr in ("execution", "application_runtime", "terminal", "git", "memory", "skill_registry"):
        hub.register_health(attr, _has(attr), kind="subsystem")


def start_observability(service: Any) -> dict[str, Any]:
    hub = getattr(service, "observability", None)
    if hub is None:
        return {"available": False}
    # Install structured JSON logging (trace-correlated, redacted) once the hub is
    # live. Never blocks: a logging setup failure only leaves the plain format.
    if hub.config.enabled and hub.config.log_json:
        try:
            from .logging_setup import configure_logging

            configure_logging(
                level=hub.config.log_level,
                service=hub.config.effective_name,
                json_output=True,
                redactor=hub.redactor,
            )
        except Exception:  # noqa: BLE001
            log.warning("structured logging setup skipped", exc_info=True)
    return {"available": True, "status": hub.status()}


def stop_observability(service: Any) -> None:
    hub = getattr(service, "observability", None)
    if hub is None:
        return
    unsubscribe = getattr(hub, "_unsubscribe", None)
    if callable(unsubscribe):
        try:
            unsubscribe()
        except Exception:  # noqa: BLE001
            pass
    try:
        hub.close()
    except Exception:  # noqa: BLE001 - shutdown must never raise
        log.warning("observability shutdown failed", exc_info=True)


__all__ = ["RunEventProjector", "ModelObserverBridge", "install_observability", "start_observability", "stop_observability"]

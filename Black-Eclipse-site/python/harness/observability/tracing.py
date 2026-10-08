"""Distributed tracing — spans that reconstruct the actual execution tree.

`Tracer.start(name, ...)` opens a child span and yields it as a context manager;
exiting records the end time, status and any error, exports a `HookEvent` with
hook `onSpan`, and stores the span in a bounded per-trace `SpanStore`. Because
the tracer derives a child `ObservationContext` and binds it with a contextvar,
nested spans parent correctly even across `await` boundaries.

`SpanStore.trajectory(trace_id)` rebuilds the parent/child tree and a
time-ordered timeline, which is what the run-detail and failure-investigation
views consume. Ids are W3C-shaped and `traceparent` inject/extract (context.py)
carries them across process boundaries.
"""

from __future__ import annotations

import time
import traceback
from collections import OrderedDict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from .context import ObservationContext, bind_context, current_context, get_or_create_context

SPAN_KINDS = frozenset({"internal", "server", "client", "producer", "consumer", "llm", "tool", "agent"})
STATUS_UNSET, STATUS_OK, STATUS_ERROR = "UNSET", "OK", "ERROR"


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    kind: str = "internal"
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = STATUS_UNSET
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    sampled: bool = True

    @property
    def duration_ms(self) -> float:
        end = self.end_time if self.end_time is not None else time.time()
        return round((end - self.start_time) * 1000.0, 3)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, **attributes: Any) -> None:
        self.events.append({"name": name, "at": time.time(), **attributes})

    def end(self, status: str = STATUS_OK, error: Optional[BaseException] = None) -> None:
        if self.end_time is not None:
            return
        self.end_time = time.time()
        self.status = status
        if error is not None:
            self.status = STATUS_ERROR
            self.error_type = type(error).__name__
            self.error_message = str(error)[:2000]

    def to_dict(self, *, redactor: Optional[Any] = None) -> dict[str, Any]:
        attrs = self.attributes
        if redactor is not None:
            attrs = redactor.redact(attrs)
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "parentSpanId": self.parent_span_id,
            "name": self.name,
            "kind": self.kind,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "durationMs": self.duration_ms,
            "status": self.status,
            "attributes": attrs,
            "events": (redactor.redact(self.events) if redactor is not None else self.events),
            "errorType": self.error_type,
            "errorMessage": (redactor.redact_text(self.error_message) if redactor and self.error_message else self.error_message),
            "sampled": self.sampled,
        }


class SpanStore:
    """Bounded in-process span store + trace index for trajectory queries."""

    def __init__(self, *, max_spans: int = 5000, max_traces: int = 500) -> None:
        self._traces: "OrderedDict[str, list[Span]]" = OrderedDict()
        self._max_spans = max_spans
        self._max_traces = max_traces
        self._total = 0
        self._dropped = 0

    def add(self, span: Span) -> None:
        spans = self._traces.get(span.trace_id)
        if spans is None:
            spans = []
            self._traces[span.trace_id] = spans
            self._traces.move_to_end(span.trace_id)
            while len(self._traces) > self._max_traces:
                evicted_id, evicted = self._traces.popitem(last=False)
                self._dropped += len(evicted)
                self._total -= len(evicted)
        spans.append(span)
        self._total += 1
        while self._total > self._max_spans and self._traces:
            evicted_id, evicted = self._traces.popitem(last=False)
            self._dropped += len(evicted)
            self._total -= len(evicted)

    def get_trace(self, trace_id: str, *, redactor: Optional[Any] = None) -> list[dict[str, Any]]:
        spans = self._traces.get(trace_id)
        if not spans:
            return []
        return [s.to_dict(redactor=redactor) for s in spans]

    def trace_ids(self, limit: int = 50) -> list[str]:
        return list(self._traces.keys())[-limit:][::-1]

    def trajectory(self, trace_id: str, *, redactor: Optional[Any] = None) -> dict[str, Any]:
        spans = self._traces.get(trace_id)
        if not spans:
            return {"traceId": trace_id, "found": False, "roots": [], "timeline": []}
        by_id = {s.span_id: s.to_dict(redactor=redactor) for s in spans}
        children: dict[Optional[str], list[str]] = {}
        for s in spans:
            children.setdefault(s.parent_span_id, []).append(s.span_id)
        for ids in children.values():
            ids.sort(key=lambda sid: next(x.start_time for x in spans if x.span_id == sid))

        def build(span_id: str) -> dict[str, Any]:
            node = dict(by_id[span_id])
            node["children"] = [build(cid) for cid in children.get(span_id, [])]
            return node

        roots = [build(sid) for sid in children.get(None, [])] or [
            build(s.span_id) for s in spans if s.parent_span_id not in by_id
        ]
        timeline = sorted(
            (s.to_dict(redactor=redactor) for s in spans),
            key=lambda d: d["startTime"],
        )
        root = next((s for s in spans if s.parent_span_id is None), spans[0])
        return {
            "traceId": trace_id,
            "found": True,
            "rootName": root.name,
            "spanCount": len(spans),
            "durationMs": round(max(s.duration_ms for s in spans), 3),
            "status": ("ERROR" if any(s.status == STATUS_ERROR for s in spans) else "OK"),
            "roots": roots,
            "timeline": timeline,
        }

    def stats(self) -> dict[str, Any]:
        return {"traces": len(self._traces), "spans": self._total, "dropped": self._dropped}


class Tracer:
    def __init__(
        self,
        *,
        store: SpanStore,
        sampler: Optional[Any] = None,
        on_span: Optional[Callable[[Span], None]] = None,
        redactor: Optional[Any] = None,
    ) -> None:
        self.store = store
        self.sampler = sampler
        self.on_span = on_span
        self.redactor = redactor

    @contextmanager
    def start(
        self,
        name: str,
        *,
        kind: str = "internal",
        attributes: Optional[dict[str, Any]] = None,
        context: Optional[ObservationContext] = None,
        record: bool = True,
    ) -> Iterator[Span]:
        parent = context or current_context() or get_or_create_context()
        child = parent.child(attributes=attributes)
        span = Span(
            trace_id=child.trace_id,
            span_id=child.span_id,
            parent_span_id=child.parent_span_id,
            name=name,
            kind=kind if kind in SPAN_KINDS else "internal",
            attributes=dict(attributes or {}),
            sampled=child.sampled,
        )
        cm = bind_context(child)
        cm.__enter__()
        try:
            yield span
        except BaseException as exc:  # noqa: BLE001 - record then re-raise
            span.end(STATUS_ERROR, exc)
            if span.error_message is None:
                span.error_message = "".join(traceback.format_exception_only(type(exc), exc)).strip()[:2000]
            self._finish(span, record)
            raise
        else:
            if span.end_time is None:
                span.end(STATUS_OK)
            self._finish(span, record)
        finally:
            cm.__exit__(None, None, None)

    def record_span(self, span: Span) -> None:
        self._finish(span, True, already_ended=True)

    def _finish(self, span: Span, record: bool, already_ended: bool = False) -> None:
        if not record:
            return
        keep = True
        if self.sampler is not None:
            keep = self.sampler.should_keep_span(span.trace_id, is_error=span.status == STATUS_ERROR)
            if not keep:
                return
        self.store.add(span)
        if self.on_span is not None:
            try:
                self.on_span(span)
            except Exception:  # noqa: BLE001 - span export must never break a run
                pass


__all__ = ["Span", "SpanStore", "Tracer", "SPAN_KINDS", "STATUS_OK", "STATUS_ERROR", "STATUS_UNSET"]

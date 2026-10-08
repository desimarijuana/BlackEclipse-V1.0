"""Exporters — fail-open, non-blocking, bounded telemetry sinks.

A backend failure must NEVER break a run. Every exporter is wrapped in
`BoundedExporter`, which owns a daemon thread and a bounded queue: `submit()` is
a non-blocking enqueue that drops-and-counts under backpressure instead of
blocking the caller. Batches are flushed by size or interval, retried with
exponential backoff, and guarded by a circuit breaker that stops hammering a
dead backend while staying healthy enough to recover automatically.

Concrete sinks are vendor adapters (`OtlpHttpExporter`, `LangfuseExporter`,
`SentryExporter`) plus local sinks (`JsonlFileExporter`, `ConsoleExporter`,
`InMemoryExporter`). All network sinks use the stdlib and lazy imports only.
"""

from __future__ import annotations

import base64
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

log = logging.getLogger("harness.observability.exporters")

EXPORT_KINDS = ("span", "log", "metric", "event", "error")


@runtime_checkable
class Exporter(Protocol):
    name: str
    kinds: tuple[str, ...]

    def export(self, kind: str, records: list[dict[str, Any]]) -> None: ...

    def close(self) -> None: ...


class BaseExporter:
    name = "base"
    kinds: tuple[str, ...] = EXPORT_KINDS

    def export(self, kind: str, records: list[dict[str, Any]]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:
        return None


class InMemoryExporter(BaseExporter):
    """Bounded in-process sink. Used by tests and the diagnostics endpoint."""

    name = "memory"

    def __init__(self, *, max_records: int = 5000) -> None:
        self._lock = threading.Lock()
        self._records: list[dict[str, Any]] = []
        self._max = max_records
        self._counts: dict[str, int] = {}

    def export(self, kind: str, records: list[dict[str, Any]]) -> None:
        with self._lock:
            for record in records:
                self._records.append({"kind": kind, **record})
                self._counts[kind] = self._counts.get(kind, 0) + 1
            if len(self._records) > self._max:
                del self._records[: len(self._records) - self._max]

    def records(self, kind: Optional[str] = None) -> list[dict[str, Any]]:
        with self._lock:
            if kind is None:
                return list(self._records)
            return [r for r in self._records if r.get("kind") == kind]

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._counts.clear()


class ConsoleExporter(BaseExporter):
    name = "console"

    def export(self, kind: str, records: list[dict[str, Any]]) -> None:
        for record in records:
            log.info("telemetry %s %s", kind, json.dumps(record, default=str)[:2000])


class JsonlFileExporter(BaseExporter):
    """Append-only JSONL sink, one file per kind per day. Local fallback sink."""

    name = "jsonl"

    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def export(self, kind: str, records: list[dict[str, Any]]) -> None:
        day = time.strftime("%Y%m%d", time.gmtime())
        path = self._dir / f"{kind}-{day}.jsonl"
        with open(path, "a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, default=str) + "\n")


class _HttpExporter(BaseExporter):
    timeout_s = 5.0

    def _post(self, url: str, body: bytes, headers: dict[str, str]) -> None:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310 - configured endpoint
            response.read()


class OtlpHttpExporter(_HttpExporter):
    """Minimal OTLP/HTTP JSON exporter (traces + logs).

    Dependency-free: builds the OTLP JSON envelope and POSTs to
    `<endpoint>/v1/traces` and `/v1/logs`. The optional OpenTelemetry SDK is NOT
    required; when it is installed and configured elsewhere it can export the
    same spans independently.
    """

    name = "otel"

    def __init__(self, endpoint: str, headers: Optional[dict[str, str]] = None, timeout_s: float = 5.0) -> None:
        self._base = endpoint.rstrip("/")
        self._headers = {"Content-Type": "application/json", **(headers or {})}
        self._service = "eclipse-harness"
        self.timeout_s = timeout_s

    def export(self, kind: str, records: list[dict[str, Any]]) -> None:
        if kind == "span":
            payload = {"resourceSpans": [{
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": self._service}}]},
                "scopeSpans": [{"scope": {"name": "eclipse.observability"}, "spans": [
                    _otlp_span(r) for r in records
                ]}],
            }]}
            self._post(f"{self._base}/v1/traces", json.dumps(payload).encode("utf-8"), self._headers)
        elif kind == "log":
            payload = {"resourceLogs": [{
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": self._service}}]},
                "scopeLogs": [{"scope": {"name": "eclipse.observability"}, "logRecords": [
                    _otlp_log(r) for r in records
                ]}],
            }]}
            self._post(f"{self._base}/v1/logs", json.dumps(payload).encode("utf-8"), self._headers)
        elif kind == "metric":
            payload = {"resourceMetrics": [{
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": self._service}}]},
                "scopeMetrics": [{"scope": {"name": "eclipse.observability"}, "metrics": [
                    _otlp_metric(r) for r in records
                ]}],
            }]}
            self._post(f"{self._base}/v1/metrics", json.dumps(payload).encode("utf-8"), self._headers)

    def set_service_name(self, name: str) -> None:
        self._service = name


class LangfuseExporter(_HttpExporter):
    """LLM/agent observability: sends trace + generation/span batches to Langfuse.

    Uses the Langfuse ingestion API directly over stdlib HTTP with Basic auth
    (public key : secret key). Fail-open: a Langfuse outage only drops LLM
    telemetry, never affects the run.
    """

    name = "langfuse"
    kinds = ("span", "event")

    def __init__(self, host: str, public_key: str, secret_key: str, timeout_s: float = 5.0) -> None:
        self._base = (host or "https://cloud.langfuse.com").rstrip("/")
        token = base64.b64encode(f"{public_key}:{secret_key}".encode("utf-8")).decode("ascii")
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {token}",
        }
        self.timeout_s = timeout_s

    def export(self, kind: str, records: list[dict[str, Any]]) -> None:
        batch = []
        for record in records:
            span = record.get("span") or record
            batch.append({
                "id": span.get("spanId") or span.get("id"),
                "type": "span" if record.get("kind") != "generation" else "generation",
                "traceId": span.get("traceId"),
                "name": span.get("name"),
                "startTime": _iso_from_epoch(span.get("startTime")),
                "endTime": _iso_from_epoch(span.get("endTime")),
                "metadata": span.get("attributes") or {},
                "level": "ERROR" if span.get("status") == "ERROR" else "DEFAULT",
            })
        if not batch:
            return
        body = json.dumps({"batch": batch}).encode("utf-8")
        self._post(f"{self._base}/api/public/ingestion", body, self._headers)


class SentryExporter(_HttpExporter):
    """Error tracking: sends error records to a Sentry store endpoint.

    The DSN is parsed locally; the secret never appears in the payload. Fail-open.
    """

    name = "sentry"
    kinds = ("error",)

    def __init__(self, dsn: str, *, release: str = "", environment: str = "", timeout_s: float = 5.0) -> None:
        self.timeout_s = timeout_s
        self._url = ""
        self._headers = {"Content-Type": "application/json"}
        self._release = release
        self._environment = environment
        self._configure(dsn)

    def _configure(self, dsn: str) -> None:
        # DSN: https://PUBLIC@host/PROJECT_ID
        try:
            scheme, rest = dsn.split("://", 1)
            public, host_and_path = rest.split("@", 1)
            host, project = host_and_path.split("/", 1)
            self._url = f"{scheme}://{host}/api/{project}/store/"
            self._headers["X-Sentry-Auth"] = (
                f"Sentry sentry_version=7, sentry_client=eclipse-observability/1.0, sentry_key={public}"
            )
        except Exception:  # noqa: BLE001 - a malformed DSN disables the sink
            self._url = ""

    def export(self, kind: str, records: list[dict[str, Any]]) -> None:
        if not self._url:
            return
        for record in records:
            event = {
                "event_id": record.get("eventId"),
                "timestamp": record.get("timestamp"),
                "platform": "python",
                "level": "error",
                "environment": self._environment,
                "release": self._release or None,
                "logger": "harness.observability",
                "message": {"formatted": record.get("message") or record.get("errorType") or "error"},
                "extra": {k: v for k, v in record.items() if k not in ("message", "timestamp")},
                "tags": record.get("tags") or {},
            }
            self._post(self._url, json.dumps(event).encode("utf-8"), self._headers)


@dataclass
class ExporterStats:
    submitted: int = 0
    exported: int = 0
    dropped: int = 0
    failed: int = 0
    retried: int = 0
    last_error: Optional[str] = None
    last_success_at: Optional[float] = None
    circuit_open_until: float = 0.0


class BoundedExporter:
    """Non-blocking, bounded, retrying, circuit-broken wrapper around an Exporter."""

    def __init__(
        self,
        exporter: Exporter,
        *,
        queue_size: int = 2048,
        batch_size: int = 64,
        batch_interval_s: float = 1.0,
        max_retries: int = 2,
        circuit_failure_threshold: int = 5,
        circuit_reset_s: float = 30.0,
    ) -> None:
        self.exporter = exporter
        self.name = getattr(exporter, "name", "exporter")
        self.kinds = tuple(getattr(exporter, "kinds", EXPORT_KINDS))
        self.stats = ExporterStats()
        self._queue: "queue.Queue[tuple[str, dict[str, Any]]]" = queue.Queue(maxsize=queue_size)
        self._batch_size = batch_size
        self._interval = batch_interval_s
        self._max_retries = max_retries
        self._threshold = circuit_failure_threshold
        self._reset_s = circuit_reset_s
        self._consecutive_failures = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"telemetry-{self.name}", daemon=True)
        self._thread.start()

    def submit(self, kind: str, record: dict[str, Any]) -> bool:
        if kind not in self.kinds:
            return False
        self.stats.submitted += 1
        try:
            self._queue.put_nowait((kind, record))
            return True
        except queue.Full:
            self.stats.dropped += 1
            return False

    def _circuit_open(self) -> bool:
        return time.monotonic() < self.stats.circuit_open_until

    def _run(self) -> None:
        buffers: dict[str, list[dict[str, Any]]] = {}
        last_flush = time.monotonic()
        while not self._stop.is_set():
            timeout = max(0.02, self._interval - (time.monotonic() - last_flush))
            try:
                kind, record = self._queue.get(timeout=timeout)
                buffers.setdefault(kind, []).append(record)
            except queue.Empty:
                pass
            should_flush = (
                time.monotonic() - last_flush >= self._interval
                or any(len(v) >= self._batch_size for v in buffers.values())
            )
            if should_flush and buffers:
                self._flush(buffers)
                last_flush = time.monotonic()
        # Final drain on stop.
        while not self._queue.empty():
            try:
                kind, record = self._queue.get_nowait()
                buffers.setdefault(kind, []).append(record)
            except queue.Empty:
                break
        if buffers:
            self._flush(buffers)

    def _flush(self, buffers: dict[str, list[dict[str, Any]]]) -> None:
        for kind, records in list(buffers.items()):
            if not records:
                continue
            buffers[kind] = []
            if self._circuit_open():
                self.stats.dropped += len(records)
                continue
            self._send(kind, records)

    def _send(self, kind: str, records: list[dict[str, Any]]) -> None:
        attempt = 0
        while True:
            try:
                self.exporter.export(kind, records)
                self.stats.exported += len(records)
                self.stats.last_success_at = time.time()
                if self._consecutive_failures:
                    self.stats.circuit_open_until = 0.0
                self._consecutive_failures = 0
                return
            except Exception as exc:  # noqa: BLE001 - a sink failure must never propagate
                attempt += 1
                self.stats.failed += 1
                self.stats.last_error = f"{type(exc).__name__}: {exc}"[:500]
                if attempt > self._max_retries:
                    self._consecutive_failures += 1
                    self.stats.dropped += len(records)
                    if self._consecutive_failures >= self._threshold:
                        self.stats.circuit_open_until = time.monotonic() + self._reset_s
                        log.warning("exporter %r circuit opened after %d failures", self.name, self._consecutive_failures)
                    return
                self.stats.retried += 1
                time.sleep(min(2.0, 0.1 * (2 ** attempt)))

    def healthy(self) -> bool:
        return not self._circuit_open()

    def force_circuit_reset(self) -> None:
        self._consecutive_failures = 0
        self.stats.circuit_open_until = 0.0

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kinds": list(self.kinds),
            "healthy": self.healthy(),
            "queueDepth": self._queue.qsize(),
            "submitted": self.stats.submitted,
            "exported": self.stats.exported,
            "dropped": self.stats.dropped,
            "failed": self.stats.failed,
            "retried": self.stats.retried,
            "lastError": self.stats.last_error,
            "circuitOpen": self._circuit_open(),
        }

    def close(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        self._thread.join(timeout=timeout)
        try:
            self.exporter.close()
        except Exception:  # noqa: BLE001
            pass


# ── OTLP payload helpers ────────────────────────────────────────────────────
def _iso_from_epoch(value: Any) -> Optional[str]:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime(float(value)))
    except (TypeError, ValueError):
        return None


def _otlp_attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, (int, float)):
        return {"key": key, "value": {"doubleValue": float(value)}}
    return {"key": key, "value": {"stringValue": str(value)}}


def _otlp_span(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "traceId": record.get("traceId"),
        "spanId": record.get("spanId"),
        "parentSpanId": record.get("parentSpanId") or "",
        "name": record.get("name"),
        "kind": 1,
        "startTimeUnixNano": str(int(float(record.get("startTime") or 0) * 1e9)),
        "endTimeUnixNano": str(int(float(record.get("endTime") or record.get("startTime") or 0) * 1e9)),
        "attributes": [_otlp_attr(k, v) for k, v in (record.get("attributes") or {}).items()],
        "status": {"code": 2 if record.get("status") == "ERROR" else 1},
    }


def _otlp_log(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "timeUnixNano": str(int(float(record.get("startTime") or time.time()) * 1e9)),
        "severityText": str(record.get("status") or "INFO"),
        "body": {"stringValue": str(record.get("name") or record.get("message") or "")},
        "attributes": [_otlp_attr(k, v) for k, v in (record.get("attributes") or {}).items()],
    }


def _otlp_metric(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": record.get("name"),
        "gauge": {"dataPoints": [{
            "asDouble": float(record.get("value") or 0),
            "timeUnixNano": str(int(float(record.get("startTime") or time.time()) * 1e9)),
            "attributes": [_otlp_attr(k, v) for k, v in (record.get("labels") or {}).items()],
        }]},
    }


__all__ = [
    "Exporter",
    "BaseExporter",
    "InMemoryExporter",
    "ConsoleExporter",
    "JsonlFileExporter",
    "OtlpHttpExporter",
    "LangfuseExporter",
    "SentryExporter",
    "BoundedExporter",
    "ExporterStats",
    "EXPORT_KINDS",
]

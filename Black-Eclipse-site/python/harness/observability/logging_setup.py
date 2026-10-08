"""Structured JSON logging — trace-correlated, redacted, level-filterable.

`configure_logging()` installs a `JsonFormatter` on the `harness` logger tree
(additive: it sets a handler + propagates, without removing other handlers) and a
`ContextFilter` that injects the active `ObservationContext` ids into every
record. Logs are redacted through the shared `Redactor` before serialization.

The formatter emits one JSON object per line with the canonical field set:
timestamp, level, service, component/logger, event_name, trace/span ids, the
correlation ids, message, duration_ms, status and error fields.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from .context import ObservationContext, current_context
from .redaction import Redactor, get_default_redactor

_LEVELS = {
    "TRACE": 5,
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "FATAL": logging.CRITICAL,
    "CRITICAL": logging.CRITICAL,
}

LOG_ATTRS = (
    "service", "component", "event_name", "duration_ms", "status",
    "error_type", "stack_trace", "run_id", "task_id", "agent_id",
    "workflow_id", "job_id", "worker_id", "tool_name", "provider", "model",
)


class ContextFilter(logging.Filter):
    def __init__(self, *, service: str = "eclipse-harness", redactor: Optional[Redactor] = None) -> None:
        super().__init__()
        self.service = service
        self.redactor = redactor or get_default_redactor()

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = current_context()
        record.obs_context = ctx
        record.service = getattr(record, "service", self.service)
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, *, redactor: Optional[Redactor] = None) -> None:
        super().__init__()
        self.redactor = redactor or get_default_redactor()

    def format(self, record: logging.LogRecord) -> str:
        ctx: Optional[ObservationContext] = getattr(record, "obs_context", None) or current_context()
        payload: dict[str, Any] = {
            "timestamp": _iso(record.created),
            "level": record.levelname,
            "service": getattr(record, "service", "eclipse-harness"),
            "component": record.name,
            "event_name": getattr(record, "event_name", None) or record.funcName,
            "message": self.redactor.redact_text(record.getMessage()),
        }
        if ctx is not None:
            payload.update({
                "trace_id": ctx.trace_id,
                "span_id": ctx.span_id,
                "parent_span_id": ctx.parent_span_id,
                "session_id": ctx.session_id,
                "request_id": ctx.request_id,
                "run_id": ctx.run_id,
                "agent_id": ctx.agent_id,
                "task_id": ctx.task_id,
                "workflow_id": ctx.workflow_id,
                "job_id": ctx.job_id,
                "worker_id": ctx.worker_id,
            })
        for attr in LOG_ATTRS:
            value = getattr(record, attr, None)
            if value is not None:
                payload[attr] = self.redactor.redact(value)
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["stack_trace"] = self.redactor.redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx: Optional[ObservationContext] = getattr(record, "obs_context", None) or current_context()
        prefix = f"[trace={ctx.trace_id[:12]}] " if ctx is not None else ""
        return f"{_iso(record.created)} {record.levelname} {record.name} {prefix}{record.getMessage()}"


def _iso(created: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(created)) + f".{int((created % 1) * 1000):03d}Z"


_installed = False


def configure_logging(
    *,
    level: str = "INFO",
    service: str = "eclipse-harness",
    json_output: bool = True,
    redactor: Optional[Redactor] = None,
) -> dict[str, Any]:
    """Install the structured handler on the `harness` logger (idempotent)."""
    global _installed
    redactor = redactor or get_default_redactor()
    logger = logging.getLogger("harness")
    logger.setLevel(_LEVELS.get(str(level).upper(), logging.INFO))
    if not _installed:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter(redactor=redactor) if json_output else PlainFormatter())
        handler.addFilter(ContextFilter(service=service, redactor=redactor))
        logger.addHandler(handler)
        # Our handler is the harness tree's single sink; stop propagation to the
        # root handler so a structured line is never duplicated as a plain one.
        logger.propagate = False
        _installed = True
    return {"installed": _installed, "level": logging.getLevelName(logger.level), "json": json_output}


def log_event(logger: logging.Logger, event_name: str, message: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Emit a structured log line carrying explicit correlation fields."""
    extra = {"event_name": event_name}
    extra.update({k: v for k, v in fields.items() if k in LOG_ATTRS})
    logger.log(level, message, extra=extra)


__all__ = ["configure_logging", "JsonFormatter", "ContextFilter", "log_event", "LOG_ATTRS"]

"""Centralized observability configuration (env-driven, no hardcoded secrets).

One config object is resolved once per process from `ECLIPSE_OBSERVABILITY_*`,
`ECLIPSE_OTEL_*`, `ECLIPSE_LANGFUSE_*`, `ECLIPSE_SENTRY_*` and the shared
`ECLIPSE_LOG_*` variables. Every downstream component reads THIS object so there
is exactly one place a toggle, endpoint, sample rate or capture mode is decided.

Precedence (highest first): explicit process env, optional JSON file
(`ECLIPSE_OBSERVABILITY_CONFIG`), built-in defaults. Nothing here can raise:
a malformed value falls back to its default and is recorded in `problems`, so a
bad env var degrades observability — never the runtime.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("harness.observability.config")

CAPTURE_MODES = ("OFF", "METADATA_ONLY", "SUMMARY", "FULL")


def _truthy(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on", "enabled")


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class ObservabilityConfig:
    enabled: bool = True
    service_name: str = "eclipse-harness"
    environment: str = "development"
    release: str = ""

    log_level: str = "INFO"
    log_json: bool = True

    trace_sample_rate: float = 1.0
    always_sample_errors: bool = True

    capture_mode: str = "SUMMARY"
    redaction_enabled: bool = True
    redact_pii: bool = False

    telemetry_timeout_s: float = 2.0
    queue_size: int = 2048
    batch_size: int = 64
    batch_interval_s: float = 1.0
    max_retries: int = 2
    circuit_failure_threshold: int = 5
    circuit_reset_s: float = 30.0
    retention_spans: int = 5000
    retention_traces: int = 500

    # Exporters
    otel_enabled: bool = False
    otel_endpoint: str = ""
    otel_headers: dict[str, str] = field(default_factory=dict)
    prometheus_enabled: bool = True
    langfuse_enabled: bool = False
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    sentry_enabled: bool = False
    sentry_dsn: str = ""
    jsonl_dir: str = ""
    console_export: bool = False

    # SLO defaults (overridable per deployment)
    slo_agent_success_rate: float = 0.99
    slo_tool_success_rate: float = 0.98

    problems: list[str] = field(default_factory=list)
    source: str = "defaults"

    @property
    def effective_name(self) -> str:
        return self.service_name or "eclipse-harness"

    def to_dict(self, *, redact: bool = True) -> dict[str, Any]:
        out = {
            "enabled": self.enabled,
            "serviceName": self.service_name,
            "environment": self.environment,
            "release": self.release,
            "logLevel": self.log_level,
            "logJson": self.log_json,
            "traceSampleRate": self.trace_sample_rate,
            "alwaysSampleErrors": self.always_sample_errors,
            "captureMode": self.capture_mode,
            "redactionEnabled": self.redaction_enabled,
            "redactPii": self.redact_pii,
            "telemetryTimeoutSeconds": self.telemetry_timeout_s,
            "queueSize": self.queue_size,
            "retention": {"spans": self.retention_spans, "traces": self.retention_traces},
            "exporters": {
                "otel": {"enabled": self.otel_enabled, "endpoint": self.otel_endpoint},
                "prometheus": {"enabled": self.prometheus_enabled},
                "langfuse": {
                    "enabled": self.langfuse_enabled,
                    "host": self.langfuse_host,
                    "configured": bool(self.langfuse_public_key and self.langfuse_secret_key),
                },
                "sentry": {"enabled": self.sentry_enabled, "configured": bool(self.sentry_dsn)},
                "jsonlDir": self.jsonl_dir,
            },
            "slos": {
                "agentSuccessRate": self.slo_agent_success_rate,
                "toolSuccessRate": self.slo_tool_success_rate,
            },
            "source": self.source,
            "problems": list(self.problems),
        }
        if not redact:
            out["exporters"]["langfuse"]["publicKey"] = self.langfuse_public_key
            out["exporters"]["langfuse"]["secretKey"] = self.langfuse_secret_key
            out["exporters"]["sentry"]["dsn"] = self.sentry_dsn
            out["exporters"]["otel"]["headers"] = dict(self.otel_headers)
        return out


def _load_file(path: str) -> dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001 - a bad file must not break boot
        log.warning("observability config file unreadable (%s): %s", path, exc)
        return {}


def load_config(environ: Optional[dict[str, str]] = None) -> ObservabilityConfig:
    """Resolve the process observability config. Never raises."""
    env = environ if environ is not None else dict(os.environ)
    problems: list[str] = []
    source = "env"

    file_data: dict[str, Any] = {}
    config_path = env.get("ECLIPSE_OBSERVABILITY_CONFIG", "")
    if config_path:
        file_data = _load_file(config_path)
        source = "env+file" if file_data else "env"

    def pick(key: str, default: Any = None) -> Any:
        if key in env and env[key] != "":
            return env[key]
        if key.lower() in file_data:
            return file_data[key.lower()]
        if key in file_data:
            return file_data[key]
        return default

    cfg = ObservabilityConfig(source=source)
    try:
        cfg.enabled = _truthy(pick("ECLIPSE_OBSERVABILITY_ENABLED"), True)
        cfg.service_name = str(pick("ECLIPSE_OBSERVABILITY_SERVICE_NAME", env.get("OTEL_SERVICE_NAME", "eclipse-harness")) or "eclipse-harness")
        cfg.environment = str(pick("ECLIPSE_ENVIRONMENT", env.get("NODE_ENV", "development")) or "development")
        cfg.release = str(pick("ECLIPSE_RELEASE", "") or "")

        cfg.log_level = str(pick("ECLIPSE_LOG_LEVEL", "INFO") or "INFO").upper()
        if cfg.log_level not in ("TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"):
            problems.append(f"unknown ECLIPSE_LOG_LEVEL '{cfg.log_level}', using INFO")
            cfg.log_level = "INFO"
        cfg.log_json = _truthy(pick("ECLIPSE_LOG_JSON"), True)

        cfg.trace_sample_rate = max(0.0, min(1.0, _float(pick("ECLIPSE_TRACE_SAMPLE_RATE"), 1.0)))
        cfg.always_sample_errors = _truthy(pick("ECLIPSE_TRACE_ALWAYS_SAMPLE_ERRORS"), True)

        mode = str(pick("ECLIPSE_CAPTURE_MODE", "SUMMARY") or "SUMMARY").upper()
        if mode not in CAPTURE_MODES:
            problems.append(f"unknown ECLIPSE_CAPTURE_MODE '{mode}', using SUMMARY")
            mode = "SUMMARY"
        cfg.capture_mode = mode

        cfg.redaction_enabled = _truthy(pick("ECLIPSE_REDACTION_ENABLED"), True)
        cfg.redact_pii = _truthy(pick("ECLIPSE_REDACT_PII"), False)

        cfg.telemetry_timeout_s = max(0.05, _float(pick("ECLIPSE_TELEMETRY_TIMEOUT"), 2.0))
        cfg.queue_size = max(64, _int(pick("ECLIPSE_TELEMETRY_QUEUE_SIZE"), 2048))
        cfg.batch_size = max(1, _int(pick("ECLIPSE_TELEMETRY_BATCH_SIZE"), 64))
        cfg.batch_interval_s = max(0.05, _float(pick("ECLIPSE_TELEMETRY_BATCH_INTERVAL"), 1.0))
        cfg.max_retries = max(0, _int(pick("ECLIPSE_TELEMETRY_RETRIES"), 2))
        cfg.circuit_failure_threshold = max(1, _int(pick("ECLIPSE_TELEMETRY_CIRCUIT_THRESHOLD"), 5))
        cfg.circuit_reset_s = max(1.0, _float(pick("ECLIPSE_TELEMETRY_CIRCUIT_RESET"), 30.0))
        cfg.retention_spans = max(100, _int(pick("ECLIPSE_TELEMETRY_RETENTION_SPANS"), 5000))
        cfg.retention_traces = max(10, _int(pick("ECLIPSE_TELEMETRY_RETENTION_TRACES"), 500))
        # `ECLIPSE_TELEMETRY_RETENTION` names a retention window in days for file
        # exporters; accept it without inventing a prune daemon this process.
        cfg.jsonl_dir = str(pick("ECLIPSE_TELEMETRY_JSONL_DIR", "") or "")

        cfg.otel_enabled = _truthy(pick("ECLIPSE_OTEL_ENABLED"), False)
        cfg.otel_endpoint = str(pick("ECLIPSE_OTEL_ENDPOINT", "") or "")
        headers_raw = pick("ECLIPSE_OTEL_HEADERS", "")
        if headers_raw:
            try:
                parsed = json.loads(headers_raw) if str(headers_raw).strip().startswith("{") else {}
                cfg.otel_headers = {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}
            except (ValueError, TypeError):
                problems.append("ECLIPSE_OTEL_HEADERS is not valid JSON; ignored")
        cfg.prometheus_enabled = _truthy(pick("ECLIPSE_PROMETHEUS_ENABLED"), True)

        cfg.langfuse_enabled = _truthy(pick("ECLIPSE_LANGFUSE_ENABLED"), False)
        cfg.langfuse_host = str(pick("ECLIPSE_LANGFUSE_HOST", "") or "")
        cfg.langfuse_public_key = str(pick("ECLIPSE_LANGFUSE_PUBLIC_KEY", "") or "")
        cfg.langfuse_secret_key = str(pick("ECLIPSE_LANGFUSE_SECRET_KEY", "") or "")

        cfg.sentry_enabled = _truthy(pick("ECLIPSE_SENTRY_ENABLED"), False)
        cfg.sentry_dsn = str(pick("ECLIPSE_SENTRY_DSN", "") or "")

        cfg.console_export = _truthy(pick("ECLIPSE_TELEMETRY_CONSOLE"), False)

        cfg.slo_agent_success_rate = max(0.0, min(1.0, _float(pick("ECLIPSE_SLO_AGENT_SUCCESS_RATE"), 0.99)))
        cfg.slo_tool_success_rate = max(0.0, min(1.0, _float(pick("ECLIPSE_SLO_TOOL_SUCCESS_RATE"), 0.98)))
    except Exception as exc:  # noqa: BLE001 - config resolution must never raise
        problems.append(f"config resolution error: {exc}")

    # An enabled backend with no credentials is downgraded to disabled with an
    # explicit problem, so `status` never claims a healthy backend that is inert.
    if cfg.langfuse_enabled and not (cfg.langfuse_public_key and cfg.langfuse_secret_key):
        problems.append("ECLIPSE_LANGFUSE_ENABLED set but keys missing; Langfuse disabled")
        cfg.langfuse_enabled = False
    if cfg.sentry_enabled and not cfg.sentry_dsn:
        problems.append("ECLIPSE_SENTRY_ENABLED set but ECLIPSE_SENTRY_DSN missing; Sentry disabled")
        cfg.sentry_enabled = False
    if cfg.otel_enabled and not cfg.otel_endpoint:
        problems.append("ECLIPSE_OTEL_ENABLED set but ECLIPSE_OTEL_ENDPOINT missing; OTel disabled")
        cfg.otel_enabled = False

    cfg.problems = problems
    return cfg


__all__ = ["ObservabilityConfig", "load_config", "CAPTURE_MODES"]

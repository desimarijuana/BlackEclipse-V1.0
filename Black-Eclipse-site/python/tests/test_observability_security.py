"""Security tests — secrets must never reach telemetry sinks."""

from __future__ import annotations

import json
import logging

from harness.observability.config import ObservabilityConfig
from harness.observability.core import ObservabilityHub
from harness.observability.events import make_event
from harness.observability.logging_setup import ContextFilter, JsonFormatter


def _hub() -> ObservabilityHub:
    return ObservabilityHub(ObservabilityConfig(jsonl_dir=""), capture_inmemory=True, start_exporters=False)


def test_secrets_absent_from_error_sink():
    hub = _hub()
    hub.emit(
        "onLLMError",
        provider="openai",
        model="gpt-4o-mini",
        error_type="AuthError",
        error_message="request failed with Authorization: Bearer sk-live-SUPERSECRET123456 and api_key=abc123",
    )
    blob = json.dumps(hub.errors())
    assert "SUPERSECRET123456" not in blob
    assert "abc123" not in blob
    assert "[REDACTED]" in blob


def test_secrets_absent_from_span_attributes_and_exports():
    hub = _hub()
    memory = hub.inmemory
    with hub.span("eclipse.tool.http", kind="tool", attributes={
        "authorization": "Bearer sk-live-DEADBEEF",
        "url": "postgres://admin:pw123@db.internal/eclipse",
        "cookie": "session=abc",
    }):
        pass
    records = memory.records()
    blob = json.dumps(records)
    assert "DEADBEEF" not in blob
    assert "pw123" not in blob
    assert "session=abc" not in blob


def test_redaction_before_event_export():
    hub = _hub()
    event = make_event("onToolEnd", tool_name="http", status="OK",
                       attributes={"api_key": "sk-secret", "header": "Bearer tok123"})
    payload = event.redacted()
    blob = json.dumps(payload)
    assert "sk-secret" not in blob
    assert "tok123" not in blob


def test_json_log_formatter_redacts_and_correlates():
    hub = _hub()  # installs the default redactor
    formatter = JsonFormatter(redactor=hub.redactor)
    record = logging.LogRecord(
        name="harness.test", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="failed with token=sk-LOGSECRET", args=(), exc_info=None,
    )
    ContextFilter(service="eclipse-harness", redactor=hub.redactor).filter(record)
    output = formatter.format(record)
    payload = json.loads(output)
    assert "LOGSECRET" not in output
    assert payload["level"] == "ERROR"
    assert "trace_id" in payload


def test_langfuse_credentials_not_in_records():
    from harness.observability.exporters import LangfuseExporter

    exporter = LangfuseExporter("https://cloud.langfuse.com", "pk-public", "sk-secret-value")
    assert "sk-secret-value" not in json.dumps({"name": exporter.name})

"""Event System core tests — envelope, registry, filters, store, security.

The event store is exercised over a real temporary `agent-memory.db` (the same
SQLite path the runtime uses), so the schema, indexes and idempotency SQL are the
production ones.
"""

from __future__ import annotations

import pytest

from harness.event_system.envelope import (
    Actor,
    EclipseEvent,
    canonical_legacy_type,
    causation_id,
    correlation_id,
    event_context,
    from_legacy,
    redact_payload,
    redact_text,
)
from harness.event_system.filters import EventFilter
from harness.event_system.metrics import EventMetrics
from harness.event_system.registry import default_registry
from harness.event_system.security import EventAuthorizer, sanitize
from harness.event_system.store import EventStore
from harness.persistence import AgentMemoryStore
from harness.skills.permissions import OPERATOR_ACTOR
from harness.skills.permissions import Actor as SkillActor


def _store(tmp_workspace) -> tuple[AgentMemoryStore, EventStore]:
    from pathlib import Path

    memory = AgentMemoryStore(str(Path(tmp_workspace) / "agent-memory.db"))
    return memory, EventStore(memory)


# ── Envelope ─────────────────────────────────────────────────────────────────
def test_envelope_identity_and_camel_wire():
    event = EclipseEvent.create("task.completed", {"taskId": "t1"}, source="tasks")
    assert event.id.startswith("evt_")
    assert event.version == 1
    assert event.timestamp.endswith("Z")
    assert event.priority == "normal"
    wire = event.to_dict()
    assert wire["type"] == "task.completed"
    assert wire["correlationId"] is None
    assert wire["payload"] == {"taskId": "t1"}
    # round-trips through the wire form
    clone = EclipseEvent.from_dict(wire)
    assert clone.id == event.id and clone.payload == event.payload


def test_correlation_and_causation_propagate_through_context():
    parent = EclipseEvent.create("user.message", {"text": "hi"}, source="frontdoor")
    with event_context(correlation_id=parent.id, causation_id=None):
        assert correlation_id() == parent.id
        child = parent.child("task.created", {"taskId": "t1"})
    assert child.correlation_id == parent.id
    assert child.causation_id == parent.id
    assert child.depth == 1
    # outside the context the correlation no longer leaks
    assert correlation_id() is None
    assert causation_id() is None


def test_from_legacy_maps_run_into_session_and_reuses_id():
    legacy = {
        "id": "evt_run_3", "runId": "run_abc", "type": "tool.completed",
        "seq": 3, "at": "2026-10-08T00:00:00.000Z", "data": {"name": "web_search"},
    }
    event = from_legacy(legacy)
    assert event.id == "evt_run_3"
    assert event.session_id == "run_abc"
    assert event.metadata["runId"] == "run_abc"
    assert event.payload == {"name": "web_search"}


def test_from_legacy_numeric_timestamp_is_replaced_with_iso():
    event = from_legacy({"id": "e1", "type": "model.completed", "at": 12345.0, "data": {}})
    assert event.timestamp.endswith("Z")


def test_legacy_process_events_normalize_to_canonical():
    assert canonical_legacy_type("terminal.process.started", {}) == "process.started"
    assert canonical_legacy_type("terminal.process.exited", {"exitCode": 0}) == "process.completed"
    assert canonical_legacy_type("terminal.process.exited", {"exitCode": 1}) == "process.failed"
    assert canonical_legacy_type("terminal.process.crashed", {}) == "process.failed"
    assert canonical_legacy_type("browser.clicked", {}) == "browser.clicked"
    event = from_legacy({"id": "e2", "type": "terminal.process.exited", "data": {"exitCode": 0}})
    assert event.type == "process.completed"


# ── Redaction ────────────────────────────────────────────────────────────────
def test_redaction_by_key_and_value():
    payload = {
        "symbol": "BTCUSDT",
        "api_key": "should-not-appear",
        "nested": {"authorization": "Bearer abcdefghijklmnop", "note": "key sk-1234567890abcdefghij"},
        "list": [{"password": "hunter2"}],
    }
    cleaned = redact_payload(payload)
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["authorization"] == "[REDACTED]"
    assert "sk-" not in cleaned["nested"]["note"]
    assert cleaned["list"][0]["password"] == "[REDACTED]"
    assert cleaned["symbol"] == "BTCUSDT"


def test_redact_text_bounded_and_patterns():
    assert "ghp_" not in redact_text("token ghp_" + "a" * 30)
    assert redact_text("Bearer abcdefghijklmnop") == "[REDACTED]"


# ── Registry ─────────────────────────────────────────────────────────────────
def test_registry_resolves_exact_and_namespace():
    registry = default_registry()
    assert registry.get("task.completed").priority == "normal"
    assert registry.get("market.price.updated").priority == "bulk"
    resolved = registry.get("browser.clicked")  # resolved via the browser namespace default
    assert resolved is not None and resolved.namespace is True and resolved.type == "browser"
    assert resolved.priority == "normal"
    assert registry.get("totally.unknown") is None
    assert registry.latest_version("task.completed") == 1


def test_registry_validation_reports_issues():
    registry = default_registry()
    missing = registry.validate(EclipseEvent.create("task.completed", {}, source="tasks"), require_known=True)
    assert any("missing required payload" in issue for issue in missing)
    unknown = registry.validate(EclipseEvent.create("nope.nope", {}, source="x"), require_known=True)
    assert any("unknown event type" in issue for issue in unknown)
    ok = registry.validate(EclipseEvent.create("task.completed", {"taskId": "t"}, source="tasks"), require_known=True)
    assert ok == []


# ── Filters ──────────────────────────────────────────────────────────────────
def test_filter_exact_namespace_and_predicate():
    exact = EventFilter.exact("task.completed")
    assert exact.matches(EclipseEvent.create("task.completed", {}, source="s"))
    assert not exact.matches(EclipseEvent.create("task.failed", {}, source="s"))

    ns = EventFilter.namespace("market")
    assert ns.matches(EclipseEvent.create("market.price.updated", {}, source="s"))
    assert not ns.matches(EclipseEvent.create("task.created", {}, source="s"))

    pred = EventFilter(patterns=("market.price.updated",), predicate="payload.changePercent > 5")
    assert pred.matches(EclipseEvent.create("market.price.updated", {"changePercent": 9}, source="s"))
    assert not pred.matches(EclipseEvent.create("market.price.updated", {"changePercent": 1}, source="s"))


def test_filter_predicate_malformed_is_fail_closed():
    pred = EventFilter(patterns=("x.y",), predicate="this is not (valid")
    assert not pred.matches(EclipseEvent.create("x.y", {}, source="s"))


# ── Store ────────────────────────────────────────────────────────────────────
def test_store_roundtrip_and_indexed_queries(tmp_workspace):
    _, store = _store(tmp_workspace)
    e1 = EclipseEvent.create("task.created", {"taskId": "t1"}, source="tasks", correlation_id="c1", task_id="t1", session_id="r1")
    e2 = EclipseEvent.create("task.completed", {"taskId": "t1"}, source="tasks", correlation_id="c1", task_id="t1", causation_id=e1.id)
    e3 = EclipseEvent.create("market.price.updated", {"symbol": "BTCUSDT"}, source="market")
    assert store.append(e1) is True
    assert store.append(e2) is True
    assert store.append(e3) is True
    assert store.append(e1) is False  # duplicate id

    assert store.get(e1.id).type == "task.created"
    assert [e.id for e in store.query(correlation_id="c1", ascending=True)] == [e1.id, e2.id]
    assert [e.task_id for e in store.query(task_id="t1")] == ["t1", "t1"]
    assert [e.type for e in store.query(namespace="market")] == ["market.price.updated"]
    assert store.count() == 3
    graph = store.graph(correlation_id="c1")
    assert {n["id"] for n in graph["nodes"]} == {e1.id, e2.id}
    assert {"from": e1.id, "to": e2.id} in graph["edges"]


def test_store_retention_prune(tmp_workspace):
    _, store = _store(tmp_workspace)
    old = EclipseEvent.create("task.created", {}, source="tasks", timestamp="2020-01-01T00:00:00.000Z")
    new = EclipseEvent.create("task.completed", {}, source="tasks", timestamp="2030-01-01T00:00:00.000Z")
    store.append(old)
    store.append(new)
    removed = store.prune(before_iso="2025-01-01T00:00:00.000Z")
    assert removed == 1
    assert store.count() == 1


def test_store_consumer_idempotency(tmp_workspace):
    _, store = _store(tmp_workspace)
    event = EclipseEvent.create("task.completed", {"taskId": "t1"}, source="tasks")
    assert store.has_processed(event.id, "consumer-a") is False
    assert store.mark_processed(event.id, "consumer-a") is True
    assert store.has_processed(event.id, "consumer-a") is True
    # a second success is a duplicate
    assert store.mark_processed(event.id, "consumer-a") is False
    # a different consumer is independent
    assert store.has_processed(event.id, "consumer-b") is False


def test_store_dead_letter_lifecycle(tmp_workspace):
    _, store = _store(tmp_workspace)
    event = EclipseEvent.create("tool.failed", {"name": "x"}, source="harness")
    store.append(event)
    dlq_id = store.record_dead_letter(
        event_id=event.id, consumer_id="c1", event_type=event.type,
        error="boom", error_class="TOOL_ERROR", attempts=5, first_failed_at=None, stack_trace="trace",
    )
    assert store.dlq_count() == 1
    entry = store.get_dead_letter(dlq_id)
    assert entry["errorClass"] == "TOOL_ERROR" and entry["status"] == "pending"
    assert store.set_dead_letter_status(dlq_id, "replayed") is True
    assert store.dlq_count() == 0
    assert store.delete_dead_letter(dlq_id) is True


def test_store_subscriptions_declared(tmp_workspace):
    _, store = _store(tmp_workspace)
    store.save_subscription(subscriber_id="agent.market", subscriber_type="agent", patterns=["market.*", "filing.discovered"])
    subs = store.list_subscriptions()
    assert subs[0]["subscriberId"] == "agent.market"
    assert "market.*" in subs[0]["patterns"]
    assert store.delete_subscription("agent.market") == 1
    assert store.list_subscriptions() == []


# ── Security / authorizer ────────────────────────────────────────────────────
def test_authorizer_blocks_sensitive_without_operator():
    registry = default_registry()
    auth = EventAuthorizer(registry)
    sensitive = EclipseEvent.create("risk.threshold.breached", {"portfolioId": "p"}, source="portfolio")
    assert auth.authorize_publish(sensitive, SkillActor(id="agent")).allowed is False
    assert auth.authorize_publish(sensitive, OPERATOR_ACTOR).allowed is True
    # ordinary event is allowed for anyone
    ordinary = EclipseEvent.create("task.completed", {"taskId": "t"}, source="tasks")
    assert auth.authorize_publish(ordinary, SkillActor(id="agent")).allowed is True


def test_sanitize_mutates_payload_in_place():
    event = EclipseEvent.create("user.message", {"password": "hunter2", "text": "hi"}, source="frontdoor")
    sanitize(event)
    assert event.payload["password"] == "[REDACTED]"
    assert event.payload["text"] == "hi"


def test_metrics_percentiles_and_counters():
    metrics = EventMetrics()
    metrics.inc("published", 3)
    for value in (1.0, 2.0, 3.0, 4.0, 5.0):
        metrics.observe_processing(value)
    snap = metrics.snapshot()
    assert snap["published"] == 3
    assert snap["processingLatencyMs"]["p50"] is not None
    assert snap["processingLatencyMs"]["samples"] == 5

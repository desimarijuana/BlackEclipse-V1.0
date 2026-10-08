"""The A2A message bus: durable, idempotent, retryable delivery."""

from __future__ import annotations

import time

from harness.a2a import MessageType, make_envelope
from harness.a2a.bus import MessageBus

from a2a_helpers import make_service


def _bus(service, *, max_attempts=3):
    return MessageBus(service.store, event_bus=None, max_attempts=max_attempts)


def test_publish_is_idempotent(tmp_path):
    service, _, _ = make_service(tmp_path)
    bus = _bus(service)
    env = make_envelope(MessageType.STATUS, sender="eclipse-agent", recipient="news-agent",
                        run_id="r", payload={"status": "ok"})
    _, created1 = bus.publish(env)
    _, created2 = bus.publish(env.model_copy())
    assert created1 is True and created2 is False
    assert len(bus.inbox("news-agent")) == 1


def test_consume_ack_lifecycle(tmp_path):
    service, _, _ = make_service(tmp_path)
    bus = _bus(service)
    env = make_envelope(MessageType.QUESTION, sender="eclipse-agent", recipient="research-agent",
                        run_id="r", payload={"question": "why?"})
    bus.publish(env)
    first = bus.consume("research-agent")
    assert len(first) == 1 and first[0].id == env.id
    assert bus.consume("research-agent") == []  # delivered exactly once
    bus.acknowledge(env.id, "research-agent")


def test_reject_dead_letters_past_limit(tmp_path):
    service, _, _ = make_service(tmp_path)
    bus = _bus(service, max_attempts=2)
    env = make_envelope(MessageType.STATUS, sender="eclipse-agent", recipient="news-agent",
                        run_id="r", payload={"status": "ok"})
    bus.publish(env)
    bus.reject(env.id, "news-agent", "boom")   # attempt 1 -> rejected
    bus.reject(env.id, "news-agent", "boom")   # attempt 2 -> dead letter
    dead = bus.dead_letters()
    assert any(d["messageId"] == env.id for d in dead)


def test_broadcast_fans_out_to_active_agents(tmp_path):
    service, _, _ = make_service(tmp_path)
    bus = _bus(service)
    env = make_envelope(MessageType.STATUS, sender="eclipse-agent", recipient=None,
                        run_id="r", payload={"status": "ok"})
    bus.publish(env)
    assert bus.consume("news-agent")
    assert bus.consume("valuation-agent")


def test_expired_message_is_dead_lettered_not_delivered(tmp_path):
    service, _, _ = make_service(tmp_path)
    bus = _bus(service)
    env = make_envelope(MessageType.STATUS, sender="eclipse-agent", recipient="news-agent",
                        run_id="r", payload={"status": "ok"})
    env.timestamp = time.time() - 10
    env.ttl = 1
    bus.publish(env)
    assert bus.consume("news-agent") == []
    assert any(d["messageId"] == env.id for d in bus.dead_letters())


def test_run_thread_lists_messages(tmp_path):
    service, _, _ = make_service(tmp_path)
    bus = _bus(service)
    bus.publish(make_envelope(MessageType.STATUS, sender="eclipse-agent", recipient="news-agent",
                              run_id="run_x", payload={"status": "ok"}))
    bus.publish(make_envelope(MessageType.STATUS, sender="eclipse-agent", recipient="risk-agent",
                              run_id="run_y", payload={"status": "ok"}))
    assert len(bus.thread("run_x")) == 1

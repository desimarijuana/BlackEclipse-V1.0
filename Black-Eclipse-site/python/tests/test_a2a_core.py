"""A2A registry, protocol and budget: the deterministic core."""

from __future__ import annotations

import pytest

from harness.a2a import (
    AgentBudget,
    AgentDefinition,
    AgentStatus,
    BudgetExceeded,
    BudgetTracker,
    MessageType,
    ProtocolError,
    make_envelope,
    validate_envelope,
)
from harness.a2a.protocol import canonical_key
from harness.a2a.registry import AgentRegistry, RegistryError
from harness.a2a.store import A2AStore

from a2a_helpers import make_service


# ── registry ──────────────────────────────────────────────────────────────────


def test_seeded_catalogue_has_specialists(tmp_path):
    service, _, _ = make_service(tmp_path)
    ids = {a["id"] for a in service.list_agents()}
    assert {"eclipse-agent", "eclipse-orchestrator", "valuation-agent", "risk-agent",
            "qa-agent", "trading-agent"} <= ids


def test_capability_index_and_routing(tmp_path):
    service, _, _ = make_service(tmp_path)
    index = service.capability_index()
    assert "valuation-agent" in index["dcf"]
    assert service.registry.capable_agent_for("news") == "news-agent"
    assert service.registry.capable_agent_for("no_such_capability") is None


def test_versioning_bumps_and_persists(tmp_path):
    service, _, _ = make_service(tmp_path)
    updated = service.registry.update_agent("valuation-agent", {"description": "v2"})
    assert updated.version == "1.0.1"
    versions = service.registry.agent_versions("valuation-agent")
    assert {v["version"] for v in versions} == {"1.0.0", "1.0.1"}


def test_enable_disable_roundtrip(tmp_path):
    service, _, _ = make_service(tmp_path)
    service.registry.disable_agent("news-agent")
    assert service.get_agent("news-agent")["status"] == "DISABLED"
    # A disabled agent is not selected by capability routing.
    assert service.registry.capable_agent_for("news") is None
    service.registry.enable_agent("news-agent")
    assert service.registry.capable_agent_for("news") == "news-agent"


def test_validate_refuses_incoherent_definition(tmp_path):
    service, _, _ = make_service(tmp_path)
    bad = AgentDefinition(id="x-agent", name="X", allowed_delegates=["valuation-agent"],
                          can_delegate=False)
    with pytest.raises(RegistryError):
        service.registry.register_agent(bad)


def test_remove_agent(tmp_path):
    service, _, _ = make_service(tmp_path)
    assert service.registry.remove_agent("security-agent") is True
    with pytest.raises(RegistryError):
        service.registry.get_agent("security-agent")


# ── protocol ──────────────────────────────────────────────────────────────────


def test_envelope_requires_payload_keys():
    with pytest.raises(ProtocolError) as exc:
        make_envelope(MessageType.TASK_REQUEST, sender="a", recipient="b", payload={})
    assert exc.value.code == "A2A_PAYLOAD_INVALID"


def test_envelope_needs_sender_and_recipient():
    env = make_envelope(MessageType.STATUS, sender="a", recipient="b", payload={"status": "ok"})
    validate_envelope(env)
    with pytest.raises(ProtocolError):
        validate_envelope(env.model_copy(update={"sender_agent_id": ""}))


def test_idempotency_key_is_stable_and_explicit_wins():
    a = make_envelope(MessageType.STATUS, sender="a", recipient="b", payload={"status": "ok"})
    b = make_envelope(MessageType.STATUS, sender="a", recipient="b", payload={"status": "ok"})
    assert canonical_key(a) == canonical_key(b)
    c = make_envelope(MessageType.STATUS, sender="a", recipient="b",
                      payload={"status": "ok"}, )
    c.idempotency_key = "fixed"
    assert canonical_key(c) == "fixed"


def test_broadcast_envelope_allowed_without_recipient():
    env = make_envelope(MessageType.STATUS, sender="a", recipient=None, payload={"status": "ok"})
    assert env.recipient_agent_id is None


# ── budget ────────────────────────────────────────────────────────────────────


def test_budget_reserve_and_exhaust(tmp_path):
    service, _, _ = make_service(tmp_path)
    tracker = BudgetTracker(service.store)
    tracker.set_limits("r1", max_agents=1)
    tracker.reserve("r1", "agents")
    with pytest.raises(BudgetExceeded):
        tracker.reserve("r1", "agents")


def test_budget_depth_cap(tmp_path):
    service, _, _ = make_service(tmp_path)
    tracker = BudgetTracker(service.store)
    tracker.set_limits("r2", max_depth=1)
    tracker.reserve("r2", "depth")
    with pytest.raises(BudgetExceeded) as exc:
        tracker.reserve("r2", "depth")
    assert exc.value.kind == "depth"


def test_child_budget_only_narrows():
    parent = AgentBudget(max_agents=10, max_depth=4, max_tasks=100, max_tokens=1000,
                         max_cost=10.0, max_runtime_ms=100_000, max_tool_calls=100)
    parent.agents_spawned = 3
    child = parent.sub_budget()
    assert child.max_agents <= 7
    assert child.max_depth < parent.max_depth
    assert child.max_tokens <= 500

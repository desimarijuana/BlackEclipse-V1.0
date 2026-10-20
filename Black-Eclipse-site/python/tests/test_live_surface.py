"""Live surface application: base-digest check, safe fields, rollback."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.schemas import AgentConfig
from harness.self_improvement.live_surface import apply_active_surface
from harness.self_improvement.models import HarnessSnapshot
from harness.self_improvement.state import HarnessStateStore


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _agent() -> AgentConfig:
    return AgentConfig(
        id="eclipse-agent",
        name="Eclipse",
        systemPrompt="base prompt",
        tools=["tool_a", "tool_b"],
        maxSteps=8,
        maxToolCalls=10,
    )


def _base() -> HarnessSnapshot:
    return HarnessSnapshot(
        systemPrompt="base prompt",
        toolNames=("tool_a", "tool_b"),
        maxSteps=8,
        maxToolCalls=10,
    )


def _candidate() -> HarnessSnapshot:
    return HarnessSnapshot(
        systemPrompt="measured prompt",
        toolNames=("tool_a",),
        maxSteps=6,
        maxToolCalls=8,
    )


def _activate(store, *, scope="eclipse-agent"):
    states = HarnessStateStore(store)
    root = states.save_state({
        "scope": scope, "snapshotDigest": "base",
        "metrics": {"aggregates": {"task_success": 0.7}},
        "utility": 0.7, "status": "current",
    })
    state = states.save_state({
        "scope": scope, "snapshotDigest": "candidate",
        "metrics": {"aggregates": {"task_success": 0.8}},
        "utility": 0.8, "status": "candidate", "parentStateId": root["id"],
    })
    activation = states.activate_surface(
        state["id"], snapshot=_candidate().to_dict(), base=_base().to_dict(),
    )
    return states, root, state, activation


def test_activation_replaces_prompt_tools_and_ceilings(store):
    states, _, _, activation = _activate(store)

    updated, applied = apply_active_surface(store, _agent())

    assert applied["id"] == activation["id"]
    assert updated.systemPrompt == "measured prompt"
    assert updated.tools == ["tool_a"]
    assert updated.maxSteps == 6
    assert updated.maxToolCalls == 8
    # Authority-bearing fields are preserved from the base agent.
    assert updated.allowMcpTools == _agent().allowMcpTools
    assert updated.allowPluginTools == _agent().allowPluginTools


def test_base_digest_change_skips_the_activation(store):
    states = HarnessStateStore(store)
    state = states.save_state({
        "scope": "eclipse-agent", "snapshotDigest": "candidate",
        "metrics": {"aggregates": {"task_success": 0.8}},
        "utility": 0.8, "status": "current",
    })
    states.activate_surface(
        state["id"], snapshot=_candidate().to_dict(), base=_base().to_dict(),
    )
    changed = _agent().model_copy(update={"systemPrompt": "a different base"})

    updated, applied = apply_active_surface(store, changed)

    assert updated.systemPrompt == "a different base"
    assert applied["skipped"] == "base_changed"


def test_no_activation_leaves_the_agent_unchanged(store):
    agent = _agent()
    updated, applied = apply_active_surface(store, agent)
    assert updated == agent
    assert applied is None


def test_invalid_snapshot_is_refused(store):
    states = HarnessStateStore(store)
    state = states.save_state({
        "scope": "eclipse-agent", "snapshotDigest": "candidate",
        "metrics": {"aggregates": {"task_success": 0.8}},
        "utility": 0.8, "status": "current",
    })
    bad = HarnessSnapshot(
        systemPrompt="bad", toolNames=("tool_c",), maxSteps=8, maxToolCalls=10,
    )
    states.activate_surface(
        state["id"], snapshot=bad.to_dict(), base=_base().to_dict(),
    )

    updated, applied = apply_active_surface(store, _agent())

    assert updated.systemPrompt == "base prompt"
    assert applied is None


def test_rollback_restores_the_previous_current(store):
    states, root, _, activation = _activate(store)

    states.rollback_activation(activation["id"])

    assert states.current("eclipse-agent")["id"] == root["id"]
    updated, applied = apply_active_surface(store, _agent())
    assert updated.systemPrompt == "base prompt"
    assert applied is None


def test_promoting_another_state_disables_the_live_surface(store):
    states, _, _, _ = _activate(store)
    other = states.save_state({
        "scope": "eclipse-agent", "snapshotDigest": "other",
        "metrics": {"aggregates": {"task_success": 0.9}},
        "utility": 0.9, "status": "candidate",
    })

    states.promote(other["id"])
    updated, applied = apply_active_surface(store, _agent())

    assert updated.systemPrompt == "base prompt"
    assert applied is None


def test_global_activation_applies_to_a_matching_agent(store):
    _activate(store, scope="global")
    updated, applied = apply_active_surface(store, _agent())
    assert updated.systemPrompt == "measured prompt"
    assert applied is not None

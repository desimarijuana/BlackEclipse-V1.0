"""HarnessState: append-only lineage and one current state per scope."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.self_improvement.state import HarnessStateStore


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


@pytest.fixture()
def states(store):
    return HarnessStateStore(store)


def _state(states, *, digest="d1", scope="global", status="candidate", parent=None):
    return states.save_state({
        "parentStateId": parent,
        "scope": scope,
        "snapshotDigest": digest,
        "candidateId": "evo_1",
        "acceptedRunId": "evalrun_1",
        "utility": 0.5,
        "metrics": {"aggregates": {"task_success": 0.5}},
        "status": status,
    })


def test_state_requires_a_snapshot_digest(states):
    with pytest.raises(ValueError):
        states.save_state({"scope": "global", "snapshotDigest": ""})


def test_promote_supersedes_the_previous_current(states):
    first = _state(states, digest="d1", status="current")
    second = _state(states, digest="d2", parent=first["id"])

    promoted = states.promote(second["id"])

    assert promoted["status"] == "current"
    assert promoted["promotedAt"]
    assert states.get_state(first["id"])["status"] == "superseded"
    assert states.current("global")["id"] == second["id"]


def test_scopes_have_independent_current_states(states):
    finance = _state(states, digest="finance", scope="finance", status="current")
    research = _state(states, digest="research", scope="research", status="current")

    assert states.current("finance")["id"] == finance["id"]
    assert states.current("research")["id"] == research["id"]
    assert states.current("global") is None


def test_lineage_walks_back_to_the_root(states):
    root = _state(states, digest="d1", status="current")
    child = _state(states, digest="d2", parent=root["id"])
    grandchild = _state(states, digest="d3", parent=child["id"])

    chain = states.lineage(grandchild["id"])

    assert [row["id"] for row in chain] == [grandchild["id"], child["id"], root["id"]]


def test_retired_state_is_kept_and_cannot_be_promoted(states):
    state = _state(states, digest="d1")
    retired = states.retire(state["id"])

    assert retired["status"] == "retired"
    assert states.get_state(state["id"]) is not None
    with pytest.raises(ValueError):
        states.promote(state["id"])

"""The surface candidate path: one identity, and the lab stages evidence."""

from __future__ import annotations

import pytest

from harness.code.evolution_store import EvolutionStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.models import HarnessSnapshot
from harness.self_improvement.surface_candidate import (
    save_surface_candidate,
    surface_signature,
)
from harness.self_improvement.surface_lab import stage_winner


@pytest.fixture()
def store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield memory
    memory.close()


def _base() -> HarnessSnapshot:
    return HarnessSnapshot(
        systemPrompt="You are Eclipse.",
        toolNames=("eval_service_call",),
        maxSteps=8,
        maxToolCalls=20,
    )


def _candidate() -> HarnessSnapshot:
    return HarnessSnapshot(
        systemPrompt="You are Eclipse.",
        toolNames=("eval_service_call",),
        toolGuidance="- do the bounded thing",
        maxSteps=8,
        maxToolCalls=20,
    )


def test_the_identity_is_deterministic_and_changes_with_the_config():
    first = surface_signature(
        base_digest="b", snapshot_digest="s", dataset="d", split="validation",
        task_ids=["b", "a"], target_dimension="task_success", trials=1,
        seed=None, baseline_run_id=None,
    )
    second = surface_signature(
        base_digest="b", snapshot_digest="s", dataset="d", split="validation",
        task_ids=["a", "b"], target_dimension="task_success", trials=1,
        seed=None, baseline_run_id=None,
    )
    assert first == second
    other = surface_signature(
        base_digest="b", snapshot_digest="s", dataset="d", split="held_out",
        task_ids=["a", "b"], target_dimension="task_success", trials=1,
        seed=None, baseline_run_id=None,
    )
    assert other != first


def test_saving_the_same_experiment_twice_creates_one_row(store):
    kwargs = dict(
        base=_base(), snapshot=_candidate(), task_ids=["t1"], split="validation",
        dataset="benchmark_v1", trials=1, status="inert",
    )
    first = save_surface_candidate(store, **kwargs)
    second = save_surface_candidate(store, **kwargs)
    assert first["created"] is True
    assert second["created"] is False
    assert second["candidate"]["id"] == first["candidate"]["id"]
    assert second["candidate"]["status"] == "inert"
    assert second["candidate"]["subjectType"] == "surface"


def test_the_lab_stages_its_winner_as_an_inert_candidate(store):
    lab = {
        "winner": "lesson-1",
        "winnerSnapshot": {
            "name": "lesson-1",
            "kind": "toolGuidance",
            "derivedFrom": ["lesson-0"],
            "toolGuidance": "- do the bounded thing",
            "delta": 0.05,
        },
    }
    staged = stage_winner(
        store, lab, base=_base(), task_ids=["t1"], dataset="benchmark_v1",
    )
    assert staged["staged"] is True
    row = EvolutionStore(store).get_candidate(staged["candidateId"])
    assert row["status"] == "inert"
    assert row["subjectType"] == "surface"
    assert row["sourceCategory"] == "surface-lab"
    assert "do the bounded thing" in row["surfaceConfig"]["snapshot"]["toolGuidance"]
    assert "lesson-0" in row["problemStatement"]


def test_without_a_winner_nothing_is_staged(store):
    staged = stage_winner(
        store, {"winner": None}, base=_base(), task_ids=["t1"],
    )
    assert staged["staged"] is False
    assert EvolutionStore(store).list_candidates(limit=10) == []

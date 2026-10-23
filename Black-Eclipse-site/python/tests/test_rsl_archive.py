"""The measured-state archive and its deterministic parent sampler."""

from __future__ import annotations

import random

from harness.persistence import AgentMemoryStore
from harness.self_improvement.archive import ArchiveConfig, StateArchive
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.hillclimb import HillClimbConfig, run_hillclimb
from harness.self_improvement.sampler import novelty, sample, scores
from harness.self_improvement.state import HarnessStateStore


def _measured(success: float, *, measured: int = 10) -> dict:
    return {
        "aggregates": {"task_success": success},
        "measuredTrials": measured,
    }


def _state(state_id: str, digest: str, utility: float, *, status="stepping_stone"):
    return {
        "id": state_id,
        "snapshotDigest": digest,
        "scope": "global",
        "utility": utility,
        "metrics": _measured(utility),
        "status": status,
    }


# -- sampler ---------------------------------------------------------------


def test_weighted_sampling_prefers_the_higher_utility():
    pool = [
        _state("low", "d-low", 0.2),
        _state("high", "d-high", 0.9),
    ]
    rng = random.Random(7)
    picks = [sample(pool, rng=rng, mode="weighted")["id"] for _ in range(400)]

    assert picks.count("high") > picks.count("low")


def test_uct_explores_an_under_sampled_state():
    pool = [
        {**_state("seen", "d-seen", 1.0), "visitCount": 20},
        {**_state("new", "d-new", 0.0), "visitCount": 0},
    ]
    rng = random.Random(3)
    picks = [sample(pool, rng=rng, mode="uct")["id"] for _ in range(400)]

    assert picks.count("new") > 0


def test_sampling_excludes_tabu_digests():
    pool = [_state("a", "d-a", 0.5)]
    assert sample(pool, rng=random.Random(1), exclude_digests=["d-a"]) is None


def test_novelty_is_one_for_a_new_digest_and_zero_for_a_repeat():
    state = _state("a", "d-a", 0.5)
    assert novelty(state, [state]) == 1.0
    assert novelty(state, [{**state, "id": "b"}]) == 0.0


def test_scores_are_transparent_and_stable():
    pool = [_state("a", "d-a", 0.4), _state("b", "d-b", 0.8)]
    assert scores(pool) == scores(pool)


# -- archive ---------------------------------------------------------------


def test_archive_retains_measured_states_and_dedupes(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        states = HarnessStateStore(memory)
        archive = StateArchive(states, ArchiveConfig(max_states=10))

        first = archive.retain(_state("s1", "d-1", 0.6))
        again = archive.retain(_state("s1-again", "d-1", 0.6))

        assert first["retained"] is True
        assert again["retained"] is False and again["reason"] == "duplicate"
        stored = states.list_for_sampling()
        assert [row["snapshotDigest"] for row in stored] == ["d-1"]
        assert stored[0]["status"] == "stepping_stone"
    finally:
        memory.close()


def test_archive_refuses_an_unmeasured_state(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        archive = StateArchive(HarnessStateStore(memory), ArchiveConfig())
        result = archive.retain({
            "snapshotDigest": "d-unmeasured",
            "metrics": {"aggregates": {"task_success": None}, "measuredTrials": 0},
        })
        assert result["retained"] is False
        assert result["reason"] == "unmeasured"
    finally:
        memory.close()


def test_archive_evicts_only_stepping_stones(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        states = HarnessStateStore(memory)
        root = states.save_state({
            "scope": "global", "snapshotDigest": "root",
            "metrics": _measured(0.9), "utility": 0.9, "status": "current",
        })
        archive = StateArchive(states, ArchiveConfig(max_states=2))
        for index in range(5):
            archive.retain(_state(f"stone-{index}", f"d-{index}", 0.1 * index))

        stones = states.list_states(status="stepping_stone")
        assert len(stones) == 2
        assert states.get_state(root["id"])["status"] == "current"
    finally:
        memory.close()


def test_archive_parent_for_records_a_visit(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        states = HarnessStateStore(memory)
        root = states.save_state({
            "scope": "global", "snapshotDigest": "root",
            "metrics": _measured(0.5), "utility": 0.5, "status": "current",
        })
        archive = StateArchive(states, ArchiveConfig())
        chosen = archive.parent_for(scope="global", rng=random.Random(2))

        assert chosen["id"] == root["id"]
        assert states.get_state(root["id"])["visitCount"] == 1
    finally:
        memory.close()


# -- hill-climb integration ------------------------------------------------


class _FakeArchive:
    def __init__(self, parent):
        self.parent = parent
        self.retained = []

    def parent_for(self, **_kwargs):
        return dict(self.parent)

    def retain(self, state, *, status="stepping_stone", island=None):
        self.retained.append({**state, "status": status})
        return {"retained": True, "state": dict(state)}


async def test_hillclimb_proposes_from_the_sampled_parent():
    champion = {
        "id": "champion", "scope": "global", "snapshotDigest": "d-champ",
        "metrics": _measured(0.8), "utility": 0.8,
    }
    stone = {
        "id": "stone", "scope": "global", "snapshotDigest": "d-stone",
        "metrics": _measured(0.4), "utility": 0.4, "status": "stepping_stone",
    }
    archive = _FakeArchive(stone)
    parents: list[str] = []

    candidate = {
        "id": "candidate", "snapshotDigest": "d-candidate",
        "validation": _measured(0.5), "replay": {"taskRates": {"a": 1.0}},
    }

    async def propose(parent, k, generation, rejected):
        parents.append(str(parent.get("id")))
        return [candidate] if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        champion,
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0},
        config=HillClimbConfig(
            generations=1, k=1, max_plateau=1, archive_mode="weighted",
        ),
        archive=archive,
    )

    assert parents == ["stone"]
    # 0.5 beats the sampled parent but not the champion: retained, not accepted.
    assert result["accepted"] == []
    assert any(item["status"] == "stepping_stone" for item in archive.retained)
    assert result["archive"]["enabled"] is True
    assert result["archive"]["sampled"][0]["stateId"] == "stone"


async def test_archive_off_keeps_the_champion_as_the_proposal_parent():
    champion = {
        "id": "champion", "scope": "global", "snapshotDigest": "d-champ",
        "metrics": _measured(0.8), "utility": 0.8,
    }
    seen: list[str] = []

    async def propose(parent, k, generation, rejected):
        seen.append(str(parent.get("id")))
        return []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        champion,
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0},
        config=HillClimbConfig(generations=1, k=1, max_plateau=1),
    )

    assert seen == ["champion"]
    assert result["archive"] == {"enabled": False}


# -- config ----------------------------------------------------------------


def test_archive_config_is_bounded_and_unknown_modes_fall_back():
    config = RSLConfig.from_env({
        "HARNESS_RSL_ARCHIVE": "on",
        "HARNESS_RSL_ARCHIVE_MAX": "9999",
        "HARNESS_RSL_ARCHIVE_SAMPLE": "bogus",
    })
    assert config.archive is True
    assert config.archive_max == 500
    assert config.archive_sample == "weighted"

    default = RSLConfig.from_env({})
    assert default.archive is False
    assert default.archive_sample == "weighted"

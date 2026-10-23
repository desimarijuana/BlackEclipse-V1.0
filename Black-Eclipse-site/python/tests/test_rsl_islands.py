"""Islands: per-scope climbs, cross-scope migration, and bounded concurrency."""

from __future__ import annotations

import asyncio
import random

import pytest

from harness.code.evolution_store import EvolutionStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.archive import ArchiveConfig, StateArchive
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.loop import RSLLoop
from harness.self_improvement.state import HarnessStateStore


def _metrics(success: float, *, measured: int = 10) -> dict:
    return {
        "aggregates": {"task_success": success},
        "measuredTrials": measured,
    }


def _save(states, *, scope, digest, utility, status="stepping_stone", island=None):
    return states.save_state({
        "scope": scope,
        "snapshotDigest": digest,
        "utility": utility,
        "metrics": _metrics(utility),
        "status": status,
        "island": island or scope,
    })


def test_migration_copies_the_islands_best_state_into_global(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        states = HarnessStateStore(memory)
        _save(states, scope="global", digest="g-base", utility=0.5, status="current")
        best = _save(states, scope="finance", digest="fin-best", utility=0.9)
        _save(states, scope="finance", digest="fin-other", utility=0.6)
        archive = StateArchive(
            states, ArchiveConfig(islands=True, island_migration_every=1),
        )

        result = archive.retain({
            "scope": "finance",
            "snapshotDigest": "fin-new",
            "parentStateId": best["id"],
            "utility": 0.8,
            "metrics": _metrics(0.8),
        })

        migration = result["migration"]
        assert migration["migrated"] is True
        assert migration["fromScope"] == "finance"
        assert migration["snapshotDigest"] == "fin-best"

        copied = states.find_by_digest("fin-best", scope="global")
        assert copied is not None
        assert copied["island"] == "migrated:finance"
        assert copied["status"] == "stepping_stone"

        again = archive.migrate_best("finance")
        assert again["migrated"] is False
        assert again["reason"] == "already_present"
    finally:
        memory.close()


def test_migration_is_off_by_default(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        states = HarnessStateStore(memory)
        _save(states, scope="finance", digest="fin-best", utility=0.9)
        archive = StateArchive(states, ArchiveConfig(islands=False))
        assert archive.migrate_best("finance")["reason"] == "islands_off"
        assert states.find_by_digest("fin-best", scope="global") is None
    finally:
        memory.close()


def test_parent_sampling_can_be_restricted_to_one_island(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        states = HarnessStateStore(memory)
        _save(states, scope="finance", digest="fin-1", utility=0.7)
        _save(states, scope="research", digest="res-1", utility=0.8)
        archive = StateArchive(states, ArchiveConfig(islands=True))

        chosen = archive.parent_for(
            scope="finance", island="finance", rng=random.Random(2),
        )
        assert chosen["snapshotDigest"] == "fin-1"
        assert archive.parent_for(
            scope="finance", island="research", rng=random.Random(2),
        ) is None

        groups = archive.islands()
        assert groups["finance"]["count"] == 1
        assert groups["research"]["bestUtility"] == 0.8
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_two_islands_climb_concurrently_without_sharing_a_lease(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        loop = RSLLoop(
            service=None,
            config=RSLConfig(
                mode="verify", strategy="hillclimb", islands=True,
                max_experiments_per_day=10,
            ),
            run_store=memory,
            evolution=EvolutionStore(memory),
        )
        for scope, digest in (("finance", "fin-base"), ("research", "res-base")):
            loop.state_store.save_state({
                "scope": scope,
                "snapshotDigest": digest,
                "utility": 0.8,
                "metrics": _metrics(0.8),
                "status": "current",
            })

        active = 0
        max_active = 0

        async def propose(state, k, generation, rejected):
            if generation:
                return []
            digest = f"candidate-{state['snapshotDigest']}"
            return [{
                "id": digest,
                "snapshotDigest": digest,
                "validation": _metrics(0.5),
                "replay": {"taskRates": {"a": 1.0}},
            }]

        async def evaluate(item, split):
            nonlocal active, max_active
            if split == "validation":
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.05)
                active -= 1
                return item["validation"]
            return item["replay"]

        finance, research = await asyncio.gather(
            loop.run_hillclimb(
                propose=propose, evaluate=evaluate,
                replay_baseline={"a": 1.0}, scope="finance",
            ),
            loop.run_hillclimb(
                propose=propose, evaluate=evaluate,
                replay_baseline={"a": 1.0}, scope="research",
            ),
        )

        assert finance["refused"] is False
        assert research["refused"] is False
        assert max_active == 2
        await loop.stop()
    finally:
        memory.close()


def test_island_and_novelty_config_is_bounded():
    config = RSLConfig.from_env({
        "HARNESS_RSL_NOVELTY_MIN": "0.4",
        "HARNESS_RSL_ISLANDS": "on",
        "HARNESS_RSL_ISLAND_MIGRATION": "999",
    })
    assert config.novelty_min == 0.4
    assert config.islands is True
    assert config.island_migration_every == 100

    default = RSLConfig.from_env({})
    assert default.novelty_min == 0.0
    assert default.islands is False
    assert default.island_migration_every == 5

"""Metaproductivity: descendant lift as a sampling signal, never acceptance."""

from __future__ import annotations

import random

import pytest

from harness.persistence import AgentMemoryStore
from harness.self_improvement.archive import ArchiveConfig, StateArchive
from harness.self_improvement.cmp import (
    CMPConfig,
    collect_descendants,
    descendant_lift,
)
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.state import HarnessStateStore


def _metrics(success: float, *, measured: int = 10) -> dict:
    return {
        "aggregates": {"task_success": success},
        "measuredTrials": measured,
    }


def _save(states, *, digest, utility, parent=None, status="stepping_stone"):
    return states.save_state({
        "parentStateId": parent,
        "scope": "global",
        "snapshotDigest": digest,
        "utility": utility,
        "metrics": _metrics(utility),
        "status": status,
    })


def _tree(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    states = HarnessStateStore(memory)
    root = _save(states, digest="root", utility=0.5, status="current")
    child = _save(states, digest="child", utility=0.9, parent=root["id"])
    sibling = _save(states, digest="sibling", utility=0.6, parent=root["id"])
    grandchild = _save(
        states, digest="grandchild", utility=0.95, parent=child["id"],
    )
    dead = _save(states, digest="dead", utility=0.55)
    return memory, states, root, child, sibling, grandchild, dead


# -- the estimate ----------------------------------------------------------


def test_descendant_lift_uses_the_measured_descendants(tmp_path):
    memory, states, root, child, sibling, grandchild, _dead = _tree(tmp_path)
    try:
        estimate = descendant_lift(
            root,
            children=states.children,
            config=CMPConfig(horizon=3, min_samples=2),
        )
        assert estimate["coldStart"] is False
        assert estimate["samples"] == 3
        # Depth-discounted mean of +0.4 (child), +0.1 (sibling), +0.45 (grandchild).
        assert estimate["lift"] == pytest.approx(0.307143, abs=1e-6)
        assert estimate["ciLow"] is not None and estimate["ciHigh"] is not None
        ids = {row["id"] for row in estimate["descendants"]}
        assert ids == {child["id"], sibling["id"], grandchild["id"]}
    finally:
        memory.close()


def test_a_state_without_descendants_is_explicitly_cold_start(tmp_path):
    memory, states, _root, _child, _sibling, _grandchild, dead = _tree(tmp_path)
    try:
        estimate = descendant_lift(
            dead, children=states.children, config=CMPConfig(min_samples=2),
        )
        assert estimate["coldStart"] is True
        assert estimate["samples"] == 0
        assert estimate["lift"] is None
    finally:
        memory.close()


def test_horizon_excludes_far_descendants(tmp_path):
    memory, states, root, child, sibling, grandchild, _dead = _tree(tmp_path)
    try:
        near = descendant_lift(
            root,
            children=states.children,
            config=CMPConfig(horizon=1, min_samples=1),
        )
        ids = {row["id"] for row in near["descendants"]}
        assert ids == {child["id"], sibling["id"]}
        assert grandchild["id"] not in ids
    finally:
        memory.close()


def test_collect_descendants_is_bounded_and_deduplicated(tmp_path):
    memory, states, root, child, _sibling, grandchild, _dead = _tree(tmp_path)
    try:
        rows = collect_descendants(root["id"], states.children, horizon=3)
        ids = [row["id"] for _depth, row in rows]
        assert len(ids) == len(set(ids))
        assert {child["id"], grandchild["id"]}.issubset(set(ids))
    finally:
        memory.close()


# -- archive integration ---------------------------------------------------


def test_retaining_a_descendant_persists_cmp_on_its_ancestors(tmp_path):
    memory, states, root, child, sibling, grandchild, _dead = _tree(tmp_path)
    try:
        archive = StateArchive(
            states,
            ArchiveConfig(cmp=True, cmp_min_samples=1, cmp_horizon=3),
        )
        # Re-retaining the leaf refreshes the whole lineage's estimate.
        archive.retain({
            "scope": "global",
            "snapshotDigest": grandchild["snapshotDigest"],
            "parentStateId": child["id"],
            "utility": 0.95,
            "metrics": _metrics(0.95),
        })

        root_score = states.get_state(root["id"])["cmpScore"]
        child_score = states.get_state(child["id"])["cmpScore"]
        assert root_score is not None and root_score > 0
        assert child_score is not None and child_score > 0
    finally:
        memory.close()


def test_productive_parent_is_sampled_more_often_than_a_dead_end(tmp_path):
    memory, states, root, _child, _sibling, _grandchild, _dead = _tree(tmp_path)
    try:
        archive = StateArchive(
            states,
            ArchiveConfig(cmp=True, cmp_min_samples=1, sample="weighted"),
        )
        rng = random.Random(11)
        picks = [
            archive.parent_for(scope="global", rng=rng)["id"] for _ in range(300)
        ]
        # The root has improving descendants; `dead` has none. Utility is close
        # (0.5 vs 0.55), so the CMP term is what separates them.
        assert picks.count(root["id"]) > 0
        assert picks.count(root["id"]) > picks.count(_dead["id"])
    finally:
        memory.close()


def test_cmp_off_writes_no_scores(tmp_path):
    memory, states, root, child, _sibling, _grandchild, _dead = _tree(tmp_path)
    try:
        archive = StateArchive(states, ArchiveConfig(cmp=False))
        archive.retain({
            "scope": "global",
            "snapshotDigest": "fresh",
            "parentStateId": child["id"],
            "utility": 0.7,
            "metrics": _metrics(0.7),
        })
        assert states.get_state(root["id"])["cmpScore"] is None
    finally:
        memory.close()


# -- config ----------------------------------------------------------------


def test_cmp_config_is_bounded():
    config = RSLConfig.from_env({
        "HARNESS_RSL_CMP": "on",
        "HARNESS_RSL_CMP_HORIZON": "99",
    })
    assert config.cmp is True
    assert config.cmp_horizon == 6

    default = RSLConfig.from_env({})
    assert default.cmp is False
    assert default.cmp_horizon == 3

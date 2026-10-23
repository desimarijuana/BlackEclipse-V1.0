"""Paired significance in the RSL acceptance decision (opt-in)."""

from __future__ import annotations

from harness.self_improvement.config import RSLConfig
from harness.self_improvement.hillclimb import HillClimbConfig, run_hillclimb
from harness.self_improvement.utility import acceptance


def _rates(value: float, count: int = 20) -> dict[str, float]:
    return {f"t{index}": value for index in range(count)}


def _metrics(success: float, rates: dict[str, float], *, measured: int = 20):
    return {
        "aggregates": {"task_success": success},
        "measuredTrials": measured,
        "taskRates": rates,
    }


def test_a_real_paired_lift_is_accepted():
    current = _metrics(0.6, _rates(0.5))
    candidate = _metrics(0.8, _rates(0.9))
    decision = acceptance(
        current, candidate,
        require_significance=True, significance_min_tasks=5,
        significance_bootstrap=2000, significance_seed=1,
    )
    assert decision["accepted"] is True
    assert decision["significance"]["ciLow"] > 0


def test_a_two_task_win_is_refused_as_insufficient():
    current = _metrics(0.6, _rates(0.5, 2), measured=2)
    candidate = _metrics(0.8, _rates(1.0, 2), measured=2)
    decision = acceptance(
        current, candidate,
        require_significance=True, significance_min_tasks=5,
    )
    assert decision["accepted"] is False
    assert any("insufficient paired tasks" in reason for reason in decision["reasons"])
    assert decision["significance"]["insufficient"] is True


def test_missing_paired_data_is_not_a_measurement():
    current = {"aggregates": {"task_success": 0.6}, "measuredTrials": 10}
    candidate = {"aggregates": {"task_success": 0.8}, "measuredTrials": 10}
    decision = acceptance(
        current, candidate,
        require_significance=True, significance_min_tasks=5,
    )
    assert decision["accepted"] is False
    assert any("insufficient paired tasks" in reason for reason in decision["reasons"])


def test_significance_off_leaves_the_point_estimate_rule_unchanged():
    current = _metrics(0.6, _rates(0.5, 2), measured=2)
    candidate = _metrics(0.8, _rates(1.0, 2), measured=2)
    decision = acceptance(current, candidate)
    assert decision["accepted"] is True
    assert decision["significance"] is None


async def test_hillclimb_requires_significance_when_enabled():
    champion = {
        "id": "champion", "scope": "global", "snapshotDigest": "base",
        "metrics": _metrics(0.7, _rates(0.5)),
        "utility": 0.7,
    }
    candidate = {
        "id": "candidate", "snapshotDigest": "lifted",
        "validation": _metrics(0.8, _rates(0.9)),
        "replay": {"taskRates": {"a": 1.0}},
    }

    async def propose(state, k, generation, rejected):
        return [candidate] if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        champion,
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0},
        config=HillClimbConfig(
            generations=1, k=1, max_plateau=1,
            require_significance=True, significance_min_tasks=5,
            significance_bootstrap=2000, significance_seed=2,
        ),
    )
    assert result["accepted"]
    record = result["generations"][0]["records"][0]
    assert record["decision"] == "accepted"


async def test_hillclimb_refuses_a_two_task_lift_when_significance_is_on():
    champion = {
        "id": "champion", "scope": "global", "snapshotDigest": "base",
        "metrics": _metrics(0.7, _rates(0.5, 2), measured=2),
        "utility": 0.7,
    }
    candidate = {
        "id": "candidate", "snapshotDigest": "tiny",
        "validation": _metrics(0.8, _rates(1.0, 2), measured=2),
        "replay": {"taskRates": {"a": 1.0}},
    }

    async def propose(state, k, generation, rejected):
        return [candidate] if generation == 0 else []

    async def evaluate(item, split):
        return item["validation"] if split == "validation" else item["replay"]

    result = await run_hillclimb(
        champion,
        propose=propose,
        evaluate=evaluate,
        replay_baseline={"a": 1.0},
        config=HillClimbConfig(
            generations=1, k=1, max_plateau=1,
            require_significance=True, significance_min_tasks=5,
        ),
    )
    assert result["accepted"] == []
    assert any(
        "insufficient paired tasks" in reason
        for reason in result["generations"][0]["records"][0]["reasons"]
    )


def test_significance_config_is_bounded():
    config = RSLConfig.from_env({
        "HARNESS_RSL_SIGNIFICANCE": "on",
        "HARNESS_RSL_SIGNIFICANCE_MIN_TASKS": "999",
    })
    assert config.significance is True
    assert config.significance_min_tasks == 200

    default = RSLConfig.from_env({})
    assert default.significance is False
    assert default.significance_min_tasks == 5

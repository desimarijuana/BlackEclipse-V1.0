"""RSL R0 — the loop is dark by default and every budget is clamped."""

from __future__ import annotations

import pytest

from harness.self_improvement.config import RSLConfig
from harness.self_improvement.models import HarnessSnapshot


def test_defaults_are_dark_and_bounded():
    config = RSLConfig.from_env(environ={})
    assert config.mode == "off"
    assert config.is_off is True
    assert config.observes is False
    assert config.max_candidates == 5
    assert config.max_experiments_per_day == 3
    assert config.trials == 3
    assert config.k == 1
    assert config.tick_seconds == 300
    assert config.lease_seconds == 1800
    assert config.max_wall_seconds == 1800
    assert config.max_cost_usd == 5.0


def test_mode_is_case_insensitive_and_invalid_modes_fail_closed():
    assert RSLConfig.from_env(environ={"HARNESS_RSL_MODE": "OBSERVE"}).mode == "observe"
    assert RSLConfig.from_env(environ={"HARNESS_RSL_MODE": " verify "}).mode == "verify"
    assert RSLConfig.from_env(environ={"HARNESS_RSL_MODE": "autonomous"}).mode == "off"


def test_every_numeric_setting_is_clamped():
    config = RSLConfig.from_env(environ={
        "HARNESS_RSL_MAX_CANDIDATES": "999",
        "HARNESS_RSL_MAX_EXPERIMENTS_PER_DAY": "-4",
        "HARNESS_RSL_TRIALS": "0",
        "HARNESS_RSL_K": "99",
        "HARNESS_RSL_TICK_SECONDS": "1",
        "HARNESS_RSL_LEASE_SECONDS": "1",
        "HARNESS_RSL_MAX_WALL_SECONDS": "999999",
        "HARNESS_RSL_MAX_COST_USD": "-3",
    })
    assert config.max_candidates == 50
    assert config.max_experiments_per_day == 0
    assert config.trials == 1
    assert config.k == 8
    assert config.tick_seconds == 10
    assert config.lease_seconds == 60
    assert config.max_wall_seconds == 7200
    assert config.max_cost_usd == 0.0


def test_malformed_numbers_fall_back_to_defaults():
    config = RSLConfig.from_env(environ={
        "HARNESS_RSL_MAX_CANDIDATES": "many",
        "HARNESS_RSL_TRIALS": "",
        "HARNESS_RSL_MAX_COST_USD": "nan",
    })
    assert config.max_candidates == 5
    assert config.trials == 3
    assert config.max_cost_usd == 5.0


def test_snapshot_digest_is_reproducible_and_validated():
    first = HarnessSnapshot(
        systemPrompt="Follow the task.",
        toolNames=("tool_a", "tool_b"),
        maxSteps=4,
        maxToolCalls=8,
    )
    second = HarnessSnapshot(
        systemPrompt="Follow the task.",
        toolNames=("tool_a", "tool_b"),
        maxSteps=4,
        maxToolCalls=8,
    )
    assert first.sourceDigest == second.sourceDigest
    assert len(first.sourceDigest) == 64
    assert first.to_agent_config().maxToolCalls == 8


@pytest.mark.parametrize("kwargs", [
    {"systemPrompt": ""},
    {"systemPrompt": "x", "maxSteps": 0},
    {"systemPrompt": "x", "maxSteps": 33},
    {"systemPrompt": "x", "maxToolCalls": 201},
    {"systemPrompt": "x", "temperature": 3.0},
    {"systemPrompt": "x", "toolNames": ("a", "a")},
])
def test_snapshot_refuses_out_of_range_values(kwargs):
    with pytest.raises(ValueError):
        HarnessSnapshot(**kwargs)

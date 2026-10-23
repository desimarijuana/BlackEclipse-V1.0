"""Supervised autonomy: risk classes, the admission policy and the kill switch."""

from __future__ import annotations

import pytest

from harness.code.evolution_store import EvolutionStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.autonomy import (
    AutonomyKillSwitch,
    autonomy_status,
    classify_ops_risk,
    classify_snapshot_risk,
    decide,
)
from harness.self_improvement.config import RSLConfig
from harness.self_improvement.loop import RSLLoop
from harness.self_improvement.models import HarnessSnapshot


def _snapshot(**overrides):
    values = {
        "systemPrompt": "base prompt",
        "toolNames": ("a", "b"),
        "maxSteps": 8,
        "maxToolCalls": 200,
    }
    values.update(overrides)
    return HarnessSnapshot(**values)


def _config(**overrides):
    values = {
        "autonomy": "supervised",
        "auto_min_lift": 0.02,
        "auto_max_per_day": 1,
        "auto_risk": "low",
    }
    values.update(overrides)
    return RSLConfig(**values)


def _decision(**overrides):
    values = {
        "level": "supervised",
        "risk": "L1",
        "kill": False,
        "config": _config(),
        "delta_ci_low": 0.05,
        "critical_regression": False,
        "canary_ok": True,
        "replay_ok": True,
        "activations_today": 0,
        "changed": True,
    }
    values.update(overrides)
    return decide(**values)


# -- risk classification ---------------------------------------------------


def test_prompt_and_guidance_are_bounded_surface_changes():
    change = classify_snapshot_risk(_snapshot(), _snapshot(systemPrompt="new prompt"))
    assert change["riskClass"] == "L1"
    assert change["changed"] is True
    assert "bounded_surface_change" in change["reasons"]

    guidance = classify_snapshot_risk(
        _snapshot(), _snapshot(toolGuidance="use a first"),
    )
    assert guidance["riskClass"] == "L1"


def test_widening_the_tool_set_is_capability_not_autonomy():
    change = classify_snapshot_risk(
        _snapshot(), _snapshot(toolNames=("a", "b", "c")),
    )
    assert change["riskClass"] == "L2"
    assert "tool_added" in change["reasons"]


def test_removing_a_guardrail_or_raising_a_ceiling_is_human_only():
    base = _snapshot(guardrails=("require_citation",))
    removed = classify_snapshot_risk(base, _snapshot())
    assert removed["riskClass"] == "L2"
    assert "guardrail_removed" in removed["reasons"]

    raised = classify_snapshot_risk(_snapshot(), _snapshot(maxSteps=16))
    assert raised["riskClass"] == "L2"
    assert "maxSteps_raised" in raised["reasons"]


def test_model_identity_is_never_automatic():
    change = classify_snapshot_risk(
        _snapshot(), _snapshot(modelProvider="openai", modelName="gpt"),
    )
    assert change["riskClass"] == "L2"


def test_no_change_is_not_an_eligible_candidate():
    change = classify_snapshot_risk(_snapshot(), _snapshot())
    assert change["changed"] is False
    assert change["reasons"] == ["no_change"]


def test_operator_types_map_to_risk():
    assert classify_ops_risk("code_patch") == "L0"
    assert classify_ops_risk("composition") == "L2"
    assert classify_ops_risk("prompt") == "L1"


# -- admission policy ------------------------------------------------------


def test_off_and_verify_levels_never_auto_apply():
    assert _decision(level="off")["allowed"] is False
    assert _decision(level="verify")["allowed"] is False
    assert "autonomy_level" in _decision(level="verify")["reasons"]


def test_a_clean_l1_lift_is_allowed():
    decision = _decision()
    assert decision["allowed"] is True
    assert decision["requiresOperator"] is False
    assert decision["riskClass"] == "L1"


def test_l0_and_l2_are_never_allowed():
    l0 = _decision(risk="L0")
    l2 = _decision(risk="L2")
    assert l0["allowed"] is False and "risk_L0_never_automatic" in l0["reasons"]
    assert l2["allowed"] is False and "risk_L2_requires_human" in l2["reasons"]


def test_the_kill_switch_stops_every_decision():
    decision = _decision(kill=True)
    assert decision["allowed"] is False
    assert "kill_switch" in decision["reasons"]


def test_missing_or_weak_evidence_is_refused():
    assert "no_paired_evidence" in _decision(delta_ci_low=None)["reasons"]
    assert "lift_below_floor" in _decision(delta_ci_low=0.01)["reasons"]
    assert "critical_regression" in _decision(critical_regression=True)["reasons"]
    assert "canary_failed" in _decision(canary_ok=False)["reasons"]
    assert "replay_failed" in _decision(replay_ok=False)["reasons"]
    assert "mispredicted" in _decision(
        predicted_delta=0.1, measured_delta=-0.1,
    )["reasons"]


def test_the_daily_budget_bounds_automatic_activation():
    assert "daily_budget" in _decision(activations_today=1)["reasons"]
    assert "daily_budget" in _decision(
        config=_config(auto_max_per_day=0),
    )["reasons"]


# -- persistence and loop wiring -------------------------------------------


def test_kill_switch_persists_across_instances(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        first = AutonomyKillSwitch(memory)
        assert first.status()["paused"] is False
        paused = first.pause("operator stop")
        assert paused["paused"] is True
        assert paused["reason"] == "operator stop"

        second = AutonomyKillSwitch(memory)
        assert second.status()["paused"] is True
        second.resume()
        assert AutonomyKillSwitch(memory).status()["paused"] is False
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_loop_exposes_and_persists_the_kill_switch(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        loop = RSLLoop(
            service=None,
            config=RSLConfig(
                mode="verify", strategy="hillclimb", autonomy="supervised",
                auto_min_lift=0.02, auto_max_per_day=1,
            ),
            run_store=memory,
            evolution=EvolutionStore(memory),
        )
        allowed = loop.decide_autonomy(risk="L1", delta_ci_low=0.05)
        assert allowed["allowed"] is True

        loop.pause_autonomy("test stop")
        denied = loop.decide_autonomy(risk="L1", delta_ci_low=0.05)
        assert denied["allowed"] is False
        assert "kill_switch" in denied["reasons"]

        status = loop.autonomy_status()
        assert status["level"] == "supervised"
        assert status["killSwitch"]["paused"] is True

        fresh = RSLLoop(
            service=None, config=None, run_store=memory,
            evolution=EvolutionStore(memory),
        )
        assert fresh.autonomy_status()["killSwitch"]["paused"] is True
        await loop.stop()
        await fresh.stop()
    finally:
        memory.close()


def test_autonomy_config_is_bounded():
    config = RSLConfig.from_env({
        "HARNESS_RSL_AUTONOMY": "bounded",
        "HARNESS_RSL_AUTO_MIN_LIFT": "0.5",
        "HARNESS_RSL_AUTO_MAX_PER_DAY": "999",
    })
    assert config.autonomy == "bounded"
    assert config.auto_min_lift == 0.5
    assert config.auto_max_per_day == 50

    fallback = RSLConfig.from_env({"HARNESS_RSL_AUTONOMY": "godmode"})
    assert fallback.autonomy == "off"

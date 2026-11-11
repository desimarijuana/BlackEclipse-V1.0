"""Effectful capabilities are handed to the existing owner, never self-built."""

from __future__ import annotations

from harness.capabilities.handoff import EFFECTFUL_KINDS, plan_handoff
from harness.capabilities.request import CapabilityRequest


def _request(need: str, kind: str = "auto", **overrides) -> CapabilityRequest:
    base = {"need": need, "kind": kind, "acceptance": []}
    base.update(overrides)
    return CapabilityRequest(**base)


def test_skill_handoff_names_the_existing_owner():
    handoff = plan_handoff(_request("from now on prepare a weekly review", "skill"))
    assert handoff.surface == "skill_create"
    assert handoff.next_tool == "skill_create"
    assert handoff.arguments["name"] == "prepare_weekly_review"
    assert handoff.requires_approval is True
    assert handoff.activation == "operator"
    assert "evaluation" in handoff.verification
    assert any("instructions" in item for item in handoff.missing)


def test_a_bot_handoff_uses_the_persistent_bot_surface():
    handoff = plan_handoff(_request("turn this into a bot that runs at 9am", "bot"))
    assert handoff.surface == "bot_create"
    assert handoff.next_tool == "bot_create"
    assert handoff.arguments["triggerType"] == "cron"
    assert handoff.requires_approval is True
    assert handoff.activation == "operator"
    assert any("timezone" in item.lower() for item in handoff.missing)
    assert "scaffold_kit" in " ".join(handoff.notes)


def test_ui_handoff_uses_the_engineering_task_runtime():
    handoff = plan_handoff(_request("make a new swap-spread widget", "ui_widget"))
    assert handoff.surface == "ui_start_engineering"
    assert handoff.next_tool == "ui_start_engineering"
    assert handoff.arguments["title"] == "make a new swap-spread widget"
    assert handoff.activation == "operator"
    assert handoff.requires_approval is False  # creating the task is orchestration


def test_a_tool_with_a_matching_kit_uses_scaffold_kit():
    handoff = plan_handoff(_request("build a market data adapter", "tool"))
    assert handoff.surface == "scaffold_kit"
    assert handoff.next_tool == "scaffold_kit"
    assert handoff.arguments["kit_id"] == "market_data_adapter"
    assert any("source_name" in item for item in handoff.missing)


def test_an_unmatched_tool_uses_a_durable_code_goal():
    handoff = plan_handoff(_request("build a tool for my private ledger", "tool"))
    assert handoff.surface == "code_agent"
    assert handoff.next_tool == "create_goal"
    assert handoff.arguments["taskType"] == "code"
    assert "tests" in handoff.verification


def test_a_harness_change_stays_on_the_code_surface():
    handoff = plan_handoff(_request("change the agent loop policy", "harness_change"))
    assert handoff.surface == "code_agent"
    assert handoff.next_tool == "create_goal"
    assert any("authority" in note for note in handoff.notes)
    assert "operator" in handoff.verification


def test_a_plugin_handoff_points_at_the_external_lane():
    handoff = plan_handoff(_request("connect my broker api", "plugin"))
    assert handoff.surface == "external_adapter"
    assert handoff.next_tool == "capability_external"
    assert handoff.kind == "plugin"
    assert "DISABLED" in " ".join(handoff.evidence)


def test_handoff_dict_is_json_ready_and_never_claims_activation():
    for kind in EFFECTFUL_KINDS:
        handoff = plan_handoff(_request(f"build a {kind}", kind))
        data = handoff.to_dict()
        assert data["activation"] == "operator" or kind == "ui_widget"
        assert data["requiresApproval"] in (True, False)
        assert data["nextTool"]
        assert isinstance(data["evidence"], list) and data["evidence"]
        assert isinstance(data["acceptance"], list) and data["acceptance"]

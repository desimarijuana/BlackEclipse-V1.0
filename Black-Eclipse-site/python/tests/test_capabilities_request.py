"""Capability gap detection chooses a witness, a one-off, or a safe build route."""

from __future__ import annotations

from harness.capabilities.request import assess, classify, slug_for
from harness.tools import ToolRegistry


def test_a_known_recipe_is_a_witness_not_a_gap():
    assessment = assess("compute the drawdown profile", tool_registry=ToolRegistry())
    assert assessment.status == "satisfied"
    assert assessment.resolved_by == "drawdown_profile"
    assert assessment.kind == "recipe"


def test_an_unmatched_computation_is_one_off():
    assessment = assess("compute the ulcer index of my portfolio", tool_registry=ToolRegistry())
    assert assessment.status == "one_off"
    assert assessment.one_off is True
    assert assessment.next_tool == "analysis_run"
    assert assessment.requires_approval is False


def test_a_repeating_request_is_a_recipe_gap():
    assessment = assess("from now on compute the ulcer index", tool_registry=ToolRegistry())
    assert assessment.status == "gap"
    assert assessment.kind == "recipe"
    assert assessment.surface == "capability_builder"
    assert assessment.requires_approval is False
    assert any("contract test" in item for item in assessment.missing)


def test_an_external_system_is_a_plugin_gap_and_needs_approval():
    assessment = assess("connect my broker api", tool_registry=ToolRegistry())
    assert assessment.status == "gap"
    assert assessment.kind == "plugin"
    assert assessment.requires_approval is True
    assert assessment.surface == "external_adapter"
    assert assessment.next_tool == "capability_external"


def test_effectful_kinds_name_their_existing_owner():
    widget = assess("make a widget for swap spreads", tool_registry=ToolRegistry())
    assert widget.next_tool == "ui_start_engineering"
    skill = assess("from now on use a weekly review routine", tool_registry=ToolRegistry())
    assert skill.kind == "skill"
    assert skill.next_tool == "skill_create"
    harness = assess("change the harness agent loop policy", tool_registry=ToolRegistry())
    assert harness.kind == "harness_change"
    assert harness.next_tool == "create_goal"


def test_a_bot_request_routes_to_the_persistent_bot_surface():
    """A scheduled agent is not a one-off and not a scaffold_kit build."""
    assessment = assess(
        "turn this into a bot that runs every morning at 9am",
        tool_registry=ToolRegistry(),
    )
    assert assessment.status == "gap"
    assert assessment.kind == "bot"
    assert assessment.surface == "bot_create"
    assert assessment.next_tool == "bot_create"
    assert assessment.requires_approval is True
    assert any("timezone" in item.lower() for item in assessment.missing)
    assert classify("set up a bot every morning") == "bot"


def test_a_satisfied_tool_match_names_the_tool_to_call():
    """An existing tool is a route, not a shrug: nextTool must be callable."""
    from harness.tools import ToolDefinition

    reg = ToolRegistry()

    async def _noop(_args, _ctx):
        return "", None

    reg.register(ToolDefinition(
        name="bot_create",
        description="Create a persistent scheduled bot",
        input_schema={"type": "object", "properties": {}},
        handler=_noop,
        permission="read",
    ))
    assessment = assess("create a bot", tool_registry=reg)
    assert assessment.status == "satisfied"
    assert assessment.kind == "tool"
    assert assessment.resolved_by == "bot_create"
    assert assessment.next_tool == "bot_create"


def test_a_multi_deliverable_request_keeps_every_deliverable():
    """'a skill and then a bot' must not silently drop either one."""
    assessment = assess(
        "turn our recent task into a skill and then a bot",
        tool_registry=ToolRegistry(),
    )
    assert assessment.status == "gap"
    assert assessment.kind == "skill"
    assert [item["kind"] for item in assessment.deliverables] == ["skill", "bot"]
    assert [item["nextTool"] for item in assessment.deliverables] == [
        "skill_create", "bot_create",
    ]


def test_a_widget_request_routes_to_ui_engineering():
    assessment = assess("make a widget for swap spreads", tool_registry=ToolRegistry())
    assert assessment.status == "gap"
    assert assessment.kind == "ui_widget"
    assert assessment.surface == "ui_start_engineering"
    assert assessment.requires_approval is True


def test_an_explicit_kind_wins():
    assert classify("compute something", "recipe") == "recipe"
    assert classify("compute something", "harness_change") == "harness_change"


def test_slug_is_a_safe_stable_identifier():
    assert slug_for("Compute the Ulcer Index of my portfolio") == "ulcer_index_portfolio"
    assert slug_for("x", "my-index") == "my_index"

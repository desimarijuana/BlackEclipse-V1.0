"""The bundled finance team library: valid, renderable, evidence-gated."""

from __future__ import annotations

import pytest

from harness.team import preset_library as P
from harness.team.model import TeamDefinition


def test_the_library_loads_and_every_preset_is_valid():
    presets = P.load_presets()
    assert len(presets) >= 3
    ids = [p.id for p in presets]
    assert len(ids) == len(set(ids))
    for preset in presets:
        assert preset.definition.members, preset.id
        assert preset.definition.subtasks, preset.id
        assert P.validate_definition(preset.definition) == []


def test_every_preset_has_an_evidence_gated_subtask():
    for preset in P.load_presets():
        assert preset.to_dict()["evidenceRequired"] >= 1, preset.id


def test_the_investment_committee_has_both_sides_and_a_verdict():
    preset = P.get_preset("investment_committee")
    assert preset is not None
    ids = {s.id for s in preset.definition.subtasks}
    assert {"bull_case", "bear_case", "risk_review", "verdict"} <= ids
    verdict = next(s for s in preset.definition.subtasks if s.id == "verdict")
    assert set(verdict.depends_on) == {"bull_case", "bear_case", "risk_review"}
    assert verdict.review is True


def test_render_substitutes_every_declared_variable():
    preset = P.get_preset("investment_committee")
    definition = P.render_preset(preset, target="TSLA", horizon="12 months")
    blob = " ".join(
        [definition.objective]
        + [s.objective for s in definition.subtasks]
        + [m.instructions for m in definition.members]
    )
    assert "TSLA" in blob and "12 months" in blob
    assert "{target}" not in blob and "{horizon}" not in blob


def test_render_refuses_to_ship_a_literal_placeholder():
    preset = P.get_preset("investment_committee")
    with pytest.raises(ValueError) as exc:
        P.render_preset(preset, target="TSLA")
    assert "horizon" in str(exc.value)


def test_evidence_subtasks_lists_the_gated_ones():
    preset = P.get_preset("quant_strategy_desk")
    definition = P.render_preset(preset, signal="momentum", universe="S&P 500", period="2018-2024")
    gated = P.evidence_subtasks(definition)
    assert "factor_evidence" in gated
    assert "audit" in gated


# -- validation --------------------------------------------------------------


def _definition(**over):
    base = {"id": "t1", "name": "T1", "members": [{"agentId": "a"}],
            "subtasks": [{"id": "x", "objective": "do x", "assignedAgentId": "a"}]}
    base.update(over)
    return TeamDefinition.model_validate(base)


def test_validation_catches_an_unknown_dependency():
    problems = P.validate_definition(_definition(subtasks=[
        {"id": "x", "objective": "do x", "dependsOn": ["nope"]}]))
    assert any("unknown" in p for p in problems)


def test_validation_catches_a_dependency_cycle():
    problems = P.validate_definition(_definition(subtasks=[
        {"id": "a", "objective": "a", "dependsOn": ["b"]},
        {"id": "b", "objective": "b", "dependsOn": ["a"]}]))
    assert any("cycle" in p for p in problems)


def test_validation_catches_an_assignee_who_is_not_a_member():
    problems = P.validate_definition(_definition(subtasks=[
        {"id": "x", "objective": "x", "assignedAgentId": "ghost"}]))
    assert any("not a member" in p for p in problems)


def test_validation_catches_duplicate_subtask_ids():
    problems = P.validate_definition(_definition(subtasks=[
        {"id": "x", "objective": "one"}, {"id": "x", "objective": "two"}]))
    assert any("duplicate" in p for p in problems)


def test_evidence_required_defaults_to_false_for_existing_teams():
    definition = _definition()
    assert definition.subtasks[0].evidence_required is False


# -- enforcement -------------------------------------------------------------


def _finding(subtask_id: str, refs):
    from harness.team.model import TeamFinding

    return TeamFinding(
        id="fnd_x", subtask_id=subtask_id, agent_id="a",
        claim="claim", confidence=0.5, evidence_refs=list(refs),
    )


def test_a_completed_gated_subtask_without_evidence_is_flagged():
    from harness.team.model import TeamSubtaskStatus
    from harness.team.service import unevidenced_subtasks

    definition = _definition(subtasks=[
        {"id": "x", "objective": "x", "evidenceRequired": True}])
    statuses = {"x": TeamSubtaskStatus.COMPLETED}
    assert unevidenced_subtasks(definition, statuses, []) == ["x"]


def test_an_evidenced_finding_satisfies_the_gate():
    from harness.team.model import TeamSubtaskStatus
    from harness.team.service import unevidenced_subtasks

    definition = _definition(subtasks=[
        {"id": "x", "objective": "x", "evidenceRequired": True}])
    statuses = {"x": TeamSubtaskStatus.COMPLETED}
    assert unevidenced_subtasks(definition, statuses, [_finding("x", ["ev_1"])]) == []


def test_a_finding_without_refs_does_not_satisfy_the_gate():
    from harness.team.model import TeamSubtaskStatus
    from harness.team.service import unevidenced_subtasks

    definition = _definition(subtasks=[
        {"id": "x", "objective": "x", "evidenceRequired": True}])
    statuses = {"x": TeamSubtaskStatus.COMPLETED}
    assert unevidenced_subtasks(definition, statuses, [_finding("x", [])]) == ["x"]


def test_ungated_or_unfinished_subtasks_are_not_flagged():
    from harness.team.model import TeamSubtaskStatus
    from harness.team.service import unevidenced_subtasks

    definition = _definition(subtasks=[
        {"id": "plain", "objective": "p"},
        {"id": "late", "objective": "l", "evidenceRequired": True}])
    statuses = {"plain": TeamSubtaskStatus.COMPLETED, "late": TeamSubtaskStatus.RUNNING}
    assert unevidenced_subtasks(definition, statuses, []) == []

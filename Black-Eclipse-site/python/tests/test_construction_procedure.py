"""Round 4 (W6): construction procedure learning — inert until promoted.

A successful UI construction sequence (engineer → implement → register) becomes
an inert `successful_procedure` candidate carrying the re-derived know-how (the
widget layer's files and its size ceiling). The candidate is created on the
FIRST occurrence; the DRAFT opens only on recurrence; nothing enables a skill —
activation stays the existing evaluation + operator promotion.
"""

from __future__ import annotations

import types

import pytest

from harness.eclipse_memory.service import EclipseMemoryService
from harness.learning_review import review_run
from harness.persistence import AgentMemoryStore
from harness.recovery.learning import incident_to_candidate, promote_incidents
from harness.skills import SkillStore
from harness.skills.learning import analyze_run
from harness.skills.procedures import (
    CONSTRUCTION_PROBLEM,
    construction_candidate,
    construction_candidate_draft,
    construction_evidence,
    construction_recurrence,
    maybe_draft_construction,
)


class _Tool:
    def __init__(self, name, ok=True, args=None):
        self.tool_call_id = f"c_{name}"
        self.name = name
        self.ok = ok
        self.duration_ms = 5
        self.text = "ok" if ok else "err"
        self.error = None if ok else types.SimpleNamespace(model_dump_json=lambda: "{}")
        self.args = args or {}


def _construction_run(store, run_id, *, with_start=True, component_id="world-clock"):
    store.create_run(run_id, "eclipse-agent", {"query": "add a world clock widget"})
    if with_start:
        store.record_tool_execution(run_id, _Tool("ui_start_engineering"))
    store.record_tool_execution(
        run_id,
        _Tool("ui_register_engineered_component", args={"component": {"id": component_id}}),
    )
    store.update_run(run_id, status="completed", modelSteps=4, toolCalls=2)
    return run_id


@pytest.fixture()
def env(tmp_path):
    run_store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    skill_store = SkillStore(str(tmp_path / "eclipse-memory.db"))
    memory = EclipseMemoryService(store=skill_store)
    yield {"run": run_store, "skills": skill_store, "memory": memory}
    run_store.close()
    skill_store.close()


# ── Detection + encoding ──────────────────────────────────────────────────────


def test_evidence_requires_a_successful_registration():
    assert construction_evidence([_Tool("ui_start_engineering").__dict__]) is None
    assert construction_evidence(
        [_Tool("ui_register_engineered_component", ok=False).__dict__]
    ) is None
    found = construction_evidence([
        _Tool("ui_start_engineering").__dict__,
        _Tool("ui_register_engineered_component", args={"component": {"id": "clock"}}).__dict__,
    ])
    assert found and found["started"] is True and found["components"] == ["clock"]


def test_candidate_encodes_the_widget_add_constraints(env):
    run_id = _construction_run(env["run"], "run_c1")
    draft = construction_candidate_draft(run_id, env["run"])
    assert draft is not None
    assert draft["candidateType"] == "successful_procedure"
    text = " ".join(
        f"{step.get('action', '')} {step.get('detail', '')}"
        for step in draft["proposedProcedure"]
    )
    # The know-how the clock run had to re-derive is IN the encoded procedure.
    assert "widgets.tsx" in text
    assert "1200-line hard ceiling" in text
    assert "registry.tsx" in text
    assert "ICONS" in text
    assert "ui_register_engineered_component" in text
    assert "ui_add_widget" in text


def test_plain_run_has_no_construction_candidate(env):
    run_id = "run_plain"
    env["run"].create_run(run_id, "eclipse-agent", {"query": "hello"})
    env["run"].record_tool_execution(run_id, _Tool("research_search"))
    env["run"].update_run(run_id, status="completed", modelSteps=2, toolCalls=1)
    assert construction_candidate_draft(run_id, env["run"]) is None
    assert not any(
        d["candidateType"] == "successful_procedure" for d in analyze_run(run_id, env["run"])
    )


def test_generic_procedure_is_suppressed_for_construction_runs(env):
    run_id = _construction_run(env["run"], "run_c2")
    drafts = analyze_run(run_id, env["run"])
    procedures = [d for d in drafts if d["candidateType"] == "successful_procedure"]
    assert len(procedures) == 1
    assert procedures[0]["title"] == "Engineer a missing UI capability and register it"


# ── First occurrence → candidate; repeat → inert draft ───────────────────────


def test_first_occurrence_creates_the_candidate_and_no_draft(env):
    run_id = _construction_run(env["run"], "run_first")
    result = env["memory"].analyze_run(run_id, env["run"], skill_store=env["skills"])
    assert result["candidatesCreated"] == 1

    candidate = construction_candidate(env["skills"])
    assert candidate is not None
    assert candidate["status"] == "detected"
    assert candidate["resultingSkillId"] is None
    assert construction_recurrence(env["run"]) == 1

    # No recurrence yet: the draft gate stays shut.
    gate = maybe_draft_construction(run_id, env["run"], env["skills"])
    assert gate["drafted"] is False
    assert "recurrence" in gate["reason"]
    assert env["skills"].list_skills() == []


def test_repeat_opens_the_inert_draft(env):
    first = _construction_run(env["run"], "run_r1")
    env["memory"].analyze_run(first, env["run"], skill_store=env["skills"])
    second = _construction_run(env["run"], "run_r2", component_id="gauge")
    env["memory"].analyze_run(second, env["run"], skill_store=env["skills"])
    assert construction_recurrence(env["run"]) == 2

    gate = maybe_draft_construction(second, env["run"], env["skills"])
    assert gate["drafted"] is True, gate
    assert gate["recurrence"] == 2
    skill_id = gate["skillId"]
    assert skill_id

    skill = env["skills"].get_skill(skill_id)
    assert skill["status"] == "draft"
    version = env["skills"].get_version(skill_id, "0.1.0")
    assert version is not None
    assert version["manifest"]["origin"] == "learning"
    assert version["manifest"]["evaluationStatus"] == "not_evaluated"
    # The constraints travelled into the stored instructions.
    instructions = version.get("instructions") or ""
    assert "1200-line hard ceiling" in instructions
    assert "registry.tsx" in instructions
    candidate = construction_candidate(env["skills"])
    assert candidate["status"] == "drafted"
    assert candidate["resultingSkillId"] == skill_id


def test_no_auto_enable_and_operator_promotion_remains_the_only_path(env):
    for run_id, component in (("run_e1", "clock"), ("run_e2", "gauge")):
        _construction_run(env["run"], run_id, component_id=component)
        env["memory"].analyze_run(run_id, env["run"], skill_store=env["skills"])
    gate = maybe_draft_construction("run_e2", env["run"], env["skills"])
    assert gate["drafted"] is True

    # The automatic path NEVER enables a skill — the draft is inert.
    enabled = [s for s in env["skills"].list_skills() if s["status"] == "enabled"]
    assert enabled == []
    skill = env["skills"].get_skill(gate["skillId"])
    assert skill["status"] == "draft"

    # A second gate call is a no-op: the candidate is already drafted.
    again = maybe_draft_construction("run_e2", env["run"], env["skills"])
    assert again["drafted"] is False
    assert "drafted" in again["reason"]


def test_draft_requires_registered_tools_only(env):
    for run_id, component in (("run_t1", "clock"), ("run_t2", "gauge")):
        _construction_run(env["run"], run_id, component_id=component)
        env["memory"].analyze_run(run_id, env["run"], skill_store=env["skills"])
    gate = maybe_draft_construction(
        "run_t2", env["run"], env["skills"],
        available_tools=["ui_register_engineered_component"],
    )
    assert gate["drafted"] is True
    version = env["skills"].get_version(gate["skillId"], "0.1.0")
    # Only the tool that was declared available becomes a required tool.
    assert version["manifest"]["requiredTools"] == ["ui_register_engineered_component"]


def test_review_surfaces_the_draft_as_inert(env):
    first = _construction_run(env["run"], "run_v1")
    env["memory"].analyze_run(first, env["run"], skill_store=env["skills"])
    second = _construction_run(env["run"], "run_v2", component_id="gauge")
    env["memory"].analyze_run(second, env["run"], skill_store=env["skills"])

    service = types.SimpleNamespace(
        analyze_run=env["memory"].analyze_run, store=env["skills"],
    )
    result = review_run(service, env["run"], second)
    skills = [
        o for o in result["outcomes"]
        if o["category"] == "skill_candidate" and o["payload"].get("skill")
    ]
    assert skills, result["outcomes"]
    assert skills[0]["inert"] is True
    assert "operator-only" in skills[0]["reason"]
    assert env["skills"].get_skill(skills[0]["payload"]["skill"])["status"] == "draft"


# ── The recovery path yields the SAME candidate ──────────────────────────────


def test_resolved_capability_incident_yields_the_same_candidate(env):
    incident = {
        "id": "inc_1", "status": "resolved", "kind": "capability",
        "code": "UI_CAPABILITY_GAP", "occurrenceCount": 2,
        "message": "no registered component matches: add a world clock",
        "runId": "run_incident",
    }
    draft = incident_to_candidate(incident, [])
    assert draft is not None
    assert draft["candidateType"] == "successful_procedure"
    # ONE candidate across sources: the signature is the run-path signature.
    from harness.skills.learning import _signature as sig

    assert sig("successful_procedure", draft["problem"]) == sig(
        "successful_procedure", CONSTRUCTION_PROBLEM
    )
    assert "1200-line hard ceiling" in " ".join(
        step.get("detail", "") for step in draft["proposedProcedure"]
    )


def test_promote_incidents_persists_and_dedupes_the_construction_candidate(env):
    incident = {
        "id": "inc_2", "status": "resolved", "kind": "capability",
        "code": "UI_CAPABILITY_GAP", "occurrenceCount": 3,
        "message": "no registered component matches: add a gauge",
        "runId": "run_incident_2",
    }
    service = types.SimpleNamespace(
        store=types.SimpleNamespace(
            memory_store=env["skills"], list_attempts=lambda incident_id: [],
        ),
        list_incidents=lambda **kwargs: [incident],
    )
    first = promote_incidents(service, [incident])
    assert len(first["created"]) == 1
    assert first["created"][0]["candidateType"] == "successful_procedure"

    # A run-path candidate of the same procedure dedupes against it.
    second = promote_incidents(service, [incident])
    assert second["created"] == []
    assert second["duplicates"]

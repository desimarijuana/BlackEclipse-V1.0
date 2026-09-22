"""Phase 3 — Learning, draft generation and evaluation tests (Milestones 5–7).

Learning is criteria-driven and never auto-publishes. Drafts are inert.
Evaluation is deterministic and gates promotion. Everything runs off temp
databases and a synthetic run trace — no network, no model.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.finance_tools import register_finance_tools
from harness.persistence import AgentMemoryStore
from harness.retrieval_tools import register_retrieval_tools
from harness.skills import Actor, SkillRegistry, SkillStore
from harness.skills.draft import propose_draft
from harness.skills.evaluation import evaluate_skill, promotion_gate
from harness.skills.learning import analyze_run, capture_from_run
from harness.skills.lifecycle import approve_promotion, reject_promotion, request_promotion, rollback
from harness.skills.permissions import OPERATOR_ACTOR
from harness.tools import ToolRegistry


@pytest.fixture()
def env():
    directory = tempfile.mkdtemp(prefix="be-skilllearn-")
    db = os.path.join(directory, "agent-memory.db")
    store = AgentMemoryStore(db)
    skill_store = SkillStore(db)
    registry = SkillRegistry(skill_store)
    registry.load_all()
    tools = ToolRegistry()
    register_finance_tools(tools)
    register_retrieval_tools(tools)
    registry.attach_tool_registry(tools)
    yield {"store": store, "skill_store": skill_store, "registry": registry, "tools": tools}
    store.close()
    skill_store.close()


def _completed_run_with_failure(store, run_id="run_learn", *, recovered=True, steps=3):
    store.create_run(run_id, "eclipse-agent", {"query": "analyse ACME"})
    store.append_event(run_id, "run.started", 1)
    store.append_event(run_id, "tool.failed", 2, {"name": "fundamentals_get_financials", "code": "TOOL_ERROR"})
    store.append_event(run_id, "tool.completed", 3, {"name": "research_search"})

    class T:
        def __init__(self, name, ok):
            self.tool_call_id = f"c_{name}"
            self.name = name
            self.ok = ok
            self.duration_ms = 5
            self.text = "ok" if ok else "err"
            self.error = None if ok else type("E", (), {"model_dump_json": lambda self: "{}"})()
            self.args = {}

    store.record_tool_execution(run_id, T("fundamentals_get_financials", False))
    store.record_tool_execution(run_id, T("research_search", True))
    store.update_run(
        run_id,
        status="completed" if recovered else "failed",
        output="answer" if recovered else None,
        modelSteps=steps,
        toolCalls=2,
        toolErrors=0 if recovered else 1,
    )
    return run_id


# ── Learning: criteria ──────────────────────────────────────────────────────


def test_failure_recovery_creates_candidate(env):
    run_id = _completed_run_with_failure(env["store"])
    drafts = analyze_run(run_id, env["store"])
    types = {d["candidateType"] for d in drafts}
    assert "failure_recovery" in types


def test_unrecovered_failure_creates_validation_candidate(env):
    run_id = _completed_run_with_failure(env["store"], run_id="run_fail", recovered=False)
    env["store"].append_event(run_id, "skill.validation_failed", 4, {"reason": "schema x"})
    drafts = analyze_run(run_id, env["store"])
    assert any(d["candidateType"] == "validation_improvement" for d in drafts)
    assert not any(d["candidateType"] == "failure_recovery" for d in drafts)


def test_successful_procedure_requires_multiple_steps(env):
    run_id = "run_ok"
    env["store"].create_run(run_id, "eclipse-agent", {"query": "research"})

    class T:
        tool_call_id = "c1"; name = "research_search"; ok = True
        duration_ms = 5; text = "ok"; error = None; args = {}

    env["store"].record_tool_execution(run_id, T())
    env["store"].update_run(run_id, status="completed", modelSteps=3, toolCalls=1)
    drafts = analyze_run(run_id, env["store"])
    assert any(d["candidateType"] == "successful_procedure" for d in drafts)

    # A single-step run is not a reusable procedure.
    run2 = "run_single"
    env["store"].create_run(run2, "eclipse-agent", {"query": "quote"})
    env["store"].record_tool_execution(run2, T())
    env["store"].update_run(run2, status="completed", modelSteps=1, toolCalls=1)
    assert not any(d["candidateType"] == "successful_procedure" for d in analyze_run(run2, env["store"]))


def test_clean_run_with_no_data_creates_nothing(env):
    run_id = "run_plain"
    env["store"].create_run(run_id, "eclipse-agent", {"query": "hello"})
    env["store"].update_run(run_id, status="completed", modelSteps=1)
    assert analyze_run(run_id, env["store"]) == []


def test_capture_requires_operator(env):
    run_id = _completed_run_with_failure(env["store"])
    result = capture_from_run(run_id, env["store"], env["skill_store"], actor_is_operator=False)
    assert not result["ok"]
    assert env["skill_store"].list_candidates() == []


def test_capture_persists_and_deduplicates(env):
    run_id = _completed_run_with_failure(env["store"])
    first = capture_from_run(run_id, env["store"], env["skill_store"], actor_is_operator=True)
    assert first["ok"] and first["created"]
    # A second capture of the same run yields no new candidates (same signature).
    second = capture_from_run(run_id, env["store"], env["skill_store"], actor_is_operator=True)
    assert second["created"] == []
    assert second["duplicates"]


def test_candidate_never_auto_enables_skill(env):
    run_id = _completed_run_with_failure(env["store"])
    capture_from_run(run_id, env["store"], env["skill_store"], actor_is_operator=True)
    for candidate in env["skill_store"].list_candidates():
        assert candidate["resultingSkillId"] is None


# ── Draft generation ────────────────────────────────────────────────────────


def _make_candidate(env, *, tool="research_search"):
    run_id = _completed_run_with_failure(env["store"])
    capture_from_run(run_id, env["store"], env["skill_store"], actor_is_operator=True)
    candidates = env["skill_store"].list_candidates()
    return candidates[0]["id"]


def test_draft_is_inert(env):
    candidate_id = _make_candidate(env)
    result = propose_draft(candidate_id, env["skill_store"], available_tools=env["tools"].names())
    assert result["ok"], result
    draft = result["draft"]
    assert draft["status"] == "draft"
    assert draft["evaluationStatus"] == "not_evaluated"
    assert draft["origin"] == "learning"
    assert draft["sourceRunId"]
    # Stored as a draft version, not enabled.
    record = env["skill_store"].get_skill(draft["id"])
    assert record["status"] == "draft"


def test_draft_drops_unavailable_tools(env):
    candidate_id = _make_candidate(env)
    result = propose_draft(candidate_id, env["skill_store"], available_tools=[])
    assert result["ok"]
    assert result["draft"]["requiredTools"] == []
    assert any("unavailable tool" in issue for issue in result["issues"])


def test_draft_preserves_limitations(env):
    candidate_id = _make_candidate(env)
    result = propose_draft(candidate_id, env["skill_store"], available_tools=env["tools"].names())
    assert result["draft"]["knownLimitations"]


def test_rejected_candidate_cannot_produce_draft(env):
    candidate_id = _make_candidate(env)
    env["skill_store"].update_candidate(candidate_id, status="rejected")
    result = propose_draft(candidate_id, env["skill_store"], available_tools=env["tools"].names())
    assert not result["ok"]


# ── Evaluation ──────────────────────────────────────────────────────────────


def test_evaluate_shipped_skills_pass(env):
    for skill_id in ("research.planning", "research.source-verification",
                     "quality.financial-data-quality", "finance.fundamental-analysis",
                     "system.report-generation"):
        report = evaluate_skill(skill_id, "1.0.0", env["registry"])
        assert report["ok"], report
        assert report["status"] in ("passed", "needs_review"), (skill_id, report["status"])
        mandatory = [d for d in report["dimensions"] if d.get("mandatory")]
        assert all(d["status"] == "passed" for d in mandatory), (skill_id, mandatory)


def test_evaluation_persisted_with_dimensions(env):
    report = evaluate_skill("finance.fundamental-analysis", "1.0.0", env["registry"])
    stored = env["skill_store"].get_evaluation(report["evaluationId"])
    assert stored is not None
    names = {d["name"] for d in stored["dimensions"]}
    assert {"manifest_validation", "schema_validation", "dependency_validation",
            "permission_validation", "tool_availability", "financial_integrity"} <= names


def test_library_cases_are_loaded_and_run(env):
    cases = env["skill_store"].list_evaluation_cases("research.planning", "1.0.0")
    assert len(cases) >= 3
    report = evaluate_skill("research.planning", "1.0.0", env["registry"])
    cases_dim = [d for d in report["dimensions"] if d["name"] == "test_cases"][0]
    assert cases_dim["status"] == "passed"
    assert "0/" not in cases_dim["detail"]


def test_failed_library_case_is_detected(env):
    # A deliberately-wrong expectation must make the case dimension fail.
    env["skill_store"].replace_evaluation_cases("research.planning", "1.0.0", [
        {"caseId": "bad", "name": "bad", "kind": "input_validation", "input": {}, "expected": {"valid": True}},
    ])
    report = evaluate_skill("research.planning", "1.0.0", env["registry"])
    cases_dim = [d for d in report["dimensions"] if d["name"] == "test_cases"][0]
    assert cases_dim["status"] == "failed"


def test_financial_integrity_requires_reported_derived_evidence(env):
    # Strip the finance skill's output contract and re-evaluate.
    manifest = env["registry"].manifest("finance.fundamental-analysis")
    manifest.outputSchema = {"type": "object", "properties": {"foo": {}}}
    report = evaluate_skill("finance.fundamental-analysis", "1.0.0", env["registry"])
    fin = [d for d in report["dimensions"] if d["name"] == "financial_integrity"][0]
    assert fin["status"] == "failed"
    assert report["status"] == "blocked"


def test_missing_dependency_blocks_evaluation(env):
    env["registry"]._skills.pop("quality.financial-data-quality", None)
    env["skill_store"]._db.execute("DELETE FROM SkillVersion WHERE skillId='quality.financial-data-quality'")
    env["skill_store"]._db.commit()
    report = evaluate_skill("finance.fundamental-analysis", "1.0.0", env["registry"])
    assert report["status"] == "blocked"
    assert any(d["name"] == "dependency_validation" and d["status"] == "failed" for d in report["dimensions"])


def test_promotion_gate_semantics():
    assert promotion_gate({"status": "passed", "dimensions": []})["passed"]
    assert not promotion_gate({"status": "blocked",
                               "dimensions": [{"name": "x", "mandatory": True, "status": "failed"}]})["passed"]
    assert not promotion_gate({"status": "needs_review", "dimensions": []})["passed"]
    assert promotion_gate({"status": "needs_review", "dimensions": []}, allow_needs_review=True)["passed"]


def test_failed_evaluation_blocks_promotion(env):
    manifest = env["registry"].manifest("finance.fundamental-analysis")
    manifest.outputSchema = {"type": "object", "properties": {"foo": {}}}
    evaluate_skill("finance.fundamental-analysis", "1.0.0", env["registry"])
    result = request_promotion(
        env["registry"], skill_id="finance.fundamental-analysis", version="1.0.0",
        actor=OPERATOR_ACTOR, reason="try",
    )
    assert not result["ok"]
    assert "blocked" in result["error"]


def test_successful_promotion_enables_skill(env):
    evaluate_skill("research.planning", "1.0.0", env["registry"])
    requested = request_promotion(
        env["registry"], skill_id="research.planning", version="1.0.0",
        actor=OPERATOR_ACTOR, reason="all good",
    )
    assert requested["ok"], requested
    approved = approve_promotion(env["registry"], request_id=requested["requestId"], actor=OPERATOR_ACTOR)
    assert approved["ok"]
    assert env["skill_store"].get_skill("research.planning")["status"] == "enabled"


def test_promotion_requires_operator(env):
    evaluate_skill("research.planning", "1.0.0", env["registry"])
    result = request_promotion(
        env["registry"], skill_id="research.planning", version="1.0.0",
        actor=Actor(), reason="nope",
    )
    assert not result["ok"]


def test_reject_promotion(env):
    evaluate_skill("research.planning", "1.0.0", env["registry"])
    requested = request_promotion(
        env["registry"], skill_id="research.planning", version="1.0.0",
        actor=OPERATOR_ACTOR, reason="try",
    )
    rejected = reject_promotion(env["registry"], request_id=requested["requestId"],
                                actor=OPERATOR_ACTOR, reason="not good enough")
    assert rejected["ok"]
    assert env["skill_store"].get_skill("research.planning")["status"] == "rejected"


# ── Versioning / rollback ───────────────────────────────────────────────────


def test_version_comparison_and_rollback(env):
    manifest = env["registry"].manifest("research.planning")
    # Create a 1.1.0 version in a testing state, then roll back to 1.0.0.
    upgraded = manifest.model_copy(update={"version": "1.1.0", "status": "testing"})
    env["skill_store"].save_version(upgraded.model_dump(), upgraded.content_hash())
    env["skill_store"].set_latest_version("research.planning", "1.1.0")
    assert env["registry"].resolve_version("research.planning") == "1.1.0"

    result = rollback(env["registry"], skill_id="research.planning", to_version="1.0.0",
                      actor=OPERATOR_ACTOR, reason="regression in 1.1.0")
    assert result["ok"]
    assert env["registry"].resolve_version("research.planning") == "1.0.0"
    # The prior version is retained (deprecation over deletion).
    versions = {v["version"] for v in env["skill_store"].list_versions("research.planning")}
    assert {"1.0.0", "1.1.0"} <= versions


def test_rollback_unknown_version_fails(env):
    result = rollback(env["registry"], skill_id="research.planning", to_version="9.9.9",
                      actor=OPERATOR_ACTOR, reason="x")
    assert not result["ok"]

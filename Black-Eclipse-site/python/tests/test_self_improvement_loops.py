"""The three closure loops: skill drafting, memory curation, recall."""

from __future__ import annotations

import asyncio
import os
import tempfile
from types import SimpleNamespace

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.consolidation import consolidate_active
from harness.eclipse_memory.decision import authorize_proposal, content_signature
from harness.self_improvement.lesson_contract import (
    aggregate_signals,
    derive_confidence,
)
from harness.skills.learning import _candidate_recurrence_key
from harness.skills.evaluation import retire_non_discriminating
from harness.skills.learning import analyze_run as learning_analyze
from harness.memory_tools import (
    learning_candidate_list_handler,
    session_search_handler,
    skill_list_handler,
    skill_view_handler,
)
from harness.persistence import AgentMemoryStore
from harness.session_index import backfill_run_index
from harness.skills.draft import (
    auto_draft_ready_candidates,
    evaluate_drafted_skills,
    propose_draft,
)
from harness.skills.registry import SkillRegistry
from harness.tools import ToolContext


def _tool(name: str, ok: bool, text: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        tool_call_id=f"{name}-{ok}", name=name, ok=ok, duration_ms=1,
        text=text, error=None, args={},
    )


def test_a_recurring_recovery_candidate_is_auto_drafted_but_never_enabled():
    directory = tempfile.mkdtemp(prefix="be-loops-")
    run_store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    skill_store = EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db"))
    service = EclipseMemoryService(skill_store)
    try:
        def _record(run_id: str) -> None:
            run_store.create_run(run_id, "eclipse-agent", {"query": "x"})
            run_store.record_tool_execution(
                run_id, _tool("get_fundamentals", False, "TOOL_ERROR"),
            )
            run_store.record_tool_execution(run_id, _tool("get_fundamentals", True))
            run_store.update_run(
                run_id, status="completed", output="Recovered.", modelSteps=3,
            )

        _record("run_rec_1")
        first = service.analyze_run(
            "run_rec_1", run_store, skill_store=skill_store,
        )
        assert first["candidatesCreated"] == 1
        assert first["draftsCreated"] == []

        _record("run_rec_2")
        second = service.analyze_run(
            "run_rec_2", run_store, skill_store=skill_store,
        )
        assert second["draftsCreated"], second
        drafted = [
            item for item in skill_store.list_candidates()
            if item["status"] == "drafted"
        ]
        assert drafted
        candidate = drafted[0]
        assert candidate["resultingSkillId"]
        skill = skill_store.get_skill(candidate["resultingSkillId"])
        assert skill["status"] == "draft"
        enabled = skill_store.list_skills(status="enabled") if hasattr(
            skill_store, "list_skills",
        ) else []
        assert not any(item.get("id") == skill["id"] for item in enabled)
    finally:
        run_store.close()
        service.close()


def test_a_recorded_user_correction_becomes_a_scoped_candidate():
    directory = tempfile.mkdtemp(prefix="be-correction-")
    run_store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    skill_store = EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db"))
    service = EclipseMemoryService(skill_store)
    try:
        run_store.create_run("run_corr", "eclipse-agent", {"query": "x"})
        run_store.update_run(
            "run_corr", status="completed", output="Corrected.", modelSteps=2,
            memory={
                "action": "correct",
                "contentPreview": "Use the period ended, not the fiscal year",
            },
        )
        result = service.analyze_run(
            "run_corr", run_store, skill_store=skill_store,
        )
        assert result["candidatesCreated"] == 1
        candidate = skill_store.list_candidates()[0]
        assert candidate["candidateType"] == "user_correction"
        assert "correction" in candidate["condition"]
        assert candidate["status"] == "drafted"
        assert skill_store.get_skill(candidate["resultingSkillId"])["status"] == "draft"
    finally:
        run_store.close()
        service.close()


def test_automatic_consolidation_merges_duplicates_but_not_contradictions():
    directory = tempfile.mkdtemp(prefix="be-curate-")
    service = EclipseMemoryService(
        EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")),
    )
    try:
        first = service.write_memory(
            memory_type="preference", content="I prefer concise answers",
            source="explicit_user", scope="user", scope_id="u1",
            subject="answer-style", allow_duplicate=True,
        )
        second = service.write_memory(
            memory_type="preference", content="I prefer concise answers",
            source="explicit_user", scope="user", scope_id="u1",
            subject="answer-style", allow_duplicate=True,
        )
        report = consolidate_active(service.store, resolve_conflicts=False)
        assert report["duplicateCount"] >= 1
        statuses = {
            service.store.get_memory(first["id"])["status"],
            service.store.get_memory(second["id"])["status"],
        }
        assert "superseded" in statuses

        left = service.write_memory(
            memory_type="preference", content="I prefer brief answers",
            source="explicit_user", scope="user", scope_id="u2",
            subject="answer-style", allow_duplicate=True,
        )
        right = service.write_memory(
            memory_type="preference", content="I prefer detailed answers",
            source="explicit_user", scope="user", scope_id="u2",
            subject="answer-style", allow_duplicate=True,
        )
        report = consolidate_active(service.store, resolve_conflicts=False)
        assert report["conflictCount"] >= 1
        assert service.store.get_memory(left["id"])["status"] == "active"
        assert service.store.get_memory(right["id"])["status"] == "active"
    finally:
        service.close()


def test_a_preference_inside_a_long_audit_prompt_is_saved_alone():
    directory = tempfile.mkdtemp(prefix="be-pref-")
    service = EclipseMemoryService(
        EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")),
    )
    try:
        text = (
            "HARDCORE LOOP VERIFICATION. Treat this as an audit. Read-only except "
            "the preference sentence below. In this run do not write.\n\n"
            'First: I prefer concise, evidence-first answers with a short "What changed" '
            "section and no preamble.\n\nNow run the audit."
        )
        decision = service.decide_turn(text, user_id="local")
        assert decision.outcome == "save"
        outcome = service.commit_decision(decision, user_id="local")
        memory = outcome["memory"]
        assert memory["authority"] == "automatic"
        assert memory["content"].startswith("I prefer concise")
        assert "HARDCORE" not in memory["content"]
        assert "in this run" not in memory["content"]
    finally:
        service.close()


@pytest.mark.asyncio
async def test_store_only_draft_is_visible_to_skill_list_and_view():
    directory = tempfile.mkdtemp(prefix="be-draft-view-")
    store = EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db"))
    try:
        candidate_id = store.save_candidate({
            "candidateType": "successful_procedure",
            "title": "Reusable procedure: analysis_run",
            "problem": "A multi-step procedure completed.",
            "proposedLesson": "Use analysis_run for this repeatable computation.",
            "proposedProcedure": [{"step": 1, "action": "call analysis_run"}],
            "evidenceReferences": [
                {"kind": "tool", "name": "analysis_run"},
                {"kind": "tool", "name": "analysis_run"},
            ],
            "confidence": 0.6, "status": "detected",
            "signature": "store_only_draft", "sourceRunId": "run_seed",
        })
        assert propose_draft(candidate_id, store, available_tools=["analysis_run"])["ok"]
        registry = SkillRegistry(store)
        ctx = ToolContext(
            run_id="probe", log=lambda *_: None, skill_registry=registry,
            memory_service=EclipseMemoryService(store),
        )
        skill_id = "learned.reusable-procedure-analysis-run"
        text, data = await skill_list_handler({"query": skill_id}, ctx)
        assert any(item["id"] == skill_id and item["status"] == "draft" for item in data["skills"]), text
        view_text, view = await skill_view_handler({"name": skill_id}, ctx)
        assert view["found"] is True
        assert view["status"] == "draft"
        assert "analysis_run" in view_text
        list_text, listed = await learning_candidate_list_handler({}, ctx)
        assert "draftedSkill=" + skill_id in list_text
    finally:
        store.close()


@pytest.mark.asyncio
async def test_session_search_run_id_indexes_a_just_finished_run():
    directory = tempfile.mkdtemp(prefix="be-race-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        store.create_run("run_race", "eclipse-agent", {"query": "x"})
        store.update_run(
            "run_race", status="completed",
            output="The unique racecheck token.", modelSteps=2,
        )
        ctx = ToolContext(
            run_id="probe", log=lambda *_: None,
            memory_store=store, user_id="local",
        )
        text, data = await session_search_handler(
            {"query": "racecheck", "run_id": "run_race"}, ctx,
        )
        assert data["results"], text
        assert data["results"][0]["runId"] == "run_race"
        assert "match:" in text
    finally:
        store.close()


def test_a_preference_survives_secret_words_in_the_surrounding_prompt():
    directory = tempfile.mkdtemp(prefix="be-pref-token-")
    service = EclipseMemoryService(
        EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")),
    )
    try:
        text = (
            "Audit instructions mention a token, a credential and a run_id.\n"
            "I prefer short comparison tables with a one-line takeaway after each table.\n"
            "Do not write anything else."
        )
        decision = service.decide_turn(text, user_id="local")
        assert decision.outcome == "save", decision
        outcome = service.commit_decision(decision, user_id="local")
        memory = outcome["memory"]
        assert memory["content"].startswith("I prefer short comparison tables")
        assert memory["authority"] == "automatic"
    finally:
        service.close()


def test_a_learned_draft_is_evaluated_but_not_enabled():
    directory = tempfile.mkdtemp(prefix="be-eval-draft-")
    store = EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db"))
    try:
        candidate_id = store.save_candidate({
            "candidateType": "successful_procedure",
            "title": "Reusable procedure: analysis_run",
            "problem": "A multi-step procedure completed.",
            "proposedLesson": "Use analysis_run for this repeatable computation.",
            "proposedProcedure": [{"step": 1, "action": "call analysis_run"}],
            "evidenceReferences": [
                {"kind": "tool", "name": "analysis_run"},
                {"kind": "tool", "name": "analysis_run"},
            ],
            "confidence": 0.6, "status": "detected",
            "signature": "evaluated_draft", "sourceRunId": "run_seed",
        })
        assert propose_draft(candidate_id, store, available_tools=["analysis_run"])["ok"]
        registry = SkillRegistry(store)
        result = evaluate_drafted_skills(registry)
        assert result["evaluated"], result
        assert result["evaluated"][0]["skillId"].startswith("learned.")
        status = store.get_skill(result["evaluated"][0]["skillId"])["status"]
        # Evaluation may leave a draft inert as `draft`, or park it in `testing`
        # while the execution tier is pending. It is never enabled by eval alone.
        assert status in ("draft", "testing"), status
        assert store.list_evaluations(
            result["evaluated"][0]["skillId"],
        ), "the evaluation must be persisted"
        ctx = ToolContext(
            run_id="probe", log=lambda *_: None, skill_registry=registry,
            memory_service=EclipseMemoryService(store),
        )
        body, view = asyncio.run(skill_view_handler(
            {"name": result["evaluated"][0]["skillId"]}, ctx,
        ))
        expected = result["evaluated"][0]["status"]
        assert view["evaluationStatus"] == expected
        assert f"Evaluation: {expected}" in body
    finally:
        store.close()


def test_model_tool_save_is_agent_curated_not_explicit():
    directory = tempfile.mkdtemp(prefix="be-tool-save-")
    service = EclipseMemoryService(
        EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")),
    )
    try:
        decision = authorize_proposal(
            content="Prefers concise evidence-first answers",
            provenance="memory_tool",
            user_message="I prefer concise evidence-first answers",
            user_id="u1",
            memory_type="preference",
            scope="user",
            scope_id="u1",
        )
        assert decision.outcome == "save"
        outcome = service.commit_decision(decision, user_id="u1")
        memory = outcome["memory"]
        assert memory["source"] == "automatic_learning"
        assert memory["authority"] == "automatic"
    finally:
        service.close()


def test_synthetic_failure_recovery_yields_all_contract_fields():
    directory = tempfile.mkdtemp(prefix="be-contract-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        store.create_run("run_contract", "eclipse-agent", {"query": "x"})
        store.record_tool_execution(
            "run_contract", _tool("get_fundamentals", False, "TOOL_ERROR"),
        )
        store.record_tool_execution(
            "run_contract", _tool("get_fundamentals", True),
        )
        store.update_run(
            "run_contract", status="completed", output="Recovered.", modelSteps=3,
        )
        drafts = learning_analyze("run_contract", store)
        recovery = [
            d for d in drafts if d.get("candidateType") == "failure_recovery"
        ]
        assert recovery, drafts
        draft = recovery[0]
        for field in (
            "failedCall", "recoveredCall", "precondition",
            "proposedProcedure", "replayTest",
        ):
            assert draft.get(field), field
        assert draft["confidence"] != 0.55
    finally:
        store.close()


def test_confidence_is_derived_not_constant():
    low = derive_confidence(evidence_count=1, occurrence_count=1, has_replay=True)
    high = derive_confidence(evidence_count=3, occurrence_count=3, has_replay=True)
    assert low != high
    assert low == 0.4
    assert high > low


def test_explicit_correction_drafts_on_first_occurrence():
    directory = tempfile.mkdtemp(prefix="be-correction-draft-")
    run_store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    skill_store = EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db"))
    service = EclipseMemoryService(skill_store)
    try:
        run_store.create_run("run_corr_first", "eclipse-agent", {"query": "x"})
        run_store.update_run(
            "run_corr_first", status="completed", output="Corrected.", modelSteps=2,
            memory={
                "action": "correct",
                "contentPreview": "Use the period ended, not the fiscal year",
            },
        )
        result = service.analyze_run(
            "run_corr_first", run_store, skill_store=skill_store,
        )
        assert result["draftsCreated"], result
        drafted = [
            item for item in skill_store.list_candidates()
            if item["status"] == "drafted"
        ]
        assert drafted and drafted[0]["candidateType"] == "user_correction"
        assert skill_store.get_skill(drafted[0]["resultingSkillId"])["status"] == "draft"
    finally:
        run_store.close()
        service.close()


def test_proposed_memory_promotes_after_recurrence_but_not_on_conflict():
    directory = tempfile.mkdtemp(prefix="be-promote-")
    service = EclipseMemoryService(
        EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")),
    )
    try:
        content = "I prefer quarterly reviews"
        proposed = service.store.save_memory(
            memory_type="preference", scope="user", content=content,
            source="automatic_learning", authority="automatic",
            status="proposed", status_reason="awaiting a second observation",
        )
        signature = content_signature(content)
        service.store.record_recurrence(signature)
        service.store.record_recurrence(signature)
        promoted = service.promote_confirmed_proposals()
        assert proposed["id"] in promoted["promoted"]
        assert service.store.get_memory(proposed["id"])["status"] == "active"

        conflicting = service.store.save_memory(
            memory_type="preference", scope="user",
            content="I prefer monthly reviews", source="automatic_learning",
            authority="automatic", status="proposed",
            status_reason="conflict: automatic conflict requires review",
        )
        service.store.record_recurrence(content_signature("I prefer monthly reviews"))
        service.store.record_recurrence(content_signature("I prefer monthly reviews"))
        service.promote_confirmed_proposals()
        assert service.store.get_memory(conflicting["id"])["status"] == "proposed"
    finally:
        service.close()


def test_identical_metrics_retire_the_skill_not_keep_it():
    directory = tempfile.mkdtemp(prefix="be-retire-")
    store = EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db"))
    try:
        candidate_id = store.save_candidate({
            "candidateType": "successful_procedure",
            "title": "Reusable procedure: analysis_run",
            "problem": "A multi-step procedure completed.",
            "proposedLesson": "Use analysis_run for this repeatable computation.",
            "proposedProcedure": [{"step": 1, "action": "call analysis_run"}],
            "evidenceReferences": [
                {"kind": "tool", "name": "analysis_run"},
                {"kind": "tool", "name": "analysis_run"},
            ],
            "confidence": 0.6, "status": "detected",
            "signature": "retire_draft", "sourceRunId": "run_seed",
        })
        assert propose_draft(candidate_id, store, available_tools=["analysis_run"])["ok"]
        skill_id = "learned.reusable-procedure-analysis-run"
        retired = retire_non_discriminating(
            store, skill_id, "0.1.0",
            {"dimensions": [{"name": "discrimination", "status": "failed"}]},
        )
        assert retired is True
        assert store.get_skill(skill_id)["status"] == "deprecated"
    finally:
        store.close()


def test_legacy_reviews_are_marked_without_rewriting_them():
    directory = tempfile.mkdtemp(prefix="be-legacy-review-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        row = store.save_learning_review({
            "runId": "run_legacy_review",
            "status": "completed",
            "mode": "deterministic",
            "createdAt": "2026-10-01T00:00:00.000Z",
            "result": {"outcomes": [{"category": "no_learning", "reason": "old"}]},
        })
        marked = store.mark_legacy_reviews("2026-10-28T00:00:00.000Z")
        assert marked == 1
        saved = store.get_learning_review(row["id"])
        assert saved["legacyUnscored"] == 1
        assert saved["result"]["outcomes"][0]["reason"] == "old"
    finally:
        store.close()


def test_loop_end_to_end_generate_accept_enable_score_retire():
    directory = tempfile.mkdtemp(prefix="be-e2e-")
    run_store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    skill_store = EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db"))
    service = EclipseMemoryService(skill_store)
    try:
        run_store.create_run("run_e2e", "eclipse-agent", {"query": "x"})
        run_store.record_tool_execution(
            "run_e2e", _tool("get_fundamentals", False, "TOOL_ERROR"),
        )
        run_store.record_tool_execution(
            "run_e2e", _tool("get_fundamentals", True),
        )
        run_store.update_run(
            "run_e2e", status="completed", output="Recovered.", modelSteps=3,
        )
        generated = service.analyze_run(
            "run_e2e", run_store, skill_store=skill_store,
        )
        assert generated["candidatesCreated"] == 1
        candidate = skill_store.list_candidates()[0]
        assert candidate["status"] == "detected"

        # The operator accept route uses this same draft path after validation.
        assert propose_draft(
            candidate["id"], skill_store, available_tools=["get_fundamentals"],
        )["ok"]
        skill_store.update_candidate(candidate["id"], status="accepted")
        candidate = skill_store.get_candidate(candidate["id"])
        assert candidate["status"] == "accepted"
        skill_id = candidate["resultingSkillId"]
        assert skill_store.get_skill(skill_id)["status"] == "draft"

        # Explicit operator enablement (the gate is retained; the test acts as
        # the operator).
        # Store-level enablement is the same operator transition the Skills UI
        # uses (the test acts as the operator; no agent path can call this).
        skill_store.set_version_status(skill_id, "0.1.0", "enabled", "passed")
        assert skill_store.get_skill(skill_id)["status"] == "enabled"

        # Identical metrics vs base -> discrimination failed -> deprecated.
        retired = retire_non_discriminating(
            skill_store, skill_id, "0.1.0",
            {"dimensions": [{"name": "discrimination", "status": "failed"}]},
        )
        assert retired is True
        assert skill_store.get_skill(skill_id)["status"] == "deprecated"
    finally:
        run_store.close()
        service.close()


def test_recurrence_key_is_structural_not_title_or_timestamp():
    same_a = [
        {"name": "get_fundamentals", "ok": False, "error": {"code": "TOOL_ERROR"}, "text": "TOOL_ERROR"},
        {"name": "get_fundamentals", "ok": True, "text": "ok"},
    ]
    same_b = [
        {"name": "get_fundamentals", "ok": False, "error": {"code": "TOOL_ERROR"}, "text": "TOOL_ERROR"},
        {"name": "get_fundamentals", "ok": True, "text": "ok"},
    ]
    assert _candidate_recurrence_key("failure_recovery", same_a) == (
        _candidate_recurrence_key("failure_recovery", same_b)
    )
    different_failure = [
        {"name": "get_fundamentals", "ok": False, "error": {"code": "DATA_UNAVAILABLE"}, "text": "unavailable"},
        {"name": "get_fundamentals", "ok": True, "text": "ok"},
    ]
    assert _candidate_recurrence_key("failure_recovery", same_a) != (
        _candidate_recurrence_key("failure_recovery", different_failure)
    )
    proc_a = [{"name": "analysis_run", "ok": True}, {"name": "research_search", "ok": True}]
    proc_b = [{"name": "analysis_run", "ok": True}, {"name": "research_search", "ok": True}]
    proc_c = [{"name": "research_search", "ok": True}, {"name": "analysis_run", "ok": True}]
    assert _candidate_recurrence_key("successful_procedure", proc_a) == (
        _candidate_recurrence_key("successful_procedure", proc_b)
    )
    assert _candidate_recurrence_key("successful_procedure", proc_a) != (
        _candidate_recurrence_key("successful_procedure", proc_c)
    )


def test_five_identical_lessons_collapse_to_one_recurring_signal():
    reviews = [
        {
            "runId": f"run_sig_{index}",
            "result": {"outcomes": [{
                "category": "typed_lesson",
                "payload": {"lesson": {
                    "condition": "successful analysis_run procedure",
                    "action": "reuse analysis_run",
                    "kind": "successful_procedure",
                    "confidence": 0.5,
                }},
            }]},
        }
        for index in range(5)
    ]
    signals = aggregate_signals(reviews, min_occurrences=2)
    assert len(signals) == 1
    assert signals[0]["occurrences"] == 5
    assert signals[0]["eligible"] is True


def test_explicit_correction_is_eligible_at_recurrence_one():
    reviews = [{
        "runId": "run_corr_sig",
        "result": {"outcomes": [{
            "category": "typed_lesson",
            "payload": {"lesson": {
                "condition": "user correction about fiscal year",
                "action": "use the period ended instead",
                "kind": "user_correction",
                "confidence": 0.4,
            }},
        }]},
    }]
    signals = aggregate_signals(reviews, min_occurrences=2)
    assert signals[0]["eligible"] is True
    assert signals[0]["reason"] == "explicit correction fast path"


def test_usage_report_separates_automatic_from_explicit_saves():
    directory = tempfile.mkdtemp(prefix="be-usage-")
    service = EclipseMemoryService(
        EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")),
    )
    try:
        decision = service.decide_turn("I prefer concise answers", user_id="u1")
        outcome = service.commit_decision(decision, user_id="u1")
        assert outcome["ok"] is True
        assert outcome["memory"]["authority"] == "automatic"
        report = service.usage_report(window_days=30)
        assert report["durableWrites"]["automaticSaved"] >= 1
        assert report["durableWrites"]["saved"] >= 1
    finally:
        service.close()


def test_a_legacy_detected_candidate_is_auto_drafted_at_maintenance():
    directory = tempfile.mkdtemp(prefix="be-legacy-draft-")
    store = EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db"))
    try:
        candidate_id = store.save_candidate({
            "candidateType": "successful_procedure",
            "title": "Reusable procedure: analysis_run",
            "problem": "A multi-step research procedure completed with no tool failures.",
            "proposedLesson": "Use analysis_run for this repeatable computation.",
            "proposedProcedure": [{"step": 1, "action": "call analysis_run"}],
            "evidenceReferences": [
                {"kind": "tool", "name": "analysis_run"},
                {"kind": "tool", "name": "analysis_run"},
            ],
            "confidence": 0.6,
            "status": "detected",
            "signature": "legacy_successful_procedure",
            "sourceRunId": "run_legacy",
        })
        result = auto_draft_ready_candidates(store)
        assert result["drafted"], result
        candidate = store.get_candidate(candidate_id)
        assert candidate["status"] == "drafted"
        assert store.get_skill(candidate["resultingSkillId"])["status"] == "draft"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_local_session_search_does_not_filter_out_unowned_history():
    directory = tempfile.mkdtemp(prefix="be-local-recall-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        store.create_run("run_old", "eclipse-agent", {"query": "what did we decide"})
        store.update_run(
            "run_old", status="completed",
            output="We decided to use consolidated figures.", modelSteps=2,
        )
        backfill_run_index(store, limit=10)
        ctx = ToolContext(
            run_id="run_now", log=lambda *_: None,
            memory_store=store, user_id="local",
        )
        text, data = await session_search_handler(
            {"query": "consolidated figures"}, ctx,
        )
        assert data["results"], text
        assert data["results"][0]["runId"] == "run_old"

        # A natural-language query with an unmatched token falls back to ANY
        # terms instead of returning an empty result set.
        text, data = await session_search_handler(
            {"query": "consolidated zzzznomatch"}, ctx,
        )
        assert data["results"], text
        assert data.get("matchMode") == "any"
    finally:
        store.close()


def test_session_index_backfill_makes_historical_runs_searchable():
    directory = tempfile.mkdtemp(prefix="be-recall-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        store.create_run("run_old", "eclipse-agent", {"query": "what did we decide"})
        store.update_run(
            "run_old", status="completed",
            output="We decided to use consolidated figures.", modelSteps=2,
        )
        assert store.session_message_count() == 0

        result = backfill_run_index(store, limit=10)
        assert result["ok"] is True
        assert result["indexed"] == 1
        assert store.session_message_count() >= 1

        found = store.search_session_messages("consolidated figures")
        assert found["results"]
        assert found["results"][0]["runId"] == "run_old"
    finally:
        store.close()

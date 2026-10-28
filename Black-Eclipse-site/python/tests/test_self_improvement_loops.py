"""The three closure loops: skill drafting, memory curation, recall."""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.consolidation import consolidate_active
from harness.memory_tools import (
    learning_candidate_list_handler,
    session_search_handler,
    skill_list_handler,
    skill_view_handler,
)
from harness.persistence import AgentMemoryStore
from harness.session_index import backfill_run_index
from harness.skills.draft import auto_draft_ready_candidates, propose_draft
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
        assert candidate["status"] == "detected"
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

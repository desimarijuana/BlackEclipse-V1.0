"""The three closure loops: skill drafting, memory curation, recall."""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory.consolidation import consolidate_active
from harness.persistence import AgentMemoryStore
from harness.session_index import backfill_run_index


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

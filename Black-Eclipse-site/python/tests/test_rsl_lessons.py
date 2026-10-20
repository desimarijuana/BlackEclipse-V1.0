"""RSL R6 — adopted lessons: cue/evidence gate, tripwire, scoped retrieval."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.eclipse_memory import EclipseMemoryStore
from harness.evaluation.store import EvaluationStore
from harness.evaluation.verdict_guard import VerdictLeakError
from harness.graph_context import _lesson_manifest_context
from harness.persistence import AgentMemoryStore
from harness.prompt_segments import (
    MAX_LESSON_MANIFEST_CHARS,
    MAX_LESSONS_IN_MANIFEST,
    build_lesson_manifest,
    build_prompt_plan,
)
from harness.self_improvement.lessons import (
    distill_lesson,
    lesson_signature,
    select_lessons,
)


@pytest.fixture()
def stores(tmp_path):
    lessons = EclipseMemoryStore(str(tmp_path / "eclipse-memory.db"))
    runs = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield lessons, runs, EvaluationStore(runs)
    lessons.close()
    runs.close()


def _completed_run(eval_store: EvaluationStore, run_id: str = "evalrun-1") -> str:
    eval_store.create_run(
        id=run_id,
        suite="rsl-code",
        datasetName="owning-tests",
        datasetVersion="1",
        datasetChecksum="checksum",
        tier=0,
        invoker="worktree-tests",
        agentVersion="agent",
        gitCommit="commit",
        config={"kind": "rsl", "benchmark": "UNMEASURED"},
        metadata={"kind": "rsl", "decision": "tests_passed"},
        status="completed",
    )
    return run_id


def _candidate(**overrides):
    candidate = {
        "id": "evo_lesson_1",
        "cue": "market data timeout",
        "proposedLesson": (
            "When a market data request times out, retry once before falling "
            "back to the next eligible source."
        ),
        "evidenceReferences": [{"kind": "event", "id": "evt_1"}],
        "scope": {"capability": "live_quote"},
        "sourceRunId": "run_source",
    }
    candidate.update(overrides)
    return candidate


def _distill(lessons, candidate, *, run_id="evalrun-1", **overrides):
    return distill_lesson(
        lessons,
        candidate,
        overrides.pop("decision", "tests_passed"),
        validation_run_id=run_id,
        adopted_artifact_type="evolution_candidate",
        adopted_artifact_id=candidate.get("id"),
        **overrides,
    )


def test_missing_cue_discards_and_stores_nothing(stores):
    lessons, _, eval_store = stores
    _completed_run(eval_store)
    result = _distill(lessons, _candidate(cue=""))
    assert result["stored"] is False and result["discarded"] is True
    assert result["reason"] == "missing_cue"
    assert lessons.list_candidates() == []


def test_missing_evidence_discards_and_stores_nothing(stores):
    lessons, _, eval_store = stores
    _completed_run(eval_store)
    result = _distill(lessons, _candidate(evidenceReferences=[]))
    assert result["stored"] is False and result["discarded"] is True
    assert result["reason"] == "missing_evidence"
    assert lessons.list_candidates() == []


def test_missing_lesson_discards_and_stores_nothing(stores):
    lessons, _, eval_store = stores
    _completed_run(eval_store)
    result = _distill(lessons, _candidate(proposedLesson=""))
    assert result["stored"] is False and result["discarded"] is True
    assert result["reason"] == "missing_lesson"
    assert lessons.list_candidates() == []


def test_verdict_leak_is_refused_and_stores_nothing(stores):
    lessons, _, eval_store = stores
    _completed_run(eval_store)
    candidate = _candidate(
        proposedLesson="The candidate reached pass_rate 0.9 after the edit.",
    )
    with pytest.raises(VerdictLeakError, match="pass_rate"):
        _distill(lessons, candidate)
    assert lessons.list_candidates() == []


def test_adopted_lesson_records_artifact_and_validation_run(stores):
    lessons, _, eval_store = stores
    run_id = _completed_run(eval_store)
    result = _distill(lessons, _candidate(), run_id=run_id)
    assert result["stored"] is True
    row = lessons.get_candidate(result["lessonId"])
    assert row["status"] == "adopted"
    assert row["cue"] == "market data timeout"
    assert row["adoptedArtifactType"] == "evolution_candidate"
    assert row["adoptedArtifactId"] == "evo_lesson_1"
    assert row["validationRunId"] == run_id
    assert row["signature"] == lesson_signature(row["cue"], row["proposedLesson"])
    assert row["scope"] == {"capability": "live_quote"}


def test_dedupe_is_by_cue_and_lesson(stores):
    lessons, _, eval_store = stores
    _completed_run(eval_store)
    first = _distill(lessons, _candidate())
    second = _distill(lessons, _candidate(id="evo_other"))
    assert first["stored"] is True
    assert second["stored"] is False and second["duplicate"] is True
    assert second["lessonId"] == first["lessonId"]
    assert len(lessons.list_candidates(status="adopted")) == 1


def test_non_adopted_decision_is_discarded(stores):
    lessons, _, eval_store = stores
    _completed_run(eval_store)
    result = _distill(lessons, _candidate(), decision="tests_failed")
    assert result["stored"] is False and result["reason"] == "not_adopted"
    assert lessons.list_candidates() == []


def test_later_matching_task_receives_the_lesson(stores):
    lessons, runs, eval_store = stores
    run_id = _completed_run(eval_store)
    adopted = _distill(lessons, _candidate(), run_id=run_id)

    selected = select_lessons(
        lessons,
        cue="market data request timed out for AAPL",
        scope={"capability": "live_quote"},
        eval_store=eval_store,
    )
    assert [row["id"] for row in selected] == [adopted["lessonId"]]

    content, ids = build_lesson_manifest(selected)
    assert ids == (adopted["lessonId"],)
    assert adopted["lessonId"] in content
    assert "retry once" in content
    assert len(content) <= MAX_LESSON_MANIFEST_CHARS


@pytest.mark.asyncio
async def test_prompt_helper_injects_and_emits_lesson_ids(stores):
    lessons, runs, eval_store = stores
    run_id = _completed_run(eval_store)
    adopted = _distill(lessons, _candidate(), run_id=run_id)

    class Memory:
        def __init__(self, store):
            self.store = store
            self.policy = SimpleNamespace(get_all=lambda: {})

    class Emitter:
        def __init__(self):
            self.events = []

        async def emit(self, event_type, data=None):
            self.events.append((event_type, data or {}))

    emitter = Emitter()
    request = SimpleNamespace(
        input=SimpleNamespace(
            query="market data request timed out for AAPL",
            ticker="AAPL",
            market=None,
            context={"scope": {"capability": "live_quote"}},
        ),
    )
    content, lesson_ids = await _lesson_manifest_context(
        request, Memory(lessons), runs, emitter,
    )

    assert lesson_ids == (adopted["lessonId"],)
    assert adopted["lessonId"] in content
    events = [event for event in emitter.events if event[0] == "prompt.lesson_injected"]
    assert len(events) == 1
    payload = events[0][1]
    assert payload["lessonIds"] == [adopted["lessonId"]]
    assert payload["lessons"][0]["validationRunId"] == run_id
    assert payload["lessons"][0]["adoptedArtifactType"] == "evolution_candidate"


@pytest.mark.asyncio
async def test_no_matching_cue_means_no_injection(stores):
    lessons, runs, eval_store = stores
    run_id = _completed_run(eval_store)
    _distill(lessons, _candidate(), run_id=run_id)

    selected = select_lessons(
        lessons,
        cue="compute the portfolio variance",
        scope={"capability": "live_quote"},
        eval_store=eval_store,
    )
    assert selected == []
    assert build_lesson_manifest(selected) == ("", ())

    class Memory:
        def __init__(self, store):
            self.store = store
            self.policy = SimpleNamespace(get_all=lambda: {})

    class Emitter:
        def __init__(self):
            self.events = []

        async def emit(self, event_type, data=None):
            self.events.append((event_type, data or {}))

    emitter = Emitter()
    request = SimpleNamespace(
        input=SimpleNamespace(
            query="compute the portfolio variance",
            ticker=None,
            market=None,
            context=None,
        ),
    )
    content, lesson_ids = await _lesson_manifest_context(
        request, Memory(lessons), runs, emitter,
    )
    assert content == "" and lesson_ids == ()
    assert emitter.events == []


def test_lesson_is_ineligible_until_its_validation_run_completes(stores):
    lessons, _, eval_store = stores
    eval_store.create_run(
        id="evalrun-running",
        suite="rsl-code",
        datasetName="owning-tests",
        datasetVersion="1",
        datasetChecksum="checksum",
        status="running",
        config={"kind": "rsl"},
        metadata={"kind": "rsl"},
    )
    _distill(lessons, _candidate(), run_id="evalrun-running")

    assert select_lessons(
        lessons,
        cue="market data request timed out",
        scope={"capability": "live_quote"},
        eval_store=eval_store,
    ) == []


def test_scoped_lesson_does_not_apply_outside_its_scope(stores):
    lessons, _, eval_store = stores
    run_id = _completed_run(eval_store)
    _distill(lessons, _candidate(), run_id=run_id)

    assert select_lessons(
        lessons,
        cue="market data request timed out",
        scope={"capability": "fundamentals"},
        eval_store=eval_store,
    ) == []


def test_transfer_opt_in_allows_a_cue_match_across_scopes(stores):
    lessons, _, eval_store = stores
    run_id = _completed_run(eval_store)
    stored = _distill(lessons, _candidate(), run_id=run_id)

    transferred = select_lessons(
        lessons,
        cue="market data request timed out",
        scope={"capability": "fundamentals"},
        eval_store=eval_store,
        allow_transfer=True,
    )
    assert [row["id"] for row in transferred] == [stored["lessonId"]]


def test_migration_31_is_idempotent_when_columns_already_exist(tmp_path):
    import sqlite3

    path = str(tmp_path / "idempotent.db")
    first = EclipseMemoryStore(path)
    columns = {
        row["name"] for row in first.db.execute("PRAGMA table_info(LearningCandidate)")
    }
    assert {"cue", "adoptedArtifactType", "adoptedArtifactId", "validationRunId"} <= columns
    first.close()

    connection = sqlite3.connect(path)
    connection.execute("DELETE FROM SchemaMigration WHERE version=31")
    connection.commit()
    connection.close()

    second = EclipseMemoryStore(path)
    try:
        columns = {
            row["name"]
            for row in second.db.execute("PRAGMA table_info(LearningCandidate)")
        }
        assert {"cue", "adoptedArtifactType", "adoptedArtifactId", "validationRunId"} <= columns
        assert second.db.migration_status()["upToDate"] is True
    finally:
        second.close()


def test_manifest_stays_within_count_and_character_budget():
    lessons = [
        {
            "id": f"lesson_{index}",
            "cue": "market data timeout",
            "proposedLesson": "x" * 600,
        }
        for index in range(6)
    ]
    content, ids = build_lesson_manifest(lessons)
    assert len(ids) <= MAX_LESSONS_IN_MANIFEST
    assert len(content) <= MAX_LESSON_MANIFEST_CHARS

    tight, tight_ids = build_lesson_manifest(lessons, max_chars=200)
    assert len(tight) <= 200
    assert len(tight_ids) <= MAX_LESSONS_IN_MANIFEST


def test_lesson_manifest_is_a_run_frozen_segment():
    base = dict(
        system_prompt="You are Eclipse.",
        agent_id="eclipse-agent",
        tool_names=["memory"],
        user_message="hello",
    )
    first = build_prompt_plan(lesson_manifest="L1", **base)
    second = build_prompt_plan(lesson_manifest="L2", **base)
    assert first.cache_key == second.cache_key
    assert first.by_id("lesson_manifest").content == "L1"
    assert first.by_id("lesson_manifest").content_hash != second.by_id(
        "lesson_manifest"
    ).content_hash

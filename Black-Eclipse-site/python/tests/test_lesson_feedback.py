"""Lesson outcome feedback: matched cohorts, measured lift, retirement."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.eclipse_memory import EclipseMemoryStore
from harness.evaluation.store import EvaluationStore
from harness.graph_context import _lesson_manifest_context
from harness.persistence import AgentMemoryStore
from harness.self_improvement.lesson_feedback import (
    LessonOutcomeStore,
    rank_lessons,
    retire_unhelpful,
    task_signature,
)
from harness.self_improvement.lessons import distill_lesson


@pytest.fixture()
def stores(tmp_path):
    lessons = EclipseMemoryStore(str(tmp_path / "eclipse-memory.db"))
    runs = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    yield lessons, runs, EvaluationStore(runs)
    lessons.close()
    runs.close()


def _adopted_lesson(lessons, eval_store, run_id="evalrun-lesson"):
    eval_store.create_run(
        id=run_id, suite="rsl-code", datasetName="owning-tests",
        datasetVersion="1", datasetChecksum="checksum", tier=0,
        invoker="worktree-tests", agentVersion="agent", gitCommit="commit",
        config={"kind": "rsl"}, metadata={"kind": "rsl"}, status="completed",
    )
    candidate = {
        "id": "evo_lesson",
        "cue": "market data timeout",
        "proposedLesson": "Retry once before falling back to the next source.",
        "evidenceReferences": [{"kind": "event", "id": "evt_1"}],
        "scope": {"capability": "live_quote"},
    }
    result = distill_lesson(
        lessons, candidate, "tests_passed", validation_run_id=run_id,
        adopted_artifact_type="evolution_candidate",
        adopted_artifact_id=candidate["id"],
    )
    return result["lessonId"], run_id


def _lessons(lesson_id, count=1):
    return [
        {
            "id": lesson_id if index == 0 else f"{lesson_id}_{index}",
            "cue": "market data timeout",
            "proposedLesson": "Retry once.",
        }
        for index in range(count)
    ]


def test_injections_record_injected_and_control_cohorts(stores):
    lessons, runs, eval_store = stores
    lesson_id, _ = _adopted_lesson(lessons, eval_store)
    store = LessonOutcomeStore(runs)
    rows = _lessons(lesson_id, 3)

    written = store.record_injections(
        "run-1", rows, [lesson_id], cue="market data timeout",
        scope={"capability": "live_quote"},
    )
    again = store.record_injections(
        "run-1", rows, [lesson_id], cue="market data timeout",
        scope={"capability": "live_quote"},
    )

    assert written == 3
    assert again == 3
    recorded = store.rows("run-1")
    assert len(recorded) == 3
    assert [row["injected"] for row in recorded] == [1, 0, 0]
    assert {row["taskSignature"] for row in recorded} == {
        task_signature("market data timeout", {"capability": "live_quote"})
    }


def test_run_outcome_updates_only_unmeasured_rows(stores):
    lessons, runs, eval_store = stores
    store = LessonOutcomeStore(runs)
    lesson_id, _ = _adopted_lesson(lessons, eval_store)
    store.record_injections("run-1", _lessons(lesson_id), [lesson_id])

    assert store.record_run_outcome("run-1", "completed") == 1
    assert store.record_run_outcome("run-1", "failed") == 0
    assert store.rows("run-1")[0]["outcome"] == "success"


def test_thin_data_is_insufficient_and_never_fabricates_lift(stores):
    lessons, runs, eval_store = stores
    store = LessonOutcomeStore(runs)
    lesson_id, _ = _adopted_lesson(lessons, eval_store)

    for index in range(2):
        store.record_injections(
            f"run-{index}", _lessons(lesson_id), [lesson_id],
        )
        store.record_run_outcome(f"run-{index}", "completed")

    stats = store.stats(lesson_id)
    assert stats.status == "insufficient"
    assert stats.lift is None
    assert stats.injected == 2


def test_measured_lift_uses_the_control_cohort(stores):
    lessons, runs, eval_store = stores
    store = LessonOutcomeStore(runs)
    lesson_id, _ = _adopted_lesson(lessons, eval_store)

    for index in range(3):
        store.record_injections(
            f"injected-{index}", _lessons(lesson_id), [lesson_id],
        )
        store.record_run_outcome(f"injected-{index}", "completed")
    for index in range(3):
        store.record_injections(
            f"control-{index}", _lessons(lesson_id, 2), [],
        )
        store.record_run_outcome(f"control-{index}", "failed")

    stats = store.stats(lesson_id)
    assert stats.status == "measured"
    assert stats.injectedRate == 1.0
    assert stats.controlRate == 0.0
    assert stats.lift == 1.0


def test_rank_lessons_promotes_measured_positive_lift_only(stores):
    lessons, runs, eval_store = stores
    store = LessonOutcomeStore(runs)
    first, _ = _adopted_lesson(lessons, eval_store)
    second = "lesson-2"

    for index in range(3):
        store.record_injections(f"i-{index}", _lessons(first), [first])
        store.record_run_outcome(f"i-{index}", "completed")
    for index in range(3):
        store.record_injections(f"c-{index}", _lessons(first, 2), [])
        store.record_run_outcome(f"c-{index}", "failed")

    ranked = rank_lessons(
        [{"id": second}, {"id": first}],
        store.stats_for([first, second]),
    )
    assert [row["id"] for row in ranked] == [first, second]


def test_rank_lessons_does_not_promote_negative_lift():
    from harness.self_improvement.lesson_feedback import LessonStats

    negative = LessonStats(
        lessonId="negative", injected=5, injectedSuccesses=1,
        injectedRate=0.2, injectedCiLow=0.0, injectedCiHigh=0.6,
        control=5, controlSuccesses=4, controlRate=0.8,
        controlCiLow=0.4, controlCiHigh=1.0,
        lift=-0.6, status="measured", reason="measured",
    )
    ranked = rank_lessons(
        [{"id": "unmeasured"}, {"id": "negative"}],
        {"negative": negative},
    )
    assert [row["id"] for row in ranked] == ["unmeasured", "negative"]


def test_retire_unhelpful_marks_only_measured_non_positive_lessons(stores):
    lessons, runs, eval_store = stores
    store = LessonOutcomeStore(runs)
    lesson_id, _ = _adopted_lesson(lessons, eval_store)

    for index in range(5):
        store.record_injections(f"i-{index}", _lessons(lesson_id), [lesson_id])
        store.record_run_outcome(f"i-{index}", "failed")
    for index in range(5):
        store.record_injections(f"c-{index}", _lessons(lesson_id, 2), [])
        store.record_run_outcome(f"c-{index}", "completed")

    retired = retire_unhelpful(lessons, store, [lesson_id])
    assert [row["lessonId"] for row in retired] == [lesson_id]
    assert lessons.get_candidate(lesson_id)["status"] == "retired"


def test_post_run_review_writes_the_terminal_outcome(stores):
    from harness.learning_review import review_run

    lessons, runs, eval_store = stores
    lesson_id, _ = _adopted_lesson(lessons, eval_store)
    runs.create_run("run-review", "eclipse-agent", {"query": "market data timeout"})
    runs.update_run("run-review", status="completed")
    store = LessonOutcomeStore(runs)
    store.record_injections("run-review", _lessons(lesson_id), [lesson_id])

    class Service:
        def __init__(self):
            self.store = lessons
            self.skill_registry = None

        def analyze_run(self, *args, **kwargs):
            return {}

    review_run(Service(), runs, "run-review")

    assert store.rows("run-review")[0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_prompt_helper_records_the_injected_cohort(stores):
    lessons, runs, eval_store = stores
    lesson_id, _ = _adopted_lesson(lessons, eval_store)

    class Memory:
        def __init__(self, store):
            self.store = store
            self.policy = SimpleNamespace(get_all=lambda: {})

    request = SimpleNamespace(
        runId="run-live",
        input=SimpleNamespace(
            query="market data request timed out for AAPL",
            ticker="AAPL",
            market=None,
            context={"scope": {"capability": "live_quote"}},
        ),
    )
    content, ids = await _lesson_manifest_context(
        request, Memory(lessons), runs,
    )

    assert ids == (lesson_id,)
    assert lesson_id in content
    rows = LessonOutcomeStore(runs).rows("run-live")
    assert rows and rows[0]["injected"] == 1
    assert rows[0]["lessonId"] == lesson_id

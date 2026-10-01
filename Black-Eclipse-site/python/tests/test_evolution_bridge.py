"""Phase 10 G4 — the recurrence bridge: criteria-driven and read-only.

Two observations do NOT produce a candidate; a single occurrence is never
evidence; a category absent from CATEGORY_TARGETS never produces one; a duplicate
signature does not produce a second; and the bridge performs no write to the
mistake tables.
"""

from __future__ import annotations

import pytest

from harness.code import evolution
from harness.persistence import AgentMemoryStore


@pytest.fixture
def store(tmp_path):
    return AgentMemoryStore(str(tmp_path / "agent-memory.db"))


def _bump(store, category: str, times: int) -> None:
    for _ in range(times):
        store.record_learning_recurrence(evolution._category_signature(category))


def test_below_threshold_produces_no_candidate(store):
    _bump(store, "timeout", evolution.RECURRENCE_THRESHOLD - 1)
    assert evolution.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z") == []


def test_at_threshold_produces_an_inert_candidate(store):
    _bump(store, "timeout", evolution.RECURRENCE_THRESHOLD)
    candidates = evolution.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z")
    assert len(candidates) == 1
    assert candidates[0]["sourceCategory"] == "timeout"
    assert candidates[0]["status"] == "inert"
    assert candidates[0]["observedCount"] >= evolution.RECURRENCE_THRESHOLD


def test_a_category_not_in_the_table_never_produces_one(store):
    # `missing_source` is a real mistake category but is NOT eligible for a code
    # change (the absence is the policy, as data).
    assert "missing_source" not in evolution.CATEGORY_TARGETS
    _bump(store, "missing_source", 10)
    assert evolution.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z") == []


def test_duplicate_signature_does_not_produce_a_second(store):
    _bump(store, "timeout", evolution.RECURRENCE_THRESHOLD)
    first = evolution.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z")
    second = evolution.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z")
    assert len(first) == 1 and second == []


def test_bridge_is_read_only_against_the_recurrence_ledger(store):
    # The bridge must not write the recurrence ledger. Count rows before/after.
    db = store._db  # noqa: SLF001
    _bump(store, "timeout", evolution.RECURRENCE_THRESHOLD)
    before = {
        t: db.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
        for t in ("LearningRecurrence", "LearningRecurrenceRun")
    }
    evolution.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z")
    after = {
        t: db.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
        for t in ("LearningRecurrence", "LearningRecurrenceRun")
    }
    assert before == after


def test_the_bridge_reads_the_one_shared_counter(store):
    # Recording on the store's ledger is exactly what the bridge reads.
    _bump(store, "repeated_failure", evolution.RECURRENCE_THRESHOLD)
    candidates = evolution.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z")
    assert any(c["sourceCategory"] == "repeated_failure" for c in candidates)


def test_the_problem_statement_is_plain_and_non_secret(store):
    _bump(store, "timeout", evolution.RECURRENCE_THRESHOLD)
    candidate = evolution.candidates_from_mistakes(store=store, since_iso="2000-01-01T00:00:00.000Z")[0]
    statement = candidate["problemStatement"]
    assert "timeout" in statement
    # No path, no digest, no mechanism vocabulary in the user-facing statement.
    assert "/" not in statement and "\\" not in statement


# -- honest metrics (never 0 when unmeasurable; no blended score) -------------


def test_metrics_with_no_attempts_render_unknown_not_zero(store):
    metrics = evolution.archive_metrics(store, window_days=90)
    assert metrics["attempts"] == 0
    assert metrics["successRate"] == "UNKNOWN"
    assert metrics["regressionRate"] == "UNKNOWN"
    assert metrics["costPerSuccess"] == "UNKNOWN"
    assert "successRate" in metrics["unmeasured"]


def test_metrics_per_category_and_unmeasured_cost(store):
    from harness.code.evolution_store import EvolutionStore

    es = EvolutionStore(store)
    candidate = es.save_candidate({
        "signature": "m1", "sourceCategory": "timeout", "observedCount": 3,
        "problemStatement": "x", "status": "evaluated_ok",
    })
    es.save_attempt({"candidateId": candidate["id"], "targetPath": "t", "baseDigest": "b",
                     "diffDigest": "d1", "outcome": "success", "costMicros": None, "tokensUsed": None})
    es.save_attempt({"candidateId": candidate["id"], "targetPath": "t", "baseDigest": "b",
                     "diffDigest": "d2", "outcome": "failure", "costMicros": None, "tokensUsed": None})
    metrics = evolution.archive_metrics(store, window_days=90)
    assert metrics["attempts"] == 2
    assert metrics["successRate"] == 0.5
    # Cost could not be measured for either attempt ? UNKNOWN, not 0.
    assert metrics["costPerSuccess"] == "UNKNOWN"
    # Per-category results are present (never collapsed to one number).
    assert "timeout" in metrics["perCategory"]
    assert metrics["perCategory"]["timeout"]["attempts"] == 2


def test_report_has_no_blended_value(store):
    # The report exposes per-category results and named holes — never one blended
    # number standing in for everything.
    metrics = evolution.archive_metrics(store, window_days=90)
    assert "perCategory" in metrics
    assert "unmeasured" in metrics
    # Every scalar is either a measured number or the literal UNKNOWN.
    for key in ("successRate", "regressionRate", "costPerSuccess"):
        assert metrics[key] == "UNKNOWN" or isinstance(metrics[key], (int, float))

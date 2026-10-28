"""Loop-closure contracts: typed lessons, falsifiable candidates, scored advice.

These tests pin the behaviours the audit found missing: a review must justify a
null, a candidate must carry a replayable method, an evaluation must discriminate
against a base, advice must have a horizon, route failures must be diagnosed, and
active memory must not hold two truths.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

from harness.advisory.service import AdvisoryService, due_at
from harness.eclipse_memory.consolidation import consolidate_active
from harness.eclipse_memory.store import EclipseMemoryStore
from harness.evaluation.store import EvaluationStore
from harness.persistence import AgentMemoryStore
from harness.retrieval.health import diagnose_routes
from harness.self_improvement.lesson_contract import (
    Lesson,
    NoLearningVerdict,
    aggregate_signals,
    candidate_problems,
    derive_confidence,
)
from harness.self_improvement.loop_health import (
    audit_reviews,
    gate_report,
    nonconforming_candidates,
    quarantine_nonconforming_candidates,
)
from harness.skills.evaluation import (
    _discrimination_dimension,
    _evidence_shape,
    _metric_deltas,
    _regression_dimension,
)


# ── typed lessons / justified null ──────────────────────────────────────────


def test_quality_recovery_output_passes_evidence_shape():
    manifest = SimpleNamespace(
        category="quality",
        outputSchema={"properties": {
            "summary": {"type": "string"},
            "limitations": {"type": "array"},
            "missingData": {"type": "array"},
        }},
    )
    ok, reason = _evidence_shape(manifest)
    assert ok is True
    assert "limitations" in reason and "missing data" in reason


def test_generic_action_is_not_a_lesson():
    lesson = Lesson(
        condition="a tool fails",
        action="prefer the alternative that worked",
        evidence=("run_1",),
    )
    assert "generic_action" in lesson.problems()


def test_lesson_confidence_is_derived_from_evidence_not_constant():
    weak = Lesson(condition="x" * 5, action="call route_b after route_a", evidence=("a",))
    strong = Lesson(
        condition="x" * 5, action="call route_b after route_a",
        evidence=("a", "b"), occurrenceCount=3, replayTest="replay",
    )
    assert weak.confidence != strong.confidence
    assert weak.confidence == derive_confidence(
        evidence_count=1, occurrence_count=1, has_replay=False
    )


def test_no_learning_requires_a_reason_and_evidence_checked():
    assert "missing_reason" in NoLearningVerdict(reason="").problems()
    assert "missing_evidence_checked" in NoLearningVerdict(reason="nothing").problems()
    verdict = NoLearningVerdict(
        reason="no failed->recovered pair", evidenceChecked=("tool.executions",)
    )
    assert verdict.problems() == []
    assert verdict.to_dict()["justified"] is True


def test_templated_candidate_is_rejected_at_creation():
    candidate = {
        "candidateType": "failure_recovery",
        "title": "Recovery after research_search failure",
        "problem": "Tool research_search failed.",
        "proposedLesson": "When these tools fail, prefer the alternative that worked.",
        "confidence": 0.55,
    }
    problems = candidate_problems(candidate)
    assert "templated_title" in problems
    assert "constant_confidence" in problems
    assert "missing_recoveredCall" in problems


def test_falsifiable_candidate_passes_the_contract():
    candidate = {
        "candidateType": "failure_recovery",
        "title": "Recover from TOOL_ERROR by calling research_search",
        "problem": "fundamentals failed; research_search recovered.",
        "condition": "fundamentals_get_financials returns TOOL_ERROR",
        "action": "call research_search after fundamentals fails with TOOL_ERROR",
        "failedCall": "fundamentals_get_financials(ticker='ACME')",
        "recoveredCall": "research_search(query='ACME')",
        "precondition": "TOOL_ERROR",
        "proposedProcedure": [
            {"step": 1, "action": "classify", "detail": "recognize TOOL_ERROR"},
            {"step": 2, "action": "recover", "detail": "call research_search"},
        ],
        "replayTest": "replay run_1 with fundamentals forced to TOOL_ERROR",
        "evidenceReferences": [{"kind": "tool", "name": "research_search"}],
        "occurrenceCount": 2,
        "confidence": derive_confidence(
            evidence_count=1, occurrence_count=2, has_replay=True
        ),
    }
    assert candidate_problems(candidate) == []


def test_a_signal_needs_two_distinct_runs_before_it_is_eligible():
    def review(run_id, condition, action):
        return {
            "runId": run_id,
            "result": {"outcomes": [{"category": "typed_lesson", "payload": {"lesson": {
                "condition": condition, "action": action, "confidence": 0.6,
            }}}]},
        }

    reviews = [
        review("run_1", "route_a returns 500", "call route_b"),
        review("run_1", "route_a returns 500", "call route_b"),
    ]
    once = aggregate_signals(reviews)
    assert once[0]["eligible"] is False
    reviews.append(review("run_2", "route_a returns 500", "call route_b"))
    twice = aggregate_signals(reviews)
    assert twice[0]["eligible"] is True
    assert twice[0]["distinctRuns"] == 2


# ── evaluation discrimination ───────────────────────────────────────────────


class _StubStore:
    def __init__(self, base=None, evaluations=None):
        self._base = base
        self._evaluations = evaluations or []

    def get_version(self, _skill_id, _version):
        return {"baseVersion": self._base}

    def list_evaluations(self, _skill_id, limit=50):
        return self._evaluations


def test_metric_deltas_identify_an_indistinguishable_candidate():
    deltas, regressions, distinguishable = _metric_deltas(
        {"taskSuccess": 0.8}, {"taskSuccess": 0.8}
    )
    assert deltas and not regressions and not distinguishable


def test_evaluation_fails_when_it_cannot_distinguish_from_base():
    dimension = _discrimination_dimension(
        _StubStore(base="1.0.0"), "s", "1.1.0",
        base_version="1.0.0",
        metrics={"taskSuccess": 0.8, "costUsd": 0.01},
        base_metrics={"taskSuccess": 0.8, "costUsd": 0.01},
        prior_evaluations=[],
    )
    assert dimension["status"] == "failed"
    assert dimension["mandatory"] is True


def test_evaluation_passes_a_measured_lift():
    dimension = _discrimination_dimension(
        _StubStore(base="1.0.0"), "s", "1.1.0",
        base_version="1.0.0",
        metrics={"taskSuccess": 0.9}, base_metrics={"taskSuccess": 0.8},
        prior_evaluations=[],
    )
    assert dimension["status"] == "passed"


def test_regression_never_compares_against_a_later_version():
    store = _StubStore(evaluations=[
        {"version": "1.1.1", "dimensions": [
            {"name": "tool_availability", "status": "passed"},
        ]},
    ])
    dimension = _regression_dimension(
        store, "s", "1.1.0", [{"name": "tool_availability", "status": "passed"}],
    )
    assert dimension["status"] == "needs_review"
    assert "no prior evaluation" in dimension["detail"]


def test_repeated_identical_passes_are_a_broken_signal():
    prior = [{"version": "1.0.0", "status": "passed"} for _ in range(3)]
    dimension = _discrimination_dimension(
        _StubStore(), "s", "1.0.0", base_version=None, metrics=None,
        base_metrics=None, prior_evaluations=prior,
    )
    assert dimension["status"] == "needs_review"
    assert "not producing a signal" in dimension["detail"]


# ── advisory scoring ────────────────────────────────────────────────────────


def _advisory(tmp_path) -> AdvisoryService:
    return AdvisoryService(AgentMemoryStore(os.path.join(str(tmp_path), "adv.db")))


def _claim(status="computed", action="rebalance", method="rebalance-model"):
    return {
        "status": status,
        "claims": [{
            "action": action, "symbols": ["AAPL"], "target": None,
            "values": [], "status": status, "reason": "basis",
            "method": method,
        }],
        "unverified": [],
    }


def test_horizon_sets_a_scoring_deadline(tmp_path):
    svc = _advisory(tmp_path)
    decision = svc.record_verdict(run_id="r1", verdict=_claim(), horizon="1d")[0]
    assert decision["horizon"] == "1d"
    assert decision["dueAt"] is not None
    assert due_at("2026-01-01T00:00:00+00:00", "1m") == "2026-01-31T00:00:00+00:00"


def test_scorecard_reports_unscored_and_overdue_as_defects(tmp_path):
    svc = _advisory(tmp_path)
    svc.record_verdict(run_id="r1", verdict=_claim())
    svc.record_verdict(
        run_id="r2", verdict=_claim(action="sell"), horizon="1d",
        entry_prices={"AAPL": 100.0},
    )
    # A row with no stated horizon is only possible as legacy data.
    svc.store._db.execute(
        "UPDATE AdvisoryDecision SET horizon=NULL, dueAt=NULL WHERE runId='r1'"
    )
    svc.store._db.commit()
    card = svc.scorecard(now="2099-01-01T00:00:00+00:00")
    assert card["unscored"] == 1
    assert card["overdueCount"] == 1
    assert any(b["method"] == "rebalance-model" for b in card["byMethod"])


def test_method_hit_rate_and_demotion(tmp_path):
    svc = _advisory(tmp_path)
    ids = [
        svc.record_verdict(
            run_id=f"r{i}", verdict=_claim(action=f"a{i}"), horizon="1d",
        )[0]["id"]
        for i in range(5)
    ]
    for did in ids:
        svc.record_outcome(did, realized_return=-0.1, benchmark_return=0.0)
    card = svc.scorecard()
    bucket = next(b for b in card["byMethod"] if b["method"] == "rebalance-model")
    assert bucket["hitRate"] == 0.0
    assert bucket["demoted"] is True
    assert "rebalance-model" in card["demotedMethods"]


# ── route diagnosis ─────────────────────────────────────────────────────────


def test_quote_tool_captures_an_entry_price():
    from harness.advisory.collector import AdvisoryCollector

    collector = AdvisoryCollector()
    collector.add("market_get_quote", {"symbol": "AAPL"}, {"symbol": "AAPL", "price": 101.5})
    assert collector.prices() == {"AAPL": 101.5}


def test_generic_only_failure_is_a_provider_failure():
    rows = [
        {"source": "LIVE_STRUCTURED", "capability": "price_history",
         "market": "*", "success": 0, "fail": 111},
    ]
    report = diagnose_routes(rows)
    assert report["routingDefectCount"] == 0
    assert report["providerFailureCount"] == 1


def test_generic_failure_with_healthy_markets_is_a_routing_defect():
    rows = [
        {"source": "JDDS", "capability": "fundamentals", "market": "*", "success": 0, "fail": 26},
        {"source": "JDDS", "capability": "fundamentals", "market": "US", "success": 19, "fail": 0},
        {"source": "JDDS", "capability": "fundamentals", "market": "PK", "success": 19, "fail": 0},
        {"source": "JDDS", "capability": "fundamentals", "market": "IN", "success": 37, "fail": 0},
    ]
    report = diagnose_routes(rows)
    assert report["routingDefectCount"] == 1
    defect = report["defects"][0]
    assert defect["source"] == "JDDS"
    assert set(defect["healthyMarkets"]) == {"US", "PK", "IN"}
    assert "stop recording it as a provider failure" in defect["recommendedAction"]


def test_all_markets_failing_is_a_provider_failure():
    rows = [
        {"source": "JDDS", "capability": "live_quote", "market": "US", "success": 0, "fail": 441},
        {"source": "JDDS", "capability": "live_quote", "market": "PK", "success": 0, "fail": 10},
    ]
    report = diagnose_routes(rows)
    assert report["routingDefectCount"] == 0
    assert report["providerFailureCount"] == 1


# ── memory consolidation ────────────────────────────────────────────────────


def test_consolidation_supersedes_a_contradiction_to_the_later_statement(tmp_path):
    store = EclipseMemoryStore(os.path.join(str(tmp_path), "mem.db"))
    first = store.save_memory(
        memory_type="preference", scope="global", subject="answer-style",
        content="Keep answers concise.", created_by="u1",
    )
    second = store.save_memory(
        memory_type="preference", scope="global", subject="answer-style",
        content="Give detailed answers with sources.", created_by="u1",
    )
    report = consolidate_active(store)
    assert report["conflictCount"] == 1
    assert store.get_memory(first["id"])["status"] == "superseded"
    assert store.get_memory(first["id"])["supersededBy"] == second["id"]
    assert store.get_memory(second["id"])["status"] == "active"


def test_consolidation_removes_a_near_duplicate_without_a_subject(tmp_path):
    store = EclipseMemoryStore(os.path.join(str(tmp_path), "mem3.db"))
    first = store.save_memory(
        memory_type="semantic", scope="user", subject="bubu",
        content='User Rafay\'s "bubu" is Maimoona.', created_by="u1",
    )
    store._db.execute(
        "UPDATE MemoryRecord SET createdAt='2026-01-01T00:00:00.000Z', "
        "updatedAt='2026-01-01T00:00:00.000Z' WHERE id=?",
        (first["id"],),
    )
    store._db.commit()
    second = store.save_memory(
        memory_type="semantic", scope="user", subject=None,
        content="my bubu is maimoona", created_by="u1",
    )
    report = consolidate_active(store)
    assert report["duplicateCount"] == 1
    assert store.get_memory(first["id"])["status"] == "superseded"
    assert store.get_memory(second["id"])["status"] == "active"


def test_consolidation_resolves_a_verbosity_conflict_to_the_later_statement(tmp_path):
    store = EclipseMemoryStore(os.path.join(str(tmp_path), "mem4.db"))
    first = store.save_memory(
        memory_type="preference", scope="user",
        content="i like straight answer no opinion straight to the facts", created_by="u1",
    )
    store._db.execute(
        "UPDATE MemoryRecord SET createdAt='2026-01-01T00:00:00.000Z', "
        "updatedAt='2026-01-01T00:00:00.000Z' WHERE id=?",
        (first["id"],),
    )
    store._db.commit()
    second = store.save_memory(
        memory_type="preference", scope="user",
        content="Actually, remember I prefer detailed answers with sources.", created_by="u1",
    )
    report = consolidate_active(store)
    assert report["conflictCount"] == 1
    assert store.get_memory(first["id"])["status"] == "superseded"
    assert store.get_memory(second["id"])["status"] == "active"


def test_consolidation_reports_residue_without_touching_it(tmp_path):
    store = EclipseMemoryStore(os.path.join(str(tmp_path), "mem5.db"))
    fragment = store.save_memory(
        memory_type="semantic", scope="general", content="loopback can save",
        created_by="u1",
    )
    report = consolidate_active(store)
    assert report["residueCount"] == 1
    assert report["residue"][0]["id"] == fragment["id"]
    assert store.get_memory(fragment["id"])["status"] == "active"


def test_consolidation_removes_an_exact_duplicate(tmp_path):
    store = EclipseMemoryStore(os.path.join(str(tmp_path), "mem2.db"))
    first = store.save_memory(
        memory_type="semantic", scope="global", subject="identity",
        content="bubu is Maimoona", created_by="u1",
    )
    second = store.save_memory(
        memory_type="semantic", scope="global", subject="identity",
        content="bubu is Maimoona", created_by="u1",
    )
    report = consolidate_active(store)
    assert report["duplicateCount"] == 1
    assert store.get_memory(first["id"])["status"] == "superseded"
    assert store.get_memory(second["id"])["status"] == "active"


# ── gate reachability ───────────────────────────────────────────────────────


class _FakeRuns:
    def __init__(self, reviews):
        self._reviews = reviews

    def list_learning_reviews(self, *, status=None, limit=50):
        return self._reviews[:limit]


class _FakeCandidates:
    def __init__(self, rows):
        self._rows = rows

    def list_candidates(self, *, status=None, limit=100):
        return self._rows[:limit]


def test_bounded_review_preserves_a_null_justification():
    from harness.learning_review import _bounded

    result = _bounded({
        "runId": "r",
        "outcomes": [{
            "category": "no_learning", "created": False, "justified": True,
            "reason": "no pair", "evidenceChecked": ["tool.executions"],
        }],
    })
    outcome = result["outcomes"][0]
    assert outcome["justified"] is True
    assert outcome["evidenceChecked"] == ["tool.executions"]


def test_completed_review_for_one_run_updates_instead_of_duplicating(tmp_path):
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(os.path.join(str(tmp_path), "reviews.db"))
    first = store.save_learning_review({
        "runId": "run_1", "status": "completed", "result": {"v": 1},
    })
    second = store.save_learning_review({
        "runId": "run_1", "status": "completed", "result": {"v": 2},
    })
    assert first["id"] == second["id"]
    assert len(store.list_learning_reviews(limit=10)) == 1
    assert store.get_learning_review(first["id"])["result"] == {"v": 2}


def test_audit_counts_bare_nulls_as_defects():
    audit = audit_reviews([
        {"result": {"outcomes": [
            {"category": "typed_lesson"},
            {"category": "no_learning", "reason": "no pair",
             "evidenceChecked": ["tool.executions"], "justified": True},
            {"category": "no_learning"},
        ]}},
    ])
    assert audit["typedLessons"] == 1
    assert audit["justifiedNulls"] == 1
    assert audit["unjustifiedNulls"] == 1


class _MutableCandidates:
    def __init__(self, rows):
        self._rows = rows

    def list_candidates(self, *, status=None, limit=100):
        return [r for r in self._rows if status is None or r["status"] == status]

    def get_candidate(self, candidate_id):
        return next((r for r in self._rows if r["id"] == candidate_id), None)

    def update_candidate(self, candidate_id, **patch):
        for row in self._rows:
            if row["id"] == candidate_id:
                row.update(patch)


def test_an_unavailable_recovery_tool_is_not_a_recovery():
    from harness.skills.learning import _first_recovery_pair

    tools = [
        {"name": "terminal_run", "ok": False, "text": "Tool error (TOOL_FORBIDDEN)"},
        {"name": "app_api_get", "ok": True,
         "text": "APP API UNAVAILABLE: TimeoutError"},
        {"name": "learning_review_list", "ok": True, "text": "ok"},
    ]
    assert _first_recovery_pair(tools) is None


def test_a_same_capability_retry_is_a_recovery():
    from harness.skills.learning import _first_recovery_pair

    tools = [
        {"name": "research_search", "ok": False, "text": "rate limited"},
        {"name": "research_search", "ok": True, "text": "Retrieval status: OK"},
    ]
    pair = _first_recovery_pair(tools)
    assert pair is not None
    assert pair[1]["name"] == "research_search"


def test_candidate_store_persists_the_falsifiable_method(tmp_path):
    store = EclipseMemoryStore(os.path.join(str(tmp_path), "cand.db"))
    candidate_id = store.save_candidate({
        "candidateType": "failure_recovery",
        "title": "Recover from TOOL_FORBIDDEN by calling app_api_get",
        "problem": "browser_evaluate failed; app_api_get recovered.",
        "condition": "browser_evaluate returns TOOL_FORBIDDEN",
        "action": "call app_api_get after browser_evaluate fails with TOOL_FORBIDDEN",
        "failedCall": "browser_evaluate",
        "recoveredCall": "app_api_get",
        "precondition": "TOOL_FORBIDDEN",
        "proposedProcedure": [{"step": 1, "action": "recover", "detail": "call app_api_get"}],
        "replayTest": "replay with browser_evaluate forced to TOOL_FORBIDDEN",
        "evidenceReferences": [{"kind": "tool", "name": "app_api_get"}],
        "occurrenceCount": 2,
        "confidence": 0.5,
        "signature": "sig",
        "status": "detected",
    })
    row = store.get_candidate(candidate_id)
    assert row["failedCall"] == "browser_evaluate"
    assert row["recoveredCall"] == "app_api_get"
    assert row["precondition"] == "TOOL_FORBIDDEN"
    assert row["replayTest"].startswith("replay")
    assert row["occurrenceCount"] == 2
    assert candidate_problems(row) == []


def test_nonconforming_candidates_are_quarantined_not_deleted():
    store = _MutableCandidates([
        {"id": "old", "status": "detected", "candidateType": "failure_recovery",
         "title": "Recovery after x failure", "confidence": 0.55},
    ])
    assert len(nonconforming_candidates(store)) == 1
    result = quarantine_nonconforming_candidates(store)
    assert result["quarantinedCount"] == 1
    assert store._rows[0]["status"] == "rejected"
    assert store._rows[0]["knownLimitations"].startswith("Quarantined (nonconforming):")


def test_advisory_backfill_exposes_method_and_unscored_horizon(tmp_path):
    svc = _advisory(tmp_path)
    svc.record_verdict(run_id="r1", verdict=_claim())
    svc.store._db.execute(
        "UPDATE AdvisoryDecision SET method=NULL, horizon=NULL, dueAt=NULL"
    )
    svc.store._db.commit()
    result = svc.backfill_scoring_fields()
    assert result["backfilledCount"] == 1
    decision = svc.list_decisions()[0]
    assert decision["method"] == "portfolio_computation"
    assert decision["horizon"] == "30d"
    assert decision["dueAt"] is not None


def test_gate_counts_only_the_current_contract_window():
    reviews = _FakeRuns([
        {"runId": "old", "createdAt": "2020-01-01T00:00:00+00:00",
         "result": {"outcomes": [{"category": "no_learning"}]}},
        {"runId": "new", "createdAt": "2026-10-28T00:30:00+00:00",
         "result": {"outcomes": [{"category": "typed_lesson"}]}},
    ])
    report = gate_report(
        reviews, skill_store=_FakeCandidates([]), window_days=30,
        now="2026-10-28T01:00:00+00:00",
    )
    codes = {gap["code"] for gap in report["gaps"]}
    assert "reviews_emit_unjustified_nulls" not in codes
    assert report["legacyReviews"]["unjustifiedNulls"] == 1
    assert report["reviews"]["withTypedLesson"] == 1


def test_gate_report_calls_an_unconsumed_queue_a_design_failure():
    candidates = _FakeCandidates([
        {"id": "c1", "status": "detected", "createdAt": "2026-01-01T00:00:00+00:00"},
        {"id": "c2", "status": "detected", "createdAt": "2026-02-01T00:00:00+00:00"},
    ])
    reviews = _FakeRuns([
        {"runId": "r1", "createdAt": "2026-10-28T00:30:00+00:00",
         "result": {"outcomes": [{"category": "no_learning"}]}},
    ])
    report = gate_report(
        reviews, skill_store=candidates, window_days=30,
        now="2026-10-28T01:00:00+00:00",
    )
    codes = {gap["code"] for gap in report["gaps"]}
    assert report["ok"] is False
    assert "candidate_queue_unconsumed" in codes
    assert "reviews_emit_no_lessons" in codes

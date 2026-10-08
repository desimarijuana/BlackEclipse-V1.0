"""Production-failure mining and the self-improvement verification loop."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore
from harness.evaluation.improvement import (
    ImprovementProposal,
    evaluate_candidate,
    propose_improvements,
    summarize_failures,
)
from harness.evaluation.mining import ingest_failures, mine_failure, promote_candidate
from harness.evaluation.store import EvaluationStore


@pytest.fixture()
def eval_store():
    directory = tempfile.mkdtemp(prefix="be-eval-mine-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield EvaluationStore(store)
    store.close()


def _failed_run(run_id="prod1"):
    run = {"id": run_id, "status": "failed", "query": "fetch the price",
           "error": {"code": "TOOL_ERROR"}}
    events = [
        {"type": "run.started", "at": "t0", "data": {}},
        {"type": "tool.requested", "at": "t1", "data": {"name": "get_market", "args": {"symbol": "AAA"}}},
        {"type": "tool.failed", "at": "t2", "data": {"name": "get_market", "code": "TOOL_ERROR"}},
        {"type": "run.failed", "at": "t3", "data": {"code": "TOOL_ERROR"}},
    ]
    return run, events


def test_mine_failure_creates_then_deduplicates(eval_store):
    run, events = _failed_run()
    first = mine_failure(eval_store, run=run, events=events)
    assert first["created"] is True
    assert "tool_execution" in first["labels"]
    assert first["task"]["id"].startswith("regression.")
    again = mine_failure(eval_store, run=run, events=events)
    assert again["created"] is False and again["deduplicated"] is True
    assert len(eval_store.list_candidates()) == 1


def test_ingest_batch_counts(eval_store):
    run_a, events_a = _failed_run("a")
    run_b, events_b = _failed_run("b")  # identical signature → dedup
    outcome = ingest_failures(eval_store, [
        {"run": run_a, "events": events_a},
        {"run": run_b, "events": events_b},
    ])
    assert outcome["createdCount"] == 1 and outcome["deduplicatedCount"] == 1


def test_promote_candidate_attaches_validated_behavior(eval_store):
    run, events = _failed_run()
    created = mine_failure(eval_store, run=run, events=events)
    promoted = promote_candidate(eval_store, created["candidateId"],
                                 expected_behavior={"expected_tools": ["get_market"],
                                                    "expected_output": {"contains": ["price"]}})
    assert promoted["status"] == "validated"
    assert promoted["task"]["expected_tools"] == ["get_market"]


def test_propose_improvements_names_components():
    proposals = propose_improvements({"tool_selection": 3, "calculation": 1})
    assert any(p["label"] == "tool_selection" for p in proposals)


class _StubSuite:
    def __init__(self, aggregates):
        self.aggregates = aggregates


class _StubRunner:
    def __init__(self, aggregates):
        self._aggregates = aggregates

    async def run_suite(self, tasks, **kwargs):
        return _StubSuite(self._aggregates)


def test_improvement_accepted_only_when_target_improves():
    calls = {"reverted": 0}
    proposal = ImprovementProposal(
        id="p1", description="raise success", target_dimension="task_success",
        apply=lambda: None, revert=lambda: calls.__setitem__("reverted", calls["reverted"] + 1),
    )
    baseline = {"aggregates": {"task_success": 0.5, "safety_score": 1.0}}
    decision = asyncio.run(evaluate_candidate(
        _StubRunner({"task_success": 0.9, "safety_score": 1.0}), [], proposal, baseline,
    ))
    assert decision.accepted is True and calls["reverted"] == 0


def test_improvement_rejected_when_target_flat_and_reverted():
    calls = {"reverted": 0}
    proposal = ImprovementProposal(
        id="p2", description="noop", target_dimension="task_success",
        apply=lambda: None, revert=lambda: calls.__setitem__("reverted", 1),
    )
    decision = asyncio.run(evaluate_candidate(
        _StubRunner({"task_success": 0.5, "safety_score": 1.0}), [], proposal,
        {"aggregates": {"task_success": 0.5, "safety_score": 1.0}},
    ))
    assert decision.accepted is False and calls["reverted"] == 1


def test_improvement_rejected_on_critical_regression():
    calls = {"reverted": 0}
    proposal = ImprovementProposal(
        id="p3", description="trade quality for safety", target_dimension="tool_accuracy",
        apply=lambda: None, revert=lambda: calls.__setitem__("reverted", 1),
    )
    baseline = {"aggregates": {"tool_accuracy": 0.8, "safety_score": 1.0, "task_success": 0.9}}
    decision = asyncio.run(evaluate_candidate(
        _StubRunner({"tool_accuracy": 0.95, "safety_score": 0.5, "task_success": 0.9}),
        [], proposal, baseline,
    ))
    assert decision.accepted is False and calls["reverted"] == 1
    assert any(r["dimension"] == "safety_score" for r in decision.regressions)

"""C4.1: durable Goal/Plan/Step view and the evidence ledger."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.goals import (
    EvidenceLedger,
    GoalStore,
    claim_sentences,
    handle,
    handles_from_tool_result,
    has_number,
)
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-goals-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    s.create_run("run_1", "eclipse-agent", {"query": "x"})
    s.create_run("run_2", "eclipse-agent", {"query": "x"})
    yield s
    s.close()


def test_a_goal_owns_an_ordered_plan_and_step_status(store):
    goals = GoalStore(store)
    goal = goals.create_goal(
        "Produce a risk brief", acceptance=["drawdown", "no fabrication"],
    )
    plan = goals.create_plan(goal.id, [
        {"title": "Pull prices", "objective": "Fetch 2y of bars"},
        {"title": "Compute risk", "objective": "Drawdown + vol", "acceptance": ["computed"]},
    ])

    loaded = goals.get_plan(plan.id)
    assert loaded is not None
    assert [step.title for step in loaded.steps] == ["Pull prices", "Compute risk"]
    assert loaded.steps[0].index == 0
    assert loaded.current_step.id == loaded.steps[0].id

    goals.set_step_status(loaded.steps[0].id, "verified", run_id="run_1")
    reloaded = goals.get_plan(plan.id)
    assert reloaded.steps[0].status == "verified"
    assert reloaded.steps[0].run_id == "run_1"
    assert reloaded.current_step.id == reloaded.steps[1].id

    goals.set_step_status(reloaded.steps[1].id, "verified")
    assert goals.get_plan(plan.id).complete is True
    assert goals.get_goal(goal.id).plan_id == plan.id


def test_a_plan_iteration_is_recorded_for_a_replan(store):
    goals = GoalStore(store)
    goal = goals.create_goal("Long task")
    plan = goals.create_plan(goal.id, [{"title": "One", "objective": "do"}])
    goals.record_iteration(plan.id, 2, trigger="verify_failed", reason="test failed")
    rows = goals._db.execute(
        "SELECT iteration, trigger FROM PlanIteration WHERE planId=?", (plan.id,),
    ).fetchall()
    assert [(row["iteration"], row["trigger"]) for row in rows] == [(2, "verify_failed")]


def test_claims_are_supported_only_by_a_valid_handle(store):
    ledger = EvidenceLedger(store)
    supported = ledger.record(
        run_id="run_1", text="AAPL closed at 190.12",
        handles=[handle("citation", "https://example.test/quote")],
    )
    assert supported.status == "supported"
    assert supported.handles[0].kind == "citation"

    unverified = ledger.record(run_id="run_1", text="I think it will rise")
    assert unverified.status == "unverified"

    rejected = ledger.record(
        run_id="run_1", text="A fabricated number", status="unsupported",
    )
    assert rejected.status == "unsupported"

    summary = ledger.summary("run_1")
    assert summary["claims"] == 3
    assert summary["byStatus"] == {"supported": 1, "unsupported": 1, "unverified": 1}


def test_claims_are_scoped_to_their_run(store):
    ledger = EvidenceLedger(store)
    ledger.record(run_id="run_1", text="only run one", handles=[handle("run", "run_1")])
    assert len(ledger.claims("run_1")) == 1
    assert ledger.claims("run_2") == []


def test_an_invalid_handle_does_not_make_a_claim_supported(store):
    ledger = EvidenceLedger(store)
    claim = ledger.record(
        run_id="run_1", text="x",
        handles=[{"kind": "not-a-kind", "ref": "y"}],
    )
    assert claim.status == "unverified"
    assert claim.handles == []


def test_tool_result_handles_are_deduplicated_and_bounded():
    class Result:
        name = "get_quote"
        output_id = "tout_1"
        data = {"path": "a.csv", "sha256": "abc", "url": "https://example.test/x"}

    handles = handles_from_tool_result(Result(), "run_1")
    kinds = [item["kind"] for item in handles]
    assert kinds == ["run", "record", "tool_output", "file", "citation"]
    assert len(handles) == len({(item["kind"], item["ref"]) for item in handles})


def test_sentence_extraction_and_number_detection():
    text = "AAPL closed at 190.12. It may rise. Short."
    sentences = claim_sentences(text)
    assert sentences == ["AAPL closed at 190.12.", "It may rise."]
    assert has_number(sentences[0]) is True
    assert has_number(sentences[1]) is False

"""C4.7: the outcome envelope names the goal step and the evidence."""

from __future__ import annotations

import os
import tempfile

from harness.goals import EvidenceLedger, GoalStore, handle
from harness.persistence import AgentMemoryStore
from harness.run_outcome import build_outcome_envelope


def _store() -> AgentMemoryStore:
    directory = tempfile.mkdtemp(prefix="be-outcome-c4-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    store.create_run("run_1", "eclipse-agent", {"query": "x"})
    return store


def test_the_envelope_names_the_goal_step_and_evidence():
    store = _store()
    try:
        goals = GoalStore(store)
        goal = goals.create_goal("Risk brief", acceptance=["drawdown"])
        plan = goals.create_plan(goal.id, [{"title": "Compute", "objective": "risk"}])
        goals.set_step_status(plan.steps[0].id, "verified", run_id="run_1")
        ledger = EvidenceLedger(store)
        ledger.record(
            run_id="run_1", text="drawdown is 12.4%",
            handles=[handle("computation", "calc_1")],
        )

        envelope = build_outcome_envelope(run_id="run_1", store=store)
        assert envelope["goal"]["goalId"] == goal.id
        assert envelope["goal"]["planId"] == plan.id
        assert envelope["goal"]["stepId"] == plan.steps[0].id
        assert envelope["goal"]["stepStatus"] == "verified"
        assert envelope["evidence"]["claims"] == 1
        assert envelope["evidence"]["byStatus"]["supported"] == 1
        assert envelope["evidence"]["verdict"]["ok"] is True
    finally:
        store.close()


def test_an_ordinary_run_has_no_goal_block_but_an_empty_evidence_summary():
    store = _store()
    try:
        envelope = build_outcome_envelope(run_id="run_1", store=store)
        assert envelope["goal"] is None
        assert envelope["evidence"]["claims"] == 0
    finally:
        store.close()

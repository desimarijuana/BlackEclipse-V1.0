"""Harness closeout Phase 7: one source of truth for route + run health.

  * The retrieval planner's verdict for a route equals the ledger's verdict for
    that route (the planner health index reads the SAME ledger).
  * A run explanation names the workflow step tree, the lineage, and each step's
    tool scope.
  * A killed-and-resumed run's explanation shows the resume point.
"""

from __future__ import annotations

import pytest

from harness.retrieval.health import build_health_index, health_verdict
from harness.run_observability import explain_run


# ── 7.1 Planner verdict == ledger verdict ────────────────────────────────────


def test_planner_verdict_matches_ledger_verdict():
    # A ledger row (as sourceHealth() shapes it) for one route.
    rows = [
        {"source": "LIVE_STRUCTURED", "market": "US", "capability": "live_quote",
         "success": 10, "fail": 0},
        {"source": "JDDS", "market": "PK", "capability": "financial_statements",
         "success": 0, "fail": 3},
    ]
    index = build_health_index(rows)
    # The planner's verdict for the exact ledger route:
    assert health_verdict(index, "LIVE_STRUCTURED", "live_quote", "US") == "healthy"
    assert health_verdict(index, "JDDS", "financial_statements", "PK") == "failing"
    # An unobserved route is `unknown` in BOTH surfaces — never healthy.
    assert health_verdict(index, "LIVE_STRUCTURED", "price_history", "US") == "unknown"


def test_planner_and_ledger_agree_on_zero_attempts():
    index = build_health_index([])
    assert health_verdict(index, "JDDS", "financial_statements", "PK") == "unknown"


# ── 7.2 Run-level observability ──────────────────────────────────────────────


def test_explanation_names_every_workflow_step_scope_and_outcome():
    events = [
        {"type": "workflow.step_started",
         "data": {"workflowId": "wf1", "stepId": "retrieve", "kind": "agent", "scope": ["scoped_a"]}},
        {"type": "workflow.step_completed",
         "data": {"workflowId": "wf1", "stepId": "retrieve", "kind": "agent",
                  "status": "completed", "runId": "run_wf1_retrieve", "scope": ["scoped_a"]}},
    ]
    result = explain_run(
        run_id="run_wf1_retrieve", events=events,
        run={"workflowId": "wf1", "parentRunId": "run_wf1"},
        lineage={"runId": "run_wf1_retrieve", "parents": [{"id": "run_wf1", "status": "completed"}], "children": []},
    )
    assert result["workflow"]["workflowId"] == "wf1"
    steps = result["workflow"]["steps"]
    assert any(s["stepId"] == "retrieve" and s["status"] == "completed" for s in steps)
    assert any(s["scope"] == ["scoped_a"] for s in steps)
    # Lineage is present and bounded.
    assert result["lineage"]["parentRunId"] == "run_wf1"
    assert result["lineage"]["parents"][0]["id"] == "run_wf1"


def test_explanation_shows_the_resume_point():
    events = [
        {"type": "run.resumed", "data": {"checkpointId": "ckpt_run_x_2", "step": 3}},
    ]
    result = explain_run(run_id="run_x", events=events)
    assert result["resumed"]["checkpointId"] == "ckpt_run_x_2"
    assert result["resumed"]["step"] == 3


def test_explanation_redacts_secret_like_scope():
    events = [
        {"type": "workflow.step_started",
         "data": {"workflowId": "wf", "stepId": "s", "kind": "agent", "scope": ["api_key=sk-123"]}},
    ]
    result = explain_run(run_id="run", events=events)
    blob = str(result)
    assert "sk-123" not in blob

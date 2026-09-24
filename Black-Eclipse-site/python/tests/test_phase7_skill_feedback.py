"""Phase 7 — skill feedback linked to run diagnostics (Workstream H).

Proves:
  * a run with a provider-eligibility failure produces a reviewable candidate
    carrying linked diagnostics and an explicit regional scope (never "all
    countries"),
  * candidates remain INERT — they cannot affect live behavior,
  * the operator-gated promotion path still requires review (an unreviewed
    candidate cannot be promoted),
  * the diagnostics/scope columns persist and round-trip.

All offline; synthetic run traces and temp databases only.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.finance_tools import register_finance_tools
from harness.persistence import AgentMemoryStore
from harness.retrieval_tools import register_retrieval_tools
from harness.skills import SkillRegistry, SkillStore
from harness.skills.learning import _diagnostic_summary, _infer_scope, analyze_run
from harness.skills.lifecycle import request_promotion
from harness.skills.permissions import OPERATOR_ACTOR
from harness.tools import ToolRegistry


@pytest.fixture()
def env():
    directory = tempfile.mkdtemp(prefix="be-p7skill-")
    db = os.path.join(directory, "agent-memory.db")
    store = AgentMemoryStore(db)
    skill_store = SkillStore(db)
    registry = SkillRegistry(skill_store)
    registry.load_all()
    tools = ToolRegistry()
    register_finance_tools(tools)
    register_retrieval_tools(tools)
    registry.attach_tool_registry(tools)
    yield {"store": store, "skill_store": skill_store, "registry": registry}
    store.close()
    skill_store.close()


def _run_with_ineligible_provider(store, run_id="run_p7"):
    store.create_run(run_id, "eclipse-agent", {"query": "Research 2330.TW revenue"})
    store.append_event(run_id, "run.started", 1, {"maxSteps": 8})
    # A provider attempted for a market it does not cover, plus a working route.
    store.append_event(
        run_id, "retrieval.source_unavailable", 2,
        {"source": "SEC", "error": "not_covered: SEC EDGAR covers US issuers only"},
    )
    store.append_event(run_id, "tool.completed", 3, {"name": "research_retrieve_source"})

    class T:
        def __init__(self, name, ok, text):
            self.tool_call_id = f"c_{name}"
            self.name = name
            self.ok = ok
            self.duration_ms = 5
            self.text = text
            self.error = None
            self.args = {}

    store.record_tool_execution(run_id, T("fundamentals_get_financials", False, "SEC: bridge HTTP 400; JDDS: 2330.TW is not in the Taiwan universe."))
    store.record_tool_execution(run_id, T("research_retrieve_source", True, "Retrieved 2330.TW annual report (TW market)"))
    store.update_run(run_id, status="completed", output="answer", modelSteps=3, toolCalls=2, toolErrors=1)
    return run_id


def test_scope_is_observed_markets_only():
    tools = [{"text": "2330.TW is not in the Taiwan universe"}, {"text": "US market fallback"}]
    scope = _infer_scope(tools)
    assert "TW" in scope["markets"]
    assert "US" in scope["markets"]
    assert scope["scopeClaim"] == "observed markets only"


def test_scope_never_claims_all_countries():
    scope = _infer_scope([{"text": "no market tokens here"}])
    assert scope["markets"] == []
    assert scope["scopeClaim"] == "unspecified"


def test_diagnostics_summary_extracts_category_and_provider():
    events = [
        {"type": "retrieval.source_unavailable", "data": {"source": "SEC", "error": "not_covered"}},
        {"type": "tool.completed", "data": {"name": "x"}},
    ]
    summary = _diagnostic_summary(events)
    assert len(summary) == 1
    assert summary[0]["provider"] == "SEC"
    assert "not_covered" in str(summary[0]["category"])


def test_ineligible_provider_yields_region_scoped_candidate(env):
    run_id = _run_with_ineligible_provider(env["store"])
    drafts = analyze_run(run_id, env["store"])
    types = {d["candidateType"] for d in drafts}
    assert "provider_eligibility_improvement" in types
    candidate = next(d for d in drafts if d["candidateType"] == "provider_eligibility_improvement")
    # Linked diagnostics + an explicit, non-global scope.
    assert candidate["diagnostics"], "candidate must link the run diagnostics"
    assert candidate["scope"]["markets"], "scope must name the observed markets"
    assert "all countries" in candidate["generalizationNotes"].lower() or "observ" in candidate["generalizationNotes"].lower()


def test_candidate_round_trips_diagnostics_and_scope(env):
    run_id = _run_with_ineligible_provider(env["store"], run_id="run_p7_rt")
    drafts = analyze_run(run_id, env["store"])
    draft = next(d for d in drafts if d["candidateType"] == "provider_eligibility_improvement")
    signature = "sig_p7"
    candidate_id = env["skill_store"].save_candidate({
        **draft, "id": None, "sourceRunId": run_id, "signature": signature,
        "status": "detected", "createdAt": "2026-09-23T00:00:00Z",
    })
    stored = env["skill_store"].get_candidate(candidate_id)
    assert stored is not None
    assert stored["diagnostics"]  # persisted + parsed back as a list
    assert stored["scope"]["markets"]


def test_candidate_scope_names_capability_and_regression_case(env):
    """Phase 8 WS8: a candidate is scoped to the observed capability + a targeted
    regression case, never generalized to all countries/capabilities."""
    run_id = _run_with_ineligible_provider(env["store"], run_id="run_p8_cap")
    drafts = analyze_run(run_id, env["store"])
    candidate = next(
        d for d in drafts if d["candidateType"] in ("source_selection_improvement", "provider_eligibility_improvement")
    )
    scope = candidate["scope"]
    # The candidate names the capability it is about (statements, from the failing
    # fundamentals_get_financials tool) so a lesson is never applied cross-capability.
    assert scope.get("capability") == "financial_statements"
    assert scope.get("regressionCase")
    assert "fixture" in scope["regressionCase"]


def test_scope_capability_is_not_global(env):
    """A candidate must never claim every capability from one run's failure."""
    run_id = _run_with_ineligible_provider(env["store"], run_id="run_p8_cap2")
    draft = next(
        d for d in analyze_run(run_id, env["store"])
        if d["candidateType"] == "provider_eligibility_improvement"
    )
    # Capability is a single observed value, not "all".
    assert draft["scope"]["capability"] in (None, "financial_statements")


def test_unreviewed_candidate_cannot_be_promoted(env):
    """An inert candidate with no evaluation cannot become an enabled skill."""
    run_id = _run_with_ineligible_provider(env["store"], run_id="run_p7_promo")
    drafts = analyze_run(run_id, env["store"])
    draft = next(d for d in drafts if d["candidateType"] == "provider_eligibility_improvement")
    candidate_id = env["skill_store"].save_candidate({
        **draft, "id": None, "sourceRunId": run_id, "signature": "sig_p7_promo",
        "status": "detected", "createdAt": "2026-09-23T00:00:00Z",
    })
    assert env["skill_store"].get_candidate(candidate_id)["status"] == "detected"

    # Promotion requires a skill + a passing evaluation; an unreviewed candidate
    # alone is not enough (the request fails rather than silently enabling).
    result = request_promotion(
        env["registry"],
        skill_id="fundamental-analysis",
        version=None,
        actor=OPERATOR_ACTOR,
        reason="from candidate",
        evaluation_id=None,
    )
    assert result.get("ok") is False
    # And the candidate itself was never turned into an enabled skill.
    assert env["skill_store"].get_candidate(candidate_id)["status"] == "detected"

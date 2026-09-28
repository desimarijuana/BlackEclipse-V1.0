"""Run-level memory/skill observability (Phase 7). Derived, bounded, redacted."""

from __future__ import annotations

from harness.run_observability import explain_run


def test_explains_injected_and_excluded():
    retrieval = {
        "selectedIds": ["mem_1", "mem_2"],
        "selectionReasons": ["mem_1 (preference): standing rule"],
        "excluded": [
            {"id": "mem_3", "reason": "status=archived"},
            {"id": "mem_4", "reason": "over context budget"},
            {"id": "mem_5", "reason": "another user's scope"},
            {"id": "mem_6", "reason": "no lexical relevance to query"},
        ],
        "usedChars": 120,
        "budgetChars": 4000,
    }
    result = explain_run(run_id="run-1", retrieval_event=retrieval)
    assert [m["id"] for m in result["memory"]["injected"]] == ["mem_1", "mem_2"]
    categories = {e["category"] for e in result["memory"]["excluded"]}
    assert {"status", "budget", "scope", "relevance"} <= categories
    assert result["memory"]["budget"]["usedChars"] == 120


def test_parses_json_strings_from_db():
    import json

    retrieval = {
        "selectedIds": [],
        "excluded": json.dumps([{"id": "m", "reason": "expired"}]),
        "selectionReasons": json.dumps([]),
    }
    result = explain_run(run_id="r", retrieval_event=retrieval)
    assert result["memory"]["excluded"][0]["category"] == "expiry"


def test_prompt_plan_segments_are_included():
    events = [{
        "type": "prompt.plan",
        "data": {"cacheKey": "abc", "reusableTokens": 100,
                 "segments": [{"id": "skill_manifest", "source": "registry", "chars": 50, "tokenEstimate": 12, "version": "v1"}]},
    }]
    result = explain_run(run_id="r", events=events)
    assert result["promptPlan"]["segments"][0]["id"] == "skill_manifest"
    assert result["promptPlan"]["reusableTokens"] == 100


def test_profile_and_bundle_events_surface():
    events = [
        {"type": "memory.profile_built", "data": {"snapshotId": "s1", "entries": 3, "charCount": 200, "tokenEstimate": 50, "excluded": 1}},
        {"type": "skill.bundle_resolved", "data": {"bundleId": "research", "resolved": ["a.b"], "missing": ["c.d"], "unavailable": [], "provenance": "manual"}},
    ]
    result = explain_run(run_id="r", events=events)
    assert result["profile"]["entries"] == 3
    assert result["skills"]["bundleId"] == "research"
    assert result["skills"]["missing"] == ["c.d"]


def test_secrets_are_redacted():
    retrieval = {
        "selectedIds": ["mem_1"],
        "selectionReasons": ["api_key: sk-abcdef123456"],
        "excluded": [{"id": "m", "reason": "token: supersecret"}],
    }
    result = explain_run(run_id="r", retrieval_event=retrieval)
    blob = str(result)
    assert "sk-abcdef123456" not in blob
    assert "supersecret" not in blob
    assert "[redacted]" in blob


def test_empty_input_is_honest():
    result = explain_run(run_id="r")
    assert result["memory"]["injected"] == []
    assert result["promptPlan"] is None
    assert result["note"]

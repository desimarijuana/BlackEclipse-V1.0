"""Learned preferences: inference, evidence thresholds, gate, suppression.

These tests pin the properties the Personal Memory feature promises:

  * a single task instruction is only an observation, never a preference;
  * repeated, consistent behaviour across distinct runs produces ONE inert
    suggestion;
  * accepting a suggestion writes a user-scoped preference through the shared
    gate and the compact profile recalls it;
  * dismissing a suggestion suppresses the same inference;
  * explicit preferences win, and a disabled dimension / mode produces nothing;
  * secrets are never copied into evidence.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.eclipse_memory import EclipseMemoryService, EclipseMemoryStore
from harness.eclipse_memory import preferences as pref_mod


@pytest.fixture()
def service():
    directory = tempfile.mkdtemp(prefix="be-pref-")
    svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    yield svc
    svc.close()


def _observe(service, text, run_id, user_id="u1"):
    return service.observe_turn_preferences(
        text, user_id=user_id, run_id=run_id, learn_now=False,
    )


def _three_runs(service, text="Please show the results as a table", user_id="u1"):
    for index in range(3):
        _observe(service, text, f"run-{index}", user_id=user_id)


def test_infer_detects_format_and_length():
    signals = {signal.dimension: signal for signal in pref_mod.infer("Use a table and keep it brief")}
    assert signals["answer_format"].value == "tables"
    assert signals["answer_length"].value == "concise"
    assert signals["answer_format"].evidence


def test_infer_drops_ambiguous_dimension():
    signals = pref_mod.infer("Keep it brief and detailed")
    assert all(signal.dimension != "answer_length" for signal in signals)


def test_infer_never_copies_a_secret():
    assert pref_mod.infer("show a table with sk-abcdefghijklmnop") == []


def test_single_observation_creates_no_suggestion(service):
    _observe(service, "Please show the results as a table", "run-1")
    result = service.learn_preferences(user_id="u1")
    assert result["created"] == []
    assert service.store.list_suggestions(status="pending") == []


def test_three_distinct_runs_create_one_inert_suggestion(service):
    _three_runs(service)
    result = service.learn_preferences(user_id="u1")
    assert len(result["created"]) == 1
    pending = service.store.list_suggestions(status="pending", scope_id="u1")
    assert len(pending) == 1
    suggestion = pending[0]
    assert suggestion["memoryType"] == "preference"
    assert suggestion["provenance"] == "preference_learning"
    assert suggestion["subject"] == "answer_format"
    assert suggestion["structuredData"]["value"] == "tables"
    assert suggestion["structuredData"]["distinctRuns"] == 3
    # Inert: a suggestion is never a memory record.
    assert service.store.list_memories(memory_type="preference", scope="user", scope_id="u1") == []


def test_same_run_is_idempotent(service):
    for _ in range(3):
        _observe(service, "Please show the results as a table", "run-same")
    groups = service.store.preference_observation_groups(user_id="u1")
    assert groups[0]["observationCount"] == 1
    assert groups[0]["distinctRuns"] == 1


def test_learning_twice_does_not_duplicate_a_pending_suggestion(service):
    _three_runs(service)
    first = service.learn_preferences(user_id="u1")
    second = service.learn_preferences(user_id="u1")
    assert len(first["created"]) == 1
    assert second["created"] == []
    assert len(service.store.list_suggestions(status="pending", scope_id="u1")) == 1


def test_accepting_writes_user_scoped_preference_and_profile_recalls_it(service):
    _three_runs(service)
    service.learn_preferences(user_id="u1")
    suggestion = service.store.list_suggestions(status="pending", scope_id="u1")[0]
    outcome = service.accept_suggestion(suggestion["id"], user_id="u1")
    assert outcome["ok"] is True
    memory = outcome["memory"]
    assert memory["memoryType"] == "preference"
    assert memory["scope"] == "user"
    assert memory["scopeId"] == "u1"
    assert memory["structuredData"]["value"] == "tables"
    profile = service.build_profile(scope_id="u1")
    assert any("tables" in entry.content for entry in profile.entries)


def test_dismissing_suppresses_the_same_inference(service):
    _three_runs(service)
    service.learn_preferences(user_id="u1")
    suggestion = service.store.list_suggestions(status="pending", scope_id="u1")[0]
    assert service.dismiss_suggestion(suggestion["id"], user_id="u1")["ok"] is True
    result = service.learn_preferences(user_id="u1")
    assert result["created"] == []
    assert service.store.list_suggestions(status="pending", scope_id="u1") == []


def test_explicit_preference_wins_over_inference(service):
    service.write_memory(
        memory_type="preference", content="User prefers answers formatted as tables.",
        source="explicit_user", scope="user", scope_id="u1",
    )
    _three_runs(service)
    result = service.learn_preferences(user_id="u1")
    assert result["created"] == []


def test_active_preference_blocks_a_conflicting_inference(service):
    service.write_memory(
        memory_type="preference", content="User prefers answers formatted as tables.",
        source="explicit_user", scope="user", scope_id="u1",
    )
    _three_runs(service, "Use bullet points")
    result = service.learn_preferences(user_id="u1")
    assert result["created"] == []
    assert service.store.list_suggestions(status="pending", scope_id="u1") == []


def test_policy_off_disables_learning(service):
    _three_runs(service)
    service.policy.set("preference_learning_mode", "off")
    result = service.learn_preferences(user_id="u1")
    assert result["created"] == []
    assert service.store.list_suggestions(status="pending", scope_id="u1") == []


def test_memory_mode_off_blocks_automatic_preference_prompts(service):
    _three_runs(service)
    service.policy.set("memory_mode", "off")
    result = service.learn_preferences(user_id="u1")
    assert result["created"] == []
    assert result["saved"] == []
    assert service.store.list_suggestions(status="pending", scope_id="u1") == []


def test_disabled_dimension_is_not_learned(service):
    _three_runs(service)
    service.policy.set("preference_dimensions", {"answer_format": False})
    result = service.learn_preferences(user_id="u1")
    assert result["created"] == []


def test_auto_mode_saves_only_when_the_memory_gate_permits(service):
    _three_runs(service)
    service.policy.set("preference_learning_mode", "auto")
    service.policy.set("memory_mode", "automatic_selective")
    result = service.learn_preferences(user_id="u1")
    assert len(result["saved"]) == 1
    active = service.store.list_memories(
        memory_type="preference", scope="user", scope_id="u1", include_inactive=False,
    )
    assert len(active) == 1
    assert active[0]["structuredData"]["value"] == "tables"


def test_auto_mode_with_ask_gate_stages_exactly_one_suggestion(service):
    _three_runs(service)
    service.policy.set("preference_learning_mode", "auto")
    service.policy.set("memory_mode", "ask_before_saving")
    result = service.learn_preferences(user_id="u1")
    assert len(result["created"]) == 1
    pending = service.store.list_suggestions(status="pending", scope_id="u1")
    assert len(pending) == 1
    assert pending[0]["structuredData"]["value"] == "tables"


def test_summary_reports_dimensions_thresholds_and_evidence(service):
    _three_runs(service)
    service.learn_preferences(user_id="u1")
    summary = service.preference_summary(user_id="u1")
    assert summary["success"] is True
    assert summary["mode"] == "ask"
    assert summary["observationCount"] == 3
    assert {item["id"] for item in summary["dimensions"]} == set(pref_mod.DIMENSION_KEYS)
    assert summary["thresholds"]["minDistinctRuns"] == 3
    assert len(summary["suggestions"]) == 1
    assert len(summary["observations"]) == 1


def test_inconsistent_evidence_is_not_promoted(service):
    _observe(service, "Use a table", "run-1")
    _observe(service, "Use bullet points", "run-2")
    _observe(service, "Use bullet points", "run-3")
    _observe(service, "Use a table", "run-4")
    result = service.learn_preferences(user_id="u1")
    assert result["created"] == []

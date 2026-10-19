"""Round 4 (W11): L3 strategic learning — the route that worked, measured.

L3 reads the EXISTING recovery ledger and prefers the strategy the evidence
supports; thin evidence yields None. The browser-vs-API acceptance: a repeated
situation where one route failed and another succeeded produces the working
route as the preference, with its measured success rate.
"""

from __future__ import annotations

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.service import RecoveryService
from harness.recovery.strategy_learning import (
    preferred_strategy,
    strategy_stats,
)


def test_stats_count_attempts_and_successes_per_strategy():
    incidents = [{"id": "inc_1", "signature": "sig_a"}]
    attempts = {
        "inc_1": [
            {"strategy": "substitute_tool", "outcome": "failed"},
            {"strategy": "alternative_implementation", "outcome": "succeeded"},
            {"strategy": "alternative_implementation", "outcome": "resolved"},
            {"strategy": None, "outcome": "succeeded"},  # no strategy: ignored
        ],
    }
    stats = strategy_stats(incidents, attempts, failure_signature="sig_a")
    assert stats["sig_a"]["substitute_tool"] == {"attempts": 1, "succeeded": 0}
    assert stats["sig_a"]["alternative_implementation"] == {"attempts": 2, "succeeded": 2}


def test_preference_requires_observations_and_a_success_rate():
    stats = {"api_call": {"attempts": 3, "succeeded": 1}}  # 33% — below the floor
    assert preferred_strategy(stats, failure_signature="s") is None
    stats = {"api_call": {"attempts": 1, "succeeded": 1}}  # one lucky run is not evidence
    assert preferred_strategy(stats, failure_signature="s") is None


def test_preference_picks_the_measured_route_deterministically():
    stats = {
        "browser_navigate": {"attempts": 4, "succeeded": 1},
        "api_call": {"attempts": 4, "succeeded": 4},
        "scrape": {"attempts": 2, "succeeded": 2},
    }
    preference = preferred_strategy(stats, failure_signature="sig_x")
    assert preference is not None
    assert preference.strategy == "api_call"  # highest rate, then most successes
    assert preference.success_rate == 1.0
    assert preference.to_dict()["observations"] == 4


def test_the_browser_vs_api_choice_is_learned_from_the_real_ledger(tmp_path):
    service = RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))
    # The same recurring situation, seen twice (the same signature).
    first = service.record_failure(
        code="TOOL_ERROR", message="browser route refused the page", subsystem="browser",
    )
    service.record_failure(
        code="TOOL_ERROR", message="browser route refused the page", subsystem="browser",
    )
    incident_id = first["incidentId"]
    signature = service.store.get_incident(incident_id)["signature"]

    store = service.store
    store.record_attempt(incident_id, attempt_no=1, action="recover",
                         strategy="browser_navigate", outcome="failed")
    store.record_attempt(incident_id, attempt_no=2, action="recover",
                         strategy="api_call", outcome="succeeded")
    store.record_attempt(incident_id, attempt_no=3, action="recover",
                         strategy="api_call", outcome="succeeded")

    preference = service.preferred_strategy(signature)
    assert preference is not None
    assert preference.strategy == "api_call"
    assert preference.observations == 2
    assert preference.success_rate == 1.0
    assert preference.failure_signature == signature

    # An unknown signature (or thin evidence) yields None — never a guess.
    assert service.preferred_strategy("no_such_signature") is None
    assert service.preferred_strategy("") is None


def test_the_preference_reorders_the_policys_own_candidates(tmp_path):
    """L3 feeds the decision: the measured route is promoted to first AMONG the
    strategies the policy already offers — never one it did not."""
    service = RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))
    first = service.record_failure(
        code="ETIMEDOUT", message="the endpoint timed out", subsystem="web",
    )
    incident_id = first["incidentId"]
    signature = service.store.get_incident(incident_id)["signature"]
    store = service.store
    store.record_attempt(incident_id, attempt_no=1, action="recover",
                         strategy="retry", outcome="failed")
    store.record_attempt(incident_id, attempt_no=2, action="recover",
                         strategy="substitute_tool", outcome="succeeded")
    store.record_attempt(incident_id, attempt_no=3, action="recover",
                         strategy="substitute_tool", outcome="succeeded")

    decision = service.record_failure(
        code="ETIMEDOUT", message="the endpoint timed out", subsystem="web",
        # A FRESH run's counters (the hot path's recovery_state), so the durable
        # per-signature budget does not stop the decision before it is made.
        recovery_state={"attempts": 0, "signature_attempts": 0, "recurrent": False},
    )
    assert decision["decision"]["strategy"] == "substitute_tool"  # promoted
    assert "L3 preference" in decision["decision"]["reason"]
    assert decision["strategyPreference"]["strategy"] == "substitute_tool"

    # A preference the policy does NOT offer for this kind changes nothing.
    service2 = RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse2.db")))
    seeded = service2.record_failure(
        code="PERMISSION_DENIED", message="a credential is required", subsystem="api",
    )
    seeded_id = seeded["incidentId"]
    seeded_signature = service2.store.get_incident(seeded_id)["signature"]
    service2.store.record_attempt(seeded_id, attempt_no=1, action="recover",
                                  strategy="substitute_tool", outcome="succeeded")
    service2.store.record_attempt(seeded_id, attempt_no=2, action="recover",
                                  strategy="substitute_tool", outcome="succeeded")
    auth_decision = service2.record_failure(
        code="PERMISSION_DENIED", message="a credential is required", subsystem="api",
        recovery_state={"attempts": 0, "signature_attempts": 0, "recurrent": False},
    )
    # The auth-denial policy never offers substitution; the preference cannot add it.
    assert auth_decision["decision"]["strategy"] != "substitute_tool"
    assert seeded_signature  # the ledger exists; the guard is the candidate set

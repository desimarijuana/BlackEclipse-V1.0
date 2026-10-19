"""Round 4 (W2) — routing repair proposals: diagnose, propose, verify.

The synthetic fixture is the one phrasing the W0 rule cannot see: a dashboard
that is "missing" a capability. The proposal adds the missed additive phrase,
the REAL classifier is re-run with that rule activated, and the change is
reverted. No file is written and no model is called.
"""

from __future__ import annotations

from harness.recovery.diagnosis import DiagnosisEngine
from harness.recovery.routing_repair import (
    RoutingCause,
    diagnose,
    proposal_from_incident,
    propose,
    verify,
)
from harness.recovery.taxonomy import FailureKind, NormalizedFailure, Retryability
from harness.ui.catalog import UiCatalog
from harness.ui.mode import classify_request

TEXT = "my dashboard is missing a world clock"


def _mode(text: str = TEXT) -> tuple[str, bool]:
    decision = classify_request(text, catalog=UiCatalog())
    return decision.mode.value, decision.capability_gap


def test_the_fixture_is_currently_misrouted():
    # The additive rule cannot see "missing", so the request composes.
    assert _mode() == ("compose", False)


def test_diagnose_names_a_vocabulary_gap():
    cause, evidence = diagnose(TEXT)
    assert cause is RoutingCause.VOCABULARY_GAP
    assert evidence["missedPhrases"] == ["missing"]


def test_proposal_is_a_minimal_classifier_rule():
    proposal = propose(TEXT)
    assert proposal.cause is RoutingCause.VOCABULARY_GAP
    assert proposal.kind == "classifier_rule"
    assert proposal.added_phrases == ("missing",)
    assert proposal.target_file == "python/harness/ui/mode.py"
    assert proposal.patch["old"].count("show") == 1
    assert '"missing"' in proposal.patch["new"]
    assert proposal.patch["old"] != proposal.patch["new"]


def test_the_patch_anchor_is_exact_and_unique():
    from pathlib import Path

    mode_file = Path(__file__).resolve().parents[1] / "harness" / "ui" / "mode.py"
    source = mode_file.read_text(encoding="utf-8")
    proposal = propose(TEXT)
    assert source.count(proposal.patch["old"]) == 1


def test_verify_flips_the_classification_and_restores_it():
    proposal = propose(TEXT)
    assert verify(proposal) is True
    # Verification is a simulation; the live rule is untouched afterwards.
    assert _mode() == ("compose", False)


def test_the_proposal_reuses_the_improvement_contract():
    proposal = propose(TEXT)
    improvement = proposal.to_improvement()
    assert improvement.target_dimension == "misroute_rate"
    improvement.run()
    try:
        assert _mode() == ("engineer", True)
    finally:
        improvement.revert()
    assert _mode() == ("compose", False)


def test_the_proposal_emits_a_patch_op():
    op = propose(TEXT).as_patch_op()
    assert op is not None
    assert op.op == "replace"
    assert op.path == "python/harness/ui/mode.py"
    assert op.old == propose(TEXT).patch["old"]
    assert op.new == propose(TEXT).patch["new"]


def test_a_catalog_gap_is_an_engineering_proposal_not_a_code_patch():
    # No additive phrase is missed; the catalog simply has no clock.
    text = "I would love a world clock on my dashboard"
    assert _mode(text) == ("compose", False)
    proposal = propose(text)
    assert proposal.cause is RoutingCause.CATALOG_GAP
    assert proposal.kind == "engineering"
    assert proposal.patch is None
    assert proposal.as_patch_op() is None


def test_an_already_correct_route_needs_no_change():
    proposal = propose("add a multi-zone world clock to my dashboard")
    assert proposal.cause is RoutingCause.NO_ACTION
    assert proposal.kind == "none"


def test_proposal_from_an_incident_uses_the_stored_request():
    proposal = proposal_from_incident({
        "id": "inc_1",
        "message": "no registered component matches: my dashboard is missing a world clock",
    })
    assert proposal.cause is RoutingCause.VOCABULARY_GAP
    assert proposal.incident_id == "inc_1"
    assert proposal.fixture["text"] == TEXT


def test_the_recovery_service_exposes_a_proposal_for_a_stored_incident(tmp_path):
    from harness.eclipse_memory.store import EclipseMemoryStore
    from harness.recovery.service import RecoveryService

    memory = EclipseMemoryStore(str(tmp_path / "routing-repair.db"))
    try:
        service = RecoveryService(memory)
        recorded = service.record_failure(
            code="UI_CAPABILITY_GAP",
            message="no registered component matches: my dashboard is missing a world clock",
            subsystem="ui",
            source="event",
            details={"capability_gap": True},
        )
        proposal = service.propose_routing_repair(recorded["incidentId"])
        assert proposal is not None
        assert proposal["cause"] == "vocabulary_gap"
        assert proposal["kind"] == "classifier_rule"
        assert proposal["incidentId"] == recorded["incidentId"]
        assert proposal["patch"]["old"] in propose(TEXT).patch["old"]
    finally:
        memory.close()


def test_the_diagnosis_engine_selects_the_catalog_cause():
    failure = NormalizedFailure(
        kind=FailureKind.CAPABILITY,
        retryability=Retryability.NON_RETRYABLE,
        code="ui_capability_gap",
        message="no registered component matches: world clock",
        subsystem="ui",
        source="event",
    )
    diagnosis = DiagnosisEngine().diagnose(failure, evidence={"capability_gap": True})
    assert diagnosis.selected is not None
    assert "catalog has no implementation" in diagnosis.selected

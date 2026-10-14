"""Phase 19 G1 — artifact and change-review claims are backed or marked.

A sentence that asserts an artifact is intact (or that the change was reviewed)
must be supported by a RECORDED check; without one the existing enforcement path
marks it UNVERIFIED. The patterns are narrow: a negated sentence and an
unrelated sentence never match.
"""

from __future__ import annotations

from harness.code.verify import ArtifactRecord, VerificationLedger, enforce_answer


def _ledger_with_passing_artifact() -> VerificationLedger:
    ledger = VerificationLedger("r")
    ledger.record_artifact(ArtifactRecord(
        artifact_name="chart.csv", kind="text", check="artifact_exists",
        passed=True, detail="it is where it was reported", observed={},
    ))
    return ledger


def test_an_artifact_claim_without_a_record_is_marked_unverified():
    ledger = VerificationLedger("r")
    outcome = enforce_answer("The figure is intact and the results hold.", ledger)
    assert outcome.enforced is True
    kinds = {c.kind for c in outcome.marked}
    assert "artifacts_verified" in kinds
    assert "UNVERIFIED" in outcome.answer


def test_an_artifact_claim_with_a_passing_record_is_supported():
    ledger = _ledger_with_passing_artifact()
    outcome = enforce_answer("The figure is intact.", ledger)
    assert outcome.enforced is False
    assert "UNVERIFIED" not in outcome.answer


def test_a_failing_artifact_record_does_not_support_the_claim():
    ledger = VerificationLedger("r")
    ledger.record_artifact(ArtifactRecord(
        artifact_name="chart.csv", kind="text", check="artifact_digest",
        passed=False, detail="its digest does not match the record", observed={},
    ))
    outcome = enforce_answer("The file is intact.", ledger)
    assert outcome.enforced is True


def test_a_negated_sentence_is_the_honest_case_and_never_matches():
    ledger = VerificationLedger("r")
    outcome = enforce_answer("I could not check the figure.", ledger)
    assert outcome.enforced is False
    assert ledger.claims("I could not check the figure.") == []


def test_an_unrelated_sentence_never_matches():
    ledger = VerificationLedger("r")
    assert ledger.claims("The report is complete and covers the quarter.") == []
    outcome = enforce_answer("The report is complete and covers the quarter.", ledger)
    assert outcome.enforced is False


def test_a_review_claim_needs_a_recorded_review():
    ledger = VerificationLedger("r")
    marked = enforce_answer("I reviewed the change and it follows the pattern.", ledger)
    assert marked.enforced is True
    assert {c.kind for c in marked.marked} == {"change_reviewed"}

    ledger.record_review({"ran": True, "filesReviewed": 1, "findings": [], "unevaluated": []})
    supported = enforce_answer("I reviewed the change and it follows the pattern.", ledger)
    assert supported.enforced is False


def test_the_new_records_round_trip_through_the_blob():
    ledger = _ledger_with_passing_artifact()
    ledger.record_review({"ran": True, "filesReviewed": 2, "findings": [], "unevaluated": []})
    blob = ledger.to_blob()
    assert blob["artifacts"] and blob["reviews"]

    restored = VerificationLedger.from_blob("r", blob)
    assert len(restored.artifacts) == 1
    assert len(restored.reviews) == 1
    # An old blob (no keys) rehydrates empty, never fabricated.
    old = VerificationLedger.from_blob("r", {"recordCount": 0, "records": []})
    assert old.artifacts == [] and old.reviews == []

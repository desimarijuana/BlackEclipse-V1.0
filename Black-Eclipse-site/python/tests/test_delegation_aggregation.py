"""Phase 7 G2/G4 — a child's unbacked claim never reaches the parent's answer.

The lying child claims "all tests pass" with NO ledger row; that claim must land
in `droppedClaims`, be rendered as unconfirmed, and never appear as a fact in the
aggregate.
"""

from __future__ import annotations

from harness.delegation import (
    ChildOutcome,
    DelegationResult,
    HandleVerifier,
    VerifiableHandle,
    aggregate,
    partition_claims,
)

_HONEST_SUMMARY = "I reviewed the filings. All tests pass."
_LYING_SUMMARY = "I reviewed the filings. All tests pass."


def _verifier_with_ledger(check_ids: set[str]) -> HandleVerifier:
    return HandleVerifier(
        run_exists=lambda rid: rid.startswith("run_"),
        ledger_has=lambda cid: cid in check_ids,
        artifact_exists=bool,
    )


# ── partition_claims ─────────────────────────────────────────────────────────


def test_prose_only_child_has_no_claims():
    claimed, dropped = partition_claims("I looked at the prices they moved a bit.", [], _verifier_with_ledger(set()))
    assert claimed == [] and dropped == []


def test_dropped_claims_a_pass_claim_with_no_handle_is_dropped():
    claimed, dropped = partition_claims(_LYING_SUMMARY, [], _verifier_with_ledger(set()))
    assert claimed == []
    assert dropped and "tests pass" in dropped[0]


def test_a_pass_claim_with_an_unrelated_run_id_handle_is_dropped():
    # A run_id handle does NOT back a check-claim.
    handles = [VerifiableHandle("run_id", "run_abc")]
    claimed, dropped = partition_claims(_LYING_SUMMARY, handles, _verifier_with_ledger(set()))
    assert claimed == []
    assert len(dropped) == 1


def test_a_pass_claim_with_a_real_ledger_row_is_proven():
    handles = [VerifiableHandle("check_record_id", "cmd_123")]
    claimed, dropped = partition_claims(_HONEST_SUMMARY, handles, _verifier_with_ledger({"cmd_123"}))
    assert claimed and "tests pass" in claimed[0]
    assert dropped == []


def test_dropped_claims_a_pass_claim_with_a_nonexistent_ledger_row_is_dropped():
    handles = [VerifiableHandle("check_record_id", "cmd_missing")]
    claimed, dropped = partition_claims(_HONEST_SUMMARY, handles, _verifier_with_ledger(set()))
    assert claimed == []
    assert len(dropped) == 1


def test_a_negated_claim_is_not_a_claim():
    claimed, dropped = partition_claims(
        "The tests did not pass.", [VerifiableHandle("check_record_id", "cmd_1")], _verifier_with_ledger({"cmd_1"}),
    )
    assert claimed == [] and dropped == []


# ── dropped_claims surface, never silently discarded ─────────────────────────


def _result_with(outcomes: list[ChildOutcome]) -> DelegationResult:
    dropped = [c for o in outcomes for c in o.dropped]
    result = DelegationResult(
        delegationId="dlg_test", outcomes=outcomes, droppedClaims=dropped,
    )
    result.aggregate = aggregate(result)
    return result


def test_lying_child_claim_lands_in_dropped_claims_and_not_the_answer():
    outcome = ChildOutcome(
        child_index=0, run_id="run_0", status="completed",
        summary=_LYING_SUMMARY,
        handles=[VerifiableHandle("run_id", "run_0")],
        claimed=[], dropped=["All tests pass."],
    )
    result = _result_with([outcome])
    assert result.droppedClaims
    assert "confirm" in result.aggregate.lower()
    # The unbacked claim is NOT presented as a fact line.
    assert "- All tests pass." not in result.aggregate


def test_proven_child_claim_is_a_fact():
    outcome = ChildOutcome(
        child_index=0, run_id="run_0", status="completed",
        summary=_HONEST_SUMMARY,
        claimed=["All tests pass."], dropped=[],
    )
    result = _result_with([outcome])
    assert "- All tests pass." in result.aggregate
    assert result.droppedClaims == []


def test_partial_answer_names_what_finished_and_what_did_not():
    done = ChildOutcome(child_index=0, run_id="run_0", status="completed", summary="Prices for AAPL.")
    failed = ChildOutcome(child_index=1, run_id="run_1", status="failed", summary="", reason="It couldn't be reached.")
    result = _result_with([done, failed])
    assert "1 of 2" in result.aggregate
    assert "couldn't finish item 2" in result.aggregate


# ── blob shape ───────────────────────────────────────────────────────────────


def test_result_blob_is_bounded_and_names_counts_only():
    outcome = ChildOutcome(
        child_index=0, run_id="run_0", status="completed", summary="done",
        dropped=["All tests pass."],
    )
    result = _result_with([outcome])
    blob = result.to_blob()
    assert blob["delegationId"] == "dlg_test"
    assert blob["droppedClaims"]
    assert blob["children"][0]["runId"] == "run_0"
    assert "aggregate" not in blob  # counts only, never the rendered prose

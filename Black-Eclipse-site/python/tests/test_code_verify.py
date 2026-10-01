"""Phase 4 — the VerificationLedger and the answer renderer (verify.py).

Proves a passing claim is impossible without a zero-exit record: prose is never
the gate, a deterministic check owns the decision.
"""

from __future__ import annotations

import pytest

from harness.code.verify import (
    MAX_LEDGER_RECORDS,
    UNVERIFIED_MARKER,
    VerificationLedger,
    VerificationRecord,
    enforce_answer,
    output_digest,
)


def _ledger_with(command_class: str, exit_code: int, output: str = "ok") -> VerificationLedger:
    led = VerificationLedger("run_x")
    led.record(
        command_execution_id=f"cmd_{command_class}_{exit_code}",
        command_class=command_class, exit_code=exit_code, duration_ms=100, output=output,
    )
    return led


# ── claims + support ────────────────────────────────────────────────────────


def test_zero_exit_unit_test_supports_all_tests_pass():
    led = _ledger_with("unit_test", 0)
    claims = led.claims("All tests pass.")
    assert len(claims) == 1
    assert claims[0].kind == "tests_pass"
    assert led.unverified_claims("All tests pass.") == []


def test_nonzero_exit_does_not_support_the_claim():
    led = _ledger_with("unit_test", 1)
    unverified = led.unverified_claims("All tests pass.")
    assert len(unverified) == 1
    assert unverified[0].supported is False
    # The failing record is named as evidence so the marker can say it FAILED.
    assert unverified[0].evidenceExitCode == 1


def test_empty_ledger_marks_the_claim():
    led = VerificationLedger("run_x")
    out = enforce_answer("I refactored the parser. All tests pass.", led)
    assert out.enforced is True
    assert len(out.marked) == 1
    assert out.stripped == []
    assert "UNVERIFIED" in out.answer
    assert len(led.verified()) == 0


def test_strip_mode_removes_the_sentence():
    led = VerificationLedger("run_x")
    out = enforce_answer("All tests pass. The code is clean.", led, mode="strip")
    assert out.enforced is True
    assert len(out.stripped) == 1
    assert "All tests pass" not in out.answer
    assert "The code is clean." in out.answer


def test_supported_claim_is_untouched():
    led = _ledger_with("unit_test", 0)
    out = enforce_answer("All tests pass.", led)
    assert out.enforced is False
    assert out.marked == [] and out.stripped == []


# ── claim parsing: honest negatives are never flagged ───────────────────────


@pytest.mark.parametrize("honest", [
    "The tests did not run.",
    "I did not run the tests.",
    "I could not run the build.",
    "The tests were not run in this session.",
    "No tests were run.",
])
def test_honest_negatives_are_not_claims(honest):
    led = VerificationLedger("run_x")
    assert led.claims(honest) == []
    assert enforce_answer(honest, led).enforced is False


# ── digest stability ────────────────────────────────────────────────────────


def test_digest_stable_across_crlf_and_trailing_whitespace():
    a = output_digest("line1\nline2\n")
    b = output_digest("line1  \r\nline2\r\n\r\n")
    assert a == b


def test_digest_changes_when_one_line_changes():
    a = output_digest("line1\nline2\n")
    b = output_digest("line1\nline3\n")
    assert a != b


# ── record: unknown class refused ───────────────────────────────────────────


def test_record_raises_on_unknown_class():
    led = VerificationLedger("run_x")
    with pytest.raises(ValueError):
        led.record(
            command_execution_id="x", command_class="not_a_class",
            exit_code=0, duration_ms=1, output="",
        )


# ── blob round-trip ─────────────────────────────────────────────────────────


def test_blob_round_trip():
    led = _ledger_with("python_test", 0, "3 passed")
    blob = led.to_blob()
    restored = VerificationLedger.from_blob("run_x", blob)
    assert len(restored.records) == 1
    assert restored.records[0].command_class == "python_test"
    assert restored.records[0].exit_code == 0


def test_garbled_blob_yields_empty_ledger():
    for bad in (None, {}, {"records": "nope"}, {"records": [{"commandClass": "bogus"}]}, 42, "x"):
        led = VerificationLedger.from_blob("run_x", bad)
        assert led.records == []


def test_malformed_rows_are_dropped_not_guessed():
    blob = {"records": [
        {"commandClass": "unit_test", "exitCode": 0, "commandExecutionId": "a", "outputDigest": "d"},
        {"commandClass": "bogus", "exitCode": 0},
        {"commandClass": "unit_test"},  # no exit code
    ]}
    led = VerificationLedger.from_blob("run_x", blob)
    assert len(led.records) == 1


def test_ledger_is_bounded():
    led = VerificationLedger("run_x", max_records=5)
    for i in range(20):
        led.record(command_execution_id=f"c{i}", command_class="unit_test", exit_code=0, duration_ms=1)
    assert len(led.records) == 5
    # The most recent survive; the oldest are dropped.
    assert led.records[-1].command_execution_id == "c19"


def test_records_are_bounded_at_default_max():
    led = VerificationLedger("run_x", max_records=MAX_LEDGER_RECORDS)
    assert led._max_records == MAX_LEDGER_RECORDS


# ── marker names the classes ────────────────────────────────────────────────


def test_marker_names_the_possible_classes():
    led = VerificationLedger("run_x")
    out = enforce_answer("All tests pass.", led)
    assert "unit_test" in out.answer or "python_test" in out.answer


def test_verification_record_from_entry_rejects_unknown_class():
    with pytest.raises(ValueError):
        VerificationRecord.from_entry({"commandClass": "bogus", "exitCode": 0})

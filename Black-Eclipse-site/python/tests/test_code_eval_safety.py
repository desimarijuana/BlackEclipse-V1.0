"""Phase 12 G3 — one test per adversarial safety case (§6.4).

Each test asserts BOTH halves: the attack was blocked or contained, AND the
refusal was recorded with its structured code. A block with no record is a
FAILURE — the record is what makes the refusal visible and auditable. The cases
are data (`safety_cases.py`); a new attack is a new row plus a new parameter, never
a rewrite.
"""

from __future__ import annotations

import pytest

from harness.code.eval.safety import run_case
from harness.code.eval.safety_cases import SAFETY_CASES, case as get_case


def _ids():
    return [c.caseId for c in SAFETY_CASES]


def test_there_are_fourteen_cases():
    # Eleven from Phase 12, plus the three Round 3 / W3 edit-guard attacks
    # (S12 never-read, S13 stale-file, S14 ambiguous-match), plus the two
    # Round 3 / W9 isolation attacks (S15 network-enforced, S16
    # shell-env-scrubbed).
    assert len(SAFETY_CASES) == 16


@pytest.mark.parametrize("case_id", _ids())
def test_attack_is_blocked_and_recorded(case_id):
    case = get_case(case_id)
    result = run_case(case)
    # 1. Blocked or contained.
    assert result.blocked, f"{case_id} was NOT blocked: {result.detail}"
    # 2. Recorded with the structured code — a block with no record is a failure.
    assert result.code == case.expectedCode, (
        f"{case_id} recorded {result.code!r}, expected {case.expectedCode!r}"
    )
    assert result.passed, f"{case_id} did not pass: {result.detail}"


def test_s7_forged_claim_is_marked_unverified_with_rate_zero():
    from harness.code.eval import run_code_evaluation

    result = run_code_evaluation()
    # The whole point of Phase 4: an unbacked "tests passed" is marked, and the
    # pack reports falseVerifiedRate exactly 0.0.
    assert result["tasks"].falseVerifiedRate == 0.0
    s7 = next(c for c in result["safety"] if c.caseId == "S7-forged-tests-passed")
    assert s7.passed and s7.code == "UNVERIFIED"


def test_s8_approval_replay_refuses_the_second_use():
    from harness.code.eval.safety import _s8_approval_replay

    result = _s8_approval_replay("S8-approval-replay")
    assert result.passed
    assert "secondRefused=True" in result.detail


def test_s9_body_scope_grants_nothing():
    from harness.code.eval.safety import _s9_cross_tenant

    result = _s9_cross_tenant("S9-cross-tenant-read")
    assert result.passed
    assert "visibleToBeta=False" in result.detail


def test_a_safety_case_without_a_runner_fails_closed():
    from harness.code.eval.safety_cases import SafetyCase
    from harness.code.eval.safety import run_case as rc

    unknown = SafetyCase("S99-not-a-real-case", "x", "y", "NOPE", "z", "m")
    result = rc(unknown)
    assert result.passed is False
    assert result.code is None

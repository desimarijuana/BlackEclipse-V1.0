"""Evidence-gated tool widening: refusals, no self-grant, frozen mechanism."""

from __future__ import annotations

import pytest

from harness.self_improvement.security import (
    RSLTargetError,
    assert_landable_target,
)
from harness.self_improvement.widening import (
    build_widening_case,
    is_case_live,
    withdraw_case,
)


def _meta(**overrides):
    values = {"permission": "read", "risk": "none", "effect": None}
    values.update(overrides)
    return values


def _need(**overrides):
    values = {
        "failureSignature": "sig-timeout-news",
        "namedFailure": "the news read times out on the same query family",
        "existingToolsCannotServe": "no registered tool reads this source",
        "occurrences": 4,
        "distinctSessions": 3,
        "distinctTasks": 2,
        "evidenceRunIds": ["r1", "r2", "r3", "r4", "r5"],
        "derivationRunIds": ["r1", "r2", "r3"],
        "validationRunIds": ["r4", "r5"],
        "derivationTaskIds": ["t1"],
        "validationTaskIds": ["t2"],
        "excludedRunIds": [],
        "evidenceCompletedAt": [
            "2026-01-01T00:00:00Z",
            "2026-01-01T01:00:00Z",
            "2026-01-01T02:00:00Z",
            "2026-01-02T00:00:00Z",
            "2026-01-02T01:00:00Z",
        ],
    }
    values.update(overrides)
    return values


def _replay(**overrides):
    values = {
        "runs": 5,
        "toolWouldHaveFired": 3,
        "passed": 3,
        "criticalRegressions": 0,
        "notNeededControlsPassed": 2,
        "denyPathTested": True,
        "denyPathRefused": True,
        "evidenceFreshness": "fresh",
        "evidenceAgeDays": 1,
        "conclusionDigestsBefore": ["d1", "d2", "d3", "d4", "d5"],
        "conclusionDigestsAfter": ["d1", "d2", "d3", "d4", "d5"],
        "expectedConclusionChanges": [],
    }
    values.update(overrides)
    return values


def _case(**overrides):
    values = {
        "added_tools": ["read_news_source"],
        "base_tools": ["read_price"],
        "registered_tools": ["read_price", "read_news_source"],
        "blocked_tools": [],
        "tool_metadata": {"read_news_source": _meta()},
        "need": _need(),
        "replay": _replay(),
        "scope": "workspace",
        "max_calls_per_day": 20,
        "proposed_at": "2026-01-10T00:00:00Z",
        "evidence_cutoff": "2026-01-05T00:00:00Z",
    }
    values.update(overrides)
    return build_widening_case(**values)


def test_a_complete_case_is_a_package_not_a_grant():
    case = _case()
    assert case["eligible"] is True
    assert case["status"] == "ready_for_operator"
    assert case["granted"] is False
    assert case["requiresOperator"] is True
    assert case["autoApply"] is False
    assert case["selfRenewable"] is False
    assert case["renewalRequiresNewEvidence"] is True
    assert case["expiresAt"] is None


def test_a_financial_action_tool_is_refused_even_if_metadata_says_read():
    case = _case(
        added_tools=["place_order"],
        tool_metadata={"place_order": _meta()},
    )
    assert case["eligible"] is False
    assert "WIDENING_TOOL_OUT_OF_SCOPE:financial_action:place_order" in case["reasons"]


def test_an_effectful_tool_and_an_unknown_tool_are_refused():
    effectful = _case(
        added_tools=["write_notes"],
        tool_metadata={"write_notes": _meta(permission="write")},
    )
    assert "WIDENING_TOOL_OUT_OF_SCOPE:effectful:write_notes" in effectful["reasons"]

    unknown = _case(
        added_tools=["phantom_tool"],
        tool_metadata={"phantom_tool": _meta()},
    )
    assert "WIDENING_TOOL_UNKNOWN:phantom_tool" in unknown["reasons"]


def test_a_blocked_tool_is_structurally_unreachable():
    case = _case(
        added_tools=["read_news_source"],
        blocked_tools=["read_news_source"],
    )
    assert "WIDENING_TOOL_BLOCKED:read_news_source" in case["reasons"]


def test_insufficient_evidence_refuses():
    weak_need = _case(need=_need(distinctSessions=1))
    assert "WIDENING_NEED_TOO_FEW_SESSIONS" in weak_need["reasons"]

    stale = _case(replay=_replay(evidenceFreshness="stale", evidenceAgeDays=30))
    assert "WIDENING_EVIDENCE_STALE" in stale["reasons"]

    no_fire = _case(replay=_replay(toolWouldHaveFired=0, passed=0))
    assert "WIDENING_REPLAY_TOOL_NEVER_FIRED" in no_fire["reasons"]

    no_deny = _case(replay=_replay(denyPathTested=False, denyPathRefused=False))
    assert "WIDENING_DENY_PATH_UNTESTED" in no_deny["reasons"]
    assert "WIDENING_DENY_PATH_FAILED" in no_deny["reasons"]


def test_cherry_picking_and_selection_are_refused():
    same_runs = _case(
        need=_need(validationRunIds=["r1", "r4"]),
    )
    assert "WIDENING_EVIDENCE_NOT_DISJOINT" in same_runs["reasons"]

    excluded = _case(need=_need(excludedRunIds=["r9"]))
    assert "WIDENING_CHERRY_PICK" in excluded["reasons"]


def test_conclusion_drift_is_refused_unless_explained():
    drifted = _case(
        replay=_replay(
            conclusionDigestsAfter=["d1", "d2", "d9", "d4", "d5"],
        ),
    )
    assert "WIDENING_CONCLUSIONS_CHANGED" in drifted["reasons"]

    explained = _case(
        replay=_replay(
            conclusionDigestsAfter=["d1", "d2", "d9", "d4", "d5"],
            expectedConclusionChanges=["d3", "d9"],
        ),
    )
    assert "WIDENING_CONCLUSIONS_CHANGED" not in explained["reasons"]


def test_a_case_cannot_renew_or_expire_itself_into_liveness():
    case = _case()
    assert case["selfRenewable"] is False
    assert case["proposedTtlDays"] <= 14

    expired = dict(case)
    expired["expiresAt"] = "2026-01-01T00:00:00Z"
    assert is_case_live(expired, now="2026-02-01T00:00:00Z") is False
    assert is_case_live(expired) is False
    assert is_case_live(case, now="2026-02-01T00:00:00Z") is True


def test_withdrawal_is_terminal_and_idempotent():
    case = _case()
    withdrawn = withdraw_case(case, reason="operator withdrew", at="2026-01-11T00:00:00Z")
    assert withdrawn["status"] == "withdrawn"
    assert withdrawn["eligible"] is False
    assert withdrawn["granted"] is False
    assert is_case_live(withdrawn) is False

    again = withdraw_case(withdrawn, reason="again", at="2026-01-12T00:00:00Z")
    assert again["status"] == "withdrawn"
    assert again["withdrawnReason"] == "again"


def test_the_widening_mechanism_is_a_frozen_rsl_target():
    for target in (
        "python/harness/self_improvement/widening.py",
        "python/harness/self_improvement/autonomy.py",
        "python/harness/capabilities/builder.py",
        "python/harness/grants.py",
        "python/harness/recovery/envelope.py",
    ):
        with pytest.raises(RSLTargetError) as refused:
            assert_landable_target(target)
        assert refused.value.code == "RSL_FROZEN_TARGET"


def test_the_frozen_denylist_cannot_be_overridden():
    with pytest.raises(TypeError):
        assert_landable_target("python/harness/safe.py", deny_globs=())

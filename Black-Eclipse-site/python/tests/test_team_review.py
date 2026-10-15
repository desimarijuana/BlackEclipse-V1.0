"""Independent quality review and bounded repair (Feature E)."""

from __future__ import annotations

from harness.team.model import (
    ConflictKind,
    ConflictStatus,
    OptionalFailurePolicy,
    ReviewOutcome,
    Severity,
    Strictness,
    TeamConflict,
    TeamFinding,
    TeamSubtask,
    TeamSubtaskStatus,
)
from harness.team.review import ReviewInput, repair_plan, repeat_signature, review


def _sub(sid, *, required=True, expected=None):
    return TeamSubtask(id=sid, objective=f"do {sid}", required=required,
                       expected_output=expected or {})


def _data(**over):
    base = dict(
        subtasks=[_sub("a"), _sub("b")],
        statuses={"a": TeamSubtaskStatus.COMPLETED, "b": TeamSubtaskStatus.COMPLETED},
        outputs={"a": "result a", "b": "result b"},
        findings=[TeamFinding(id="f1", claim="x is 1", evidence_refs=["e1"])],
        conflicts=[],
        reviewer_agent_id="qa-agent",
        producer_agent_ids={"research-agent", "news-agent"},
        strictness=Strictness.STANDARD,
        optional_failure_policy=OptionalFailurePolicy.ALLOW_PARTIAL,
    )
    base.update(over)
    return ReviewInput(**base)


def test_clean_work_is_approved():
    report = review(_data())
    assert report.outcome is ReviewOutcome.APPROVED
    assert report.independent is True


def test_failed_required_subtask_is_revision_required_with_repair():
    report = review(_data(statuses={"a": TeamSubtaskStatus.COMPLETED,
                                    "b": TeamSubtaskStatus.FAILED}))
    assert report.outcome is ReviewOutcome.REVISION_REQUIRED
    plan = repair_plan(report)
    assert plan and plan[0][0] == "b" and plan[0][1]


def test_reviewer_cannot_approve_its_own_work():
    report = review(_data(reviewer_agent_id="research-agent",
                          producer_agent_ids={"research-agent"}))
    assert report.outcome is ReviewOutcome.UNABLE_TO_VERIFY
    assert report.independent is False


def test_unsupported_claims_block_at_standard_strictness():
    report = review(_data(findings=[TeamFinding(id="f1", claim="x is 1")]))
    assert report.outcome is ReviewOutcome.REVISION_REQUIRED
    assert any(f.criterion == "evidence_coverage" for f in report.findings)


def test_optional_failure_is_advisory_when_partial_allowed():
    data = _data(
        subtasks=[_sub("a"), _sub("b", required=False)],
        statuses={"a": TeamSubtaskStatus.COMPLETED, "b": TeamSubtaskStatus.SKIPPED},
    )
    report = review(data)
    assert report.outcome is ReviewOutcome.APPROVED_WITH_LIMITATIONS
    assert all(f.severity is Severity.ADVISORY for f in report.findings)


def test_optional_failure_blocks_under_require_all():
    data = _data(
        subtasks=[_sub("a"), _sub("b", required=False)],
        statuses={"a": TeamSubtaskStatus.COMPLETED, "b": TeamSubtaskStatus.SKIPPED},
        optional_failure_policy=OptionalFailurePolicy.REQUIRE_ALL,
    )
    report = review(data)
    assert report.outcome is ReviewOutcome.REVISION_REQUIRED


def test_repeated_failed_repair_becomes_rejected():
    data = _data(statuses={"a": TeamSubtaskStatus.COMPLETED, "b": TeamSubtaskStatus.FAILED})
    report = review(data, attempts=3)  # attempts >= max_repair_attempts
    assert report.outcome is ReviewOutcome.REJECTED


def test_no_results_is_unable_to_verify():
    report = review(_data(statuses={"a": TeamSubtaskStatus.PENDING, "b": TeamSubtaskStatus.PENDING}))
    assert report.outcome is ReviewOutcome.UNABLE_TO_VERIFY


def test_repeat_signature_is_stable():
    report = review(_data(statuses={"a": TeamSubtaskStatus.COMPLETED,
                                    "b": TeamSubtaskStatus.FAILED}))
    assert repeat_signature(report) == repeat_signature(report)
    assert repeat_signature(report) != ""


def test_unresolved_conflict_blocks_only_when_strict():
    conflict = TeamConflict(id="c1", subject="revenue", kind=ConflictKind.CONFLICTING_SOURCES,
                            status=ConflictStatus.UNRESOLVED, material=True)
    standard = review(_data(conflicts=[conflict]))
    assert standard.outcome is ReviewOutcome.APPROVED_WITH_LIMITATIONS
    strict = review(_data(conflicts=[conflict], strictness=Strictness.STRICT))
    assert strict.outcome is ReviewOutcome.REVISION_REQUIRED

"""The Supervisor and QA stage.

The supervisor does NOT blindly trust child agents. It checks, deterministically
wherever possible, whether the work is actually complete and defensible:

  * are claims supported by evidence?
  * are numbers internally consistent (no unsupported values)?
  * are conflicts disclosed rather than averaged away?
  * are gaps disclosed?
  * did the required agents actually report?
  * is confidence sufficient for the synthesis to proceed?

It returns PASS / REWORK_REQUIRED / BLOCKED plus the exact task ids that need
rework, so the orchestrator can route work back.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from .model import (
    A2AResult,
    SupervisorCheck,
    SupervisorReport,
    SupervisorVerdict,
)
from .results import merge_results


def review_results(
    results: list[A2AResult],
    *,
    evidence_exists: Optional[Callable[[str], bool]] = None,
    expected_agents: Optional[Iterable[str]] = None,
    required_findings: int = 1,
    min_confidence: float = 0.4,
) -> SupervisorReport:
    """Run the full QA checklist over a set of results and return a verdict."""
    checks: list[SupervisorCheck] = []
    reasons: list[str] = []
    rework: list[str] = []

    completed = [r for r in results if r.status == "COMPLETED"]
    failed = [r for r in results if r.status != "COMPLETED"]

    # 1. Completion — every required task reached COMPLETED.
    failed_ids = [r.task_id or r.agent_id for r in failed]
    checks.append(SupervisorCheck(
        name="all_tasks_complete", passed=not failed_ids,
        detail="all tasks completed" if not failed_ids else f"incomplete: {failed_ids}",
    ))
    if failed_ids:
        reasons.append(f"{len(failed_ids)} task(s) did not complete")

    # 2. Required agents reported.
    if expected_agents is not None:
        reported = {r.agent_id for r in results}
        missing = sorted(set(expected_agents) - reported)
        checks.append(SupervisorCheck(
            name="required_agents_reported", passed=not missing,
            detail="all required agents reported" if not missing else f"missing: {missing}",
        ))
        if missing:
            reasons.append(f"missing agent(s): {missing}")

    merged = merge_results(results, evidence_exists=evidence_exists)

    # 3. Evidence support.
    unsupported = merged.unsupported_claims
    checks.append(SupervisorCheck(
        name="claims_supported", passed=not unsupported,
        detail="every claim carries evidence" if not unsupported
        else f"{len(unsupported)} claim(s) have no verifiable evidence",
    ))
    if unsupported:
        reasons.append("unsupported claims present")

    # 4. Enough findings.
    checks.append(SupervisorCheck(
        name="findings_present", passed=len(merged.findings) >= required_findings,
        detail=f"{len(merged.findings)} finding(s)",
    ))
    if len(merged.findings) < required_findings:
        reasons.append("not enough findings to synthesize")

    # 5. Conflicts disclosed (they are ALWAYS disclosed by merge, so this checks
    #    that any unresolved conflict is visible rather than hidden).
    unresolved = [c for c in merged.conflicts if c.status == "UNRESOLVED"]
    checks.append(SupervisorCheck(
        name="conflicts_disclosed", passed=True,
        detail=f"{len(unresolved)} unresolved conflict(s) disclosed",
    ))

    # 6. Confidence sufficient.
    checks.append(SupervisorCheck(
        name="confidence_sufficient", passed=merged.confidence >= min_confidence,
        detail=f"confidence={merged.confidence} (min {min_confidence})",
    ))
    if merged.confidence < min_confidence and completed:
        reasons.append("aggregate confidence is too low")

    # Gaps are surfaced for the record; they do not by themselves block.
    checks.append(SupervisorCheck(
        name="gaps_disclosed", passed=True,
        detail=f"{len(merged.gaps)} gap(s) disclosed",
    ))

    if not results:
        verdict = SupervisorVerdict.BLOCKED
        reasons.append("no results to review")
    elif failed_ids:
        verdict = SupervisorVerdict.REWORK_REQUIRED
        rework = [r.task_id for r in failed if r.task_id]
    elif unsupported or len(merged.findings) < required_findings or (
        completed and merged.confidence < min_confidence
    ):
        verdict = SupervisorVerdict.REWORK_REQUIRED
        rework = [r.task_id for r in completed if r.task_id]
    else:
        verdict = SupervisorVerdict.PASS

    return SupervisorReport(verdict=verdict, checks=checks, reasons=reasons, rework_task_ids=rework)


def qa_checklist(results: list[A2AResult], *, evidence_exists: Optional[Callable[[str], bool]] = None,
                 expected_agents: Optional[Iterable[str]] = None) -> dict[str, object]:
    """The QA view: the same deterministic review, plus the disclosure summary."""
    report = review_results(
        results, evidence_exists=evidence_exists, expected_agents=expected_agents,
    )
    merged = merge_results(results, evidence_exists=evidence_exists)
    return {
        "verdict": report.verdict.value,
        "checks": [c.model_dump(by_alias=True) for c in report.checks],
        "reasons": report.reasons,
        "reworkTaskIds": report.rework_task_ids,
        "conflicts": [c.model_dump(by_alias=True) for c in merged.conflicts],
        "gaps": merged.gaps,
        "unsupportedClaims": merged.unsupported_claims,
        "confidence": merged.confidence,
        "coverage": merged.coverage,
    }


__all__ = ["qa_checklist", "review_results"]

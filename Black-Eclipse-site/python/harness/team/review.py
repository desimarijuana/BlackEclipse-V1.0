"""Independent quality review with bounded repair for a team run.

The reviewer inspects the ACTUAL produced artifacts: each subtask's terminal
status, the run's output, the recorded findings and their evidence, and the
detected conflicts. It returns a structured verdict (APPROVED /
APPROVED_WITH_LIMITATIONS / REVISION_REQUIRED / REJECTED / UNABLE_TO_VERIFY)
carrying severity, evidence references and actionable repair instructions.

Independence is enforced and testable: a reviewer whose agent id is one of the
producers of the work under review cannot approve it — the verdict is
UNABLE_TO_VERIFY. The repair loop is bounded by attempt count and cost, and
detects a repeated unsuccessful repair so it terminates with an explicit failure
or a qualified partial result rather than looping forever.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .model import (
    MAX_REPAIR_ATTEMPTS,
    ConflictStatus,
    OptionalFailurePolicy,
    ReviewFinding,
    ReviewOutcome,
    ReviewReport,
    Severity,
    Strictness,
    TeamConflict,
    TeamFinding,
    TeamSubtask,
    TeamSubtaskStatus,
    new_review_finding_id,
)


@dataclass
class ReviewInput:
    """Everything the reviewer is allowed to inspect (no hidden state)."""

    subtasks: list[TeamSubtask]
    statuses: dict[str, TeamSubtaskStatus]
    outputs: dict[str, str] = field(default_factory=dict)
    findings: list[TeamFinding] = field(default_factory=list)
    conflicts: list[TeamConflict] = field(default_factory=list)
    reviewer_agent_id: str = "qa-agent"
    producer_agent_ids: set[str] = field(default_factory=set)
    strictness: Strictness = Strictness.STANDARD
    optional_failure_policy: OptionalFailurePolicy = OptionalFailurePolicy.ALLOW_PARTIAL
    max_repair_attempts: int = MAX_REPAIR_ATTEMPTS


def _finding(
    *, subtask_id: Optional[str], criterion: str, severity: Severity,
    detail: str, repair: str = "", evidence: Optional[list[str]] = None,
) -> ReviewFinding:
    return ReviewFinding(
        id=new_review_finding_id(), subtask_id=subtask_id, criterion=criterion,
        severity=severity, detail=detail, repair_instruction=repair,
        evidence_refs=list(evidence or []),
    )


def _is_independent(data: ReviewInput) -> bool:
    producers = {p for p in data.producer_agent_ids if p}
    return bool(data.reviewer_agent_id) and data.reviewer_agent_id not in producers


def review(data: ReviewInput, *, attempts: int = 0) -> ReviewReport:
    """Produce a structured verdict over the inspected artifacts."""
    findings: list[ReviewFinding] = []
    notes: list[str] = []
    blocking = 0
    advisory = 0

    independent = _is_independent(data)
    strict = data.strictness in (Strictness.STANDARD, Strictness.STRICT)
    hard = data.strictness is Strictness.STRICT

    if not independent:
        # A producer cannot sign off on its own work when review is required.
        return ReviewReport(
            outcome=ReviewOutcome.UNABLE_TO_VERIFY, independent=False, attempts=attempts,
            reviewer_agent_id=data.reviewer_agent_id,
            notes=["the reviewer is one of the producers; independence could not be established"],
        )

    # ── 1. completeness against the original request ───────────────────────────
    any_terminal_work = False
    for subtask in data.subtasks:
        status = data.statuses.get(subtask.id, TeamSubtaskStatus.PENDING)
        if status in (TeamSubtaskStatus.COMPLETED, TeamSubtaskStatus.FAILED,
                      TeamSubtaskStatus.SKIPPED, TeamSubtaskStatus.CANCELLED):
            any_terminal_work = True
        if status is TeamSubtaskStatus.COMPLETED:
            continue
        if not subtask.required:
            if status in (TeamSubtaskStatus.FAILED, TeamSubtaskStatus.CANCELLED,
                          TeamSubtaskStatus.SKIPPED):
                if data.optional_failure_policy is OptionalFailurePolicy.REQUIRE_ALL:
                    findings.append(_finding(
                        subtask_id=subtask.id, criterion="completeness",
                        severity=Severity.BLOCKING,
                        detail=f"optional subtask {subtask.id!r} did not complete ({status.value})",
                        repair=f"re-run optional subtask {subtask.id!r}",
                    ))
                    blocking += 1
                else:
                    findings.append(_finding(
                        subtask_id=subtask.id, criterion="completeness",
                        severity=Severity.ADVISORY,
                        detail=f"optional subtask {subtask.id!r} did not complete ({status.value})",
                    ))
                    advisory += 1
            continue
        # A required subtask that is not COMPLETED is a blocking defect.
        findings.append(_finding(
            subtask_id=subtask.id, criterion="completeness", severity=Severity.BLOCKING,
            detail=f"required subtask {subtask.id!r} is {status.value}, not COMPLETED",
            repair=f"complete subtask {subtask.id!r}: {subtask.objective[:200]}",
        ))
        blocking += 1

    if not any_terminal_work:
        return ReviewReport(
            outcome=ReviewOutcome.UNABLE_TO_VERIFY, independent=True, attempts=attempts,
            reviewer_agent_id=data.reviewer_agent_id,
            notes=["no subtask produced a result to review"],
        )

    # ── 2. evidence coverage / unsupported claims ───────────────────────────────
    unsupported = [f for f in data.findings if not f.evidence_refs]
    if unsupported:
        severity = Severity.BLOCKING if strict else Severity.ADVISORY
        findings.append(_finding(
            subtask_id=unsupported[0].subtask_id, criterion="evidence_coverage",
            severity=severity,
            detail=f"{len(unsupported)} finding(s) carry no evidence reference",
            repair="attach the source evidence to each unsupported claim or remove it",
        ))
        blocking += severity is Severity.BLOCKING
        advisory += severity is Severity.ADVISORY

    # ── 3. unresolved conflicts ─────────────────────────────────────────────────
    unresolved = [c for c in data.conflicts if c.status is ConflictStatus.UNRESOLVED and c.material]
    if unresolved:
        severity = Severity.BLOCKING if hard else Severity.ADVISORY
        findings.append(_finding(
            subtask_id=None, criterion="conflicts_disclosed", severity=severity,
            detail=f"{len(unresolved)} unresolved material conflict(s): "
                   + ", ".join(c.subject or c.kind.value for c in unresolved)[:500],
            repair="resolve with additional evidence or state the limitation explicitly",
            evidence=[ref for c in unresolved for ref in c.evidence_refs][:20],
        ))
        blocking += severity is Severity.BLOCKING
        advisory += severity is Severity.ADVISORY

    # ── 4. the required output shape ────────────────────────────────────────────
    for subtask in data.subtasks:
        if not subtask.expected_output or data.statuses.get(subtask.id) is not TeamSubtaskStatus.COMPLETED:
            continue
        if not str(data.outputs.get(subtask.id) or "").strip():
            findings.append(_finding(
                subtask_id=subtask.id, criterion="output_schema", severity=Severity.BLOCKING,
                detail=f"subtask {subtask.id!r} produced no output for its expected shape",
                repair=f"produce the expected output: {sorted(subtask.expected_output.keys())}",
            ))
            blocking += 1

    notes.append(
        f"reviewed {len(data.subtasks)} subtasks, {len(data.findings)} findings, "
        f"{len(data.conflicts)} conflicts"
    )

    if blocking:
        outcome = (ReviewOutcome.REVISION_REQUIRED if attempts < data.max_repair_attempts
                   else ReviewOutcome.REJECTED)
    elif advisory:
        outcome = ReviewOutcome.APPROVED_WITH_LIMITATIONS
    else:
        outcome = ReviewOutcome.APPROVED

    return ReviewReport(
        outcome=outcome, findings=findings, reviewer_agent_id=data.reviewer_agent_id,
        independent=True, attempts=attempts, notes=notes,
    )


def repair_plan(report: ReviewReport) -> list[tuple[str, str]]:
    """The (subtask_id, instruction) pairs a repair pass should run, deduped."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for finding in report.findings:
        if finding.severity is not Severity.BLOCKING or not finding.subtask_id:
            continue
        if finding.subtask_id in seen:
            continue
        seen.add(finding.subtask_id)
        out.append((finding.subtask_id, finding.repair_instruction or finding.detail))
    return out


def repeat_signature(report: ReviewReport) -> str:
    """A stable signature of a failing verdict, to detect a repeated no-op repair."""
    parts = sorted(
        f"{f.subtask_id or '-'}:{f.criterion}:{f.detail[:80]}"
        for f in report.findings if f.severity is Severity.BLOCKING
    )
    return "|".join(parts)


__all__ = ["ReviewInput", "repair_plan", "repeat_signature", "review"]

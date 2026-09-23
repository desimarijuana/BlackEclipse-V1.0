"""Response metadata + citations (Phase 4 + workflow-editor interfaces).

Builds the structured, user-facing research metadata a chat/answer surface (and a
future workflow-editor node) can render without reimplementing the engine:

  * supporting citations, assembled ONLY from retrieved evidence,
  * data freshness + temporal status,
  * assumptions, estimates and interpretations,
  * research limitations / missing evidence,
  * unresolved conflicts,
  * calculation inputs.

No URL, source name, evidence id or publication date is ever fabricated: every
field is copied from an actual evidence record or the run's coverage/validation.
The public functions here are the **stable interfaces** future visual-workflow
nodes should call (`build_response_metadata`, `summarize_limitations`).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .claims import ValidationOutcome
from .coverage import CoverageReport
from .mandate import ResearchMandate


class Citation(BaseModel):
    evidenceId: str
    kind: str
    source: Optional[str] = None
    sourceType: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    publishedAt: Optional[str] = None
    retrievedAt: Optional[str] = None
    validationStatus: Optional[str] = None


class ResponseMetadata(BaseModel):
    taskType: str
    status: str
    asOf: Optional[str] = None
    citations: list[Citation] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    estimates: list[str] = Field(default_factory=list)
    interpretations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missingEvidence: list[str] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    calculations: list[dict[str, Any]] = Field(default_factory=list)


def build_citations(evidence: list[Any]) -> list[Citation]:
    """Citations derived strictly from retrieved evidence records."""
    out: list[Citation] = []
    for item in evidence:
        source = getattr(item, "source", None)
        out.append(
            Citation(
                evidenceId=getattr(item, "id", ""),
                kind=getattr(item, "kind", "unknown"),
                source=getattr(source, "source", None),
                sourceType=getattr(source, "sourceType", None),
                url=getattr(source, "url", None),
                title=getattr(source, "title", None),
                publishedAt=getattr(source, "publishedAt", None),
                retrievedAt=getattr(source, "retrievedAt", None),
                validationStatus=getattr(source, "validationStatus", None),
            )
        )
    return out


def summarize_limitations(
    coverage: CoverageReport,
    validation: Optional[ValidationOutcome],
) -> list[str]:
    """Material limitations the answer must disclose (coverage + validation)."""
    limitations: list[str] = []
    for leg in coverage.legs:
        if leg.status == "unavailable":
            limitations.append(f"no evidence retrieved for {leg.metric} {leg.period or ''}".strip())
        elif leg.status == "unknown":
            limitations.append(
                f"metadata incomplete for {leg.metric} {leg.period or ''} ({leg.reason})"
            )
        elif leg.status == "conflicting":
            limitations.append(f"sources disagree on {leg.metric} {leg.period or ''}")
    if validation is not None:
        for claim in validation.claims:
            # Never echo an unsupported claim's text — it may embed a fabricated
            # figure. A `needs_review` claim is shown but explicitly unverified.
            if claim.supportStatus == "unsupported":
                label = claim.kind + (f" for {claim.legId}" if claim.legId else "")
                reason = "; ".join(claim.issues[:2]) if claim.issues else "unsupported"
                limitations.append(f"{label} was not established: {reason}")
            elif claim.supportStatus == "needs_review":
                limitations.append(f"claim needs review (unverified): {claim.text[:120]}")
    seen: set[str] = set()
    out: list[str] = []
    for item in limitations:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:30]


def build_response_metadata(
    mandate: ResearchMandate,
    coverage: CoverageReport,
    evidence: list[Any],
    *,
    validation: Optional[ValidationOutcome] = None,
    conflicts: Optional[list[dict[str, Any]]] = None,
    calculations: Optional[list[Any]] = None,
) -> ResponseMetadata:
    """Assemble the final, renderable research metadata.

    A stable interface: future workflow nodes and the answer surface call this
    rather than re-deriving citations/limitations themselves.
    """
    conflict_rows = []
    for conflict in (conflicts or []):
        conflict_rows.append(
            {
                "metric": conflict.get("metric"),
                "period": conflict.get("period"),
                "candidates": [
                    {
                        "value": c.get("value"),
                        "unit": c.get("unit"),
                        "source": c.get("source"),
                        "sourceType": c.get("sourceType"),
                    }
                    for c in conflict.get("candidates", [])
                ],
            }
        )

    calc_rows = []
    for calc in (calculations or []):
        if hasattr(calc, "to_dict"):
            calc_rows.append(calc.to_dict())

    assumptions: list[str] = []
    estimates: list[str] = []
    interpretations: list[str] = []
    if validation is not None:
        for claim in validation.claims:
            assumptions.extend(claim.assumptions)
            estimates.extend(claim.estimates)
            interpretations.extend(claim.interpretations)

    status = validation.status if validation is not None else coverage.status

    return ResponseMetadata(
        taskType=mandate.taskType,
        status=status,
        asOf=mandate.asOf,
        citations=build_citations(evidence),
        assumptions=sorted(set(assumptions))[:20],
        estimates=sorted(set(estimates))[:20],
        interpretations=sorted(set(interpretations))[:20],
        limitations=summarize_limitations(coverage, validation),
        missingEvidence=[l for l in summarize_limitations(coverage, validation) if l.startswith("no evidence")],
        conflicts=conflict_rows,
        calculations=calc_rows,
    )


__all__ = [
    "Citation",
    "ResponseMetadata",
    "build_citations",
    "summarize_limitations",
    "build_response_metadata",
]

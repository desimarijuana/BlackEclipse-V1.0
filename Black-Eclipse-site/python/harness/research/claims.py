"""Structured claims + deterministic answer validator (Phase 4, Milestone 4).

The model produces structured synthesis: material claims, each with a kind
(`reported_fact`, `derived_fact`, `qualitative_fact`, `interpretation`), the
evidence IDs it cites, and any assumptions/estimates. This module renders prose
from that structure where practical and validates the structure deterministically:

  * every cited evidence ID must exist in THIS run,
  * a `reported_fact` citation must match entity/security, metric, period, basis,
    unit and currency where the mandate established them,
  * a `derived_fact` must reference a registered calculation and its inputs,
  * `unverified` snippets may not be presented as verified facts,
  * conflicts stay visible absent a documented resolution,
  * unknown/unavailable/post-cutoff legs may not be established,
  * the model may not introduce a citation URL absent from retrieved evidence.

ID validation does NOT prove semantic entailment. Where meaning cannot be checked
deterministically the claim is marked `needs_review` and presented as unverified.
The model is never the sole gate; a deterministic check owns the decision.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .coverage import CoverageReport
from .mandate import ResearchMandate

ClaimKind = Literal["reported_fact", "derived_fact", "qualitative_fact", "interpretation"]
SupportStatus = Literal["supported", "needs_review", "unsupported", "stripped", "unverified"]


class Claim(BaseModel):
    text: str
    kind: ClaimKind = "reported_fact"
    evidenceIds: list[str] = Field(default_factory=list)
    legId: Optional[str] = None
    calculationId: Optional[str] = None
    inputEvidenceIds: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    estimates: list[str] = Field(default_factory=list)
    interpretations: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)  # URLs the model asserted
    supportStatus: SupportStatus = "unverified"
    issues: list[str] = Field(default_factory=list)


class ClaimSet(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    estimates: list[str] = Field(default_factory=list)


class Synthesis(BaseModel):
    """The structured part of a model's answer (parsed from JSON)."""

    claims: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    estimates: list[str] = Field(default_factory=list)
    prose: Optional[str] = None


class ValidationOutcome(BaseModel):
    status: Literal["accepted", "partial", "rejected"]
    claims: list[Claim]
    unresolved: list[str] = Field(default_factory=list)
    repaired: bool = False
    repairInstruction: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


def _evidence_index(evidence: list[Any]) -> dict[str, Any]:
    return {getattr(item, "id", ""): item for item in evidence}


def _evidence_urls(evidence: list[Any]) -> set[str]:
    urls: set[str] = set()
    for item in evidence:
        source = getattr(item, "source", None)
        url = getattr(source, "url", None) if source else None
        if url:
            urls.add(str(url).rstrip("/"))
    return urls


def _leg_by_id(mandate: ResearchMandate) -> dict[str, Any]:
    return {leg.id: leg for leg in mandate.factLegs}


def _coverage_by_leg(coverage: CoverageReport) -> dict[str, Any]:
    return {leg.legId: leg for leg in coverage.legs}


def _validate_reported_fact(
    claim: Claim,
    evidence_index: dict[str, Any],
    leg: Any,
    coverage: Any,
    issues: list[str],
) -> None:
    if not claim.evidenceIds:
        issues.append("reported_fact cites no evidence")
        return
    for evidence_id in claim.evidenceIds:
        item = evidence_index.get(evidence_id)
        if item is None:
            issues.append(f"citation {evidence_id!r} does not exist in this run")
            continue
        if getattr(item, "kind", None) == "unverified":
            issues.append(f"citation {evidence_id!r} is unverified and cannot support a reported fact")
    if coverage is not None:
        if coverage.status in ("unknown", "stale"):
            issues.append(f"leg {leg.id if leg else '?'} metadata is unknown/stale — cannot assert as fact")
        elif coverage.status == "unavailable":
            issues.append(f"leg {leg.id if leg else '?'} is unavailable — cannot assert as fact")
        elif coverage.status == "no_matching_period":
            issues.append(f"leg {leg.id if leg else '?'} has no observation for the requested period")
        elif coverage.status == "conflicting":
            issues.append(f"leg {leg.id if leg else '?'} is conflicting — a resolution must be shown")
        # `qualified`: the value is present but a required field is unconfirmed.
        # The claim may be asserted WITH the qualification, which the renderer
        # appends from the coverage reason — it is not an assertion failure.


def _validate_derived_fact(
    claim: Claim,
    evidence_index: dict[str, Any],
    calculations: dict[str, Any],
    issues: list[str],
) -> None:
    if not claim.calculationId:
        issues.append("derived_fact references no registered calculation")
        return
    calc = calculations.get(claim.calculationId)
    if calc is None:
        issues.append(f"calculation {claim.calculationId!r} is not registered in this run")
        return
    for evidence_id in claim.inputEvidenceIds or claim.evidenceIds:
        if evidence_id not in evidence_index:
            issues.append(f"derived input evidence {evidence_id!r} does not exist in this run")
    if getattr(calc, "status", "OK") != "OK":
        issues.append(f"calculation {claim.calculationId!r} did not complete honestly")


def validate_claims(
    mandate: ResearchMandate,
    synthesis: Synthesis,
    evidence: list[Any],
    coverage: CoverageReport,
    *,
    calculations: Optional[list[Any]] = None,
    conflicts: Optional[list[dict[str, Any]]] = None,
) -> ValidationOutcome:
    """Deterministically validate structured claims against this run's evidence.

    Returns an `accepted`/`partial`/`rejected` outcome with per-claim support
    status. A claim that fails is marked `unsupported` (to be stripped/qualified
    by the caller) rather than silently passing.
    """
    evidence_index = _evidence_index(evidence)
    evidence_urls = _evidence_urls(evidence)
    legs = _leg_by_id(mandate)
    coverage_by_leg = _coverage_by_leg(coverage)
    calc_index = {getattr(c, "calculationId", ""): c for c in (calculations or [])}
    conflicts = conflicts or []

    validated: list[Claim] = []
    unresolved: list[str] = []

    for raw in synthesis.claims:
        try:
            claim = Claim(**raw) if not isinstance(raw, Claim) else raw
        except Exception:  # noqa: BLE001 - a malformed claim is unsupported, not trusted
            bad = Claim(text="[malformed claim]", kind="reported_fact",
                        supportStatus="unsupported", issues=["claim payload was malformed"])
            validated.append(bad)
            unresolved.append("a malformed claim was not established")
            continue

        issues: list[str] = []
        leg = legs.get(claim.legId) if claim.legId else None
        cov = coverage_by_leg.get(claim.legId) if claim.legId else None

        if claim.kind == "reported_fact":
            _validate_reported_fact(claim, evidence_index, leg, cov, issues)
        elif claim.kind == "derived_fact":
            _validate_derived_fact(claim, evidence_index, calc_index, issues)
        elif claim.kind in ("qualitative_fact", "interpretation"):
            # Qualitative/interpretation claims may cite web evidence but must not
            # present an unverified snippet as verified; they only need existent IDs.
            for evidence_id in claim.evidenceIds:
                if evidence_id not in evidence_index:
                    issues.append(f"citation {evidence_id!r} does not exist in this run")

        # The model must not introduce a URL absent from retrieved evidence.
        for citation in claim.citations:
            if str(citation).rstrip("/") not in evidence_urls:
                issues.append(f"citation URL {citation!r} is not present in retrieved evidence")

        # A conflict touching a cited leg must remain visible.
        if claim.legId:
            relevant_conflicts = [c for c in conflicts if _conflict_touches(c, leg)]
            if relevant_conflicts and not claim.interpretations:
                issues.append("claim rests on conflicting evidence without disclosing the conflict")

        if issues:
            claim.supportStatus = "unsupported"
            claim.issues = issues
            # Never echo an unsupported claim's text into the answer/gaps: it may
            # embed a fabricated figure. Report the failure, not the claim.
            label = f"{claim.kind} claim"
            if claim.legId:
                label += f" for {claim.legId}"
            unresolved.append(f"{label} was not established: {'; '.join(issues[:3])}")
        elif claim.kind in ("interpretation",):
            # Interpretation is inherently non-deterministic: never claimed verified.
            claim.supportStatus = "needs_review"
        elif not claim.evidenceIds and claim.kind != "interpretation":
            claim.supportStatus = "needs_review"
        else:
            claim.supportStatus = "supported"
        validated.append(claim)

    # A required leg that is not fully covered must surface as a gap. `qualified`
    # is included because an unconfirmed required field must be disclosed even
    # when the value itself is present.
    gaps = list(synthesis.gaps)
    _gap_statuses = {"unavailable", "unknown", "stale", "no_matching_period", "conflicting", "qualified"}
    for leg_cov in coverage.legs:
        if leg_cov.status in _gap_statuses:
            message = f"unmet requirement: {leg_cov.metric} {leg_cov.period or ''} ({leg_cov.status})"
            if message not in gaps:
                gaps.append(message)

    if coverage.status == "rejected":
        # No usable evidence at all → nothing can be established honestly.
        status: Literal["accepted", "partial", "rejected"] = "rejected"
    elif any(c.supportStatus == "unsupported" for c in validated) and not any(
        c.supportStatus == "supported" for c in validated
    ):
        status = "rejected"
    elif unresolved or gaps or coverage.status != "accepted":
        status = "partial"
    else:
        status = "accepted"

    # Unmet coverage requirements are gaps the answer must disclose; surface them
    # in `unresolved` so callers and receipts carry them, not just `gaps`.
    combined_gaps = list(gaps)
    for message in unresolved:
        if message not in combined_gaps:
            combined_gaps.append(message)
    return ValidationOutcome(status=status, claims=validated, unresolved=combined_gaps)


def _conflict_touches(conflict: dict[str, Any], leg: Any) -> bool:
    if leg is None:
        return False
    metric = str(conflict.get("metric") or "").strip().lower()
    if metric != str(leg.metric).strip().lower():
        return False
    if not leg.period:
        return True
    period = str(conflict.get("period") or "").strip().lower()
    req = str(leg.period).strip().lower()
    return (not period) or (req in period) or (period in req)


def render_prose(outcome: ValidationOutcome) -> str:
    """Render validated structure to prose, qualifying unverified material.

    Unsupported claims are not rendered as fact; they are moved to an explicit
    "not established" section. This is the practical path from validated
    structure to a user-facing answer.
    """
    lines: list[str] = []
    supported = [c for c in outcome.claims if c.supportStatus == "supported"]
    review = [c for c in outcome.claims if c.supportStatus == "needs_review"]
    unsupported = [c for c in outcome.claims if c.supportStatus == "unsupported"]

    for claim in supported:
        suffix = " [derived]" if claim.kind == "derived_fact" else ""
        lines.append(f"- {claim.text}{suffix}")
    for claim in review:
        lines.append(f"- {claim.text} (unverified — needs review)")
    if unsupported:
        # Never echo an unsupported claim's text — it may embed a fabricated
        # figure. Report the failure reason and the leg/kind instead.
        lines.append("")
        lines.append("Not established (unsupported claims were removed):")
        for claim in unsupported:
            reason = "; ".join(claim.issues) if claim.issues else "unsupported"
            label = f"{claim.kind}" + (f" for {claim.legId}" if claim.legId else "")
            lines.append(f"- {label} — {reason}")
    if outcome.unresolved:
        lines.append("")
        lines.append("Gaps: " + "; ".join(outcome.unresolved[:6]))
    return "\n".join(lines)


__all__ = [
    "ClaimKind",
    "SupportStatus",
    "Claim",
    "ClaimSet",
    "Synthesis",
    "ValidationOutcome",
    "validate_claims",
    "render_prose",
]

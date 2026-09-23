"""Evidence coverage gate (Phase 4, Milestone 3).

Given a mandate and the evidence actually retrieved, decide — deterministically
and per fact leg — whether the answer can establish that fact:

    covered       usable evidence matches identity, metric, period, basis and
                  unit/currency requirements.
    conflicting   eligible sources disagree without a supported resolution.
    unavailable   retrieval was attempted but no usable evidence exists.
    unknown       evidence exists but required metadata (basis, or publication
                  time for point-in-time work) cannot be established.
    not_applicable excluded by an explicit task rule, with a reason.

Critical rule: successful HTTP/tool execution does NOT equal coverage. A
wrong-period row, a search snippet, a planning response, a stale cache entry, or
an ambiguous identity can never satisfy a numeric leg.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .mandate import FactLeg, ResearchMandate

CoverageStatus = Literal[
    "covered", "conflicting", "unavailable", "unknown", "not_applicable"
]

# Evidence kinds that can satisfy a precise numeric leg. Web snippets and cached
# copies are deliberately excluded — a search result is never a number.
_NUMERIC_KINDS = {"structured", "derived", "filing"}
# Kinds that may support a qualitative leg.
_QUALITATIVE_KINDS = {"web", "filing", "user", "unverified"}


class LegCoverage(BaseModel):
    legId: str
    metric: str
    period: Optional[str] = None
    basis: Optional[str] = None
    status: CoverageStatus
    evidenceIds: list[str] = Field(default_factory=list)
    sourceTiers: list[str] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    reason: Optional[str] = None

    @property
    def satisfied(self) -> bool:
        return self.status in ("covered", "not_applicable")


class CoverageReport(BaseModel):
    status: str  # accepted | partial | rejected
    legs: list[LegCoverage] = Field(default_factory=list)
    coveredCount: int = 0
    missingCount: int = 0
    conflictingCount: int = 0
    unknownCount: int = 0
    warnings: list[str] = Field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.missingCount == 0 and self.conflictingCount == 0


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _period_matches(required: Optional[str], candidate: Optional[str]) -> bool:
    if not required:
        return True  # no period requirement → any period is admissible
    if not candidate:
        return False  # a period was required but the evidence is undated
    req, cand = _norm(required), _norm(candidate)
    if req == cand:
        return True
    # FY2024 should match a "2024" or "2024-Q4"/"FY2024" label and vice versa.
    req_digits = "".join(ch for ch in req if ch.isdigit())
    cand_digits = "".join(ch for ch in cand if ch.isdigit())
    return bool(req_digits and cand_digits and req_digits in cand_digits)


def _basis_matches(required: Optional[str], candidate: Optional[str]) -> bool:
    if not required:
        return True
    return _norm(required) == _norm(candidate)


def _unit_matches(leg: FactLeg, obj: Any) -> bool:
    """Unit/currency compatibility. A required unit/currency must be present and
    match; when none is required, the value is still accepted."""
    if leg.currency:
        if not getattr(obj, "currency", None):
            return False
        if _norm(obj.currency) != _norm(leg.currency):
            return False
    if leg.unit:
        unit = getattr(obj, "unit", None)
        if unit and _norm(unit) != _norm(leg.unit):
            return False
    return True


def _admissible_by_asof(leg: FactLeg, obj: Any, asof: Optional[str]) -> tuple[bool, Optional[str]]:
    """Point-in-time admissibility (Milestone 5).

    When an `asOf` cutoff applies, an observation with a `publishedAt` after the
    cutoff is excluded. An UNKNOWN publication time stays unknown and cannot be
    claimed admissible for strict point-in-time work — it is not silently
    accepted.
    """
    if not asof:
        return True, None
    published = getattr(obj, "publishedAt", None)
    if not published:
        return False, "publication time is unknown; cannot be established before as-of cutoff"
    if str(published) > str(asof):
        return False, f"published {published} after as-of cutoff {asof}"
    return True, None


def _object_matches(leg: FactLeg, obj: Any, asof: Optional[str]) -> tuple[bool, Optional[str]]:
    """Does one normalized object satisfy the leg's identity/metric/period/basis/
    unit requirements?"""
    if _norm(getattr(obj, "name", None)) != _norm(leg.metric):
        return False, "metric differs"
    if not _period_matches(leg.period, getattr(obj, "period", None) or getattr(obj, "dataTimestamp", None)):
        return False, "period differs"
    if not _basis_matches(leg.basis, getattr(obj, "basis", None)):
        return False, "consolidation basis differs"
    if not _unit_matches(leg, obj):
        return False, "unit/currency differs"
    if leg.entitySymbol and getattr(obj, "instrument", None):
        if _norm(obj.instrument) != _norm(leg.entitySymbol):
            return False, "instrument differs"
    return _admissible_by_asof(leg, obj, asof)


def evaluate_leg(
    leg: FactLeg,
    evidence: list[Any],
    *,
    asof: Optional[str] = None,
    conflicts: Optional[list[dict[str, Any]]] = None,
) -> LegCoverage:
    """Classify one leg against the run's evidence items.

    `evidence` is a list of `EvidenceItem`. Each item's objects are checked
    individually; identity, metric, period, basis, unit/currency and as-of must
    all line up for a `covered` verdict.
    """
    conflicts = conflicts or []
    qualitative = leg.metric in ("sentiment", "commentary", "outlook", "narrative")
    admissible_kinds = _QUALITATIVE_KINDS if qualitative else _NUMERIC_KINDS

    matched_ids: list[str] = []
    matched_tiers: list[str] = []
    reasons: list[str] = []
    saw_evidence_for_metric = False
    saw_unknown_metadata = False

    for item in evidence:
        kind = getattr(item, "kind", None)
        if kind not in admissible_kinds:
            continue
        if qualitative:
            matched_ids.append(getattr(item, "id", ""))
            matched_tiers.append(getattr(getattr(item, "source", None), "sourceType", "unknown"))
            continue
        for obj in getattr(item, "objects", []) or []:
            if _norm(getattr(obj, "name", None)) == _norm(leg.metric):
                saw_evidence_for_metric = True
            ok, why = _object_matches(leg, obj, asof)
            if ok:
                matched_ids.append(getattr(item, "id", ""))
                matched_tiers.append(getattr(getattr(item, "source", None), "sourceType", "unknown"))
            else:
                if why and "publication time is unknown" in why or (
                    why and "basis" in (why or "")
                ):
                    saw_unknown_metadata = True
                if why:
                    reasons.append(why)

    if matched_ids:
        # A conflict touching this metric/period makes the leg conflicting rather
        # than cleanly covered, even though evidence exists.
        relevant = [
            c for c in conflicts
            if _norm(c.get("metric")) == _norm(leg.metric)
            and (not leg.period or _period_matches(leg.period, c.get("period")))
        ]
        if relevant:
            return LegCoverage(
                legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
                status="conflicting", evidenceIds=sorted(set(matched_ids)),
                sourceTiers=sorted(set(matched_tiers)), conflicts=relevant,
                reason="eligible sources disagree without a supported resolution",
            )
        return LegCoverage(
            legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
            status="covered", evidenceIds=sorted(set(matched_ids)),
            sourceTiers=sorted(set(matched_tiers)),
        )

    if saw_unknown_metadata:
        return LegCoverage(
            legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
            status="unknown", reason="evidence exists but a required metadata field is unknown",
        )
    if saw_evidence_for_metric:
        return LegCoverage(
            legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
            status="unknown",
            reason="evidence for the metric exists but does not match the required period/basis/identity",
        )
    return LegCoverage(
        legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
        status="unavailable",
        reason="; ".join(sorted(set(reasons))[:3]) or "no usable evidence retrieved for this leg",
    )


def build_coverage(
    mandate: ResearchMandate,
    evidence: list[Any],
    *,
    conflicts: Optional[list[dict[str, Any]]] = None,
) -> CoverageReport:
    """Deterministically classify every required mandate leg.

    `status` is the gate's early verdict: `rejected` when a required leg is
    unavailable and no evidence at all was retrieved, otherwise `partial` when
    anything required is missing/conflicting/unknown, else `accepted`.
    """
    conflicts = conflicts or []
    report = CoverageReport(status="accepted")
    for leg in mandate.factLegs:
        if not leg.required:
            report.legs.append(
                LegCoverage(
                    legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
                    status="not_applicable", reason="leg marked optional by the mandate",
                )
            )
            continue
        leg_coverage = evaluate_leg(leg, evidence, asof=mandate.asOf, conflicts=conflicts)
        report.legs.append(leg_coverage)

    report.coveredCount = sum(1 for l in report.legs if l.status in ("covered", "not_applicable"))
    report.missingCount = sum(1 for l in report.legs if l.status == "unavailable")
    report.conflictingCount = sum(1 for l in report.legs if l.status == "conflicting")
    report.unknownCount = sum(1 for l in report.legs if l.status == "unknown")

    if report.missingCount or report.conflictingCount or report.unknownCount:
        required_legs = [l for l in report.legs if l.status != "not_applicable"]
        if not evidence and required_legs:
            report.status = "rejected"
        else:
            report.status = "partial"
        for leg in report.legs:
            if leg.status in ("unavailable", "conflicting", "unknown"):
                report.warnings.append(f"{leg.metric} {leg.period or ''}: {leg.status} — {leg.reason}")
    return report


__all__ = [
    "CoverageStatus",
    "LegCoverage",
    "CoverageReport",
    "evaluate_leg",
    "build_coverage",
]

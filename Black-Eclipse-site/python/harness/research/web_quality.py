"""Research-quality score (deterministic, explainable, internal).

A single number is dangerous: it invites false precision. This module computes a
quality score that is (a) built only from components already established by the
engine (coverage, source authority, primary coverage, freshness, claim support,
conflict resolution, citation coverage, evidence volume), (b) fully explainable —
every component's raw value, weight and contribution is returned, and (c)
explicitly INTERNAL. It is used to decide whether to research more; it is never
presented to a user as scientific truth.

The output carries the honesty caveat in `disclaimer` on every result.
"""

from __future__ import annotations

from typing import Any

# Component weights sum to 1.0. Each is a judgement call, named, not hidden.
WEIGHTS: dict[str, float] = {
    "sourceAuthority": 0.18,
    "primaryCoverage": 0.14,
    "evidenceCoverage": 0.16,
    "claimSupport": 0.16,
    "freshness": 0.10,
    "conflictResolution": 0.12,
    "citationCoverage": 0.14,
}

_DISCLAIMER = (
    "This score is an INTERNAL research-quality heuristic, not a measure of truth. "
    "It aggregates coverage, source authority, freshness, claim support, conflict resolution "
    "and citation coverage; it must never be presented as scientific or objective."
)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _freshness_component(evidence: list[Any], freshness: str | None) -> float:
    """Fraction of evidence inside the requested freshness window (1.0 when none set)."""
    if not freshness or freshness == "any":
        return 1.0
    from .web_freshness import is_fresh

    if not evidence:
        return 0.0
    fresh = sum(1 for ev in evidence if is_fresh(ev, freshness)[0])
    return fresh / len(evidence)


def compute_quality(
    *,
    coverage: dict[str, Any],
    sources: list[dict[str, Any]],
    evidence: list[Any],
    claims: list[Any],
    conflicts: list[Any],
    citation_report: dict[str, Any],
    freshness: str | None = None,
) -> dict[str, Any]:
    """Compute the composite research-quality score with full attribution.

    All inputs are already-produced engine artifacts; this function adds no I/O and
    makes no judgement the engine has not already made. It only AGGREGATES.
    """
    total_sources = len(sources) or 1
    authority_types = {"official_filing", "government", "regulator", "investor_relations", "academic"}
    primary_sources = sum(1 for s in sources if str(s.get("sourceType")) in authority_types)
    source_authority = _clamp(primary_sources / total_sources)

    unmet = coverage.get("unmet") or []
    primary_required = any("primary sources were required" in str(u) for u in unmet) or primary_sources > 0
    if primary_sources >= 1:
        primary_coverage = 1.0
    elif primary_required:
        primary_coverage = 0.0
    else:
        primary_coverage = 0.5  # neutral when the question did not demand a primary source

    answered = int(coverage.get("answeredQuestions", 0))
    total_q = max(1, int(coverage.get("questionsTotal", 0)))
    evidence_coverage = _clamp(answered / total_q)

    material = [c for c in claims if getattr(c, "kind", None) in ("FACT", "CALCULATION")]
    if material:
        supported = sum(1 for c in material if getattr(c, "status", "") in ("SUPPORTED", "CALCULATED"))
        claim_support = _clamp(supported / len(material))
    else:
        claim_support = 0.0

    freshness_component = _freshness_component(evidence, freshness)

    unresolved_material = [
        c for c in conflicts
        if (getattr(c, "material", True)) and (getattr(c, "status", "") == "UNRESOLVED")
    ]
    if not conflicts:
        conflict_resolution = 1.0
    else:
        conflict_resolution = _clamp(1.0 - (len(unresolved_material) / max(1, len(conflicts))))

    citation_coverage = _clamp(float(citation_report.get("coverage", 0.0)))
    if not citation_report.get("ok", True):
        citation_coverage = _clamp(citation_coverage - 0.25)

    components = {
        "sourceAuthority": source_authority,
        "primaryCoverage": primary_coverage,
        "evidenceCoverage": evidence_coverage,
        "claimSupport": claim_support,
        "freshness": freshness_component,
        "conflictResolution": conflict_resolution,
        "citationCoverage": citation_coverage,
    }
    contributions = {name: round(WEIGHTS[name] * value, 4) for name, value in components.items()}
    score = round(sum(contributions.values()), 4)

    if score >= 0.8:
        band = "HIGH"
    elif score >= 0.6:
        band = "MODERATE"
    elif score >= 0.4:
        band = "WEAK"
    else:
        band = "POOR"

    # The decision the engine actually needs.
    if coverage.get("status") == "COMPLETE" and score >= 0.7:
        verdict = "COMPLETE"
    elif score >= 0.55:
        verdict = "SUFFICIENT"
    else:
        verdict = "NEEDS_MORE_RESEARCH"

    return {
        "score": score,
        "band": band,
        "verdict": verdict,
        "components": {k: round(v, 4) for k, v in components.items()},
        "weights": dict(WEIGHTS),
        "contributions": contributions,
        "raw": {
            "primarySources": primary_sources,
            "totalSources": len(sources),
            "answeredQuestions": answered,
            "questionsTotal": total_q,
            "materialClaims": len(material),
            "conflicts": len(conflicts),
            "unresolvedMaterialConflicts": len(unresolved_material),
        },
        "disclaimer": _DISCLAIMER,
    }


__all__ = ["WEIGHTS", "compute_quality"]

"""Verification: source comparison, conflict detection, claim verification, citations.

The model never decides truth here. Given evidence and claims, this module
deterministically:

  * compares sources over numbers/dates/periods/basis/authority/freshness,
  * detects and classifies conflicts (resolved/explained/unresolved; material),
  * verifies claims against the evidence they cite (support level + reason),
  * generates citations (claim → evidence → source → location) and validates them.

A difference is never silently averaged away: the engine names whether it comes
from a reported period, currency, GAAP/non-GAAP basis, estimate-vs-reported,
revision, stale data or a genuine conflict.
"""

from __future__ import annotations

from typing import Any, Optional

from .web_contracts import Citation, Claim, Evidence, SourceConflict, SourceType
from .web_freshness import is_admissible_at, is_fresh
from .web_sources import classify_source_type

_NUMERIC_TOLERANCE = 0.005  # 0.5% relative

# Source types that count as primary for support strength.
_PRIMARY = (
    SourceType.OFFICIAL_FILING,
    SourceType.GOVERNMENT,
    SourceType.REGULATOR,
    SourceType.INVESTOR_RELATIONS,
)


def _num(value: Any) -> Optional[float]:
    try:
        if isinstance(value, bool):
            return None
        return float(str(value).replace(",", "").replace("$", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def compare_values(a: Any, b: Any, *, tolerance: float = _NUMERIC_TOLERANCE) -> dict[str, Any]:
    """Compare two values. Returns agreement + the likely cause of any difference."""
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None:
        denom = max(abs(na), abs(nb), 1e-9)
        rel = abs(na - nb) / denom
        if rel <= tolerance:
            return {"agree": True, "relativeDiff": round(rel, 6), "cause": None}
        cause = "estimate_vs_reported" if (na < 0) != (nb < 0) else "value_difference"
        return {"agree": False, "relativeDiff": round(rel, 6), "cause": cause}
    same = str(a).strip().lower() == str(b).strip().lower()
    return {"agree": same, "relativeDiff": None, "cause": None if same else "different_text"}


def compare_sources(a: Evidence, b: Evidence, *, tolerance: float = _NUMERIC_TOLERANCE) -> dict[str, Any]:
    """Compare two evidence items over the axes that matter for a financial fact."""
    result: dict[str, Any] = {"evidenceA": a.evidenceId, "evidenceB": b.evidenceId}
    result["value"] = compare_values(a.structuredValue, b.structuredValue, tolerance=tolerance)
    result["samePeriod"] = (a.period or "") == (b.period or "")
    result["sameCurrency"] = (a.unit or "") == (b.unit or "")
    result["sameBasis"] = (a.provenance.get("basis") if isinstance(a.provenance, dict) else None) == (
        b.provenance.get("basis") if isinstance(b.provenance, dict) else None
    )
    result["sameSourceType"] = a.sourceType == b.sourceType
    result["sameEntity"] = (a.entityId or "") == (b.entityId or "")
    result["authority"] = {
        "a": getattr(a.sourceType, "value", a.sourceType),
        "b": getattr(b.sourceType, "value", b.sourceType),
    }
    return result


def _cause_for_pair(a: Evidence, b: Evidence, value_cmp: dict[str, Any]) -> Optional[str]:
    """Explain why two figures differ, when a benign cause exists."""
    if a.period and b.period and a.period != b.period:
        return "different reporting period"
    if (a.unit or "") != (b.unit or ""):
        return "different currency/unit"
    basis_a = a.provenance.get("basis") if isinstance(a.provenance, dict) else None
    basis_b = b.provenance.get("basis") if isinstance(b.provenance, dict) else None
    if basis_a != basis_b and (basis_a or basis_b):
        return "different accounting basis (GAAP vs non-GAAP / consolidated vs standalone)"
    if value_cmp.get("cause") == "estimate_vs_reported":
        return "estimate versus reported figure"
    # A revision: same period + same source family but different known_at.
    if a.sourceId == b.sourceId and a.knownAt and b.knownAt and a.knownAt != b.knownAt:
        return "a later revision of the same source"
    return None


def detect_conflicts(
    evidence: list[Evidence],
    *,
    tolerance: float = _NUMERIC_TOLERANCE,
    research_id: str = "",
) -> list[SourceConflict]:
    """Group evidence by (metric, period) and classify any disagreement."""
    groups: dict[tuple[str, str], list[Evidence]] = {}
    for item in evidence:
        if item.structuredValue is None:
            continue
        metric = str(item.claimText or item.provenance.get("metric") or "").strip().lower()
        if not metric:
            continue
        key = (metric, str(item.period or ""))
        groups.setdefault(key, []).append(item)

    conflicts: list[SourceConflict] = []
    for (metric, period), items in groups.items():
        if len(items) < 2:
            continue
        # Find any disagreeing pair.
        disagreeing: list[tuple[Evidence, Evidence, dict[str, Any]]] = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                cmp = compare_values(items[i].structuredValue, items[j].structuredValue, tolerance=tolerance)
                if not cmp["agree"]:
                    disagreeing.append((items[i], items[j], cmp))
        if not disagreeing:
            continue
        causes = {_cause_for_pair(a, b, c) for a, b, c in disagreeing}
        causes.discard(None)
        candidates = [
            {
                "value": it.structuredValue,
                "unit": it.unit,
                "period": it.period,
                "source": it.publisher or it.sourceUrl,
                "sourceType": getattr(it.sourceType, "value", it.sourceType),
                "evidenceId": it.evidenceId,
            }
            for it in items
        ]
        if causes:
            status = "EXPLAINED"
            explanation = "; ".join(sorted(causes))
            material = False
        else:
            status = "UNRESOLVED"
            explanation = None
            material = True
        conflicts.append(
            SourceConflict(
                metric=metric,
                period=period or None,
                candidates=candidates,
                status=status,
                material=material,
                explanation=explanation,
            )
        )
    return conflicts


def _evidence_metric(ev: Evidence) -> str:
    if isinstance(ev.provenance, dict) and ev.provenance.get("metric"):
        return str(ev.provenance["metric"]).strip().lower()
    return str(ev.claimText or "").strip().lower()


def verify_claim(
    claim: Claim,
    evidence_by_id: dict[str, Evidence],
    *,
    conflicts: Optional[list[SourceConflict]] = None,
    as_of: Optional[str] = None,
    freshness: Optional[str] = None,
) -> Claim:
    """Deterministically verify one claim against the evidence it cites.

    Returns the claim with a `status`, `confidence` and explanatory `issues`.
    Weak evidence is never silently upgraded: a claim with no evidence is
    UNSUPPORTED; a claim whose only support is stale is OUTDATED; a claim touching
    an unresolved material conflict is CONTRADICTED unless it discloses the tie.
    """
    conflicts = conflicts or []
    issues: list[str] = []

    if claim.calculationId:
        claim.status = "CALCULATED"
        claim.confidence = 0.9
        return claim

    if not claim.evidenceIds:
        claim.status = "UNSUPPORTED"
        claim.confidence = 0.0
        claim.issues = ["no evidence is cited for this claim"]
        return claim

    present: list[Evidence] = []
    for eid in claim.evidenceIds:
        ev = evidence_by_id.get(eid)
        if ev is None:
            issues.append(f"cited evidence {eid!r} does not exist in this run")
            continue
        present.append(ev)

    if not present:
        claim.status = "UNSUPPORTED"
        claim.confidence = 0.0
        claim.issues = issues or ["no cited evidence exists in this run"]
        return claim

    # Point-in-time + freshness.
    admissible: list[Evidence] = []
    for ev in present:
        ok_pt, why_pt = is_admissible_at(ev, as_of)
        if not ok_pt:
            issues.append(f"evidence {ev.evidenceId} is not admissible at the cutoff: {why_pt}")
            continue
        ok_fresh, why_fresh = is_fresh(ev, freshness)
        if not ok_fresh:
            issues.append(f"evidence {ev.evidenceId} is stale: {why_fresh}")
            continue
        admissible.append(ev)

    if not admissible:
        # Every citation was stale or inadmissible.
        claim.status = "OUTDATED" if any("stale" in i for i in issues) else "UNSUPPORTED"
        claim.confidence = 0.0
        claim.issues = issues
        return claim

    # Conflict check: a material, unresolved conflict over the same metric makes
    # the claim CONTRADICTED unless it already names the disagreement.
    metric = _evidence_metric(admissible[0])
    metric_conflicts = [
        c for c in conflicts
        if c.metric == metric and (not c.period or not admissible[0].period or c.period == admissible[0].period)
    ]
    unresolved = [c for c in metric_conflicts if c.status == "UNRESOLVED" and c.material]
    if unresolved:
        claim.status = "CONTRADICTED"
        claim.confidence = 0.2
        claim.issues = issues + [
            f"sources disagree on {metric!r} without a supported resolution"
        ]
        return claim

    # Support strength: independent sources, primary preference, agreement.
    distinct_sources = {ev.sourceId for ev in admissible}
    has_primary = any(ev.sourceType in _PRIMARY for ev in admissible)
    if len(distinct_sources) >= 2:
        claim.status = "SUPPORTED"
        claim.confidence = 0.9 if has_primary else 0.75
    else:
        claim.status = "PARTIALLY_SUPPORTED"
        claim.confidence = 0.6 if has_primary else 0.45

    # A value that cannot be reproduced from the evidence text is ambiguous.
    if any(ev.contentTrust != "UNTRUSTED" for ev in admissible):
        issues.append("evidence trust marker was not UNTRUSTED; ignored")
    basis = admissible[0].provenance.get("basis") if isinstance(admissible[0].provenance, dict) else None
    if admissible[0].structuredValue is not None and not basis:
        claim.status = "AMBIGUOUS" if claim.status == "SUPPORTED" else claim.status
        issues.append("the accounting basis of the supporting value is unconfirmed")

    claim.issues = issues
    return claim


def build_citations(
    claims: list[Claim],
    evidence_by_id: dict[str, Evidence],
    *,
    research_id: str = "",
) -> list[Citation]:
    """Build citations claim → evidence → source → location. Never fabricates.

    Citation ids are namespaced by `researchId` so two runs never collide in the
    store (the same evidence/claim shapes recur across runs).
    """
    prefix = f"{research_id}_" if research_id else ""
    citations: list[Citation] = []
    for idx, claim in enumerate(claims):
        for ev_id in claim.evidenceIds:
            ev = evidence_by_id.get(ev_id)
            if ev is None:
                continue
            locator = None
            if ev.page is not None:
                locator = f"page {ev.page}"
            if ev.section:
                locator = f"{locator + ', ' if locator else ''}{ev.section}"
            citations.append(
                Citation(
                    citationId=f"{prefix}cit_{idx}_{ev_id}",
                    claimText=claim.text,
                    evidenceId=ev_id,
                    sourceUrl=ev.sourceUrl,
                    title=(ev.provenance.get("title") if isinstance(ev.provenance, dict) else None),
                    section=ev.section,
                    page=ev.page,
                    retrievedAt=ev.retrievedAt,
                    publishedAt=ev.publishedAt,
                    locator=locator,
                )
            )
    return citations


def validate_citations(
    claims: list[Claim],
    citations: list[Citation],
    evidence_by_id: dict[str, Evidence],
    *,
    as_of: Optional[str] = None,
    freshness: Optional[str] = None,
    require_citations: bool = True,
) -> dict[str, Any]:
    """Validate that every material claim is traceable and its citation is honest.

    Returns `{"ok": bool, "issues": [...], "coverage": float}`. A citation pointing
    at non-existent evidence, or a material claim with no citation, is an issue.
    """
    issues: list[str] = []
    cited_claims = {c.claimText for c in citations if c.evidenceId in evidence_by_id}
    material = [c for c in claims if c.kind in ("FACT", "CALCULATION")]
    for claim in material:
        if claim.status in ("UNSUPPORTED", "CONTRADICTED", "OUTDATED"):
            continue
        if claim.text not in cited_claims:
            if require_citations:
                issues.append(f"material claim has no citation: {claim.text[:80]}")
    for c in citations:
        ev = evidence_by_id.get(c.evidenceId)
        if ev is None:
            issues.append(f"citation {c.citationId} points at non-existent evidence {c.evidenceId!r}")
            continue
        if c.sourceUrl != ev.sourceUrl:
            issues.append(f"citation {c.citationId} URL does not match its evidence")
        ok_pt, why = is_admissible_at(ev, as_of)
        if not ok_pt:
            issues.append(f"citation {c.citationId} fails point-in-time check: {why}")
        ok_fresh, why_f = is_fresh(ev, freshness)
        if not ok_fresh:
            issues.append(f"citation {c.citationId} is outside the freshness window: {why_f}")
    total = len(material) or 1
    covered = sum(1 for c in material if c.text in cited_claims)
    return {"ok": not issues, "issues": issues, "coverage": round(covered / total, 4)}


__all__ = [
    "compare_values",
    "compare_sources",
    "detect_conflicts",
    "verify_claim",
    "build_citations",
    "validate_citations",
]

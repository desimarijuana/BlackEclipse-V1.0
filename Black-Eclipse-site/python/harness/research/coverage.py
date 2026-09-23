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
from .periods import periods_match

CoverageStatus = Literal[
    "covered", "qualified", "conflicting", "unavailable", "unknown", "not_applicable",
    "no_matching_period", "stale",
]

# A status whose value may be presented (with disclosure for `qualified`).
_PRESENTABLE = {"covered", "qualified", "not_applicable"}

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
        """True when the leg's value may be presented (fully or qualified)."""
        return self.status in _PRESENTABLE


class CoverageReport(BaseModel):
    status: str  # accepted | partial | rejected
    legs: list[LegCoverage] = Field(default_factory=list)
    coveredCount: int = 0
    qualifiedCount: int = 0
    missingCount: int = 0
    conflictingCount: int = 0
    unknownCount: int = 0
    periodMissCount: int = 0
    warnings: list[str] = Field(default_factory=list)

    @property
    def complete(self) -> bool:
        return (
            self.missingCount == 0
            and self.conflictingCount == 0
            and self.unknownCount == 0
            and self.qualifiedCount == 0
        )


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _period_matches(required: Optional[str], candidate: Optional[str], *, from_timestamp: bool = False) -> bool:
    """Canonical period match. See `periods.periods_match`."""
    return periods_match(required, candidate, candidate_is_timestamp=from_timestamp)


def _basis_matches(required: Optional[str], candidate: Optional[str]) -> tuple[bool, Optional[str]]:
    """A required basis must be present and match.

    A *missing* basis is a QUALIFYING gap, not a hard mismatch: the issuer-
    reported number is still valid, but the basis cannot be confirmed. A basis
    that is present but different is a hard mismatch. The caller maps the
    missing case to `qualified`, never to `covered`.
    """
    if not required:
        return True, None
    if not candidate:
        return False, "required consolidation basis is missing from the evidence"
    if _norm(required) != _norm(candidate):
        return False, "consolidation basis differs"
    return True, None


def _currency_matches(leg: FactLeg, obj: Any) -> tuple[bool, Optional[str]]:
    """A required currency must be present AND match. Missing → unknown."""
    if not leg.currency:
        return True, None
    currency = getattr(obj, "currency", None)
    if not currency:
        return False, "required currency is missing from the evidence"
    if _norm(currency) != _norm(leg.currency):
        return False, "currency differs"
    return True, None


def _unit_matches(leg: FactLeg, obj: Any) -> tuple[bool, Optional[str]]:
    """A required unit must be present AND match. Missing → unknown.

    The previous behaviour let an absent unit pass; per the hardening brief a
    required unit that the evidence omits is `unknown`, never covered.
    """
    if not leg.unit:
        return True, None
    unit = getattr(obj, "unit", None)
    if not unit:
        return False, "required unit is missing from the evidence"
    if _norm(unit) != _norm(leg.unit):
        return False, "unit differs"
    return True, None


def _identity_matches(leg: FactLeg, obj: Any) -> tuple[bool, Optional[str]]:
    """A required instrument must be present and match on the strongest fields.

    Compares canonical identity (market+symbol), then market, then symbol using
    whichever fields the observation actually supplies. A leg requiring an
    instrument is NOT covered by an observation with no instrument at all —
    missing identity is `unknown`, never a wildcard.
    """
    if not leg.entitySymbol:
        return True, None

    obj_identity = getattr(obj, "identity", None)
    obj_market = _norm(getattr(obj_identity, "market", None)) if obj_identity else ""
    obj_canon_symbol = _norm(getattr(obj_identity, "symbol", None)) if obj_identity else ""
    obj_instrument = _norm(getattr(obj, "instrument", None))
    req_symbol = _norm(leg.entitySymbol)
    req_market = _norm(leg.market)

    # Canonical identity (market + symbol) is the strongest signal when present.
    if obj_canon_symbol:
        if obj_canon_symbol != req_symbol:
            return False, "canonical symbol differs"
        if req_market and obj_market and obj_market != req_market:
            return False, "canonical market differs"
        return True, None

    if not obj_instrument:
        return False, "required instrument identity is missing from the evidence"
    if obj_instrument != req_symbol:
        return False, "instrument differs"
    if req_market and obj_market and obj_market != req_market:
        return False, "instrument market differs"
    return True, None


def _published_at(obj: Any, item: Any) -> Optional[str]:
    """Publication time for an observation: object-level, else source-level."""
    published = getattr(obj, "publishedAt", None)
    if published:
        return str(published)
    source = getattr(item, "source", None)
    source_published = getattr(source, "publishedAt", None) if source else None
    return str(source_published) if source_published else None


def _admissible_by_asof(obj: Any, item: Any, asof: Optional[str]) -> tuple[bool, Optional[str]]:
    """Point-in-time admissibility (Milestone 5).

    When an `asOf` cutoff applies, an observation with a `publishedAt` after the
    cutoff is excluded. An UNKNOWN publication time stays unknown and cannot be
    claimed admissible for strict point-in-time work — it is not silently
    accepted.
    """
    if not asof:
        return True, None
    published = _published_at(obj, item)
    if not published:
        return False, "publication time is unknown; cannot be established before as-of cutoff"
    if str(published) > str(asof):
        return False, f"published {published} after as-of cutoff {asof}"
    return True, None


class MatchOutcome:
    """Result of matching one object to a leg."""

    MATCH = "match"           # fully satisfies the leg
    QUALIFIED = "qualified"   # value valid; a non-blocking required field is missing
    PERIOD = "no_matching_period"
    OTHER = "miss"


def _object_matches(leg: FactLeg, obj: Any, item: Any, asof: Optional[str]) -> tuple[str, Optional[str]]:
    """Classify one normalized object against the leg.

    Returns `(outcome, reason)` where outcome is one of MatchOutcome. A
    `QUALIFIED` outcome means the reported value itself is valid (metric, period,
    identity and currency line up) but a required non-blocking field — the
    consolidation basis, or a required unit — is absent, so the value may be
    presented with an explicit qualification. A present-but-different value is a
    hard `miss`, never qualified.
    """
    if _norm(getattr(obj, "name", None)) != _norm(leg.metric):
        return MatchOutcome.OTHER, "metric differs"

    explicit_period = getattr(obj, "period", None)
    if explicit_period:
        period_ok = _period_matches(leg.period, explicit_period)
    else:
        # No explicit fiscal label: a data timestamp may satisfy an annual/quarter
        # leg only when it falls inside that period (never a cross-match).
        period_ok = _period_matches(
            leg.period, getattr(obj, "dataTimestamp", None), from_timestamp=True
        )
    if not period_ok:
        return MatchOutcome.PERIOD, "no observation matches the requested fiscal period"

    # Identity and currency are blocking: an unconfirmed entity or currency
    # cannot be presented as a measured fact.
    identity_ok, identity_why = _identity_matches(leg, obj)
    if not identity_ok:
        return MatchOutcome.OTHER, identity_why
    currency_ok, currency_why = _currency_matches(leg, obj)
    if not currency_ok:
        return MatchOutcome.OTHER, currency_why

    # Basis and unit are qualifying: a missing value is disclosed, not fatal.
    basis_ok, basis_why = _basis_matches(leg.basis, getattr(obj, "basis", None))
    if not basis_ok and "differs" in (basis_why or ""):
        return MatchOutcome.OTHER, basis_why
    unit_ok, unit_why = _unit_matches(leg, obj)
    if not unit_ok and "differs" in (unit_why or ""):
        return MatchOutcome.OTHER, unit_why

    admitted, asof_why = _admissible_by_asof(obj, item, asof)
    if not admitted:
        return MatchOutcome.OTHER, asof_why

    if not basis_ok or not unit_ok:
        detail = basis_why or unit_why
        return MatchOutcome.QUALIFIED, detail

    return MatchOutcome.MATCH, None


def evaluate_leg(
    leg: FactLeg,
    evidence: list[Any],
    *,
    asof: Optional[str] = None,
    conflicts: Optional[list[dict[str, Any]]] = None,
) -> LegCoverage:
    """Classify one leg against the run's evidence items.

    Distinct statuses are preserved so the user explanation is precise:
    `covered`, `qualified` (value valid, a required field is unconfirmed),
    `conflicting`, `no_matching_period`, `stale`, `unavailable`, `unknown`.
    """
    conflicts = conflicts or []
    qualitative = leg.metric in ("sentiment", "commentary", "outlook", "narrative")
    admissible_kinds = _QUALITATIVE_KINDS if qualitative else _NUMERIC_KINDS

    matched_ids: list[str] = []
    qualified_ids: list[str] = []
    matched_tiers: list[str] = []
    qualified_reasons: list[str] = []
    reasons: list[str] = []
    saw_evidence_for_metric = False
    saw_period_mismatch = False
    saw_stale = False

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
            outcome, why = _object_matches(leg, obj, item, asof)
            tier = getattr(getattr(item, "source", None), "sourceType", "unknown")
            if outcome == MatchOutcome.MATCH:
                matched_ids.append(getattr(item, "id", ""))
                matched_tiers.append(tier)
            elif outcome == MatchOutcome.QUALIFIED:
                qualified_ids.append(getattr(item, "id", ""))
                matched_tiers.append(tier)
                if why:
                    qualified_reasons.append(why)
            else:
                if outcome == MatchOutcome.PERIOD:
                    saw_period_mismatch = True
                if why and "stale" in why.lower():
                    saw_stale = True
                if why:
                    reasons.append(why)

    present_ids = sorted(set(matched_ids + qualified_ids))
    if matched_ids or qualified_ids:
        relevant = [
            c for c in conflicts
            if _norm(c.get("metric")) == _norm(leg.metric)
            and (not leg.period or _period_matches(leg.period, c.get("period")))
        ]
        if relevant:
            return LegCoverage(
                legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
                status="conflicting", evidenceIds=present_ids,
                sourceTiers=sorted(set(matched_tiers)), conflicts=relevant,
                reason="eligible sources disagree without a supported resolution",
            )
        if matched_ids:
            return LegCoverage(
                legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
                status="covered", evidenceIds=sorted(set(matched_ids)),
                sourceTiers=sorted(set(matched_tiers)),
            )
        # Only qualified matches: the value is present but a required field is
        # unconfirmed. Present it with a precise qualification.
        detail = "; ".join(sorted(set(r for r in qualified_reasons if r))[:2])
        return LegCoverage(
            legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
            status="qualified", evidenceIds=present_ids,
            sourceTiers=sorted(set(matched_tiers)),
            reason=f"value present but a required field is unconfirmed: {detail}",
        )

    if saw_period_mismatch:
        return LegCoverage(
            legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
            status="no_matching_period",
            reason=f"evidence exists for {leg.metric} but no observation matches {leg.period or 'the requested period'}",
        )
    if saw_stale:
        return LegCoverage(
            legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
            status="stale", reason="the only matching observation is stale",
        )
    if saw_evidence_for_metric:
        return LegCoverage(
            legId=leg.id, metric=leg.metric, period=leg.period, basis=leg.basis,
            status="unknown",
            reason="evidence for the metric exists but does not match the required identity/period/currency",
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

    report.coveredCount = sum(1 for l in report.legs if l.status == "covered")
    report.qualifiedCount = sum(1 for l in report.legs if l.status == "qualified")
    report.missingCount = sum(1 for l in report.legs if l.status == "unavailable")
    report.conflictingCount = sum(1 for l in report.legs if l.status == "conflicting")
    report.unknownCount = sum(1 for l in report.legs if l.status in ("unknown", "stale"))
    report.periodMissCount = sum(1 for l in report.legs if l.status == "no_matching_period")

    unmet = (
        report.missingCount + report.conflictingCount + report.unknownCount
        + report.periodMissCount + report.qualifiedCount
    )
    if unmet:
        required_legs = [l for l in report.legs if l.status != "not_applicable"]
        if not evidence and required_legs:
            report.status = "rejected"
        else:
            report.status = "partial"
        for leg in report.legs:
            if leg.status in ("unavailable", "conflicting", "unknown", "stale", "no_matching_period", "qualified"):
                report.warnings.append(f"{leg.metric} {leg.period or ''}: {leg.status} — {leg.reason}")
    return report


__all__ = [
    "CoverageStatus",
    "LegCoverage",
    "CoverageReport",
    "evaluate_leg",
    "build_coverage",
]

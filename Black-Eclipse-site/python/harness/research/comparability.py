"""Identity and comparability gate (Phase 7 hardening, WS6).

A percentage change is only meaningful when its two legs are the SAME fact for
the SAME entity over a comparable span. Before this, nothing deterministically
refused a change computed across, e.g., a nine-month base and a twelve-month
current period, a standalone figure against a consolidated one, gross revenue
against revenue from operations, or the pre-/post-demerger entity behind a reused
ticker. The model was the only place those distinctions lived — and a model is
not a validator.

This module is the deterministic gate. It takes per-leg descriptors and returns,
per candidate comparison:

  * `compatible`  — the legs may be differenced/ratioed;
  * `blocked`     — they may NOT, with the EXACT reason, so the answer can present
                    each verified fact separately and name the blocked comparison.

It never fabricates a value and never "repairs" a mismatch. Every rule is a data
row so a new comparability dimension is added in one place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .periods import parse_period, periods_match

# Dimensions that MUST match for two legs to be comparable. Order is the order
# reasons are emitted, for deterministic messages.
# Order matters: a MORE SPECIFIC mismatch (restatement/basis/scale) is diagnosed
# before the generic "these are the same period" check, so the reason names the
# real incompatibility. The identical-period check runs last.
_DIMENSIONS = (
    "entity",
    "security",
    "restatement",
    "duration",
    "metric",
    "basis",
    "currency",
    "unit",
    "scale",
    "period",
)


@dataclass
class LegDescriptor:
    """Everything needed to decide whether a leg may be compared with another.

    Every field is optional: an unknown dimension is NEVER treated as matching.
    A comparison whose required dimension is unknown is BLOCKED as unverified,
    not silently allowed (the pre-hardening behaviour).
    """

    legId: str
    metric: Optional[str] = None
    period: Optional[str] = None
    # Explicit reported span in months when the source states one (9, 12). Used
    # to catch a nine-month base presented beside a twelve-month current period.
    durationMonths: Optional[int] = None
    basis: Optional[str] = None            # consolidated | standalone
    currency: Optional[str] = None
    unit: Optional[str] = None             # e.g. "%", "per-share"
    scale: Optional[int] = None            # 1, 1000, 1_000_000 (reporting scale)
    # Entity identity. `legalName` + market + symbol pin the issuer; `tickerReused`
    # flags a symbol that now names a DIFFERENT legal issuer (demerger/rename).
    symbol: Optional[str] = None
    market: Optional[str] = None
    exchange: Optional[str] = None
    legalName: Optional[str] = None
    tickerReused: bool = False
    # Restatement/version provenance, when the source exposes it.
    versionId: Optional[str] = None
    documentId: Optional[str] = None
    # Raw evidence ids backing this descriptor (for the receipt).
    evidenceIds: list[str] = field(default_factory=list)


@dataclass
class BlockedComparison:
    legs: tuple[str, str]
    reason: str
    dimension: str


@dataclass
class ComparabilityVerdict:
    compatible: list[tuple[str, str]] = field(default_factory=list)
    blocked: list[BlockedComparison] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blocked

    def blockedMessages(self) -> list[str]:
        return [
            f"comparison blocked: {b.legs[0]} vs {b.legs[1]} — {b.reason}"
            for b in self.blocked
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "compatible": [list(pair) for pair in self.compatible],
            "blocked": [
                {"legs": list(b.legs), "dimension": b.dimension, "reason": b.reason}
                for b in self.blocked
            ],
        }


# ── Duration parsing ─────────────────────────────────────────────────────────

_DURATION_PATTERNS = (
    (re.compile(r"\b(fy|annual|full[- ]year|12[- ]?year)\b", re.I), 12),
    (re.compile(r"\b(h1|half[- ]?year|six[- ]?month|6[- ]?month|first half|second half)\b", re.I), 6),
    (re.compile(r"\b(nine[- ]?month|9[- ]?month|9m|three[- ]?quarter)\b", re.I), 9),
    (re.compile(r"\b(q[1-4]|quarter|3[- ]?month|three[- ]?month)\b", re.I), 3),
)


def parse_duration_months(period: Optional[str], explicit: Optional[int] = None) -> Optional[int]:
    """Reported span in months for a period label, or the explicit value.

    A plain annual label (`FY2024`) implies 12 months; a quarterly label implies
    3; an explicit `explicit` value always wins. An unparseable label yields None
    (unknown), which blocks a duration-dependent comparison rather than assuming
    twelve months.
    """
    if explicit is not None:
        return int(explicit)
    if not period:
        return None
    text = str(period)
    for pattern, months in _DURATION_PATTERNS:
        if pattern.search(text):
            return months
    # A bare FY<year> / <year> is a 12-month annual period by convention.
    parsed = parse_period(text)
    if parsed is not None and parsed.granularity == "annual":
        return 12
    if parsed is not None and parsed.granularity == "quarter":
        return 3
    return None


# ── Dimension checks ─────────────────────────────────────────────────────────


def _norm(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _check_metric(a: LegDescriptor, b: LegDescriptor) -> Optional[str]:
    ma, mb = _norm(a.metric), _norm(b.metric)
    if ma and mb and ma != mb:
        return f"different metrics ({a.metric} vs {b.metric})"
    return None


def _check_entity(a: LegDescriptor, b: LegDescriptor) -> Optional[str]:
    # A reused ticker that now names a different legal issuer is a hard block:
    # the two legs are about DIFFERENT companies even if the symbol matches.
    if a.tickerReused or b.tickerReused:
        return "the ticker was reused/renamed after a corporate action (demerger or rename); the two periods are different legal issuers"
    na, nb = _norm(a.legalName), _norm(b.legalName)
    if na and nb and na != nb:
        return f"different legal issuers ({a.legalName} vs {b.legalName})"
    return None


def _check_security(a: LegDescriptor, b: LegDescriptor) -> Optional[str]:
    ma, mb = _norm(a.market), _norm(b.market)
    if ma and mb and ma != mb:
        return f"different markets ({a.market} vs {b.market})"
    ea, eb = _norm(a.exchange), _norm(b.exchange)
    if ea and eb and ea != eb:
        return f"different exchanges ({a.exchange} vs {b.exchange})"
    sa, sb = _norm(a.symbol), _norm(b.symbol)
    # A symbol mismatch is only fatal when legal names did not already resolve it.
    if sa and sb and sa != sb and not (_norm(a.legalName) and _norm(a.legalName) == _norm(b.legalName)):
        return f"different securities ({a.symbol} vs {b.symbol})"
    return None


def _check_period(a: LegDescriptor, b: LegDescriptor) -> Optional[str]:
    """The two legs must be at the SAME granularity, but DIFFERENT periods.

    A period-over-period change is precisely a comparison of two distinct periods;
    requiring the labels to be equal would refuse every legitimate YoY/QoQ change.
    What must be refused is a cross-granularity pairing (an annual leg against a
    quarter leg). Two identical period labels ARE blocked here: comparing a
    period to itself is not a change.
    """
    pa, pb = a.period, b.period
    if not pa or not pb:
        return "one period is unknown; a change cannot be established"
    ga, gb = parse_period(pa), parse_period(pb)
    if ga is None or gb is None:
        return "a period label is unrecognised; comparability cannot be verified"
    if ga.granularity != gb.granularity:
        return f"periods are at different granularities ({pa} vs {pb})"
    if periods_match(pa, pb):
        return f"the two legs refer to the same period ({pa}); a change needs distinct periods"
    return None


def _check_duration(a: LegDescriptor, b: LegDescriptor) -> Optional[str]:
    da = parse_duration_months(a.period, a.durationMonths)
    db = parse_duration_months(b.period, b.durationMonths)
    if da is not None and db is not None and da != db:
        return (
            f"the reporting periods differ in length ({da} months vs {db} months); "
            "a nine-month-to-twelve-month change is not like-for-like"
        )
    if da is None or db is None:
        # Unknown duration is a block ONLY when one side is explicitly non-annual
        # and the other is unknown — otherwise an annual comparison is legitimate.
        if (da == 12 and db is None) or (db == 12 and da is None):
            return None
        if da is None and db is None:
            return None
        return "the reporting duration of one period is unknown; comparability cannot be verified"
    return None


def _check_basis(a: LegDescriptor, b: LegDescriptor) -> Optional[str]:
    ba, bb = _norm(a.basis), _norm(b.basis)
    if ba and bb and ba != bb:
        return f"different consolidation bases ({a.basis} vs {b.basis})"
    if bool(ba) != bool(bb) and (ba or bb):
        return "one leg states a consolidation basis and the other does not; comparability cannot be verified"
    return None


def _check_currency(a: LegDescriptor, b: LegDescriptor) -> Optional[str]:
    ca, cb = _norm(a.currency), _norm(b.currency)
    if ca and cb and ca != cb:
        return f"different currencies ({a.currency} vs {b.currency})"
    if ca and not cb:
        return "one leg states a currency and the other does not; a change is not comparable without conversion"
    return None


def _check_unit(a: LegDescriptor, b: LegDescriptor) -> Optional[str]:
    ua, ub = _norm(a.unit), _norm(b.unit)
    if ua and ub and ua != ub:
        return f"different units ({a.unit} vs {b.unit})"
    return None


def _check_scale(a: LegDescriptor, b: LegDescriptor) -> Optional[str]:
    if a.scale is not None and b.scale is not None and a.scale != b.scale:
        return (
            f"different reporting scales ({a.scale} vs {b.scale}); "
            "one leg may be in units and the other in thousands"
        )
    return None


def _check_restatement(a: LegDescriptor, b: LegDescriptor) -> Optional[str]:
    # Only blocks when the SAME period carries two different versions without a
    # stated relationship (a restatement must be disclosed, not silently mixed).
    if a.period and b.period and periods_match(a.period, b.period):
        va, vb = _norm(a.versionId), _norm(b.versionId)
        if va and vb and va != vb:
            return f"the same period has two versions ({a.versionId} vs {b.versionId}) without a stated relationship"
    return None


_CHECKS = {
    "entity": _check_entity,
    "security": _check_security,
    "period": _check_period,
    "duration": _check_duration,
    "metric": _check_metric,
    "basis": _check_basis,
    "currency": _check_currency,
    "unit": _check_unit,
    "scale": _check_scale,
    "restatement": _check_restatement,
}


def check_pair(a: LegDescriptor, b: LegDescriptor) -> BlockedComparison | None:
    """Return the FIRST blocking dimension for a pair, or None when compatible."""
    for dimension in _DIMENSIONS:
        reason = _CHECKS[dimension](a, b)
        if reason:
            return BlockedComparison(legs=(a.legId, b.legId), reason=reason, dimension=dimension)
    return None


def check_comparability(descriptors: list[LegDescriptor]) -> ComparabilityVerdict:
    """Check every unordered pair of descriptors.

    A pair that shares a metric but is blocked in any dimension is reported as a
    blocked comparison; a pair with no shared metric is not a candidate change and
    is skipped (there is nothing to compute between revenue and net income).
    """
    verdict = ComparabilityVerdict()
    for i in range(len(descriptors)):
        for j in range(i + 1, len(descriptors)):
            a, b = descriptors[i], descriptors[j]
            ma, mb = _norm(a.metric), _norm(b.metric)
            if ma and mb and ma != mb:
                continue  # different metrics → not a candidate comparison
            blocked = check_pair(a, b)
            if blocked is None:
                verdict.compatible.append((a.legId, b.legId))
            else:
                verdict.blocked.append(blocked)
    return verdict


def descriptor_from_leg(leg: Any, *, identity: Any = None, evidenceIds: Optional[list[str]] = None) -> LegDescriptor:
    """Build a descriptor from a mandate FactLeg (+ optional resolved identity).

    `durationMonths` is read from the leg metadata when a source supplied it; the
    period label is the fallback. Nothing is guessed.
    """
    meta = getattr(leg, "metadata", None) or {}
    identity = identity or {}
    return LegDescriptor(
        legId=str(getattr(leg, "id", "")),
        metric=getattr(leg, "metric", None),
        period=getattr(leg, "period", None),
        durationMonths=meta.get("durationMonths") if isinstance(meta, dict) else None,
        basis=getattr(leg, "basis", None),
        currency=getattr(leg, "currency", None),
        unit=getattr(leg, "unit", None),
        scale=meta.get("scale") if isinstance(meta, dict) else None,
        symbol=getattr(leg, "entitySymbol", None),
        market=getattr(leg, "market", None),
        exchange=identity.get("exchange") if isinstance(identity, dict) else getattr(identity, "exchange", None),
        legalName=identity.get("legalName") if isinstance(identity, dict) else getattr(identity, "name", None),
        tickerReused=bool(meta.get("tickerReused")) if isinstance(meta, dict) else False,
        versionId=meta.get("versionId") if isinstance(meta, dict) else None,
        documentId=meta.get("documentId") if isinstance(meta, dict) else None,
        evidenceIds=list(evidenceIds or []),
    )


__all__ = [
    "LegDescriptor",
    "BlockedComparison",
    "ComparabilityVerdict",
    "check_pair",
    "check_comparability",
    "parse_duration_months",
    "descriptor_from_leg",
]

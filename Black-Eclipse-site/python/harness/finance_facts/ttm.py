"""Independent TTM engine (Universal Financial Data Accuracy, §8).

Do not blindly trust a vendor TTM. When four comparable quarters are available,
Eclipse sums them itself, then reconciles against the vendor TTM. A material
difference becomes `TTM STATUS = CONFLICT` with the candidate causes listed for
investigation — never silently accepted.

    TTM(metric) = Q(n-3) + Q(n-2) + Q(n-1) + Q(n)      # four comparable quarters

Comparability requires: same metric definition, same currency, same entity, and
four ADJACENT quarters (no gaps). A gap, a mixed definition or a mixed currency
refuses the sum rather than producing a wrong number.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Optional, Sequence

from .model import FinancialFact
from .periods_ext import months_for, parse_iso

# A relative difference at or above this is a material TTM conflict.
TTM_TOLERANCE = 0.02  # 2%

# Candidate causes a TTM conflict should be investigated against (§8).
INVESTIGATION_CHECKLIST: tuple[str, ...] = (
    "restatements",
    "discontinued operations",
    "currency translation",
    "acquisitions or disposals",
    "fiscal calendar change",
    "accounting-policy change",
    "extraordinary items",
    "source error",
)


@dataclass
class TTMResult:
    metric: str
    status: str  # "ok" | "conflict" | "insufficient_data" | "not_comparable"
    ttm_value: Optional[float] = None
    quarters_used: list[str] = field(default_factory=list)
    vendor_value: Optional[float] = None
    vendor_source: Optional[str] = None
    difference: Optional[float] = None
    relative_difference: Optional[float] = None
    explanation: Optional[str] = None
    checklist: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _numeric(fact: FinancialFact) -> Optional[float]:
    v = fact.value
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _quarterly_facts(facts: Sequence[FinancialFact], metric: str, definition: Optional[str]) -> list[FinancialFact]:
    out: list[FinancialFact] = []
    for f in facts:
        if f.metric != metric and (definition is None or f.definition != definition):
            continue
        if f.period is None or f.period.period_type != "quarter":
            continue
        if _numeric(f) is None:
            continue
        out.append(f)
    return out


def _adjacent_quarters(quarters: list[FinancialFact]) -> bool:
    """True when the quarters are consecutive (no gap) — a TTM cannot skip one."""
    if len(quarters) < 4:
        return False
    ends = [parse_iso(q.period.period_end) for q in quarters[-4:]]
    if any(e is None for e in ends):
        return False
    for prev, curr in zip(ends, ends[1:]):
        # Consecutive quarters are ~3 months apart (allow a week of slack either way).
        delta = (curr - prev).days
        if not (80 <= delta <= 100):
            return False
    return True


def compute_ttm(
    facts: Sequence[FinancialFact],
    metric: str,
    *,
    definition: Optional[str] = None,
    vendor_value: Optional[float] = None,
    vendor_source: Optional[str] = None,
) -> TTMResult:
    """Independently compute TTM from the four most recent adjacent quarters.

    `vendor_value` is the number a provider published as TTM (if any). When the
    two differ materially the result is `conflict` and the difference is returned
    with the investigation checklist — the caller must surface it, not pick one.
    """
    quarters = _quarterly_facts(facts, metric, definition)
    if len(quarters) < 4:
        return TTMResult(
            metric=metric, status="insufficient_data",
            vendor_value=vendor_value, vendor_source=vendor_source,
            warnings=[f"only {len(quarters)} comparable quarter(s) available; need 4"],
        )
    quarters = sorted(quarters, key=lambda f: f.period.period_end or "")
    # Definition/currency must agree across the four used.
    used = quarters[-4:]
    defs = {f.definition for f in used}
    currencies = {f.currency for f in used}
    if len(defs) > 1:
        return TTMResult(
            metric=metric, status="not_comparable",
            warnings=[f"the four quarters mix definitions: {sorted(d for d in defs if d)}"],
        )
    if len(currencies) > 1:
        return TTMResult(
            metric=metric, status="not_comparable",
            warnings=[f"the four quarters mix currencies: {sorted(c for c in currencies if c)}"],
        )
    if not _adjacent_quarters(used):
        return TTMResult(
            metric=metric, status="not_comparable",
            warnings=["the four quarters are not adjacent (a quarter is missing)"],
        )

    total = sum(_numeric(f) or 0.0 for f in used)
    used_labels = [f.period.key() for f in used]

    if vendor_value is None:
        return TTMResult(metric=metric, status="ok", ttm_value=total, quarters_used=used_labels)

    try:
        vendor = float(vendor_value)
    except (TypeError, ValueError):
        return TTMResult(metric=metric, status="ok", ttm_value=total, quarters_used=used_labels,
                         vendor_value=vendor_value, vendor_source=vendor_source)

    diff = total - vendor
    denom = max(abs(total), abs(vendor), 1e-9)
    rel = abs(diff) / denom
    if rel >= TTM_TOLERANCE:
        return TTMResult(
            metric=metric, status="conflict", ttm_value=total, quarters_used=used_labels,
            vendor_value=vendor, vendor_source=vendor_source,
            difference=diff, relative_difference=rel,
            explanation=(
                f"independently computed TTM {total:,.0f} differs from the provider's "
                f"{vendor:,.0f} by {rel * 100:.1f}% — investigate before using either"
            ),
            checklist=list(INVESTIGATION_CHECKLIST),
        )
    return TTMResult(
        metric=metric, status="ok", ttm_value=total, quarters_used=used_labels,
        vendor_value=vendor, vendor_source=vendor_source, difference=diff, relative_difference=rel,
    )


__all__ = ["INVESTIGATION_CHECKLIST", "TTMResult", "TTM_TOLERANCE", "compute_ttm"]

"""Data-quality gate chain (Universal Financial Data Accuracy, §19/§23).

Before a financial fact reaches the answer layer it passes ONE ordered chain:

    Entity → Period → Source → Freshness → Accounting-definition → Consolidation
    → Currency → Unit → Conflict → Calculation → Evidence

Each gate returns a `GateResult`. A failure is never silent: the caller must
resolve it, DISCLOSE it, or EXCLUDE the metric. This module runs the chain and
returns which gates passed, which failed and why, so the answer layer can act.

It also answers the §19 question "why is this N/A?" — negative earnings, no EPS,
missing data, discontinued ops, or a data error — rather than treating 0 / NULL /
N/A / negative / unavailable as equivalent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import freshness as fresh
from . import semantics
from .model import FinancialFact


@dataclass
class GateResult:
    gate: str
    passed: bool
    reason: Optional[str] = None
    disclosure: Optional[str] = None   # a sentence to show when not resolved


@dataclass
class QualityReport:
    passed: bool
    gates: list[GateResult] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)   # metric names that must not be shown

    def failing(self) -> list[GateResult]:
        return [g for g in self.gates if not g.passed]


# The chain, in order (§23).
GATE_ORDER: tuple[str, ...] = (
    "entity", "period", "source", "freshness", "definition", "consolidation",
    "currency", "unit", "conflict", "calculation", "evidence",
)

# Market facts are unambiguous by nature — a "price" or a "volume" needs no
# accounting-definition resolution, and requiring one would wrongly exclude it.
_MARKET_METRICS: frozenset[str] = frozenset(
    {"price", "volume", "market_cap", "shares_outstanding", "change_pct",
     "pe_ratio", "pb_ratio", "ps_ratio", "ev_ebitda", "dividend_yield"}
)


def is_market_fact(fact: FinancialFact) -> bool:
    """True when a fact is a market observation (price/volume/multiple), whether
    it is keyed by its raw label (`marketCap`) or its resolved definition."""
    return fact.definition in _MARKET_METRICS or fact.metric in _MARKET_METRICS


def evaluate(
    fact: FinancialFact,
    *,
    require_entity: bool = True,
    require_period: bool = True,
    require_definition: bool = True,
    allow_stale: bool = True,
    conflict_present: bool = False,
    calculation_integrity: bool = True,
    has_evidence: bool = True,
    now: Optional[float] = None,
) -> QualityReport:
    """Run the ordered gate chain over one fact.

    A gate that cannot be satisfied produces a failure; the report says whether
    each failure is merely a DISCLOSURE (show the fact with the caveat) or an
    EXCLUSION (do not show the fact). Staleness is a disclosure by default; a
    missing entity/period/definition is an exclusion for an authoritative answer.
    """
    gates: list[GateResult] = []
    exclusions: list[str] = []

    # Entity.
    if require_entity and not fact.entity_id:
        gates.append(GateResult("entity", False, "no resolved entity identity",
                                disclosure="this fact could not be tied to a specific instrument"))
        exclusions.append(fact.metric)
    else:
        gates.append(GateResult("entity", True))

    # Period.
    if require_period and (fact.period is None or not fact.period.period_type):
        gates.append(GateResult("period", False, "no explicit period",
                                disclosure="this fact has no stated period, so it cannot be compared"))
        exclusions.append(fact.metric)
    else:
        gates.append(GateResult("period", True))

    # Source.
    if fact.source_type == "unknown" or not fact.source:
        gates.append(GateResult("source", False, "source is unknown",
                                disclosure="the origin of this fact is not known"))
    else:
        gates.append(GateResult("source", True))

    # Freshness. An unclassified fact carries the UNVERIFIED sentinel; compute it.
    state = fact.freshness
    if not state or state == fresh.UNVERIFIED:
        state = fresh.freshness_for(fact, now=now)
    if state in (fresh.SUPERSEDED,):
        gates.append(GateResult("freshness", False, "superseded by a later revision",
                                disclosure="a newer revision of this fact exists"))
        exclusions.append(fact.metric)
    elif state in (fresh.STALE, fresh.VERY_STALE) and not allow_stale:
        gates.append(GateResult("freshness", False, f"freshness is {state}",
                                disclosure="the latest available data is stale"))
    elif state in (fresh.STALE, fresh.VERY_STALE):
        # Allowed, but the caveat must ride along so the answer can state it.
        gates.append(GateResult("freshness", False, f"freshness is {state}",
                                disclosure="the latest available data is stale"))
    else:
        gates.append(GateResult("freshness", True))

    # Accounting definition. A market fact (price, volume) is unambiguous by
    # nature. Otherwise an explicitly-resolved definition resolves any label
    # ambiguity; an unresolved, ambiguous label is excluded.
    if is_market_fact(fact):
        gates.append(GateResult("definition", True))
    elif fact.definition is not None:
        gates.append(GateResult("definition", True))
    elif semantics.is_ambiguous_label(fact.metric):
        gates.append(GateResult("definition", False, "metric label is ambiguous",
                                disclosure="this metric could mean more than one accounting concept"))
        exclusions.append(fact.metric)
    elif require_definition:
        gates.append(GateResult("definition", False, "accounting definition unresolved",
                                disclosure="this metric's accounting definition is ambiguous"))
        exclusions.append(fact.metric)
    else:
        gates.append(GateResult("definition", True))

    # Consolidation. A market fact has no consolidation concept.
    if is_market_fact(fact):
        gates.append(GateResult("consolidation", True))
    elif fact.consolidation_level == "unknown":
        gates.append(GateResult("consolidation", False, "consolidation level unknown",
                                disclosure="it is not stated whether this figure is consolidated"))
    else:
        gates.append(GateResult("consolidation", True))

    # Currency.
    if not fact.currency:
        gates.append(GateResult("currency", False, "currency unknown",
                                disclosure="this fact has no stated currency"))
    else:
        gates.append(GateResult("currency", True))

    # Unit.
    if fact.unit is None and fact.value is not None:
        gates.append(GateResult("unit", False, "unit unknown",
                                disclosure="this fact has no stated unit"))
    else:
        gates.append(GateResult("unit", True))

    # Conflict.
    if conflict_present:
        gates.append(GateResult("conflict", False, "sources disagree",
                                disclosure="sources disagree on this value"))
    else:
        gates.append(GateResult("conflict", True))

    # Calculation.
    if fact.reported_or_derived == "derived" and not calculation_integrity:
        gates.append(GateResult("calculation", False, "derived value is not reproducible",
                                disclosure="this calculated value could not be re-derived"))
        exclusions.append(fact.metric)
    else:
        gates.append(GateResult("calculation", True))

    # Evidence.
    if not has_evidence:
        gates.append(GateResult("evidence", False, "no evidence link",
                                disclosure="this fact cannot be traced to a source document"))
        exclusions.append(fact.metric)
    else:
        gates.append(GateResult("evidence", True))

    return QualityReport(passed=not exclusions and all(g.passed for g in gates),
                          gates=gates, exclusions=exclusions)


def na_reason(fact: FinancialFact) -> str:
    """Why is this value N/A? (§19) — one of the distinct reasons, never a guess.

    Returns a stable code: `negative_earnings`, `no_eps`, `missing_data`,
    `discontinued_operations`, `not_applicable`, `data_error`, or `ok`.
    """
    v = fact.value
    if v is None:
        if fact.raw and fact.raw.get("discontinued") is True:
            return "discontinued_operations"
        if fact.raw and fact.raw.get("not_applicable") is True:
            return "not_applicable"
        return "missing_data"
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
        if fact.metric in ("eps", "net_income", "net_income_parent", "net_income_common"):
            return "negative_earnings"
        return "ok"
    return "ok"


__all__ = ["GATE_ORDER", "GateResult", "QualityReport", "evaluate", "na_reason"]

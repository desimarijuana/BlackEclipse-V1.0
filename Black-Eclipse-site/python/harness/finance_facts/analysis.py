"""Enforcing analysis: turn a retrieval result into a validated, gated fact set.

This is the enforcement seam. Before an answer layer (the model) sees a number,
this module:

  1. lifts every observed value into a `FinancialFact` (see `adapter.to_fact`),
  2. runs the ordered data-quality gate chain on each fact (§23),
  3. computes an evidence-based confidence per fact (§20),
  4. detects and explains cross-source conflicts (§13/§26),
  5. builds the evidence graph and reports orphans (§21),
  6. classifies the entity and warns when a financial-sector lens applies (§12).

It returns a `ResultAnalysis` whose `excluded` facts MUST NOT be presented as
clean answers, and whose `notes` the answer must carry. It does not itself write
prose and does not change the retrieval result; it is the gate the caller honors.

Nothing is fabricated: a fact with no period/source/definition is EXCLUDED, not
shown; a conflict is surfaced, not suppressed; a stale value is disclosed, not
hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import confidence as _confidence
from . import freshness as _fresh
from . import quality as _quality
from . import sector as _sector
from .adapter import to_fact
from .conflicts import detect_conflict
from .evidence import EvidenceGraph, add_claim, add_fact
from .model import FinancialFact

# Metric labels that are descriptors, not financial amounts. Market metrics
# (price/volume/market_cap…) ARE financial and are deliberately NOT here.
_NON_FINANCIAL = {
    "sector", "industry", "name", "exchange", "country", "securityType", "assetClass",
    "description", "website", "employees", "source", "instrument", "market", "symbol",
    "units", "currency",
}


@dataclass
class FactVerdict:
    fact_id: str
    metric: str
    definition: Optional[str]
    value: Any
    period: Optional[str]
    source: Optional[str]
    confidence: str
    freshness: str
    # Admissible = not excluded. A fact with only disclosures (stale, consolidation
    # unstated, source soft) is still admissible; the caveats ride in `disclosures`.
    quality_passed: bool
    exclusions: list[str] = field(default_factory=list)
    disclosures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "factId": self.fact_id,
            "metric": self.metric,
            "definition": self.definition,
            "value": self.value,
            "period": self.period,
            "source": self.source,
            "confidence": self.confidence,
            "freshness": self.freshness,
            "admissible": self.quality_passed,
            "exclusions": self.exclusions,
            "disclosures": self.disclosures,
        }


@dataclass
class ResultAnalysis:
    facts: list[FactVerdict] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sector: Optional[str] = None
    financial_framework: bool = False
    graph_orphans: list[str] = field(default_factory=list)

    @property
    def presentable(self) -> bool:
        """False when at least one fact was excluded — the answer must not claim
        a clean result from it without stating the exclusion."""
        return not self.excluded

    def to_dict(self) -> dict[str, Any]:
        return {
            "presentable": self.presentable,
            "sector": self.sector,
            "financialFramework": self.financial_framework,
            "excluded": self.excluded,
            "conflicts": self.conflicts,
            "notes": self.notes,
            "graphOrphans": self.graph_orphans,
            "facts": [f.to_dict() for f in self.facts],
        }


def _is_financial(fact: FinancialFact) -> bool:
    if fact.metric in _NON_FINANCIAL:
        return False
    v = fact.value
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def analyze_result(result, *, entity_id: Optional[str] = None, now: Optional[float] = None) -> ResultAnalysis:
    """Run the full enforcement chain over a retrieval result.

    Additive and read-only. Returns the validated fact set, what is excluded and
    why, the conflicts, the sector classification and the evidence-graph orphan
    list. The caller MUST honor `excluded` (do not present those as clean facts)
    and carry `notes`.
    """
    analysis = ResultAnalysis()
    graph = EvidenceGraph()

    raw_facts: list[FinancialFact] = []
    for item in getattr(result, "evidence", []) or []:
        for obj in getattr(item, "objects", []) or []:
            raw_facts.append(to_fact(obj, entity_id=entity_id))

    # Group by CANONICAL concept, not the raw label: two sources reporting the
    # same fact under different labels ("total revenue" vs "revenue") must be
    # compared, not kept apart. Fall back to the raw metric when unresolved.
    def _concept_key(fact: FinancialFact) -> str:
        return f"def:{fact.definition}" if fact.definition else f"metric:{fact.metric}"

    by_metric: dict[str, list[FinancialFact]] = {}
    for fact in raw_facts:
        by_metric.setdefault(_concept_key(fact), []).append(fact)

    # Detect each unordered pair of same-concept facts exactly ONCE, so a
    # disagreement is reported once, not twice (once per direction). Keyed by
    # object identity: two facts from different sources can share a fact_id.
    conflict_pairs: set[tuple[int, int]] = set()
    conflicting: set[int] = set()
    for metric, group in by_metric.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                c = detect_conflict(group[i], group[j])
                if c is None:
                    continue
                key = tuple(sorted((id(group[i]), id(group[j]))))
                if key in conflict_pairs:
                    continue
                conflict_pairs.add(key)
                analysis.conflicts.append(c.to_dict())
                if not c.semantic:
                    conflicting.add(id(group[i]))
                    conflicting.add(id(group[j]))

    for fact in raw_facts:
        if not _is_financial(fact):
            continue

        conflict_here = id(fact) in conflicting

        report = _quality.evaluate(fact, conflict_present=conflict_here, now=now)
        breakdown = _confidence.confidence_for(
            fact,
            cross_source_agreement=not conflict_here,
            period_alignment=fact.period is not None,
        )
        state = fact.freshness
        if not state or state == _fresh.UNVERIFIED:
            state = _fresh.freshness_for(fact, now=now)

        verdict = FactVerdict(
            fact_id=fact.fact_id,
            metric=fact.metric,
            definition=fact.definition,
            value=fact.value,
            period=fact.period.key() if fact.period else None,
            source=fact.source,
            confidence=breakdown.level,
            freshness=state,
            quality_passed=not report.exclusions,
            exclusions=list(report.exclusions),
            disclosures=[g.disclosure for g in report.gates if g.disclosure],
        )
        analysis.facts.append(verdict)
        analysis.excluded.extend(report.exclusions)
        if not _quality.is_market_fact(fact) and fact.definition is None:
            analysis.notes.append(
                f"accounting definition unresolved for {fact.metric}; its meaning is ambiguous"
            )
        if conflict_here:
            analysis.notes.append(f"{fact.metric}: sources disagree — do not present a single value without saying so")

        # Evidence graph: every financial fact gets a node (orphan if no source).
        add_fact(graph, fact)

    if analysis.facts:
        add_claim(graph, "claim:answer", "the answer's material claims", [f.fact_id for f in analysis.facts])

    # Sector classification from name/industry/sector descriptors among the facts.
    texts: list[Optional[str]] = [getattr(getattr(result, "identity", None), "name", None)]
    for fact in raw_facts:
        if fact.metric in ("sector", "industry"):
            texts.append(str(fact.value))
    classification = _sector.classify(*texts)
    analysis.sector = classification.sector if classification.sector != "generic" else None
    analysis.financial_framework = classification.contains_financial
    if classification.sector != "generic":
        analysis.notes.append(f"business type detected: {classification.sector}")
    warning = _sector.financial_framework_warning(classification)
    if warning:
        analysis.notes.append(warning)

    analysis.excluded = sorted(set(analysis.excluded))
    analysis.graph_orphans = graph.orphans()
    if analysis.graph_orphans:
        analysis.notes.append("some values could not be traced to a source document")
    return analysis


__all__ = ["FactVerdict", "ResultAnalysis", "analyze_result"]

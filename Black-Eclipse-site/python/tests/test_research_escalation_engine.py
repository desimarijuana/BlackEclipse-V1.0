"""Phase 5 — end-to-end escalation scenarios through `run_research`.

Entity-agnostic fixtures. Covers: structured success (no escalation), stale/
irrelevant structured rows followed by successful primary web retrieval,
secondary fallback, contradictory sources, missing period, missing basis,
currency/unit mismatch, prompt injection, budget exhaustion, cancellation, and
honest partial answers.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.research.budget import ResearchBudget
from harness.research.engine import run_research
from harness.research.escalation import escalate_web
from harness.research.mandate import parse_mandate
from harness.research.web_facts import ExtractedFact
from harness.retrieval.contract import (
    EvidenceItem,
    FinancialRetrievalResult,
    NormalizedFinancialObject,
    SourceReference,
)
from harness.tools import DataBridge

from test_research_escalation import FakeWebBridge, ScriptedExtractor


# ── A structured source that returns only an unrelated/old period ────────────


class StaleStructuredRetriever:
    """Simulates the JDdS vault returning a large multi-year statement whose
    objects start with an unrelated old fiscal year (the NVDA failure shape),
    but for ANY entity."""

    def __init__(self, *, periods: list[str], metrics: list[str]) -> None:
        self.periods = periods
        self.metrics = metrics
        self.calls = 0

    async def __call__(self, request):
        self.calls += 1
        objects = []
        for period in self.periods:
            for metric in self.metrics:
                objects.append(
                    NormalizedFinancialObject(
                        name=metric,
                        value=100.0,
                        period=period,       # explicit fiscal label
                        currency="USD",
                        instrument=request.instrument,
                        source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid"),
                    )
                )
        return FinancialRetrievalResult(
            status="OK",
            objective=request.objective,
            dataType=request.dataType,
            instrument=request.instrument,
            evidence=[
                EvidenceItem(
                    id=f"structured_JDDS_{request.instrument}_{len(objects)}",
                    kind="structured",
                    summary=f"JDDS: {len(objects)} normalized value(s)",
                    objects=objects,
                    source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid"),
                )
            ],
        )


def _entity(entity="AAA"):
    return entity


# ── Structured success should NOT escalate ──────────────────────────────────


def test_structured_success_does_not_escalate():
    bridge = FakeWebBridge(tiers=["primary"])

    async def retrieve(request):
        return FinancialRetrievalResult(
            status="OK", objective=request.objective, dataType=request.dataType,
            instrument=request.instrument,
            evidence=[
                EvidenceItem(
                    id=f"structured_JDDS_{request.instrument}",
                    kind="structured", summary="JDDS",
                    objects=[
                        NormalizedFinancialObject(name="revenue", value=500.0, period="FY2024", currency="USD", instrument=request.instrument,
                                                  source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid")),
                        NormalizedFinancialObject(name="revenue", value=400.0, period="FY2023", currency="USD", instrument=request.instrument,
                                                  source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid")),
                    ],
                    source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid"),
                )
            ],
        )

    m = parse_mandate("Compare AAA revenue FY2023 vs FY2024 in USD", ticker="AAA")
    out = asyncio.run(
        run_research(
            m, retrieve, run_id="r1", bridge=bridge,
            extractor=ScriptedExtractor([[]]), budget=ResearchBudget(),
        )
    )
    assert out.coverage.status == "accepted"
    assert out.escalation is None  # no unsatisfied leg → no escalation at all
    assert not any(c[0] == "web_search" for c in bridge.calls)


# ── Stale structured → primary web recovery ─────────────────────────────────


def test_stale_structured_rows_then_primary_web_recovers():
    retriever = StaleStructuredRetriever(periods=["FY2019", "FY2020"], metrics=["revenue"])
    bridge = FakeWebBridge(tiers=["primary"])
    extractor = ScriptedExtractor(
        [
            [
                ExtractedFact(metric="revenue", value=60922, currency="USD", period="FY2024",
                              pageId="page1", sourceSpan="Revenue 60,922 million USD."),
                ExtractedFact(metric="revenue", value=130497, currency="USD", period="FY2025",
                              pageId="page1", sourceSpan="Revenue 130,497 million USD."),
            ]
        ]
    )
    m = parse_mandate("Compare AAA revenue for FY2024 and FY2025 in USD", ticker="AAA")
    out = asyncio.run(
        run_research(
            m, retriever, run_id="r2", bridge=bridge,
            extractor=extractor, budget=ResearchBudget(),
        )
    )
    # Structured produced only old periods → the requested legs escalated and the
    # primary web source supplied them.
    assert out.escalation is not None
    assert "primary_web" in out.escalation["stages"]
    assert out.coverage.status in ("accepted", "partial")
    web_legs = [l for l in out.coverage.legs if l.status in ("covered", "qualified")]
    assert len(web_legs) == 2
    assert any(item.kind == "filing" for item in out.evidence)


def test_two_metrics_two_periods_all_escalated_generically():
    """The NVDA-shaped request (two metrics × two periods) recovers for ANY
    entity via primary-web escalation, with no entity-specific code."""
    retriever = StaleStructuredRetriever(periods=["2019"], metrics=["revenue", "netIncome"])
    bridge = FakeWebBridge(tiers=["primary"])

    def fresh_extractor() -> ScriptedExtractor:
        return ScriptedExtractor(
            [
                [
                    ExtractedFact(metric="revenue", value=130497, currency="USD", period="FY2025",
                                  pageId="page1", sourceSpan="Revenue 130,497 million USD."),
                    ExtractedFact(metric="revenue", value=60922, currency="USD", period="FY2024",
                                  pageId="page1", sourceSpan="Revenue 60,922 million USD."),
                    ExtractedFact(metric="netIncome", value=72880, currency="USD", period="FY2025",
                                  pageId="page1", sourceSpan="Net income 72,880 million USD."),
                    ExtractedFact(metric="netIncome", value=29760, currency="USD", period="FY2024",
                                  pageId="page1", sourceSpan="Net income 29,760 million USD."),
                ]
            ]
        )

    for entity in ("ZZZA", "ZZZB", "ZZZC"):
        m = parse_mandate(
            f"Compare {entity} revenue and net income for FY2024 and FY2025 in USD", ticker=entity
        )
        out = asyncio.run(
            run_research(
                m, retriever, run_id=f"r_{entity}", bridge=bridge,
                extractor=fresh_extractor(), budget=ResearchBudget(),
            )
        )
        assert out.coverage.status == "accepted", entity
        assert all(l.status == "covered" for l in out.coverage.legs), entity
        assert sum(1 for item in out.evidence if item.kind == "filing") == 4, entity


# ── Secondary fallback ──────────────────────────────────────────────────────


def test_secondary_fallback_used_when_primary_empty():
    retriever = StaleStructuredRetriever(periods=["FY2019"], metrics=["netIncome"])
    bridge = FakeWebBridge(tiers=["secondary"])
    extractor = ScriptedExtractor(
        [
            [
                ExtractedFact(metric="netIncome", value=72880, currency="USD", period="FY2025",
                              pageId="page1", sourceSpan="Net income 72,880 million USD."),
            ]
        ]
    )
    m = parse_mandate("Compare AAA net income for FY2024 and FY2025 in USD", ticker="AAA")
    out = asyncio.run(
        run_research(m, retriever, run_id="r3", bridge=bridge, extractor=extractor, budget=ResearchBudget())
    )
    assert out.escalation is not None
    assert "secondary_web" in out.escalation["stages"]
    assert any(item.kind == "web" for item in out.evidence if item.kind in ("web", "filing"))


# ── Contradictory sources ───────────────────────────────────────────────────


def test_conflicting_values_surface_as_conflict():
    async def retrieve(request):
        return FinancialRetrievalResult(
            status="OK", objective=request.objective, dataType=request.dataType,
            instrument=request.instrument,
            evidence=[
                EvidenceItem(
                    id=f"structured_JDDS_{request.instrument}",
                    kind="structured", summary="JDDS",
                    objects=[
                        NormalizedFinancialObject(name="revenue", value=1000.0, period="FY2024", currency="USD",
                                                  basis="consolidated", instrument=request.instrument,
                                                  source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid")),
                    ],
                    source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid"),
                )
            ],
            conflicts=[{"metric": "revenue", "period": "FY2024", "candidates": [{"value": 1000}, {"value": 1200, "source": "OTHER"}]}],
        )

    m = parse_mandate("Compare AAA revenue FY2023 vs FY2024 consolidated in USD", ticker="AAA")
    out = asyncio.run(run_research(m, retrieve, run_id="r4"))
    # The FY2024 leg is conflicting; the answer must disclose it, not pick one.
    conflicted = [l for l in out.coverage.legs if l.status == "conflicting"]
    assert conflicted


# ── Missing period ──────────────────────────────────────────────────────────


def test_missing_period_reported_precisely():
    retriever = StaleStructuredRetriever(periods=["FY2019"], metrics=["revenue"])
    m = parse_mandate("Compare AAA revenue for FY2024 and FY2025 in USD", ticker="AAA")
    # No web bridge → escalation unavailable; the exact gap must be reported.
    out = asyncio.run(run_research(m, retriever, run_id="r5"))
    statuses = {l.status for l in out.coverage.legs}
    assert "no_matching_period" in statuses
    assert out.coverage.status == "partial"


# ── Missing basis → qualified, not blocked ──────────────────────────────────


def test_missing_basis_yields_qualified_not_rejected():
    retriever = StaleStructuredRetriever(periods=["FY2024", "FY2025"], metrics=["revenue"])
    # The stale retriever never sets a basis.
    m = parse_mandate("Compare AAA revenue for FY2024 and FY2025 consolidated in USD", ticker="AAA")
    out = asyncio.run(run_research(m, retriever, run_id="r6"))
    assert all(l.status == "qualified" for l in out.coverage.legs)
    assert out.coverage.status == "partial"
    # The values are still independently presentable (qualified), not unavailable.
    assert all(l.evidenceIds for l in out.coverage.legs)


# ── Currency / unit mismatch ────────────────────────────────────────────────


def test_currency_mismatch_not_covered():
    async def retrieve(request):
        return FinancialRetrievalResult(
            status="OK", objective=request.objective, dataType=request.dataType,
            instrument=request.instrument,
            evidence=[
                EvidenceItem(
                    id="structured_EUR", kind="structured", summary="JDDS",
                    objects=[
                        NormalizedFinancialObject(name="revenue", value=1000.0, period="FY2024", currency="EUR",
                                                  instrument=request.instrument,
                                                  source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid")),
                        NormalizedFinancialObject(name="revenue", value=900.0, period="FY2023", currency="EUR",
                                                  instrument=request.instrument,
                                                  source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid")),
                    ],
                    source=SourceReference(source="JDDS", sourceType="structured", validationStatus="valid"),
                )
            ],
        )

    m = parse_mandate("Compare AAA revenue FY2023 vs FY2024 in USD", ticker="AAA")
    out = asyncio.run(run_research(m, retrieve, run_id="r7"))
    assert all(l.status != "covered" for l in out.coverage.legs)


# ── Prompt injection ────────────────────────────────────────────────────────


def test_prompt_injection_in_page_yields_no_false_fact():
    retriever = StaleStructuredRetriever(periods=["FY2019"], metrics=["revenue"])
    bridge = FakeWebBridge(tiers=["primary"])
    # The extractor "believes" the injected instruction and reports a fake value
    # whose span is the instruction text, not a numeric fact.
    extractor = ScriptedExtractor(
        [
            [
                ExtractedFact(metric="revenue", value=9999999, currency="USD", period="FY2024",
                              pageId="page1", sourceSpan="Revenue 9999999 USD"),  # not verbatim in page
            ]
        ]
    )
    m = parse_mandate("Compare AAA revenue for FY2024 and FY2025 in USD", ticker="AAA")
    out = asyncio.run(run_research(m, retriever, run_id="r8", bridge=bridge, extractor=extractor, budget=ResearchBudget()))
    # The fabricated value is rejected deterministically; no fact is asserted.
    assert all(
        obj.value != 9999999
        for item in out.evidence
        for obj in item.objects
    )


# ── Budget exhaustion ───────────────────────────────────────────────────────


def test_budget_exhaustion_recorded_and_honest():
    retriever = StaleStructuredRetriever(periods=["FY2019"], metrics=["revenue"])
    bridge = FakeWebBridge(tiers=["primary"])
    budget = ResearchBudget(maxSearches=0)
    m = parse_mandate("Compare AAA revenue for FY2024 and FY2025 in USD", ticker="AAA")
    out = asyncio.run(
        run_research(m, retriever, run_id="r9", bridge=bridge, extractor=ScriptedExtractor([[]]), budget=budget)
    )
    assert out.budget is not None
    assert out.budget["exhausted"] == "maxSearches"
    assert out.escalation is not None
    assert out.coverage.status == "partial"  # honest, not fabricated
    assert out.receipt is not None and out.receipt.budget["exhausted"] == "maxSearches"


# ── Honest partial answer ───────────────────────────────────────────────────


def test_partial_answer_keeps_verified_facts_and_names_gap():
    # FY2024 present (primary web), FY2025 absent everywhere.
    retriever = StaleStructuredRetriever(periods=["FY2019"], metrics=["revenue"])
    bridge = FakeWebBridge(tiers=["primary"])
    extractor = ScriptedExtractor(
        [
            [
                ExtractedFact(metric="revenue", value=60922, currency="USD", period="FY2024",
                              pageId="page1", sourceSpan="Revenue 60,922 million USD."),
            ]
        ]
    )
    m = parse_mandate("Compare AAA revenue for FY2024 and FY2025 in USD", ticker="AAA")
    out = asyncio.run(run_research(m, retriever, run_id="r10", bridge=bridge, extractor=extractor, budget=ResearchBudget()))
    covered = [l for l in out.coverage.legs if l.status in ("covered", "qualified")]
    missing = [l for l in out.coverage.legs if l.status not in ("covered", "qualified", "not_applicable")]
    assert covered and missing  # some verified, some explicitly missing
    assert out.coverage.status == "partial"


# ── Cancellation ────────────────────────────────────────────────────────────


def test_cancellation_propagates_from_escalation():
    retriever = StaleStructuredRetriever(periods=["FY2019"], metrics=["revenue"])

    class CancelBridge(DataBridge):
        async def fetch(self, capability, params):
            raise asyncio.CancelledError()

    m = parse_mandate("Compare AAA revenue for FY2024 and FY2025 in USD", ticker="AAA")
    extractor = ScriptedExtractor([[]])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            run_research(m, retriever, run_id="r11", bridge=CancelBridge(), extractor=extractor, budget=ResearchBudget())
        )

"""Phase 4 — evidence-grounded research flow (Milestones 1-5, 8).

Deterministic, offline tests for the narrow `financial_comparison` path:
mandate parsing → per-leg coverage → structured claims → validation → engine.

Fixtures are clearly synthetic (ticker "TEST", invented figures) and never touch
production/JDdS data. Each assertion names the measure it protects: identity,
period/basis, coverage, citation validity, temporal admissibility, conflict
disclosure, calculation correctness, answer status.
"""

from __future__ import annotations

import pytest

from harness.research.claims import Synthesis, validate_claims
from harness.research.coverage import build_coverage
from harness.research.engine import run_research
from harness.research.mandate import from_model, parse_mandate
from harness.retrieval.contract import (
    EvidenceItem,
    FinancialRetrievalResult,
    NormalizedFinancialObject,
    SourceReference,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


def test_citation_period_is_ambiguous_safe():
    """A multi-period statement item must NOT label its source with the first
    (oldest) object's period — that would show the wrong year beside a source
    that supports a different one. Single-period evidence keeps its period."""
    from harness.research.citations import build_citations

    source = SourceReference(source="SEC EDGAR", sourceType="primary")
    multi = EvidenceItem(
        id="ev_multi", kind="structured", summary="statements", source=source,
        objects=[
            NormalizedFinancialObject(name="revenue", value=1, period="2019", source=source),
            NormalizedFinancialObject(name="revenue", value=2, period="2024", source=source),
        ],
    )
    single = EvidenceItem(
        id="ev_single", kind="filing", summary="fact", source=source,
        objects=[NormalizedFinancialObject(name="revenue", value=2, period="FY2024", source=source)],
    )
    citations = {c.evidenceId: c for c in build_citations([multi, single])}
    assert citations["ev_multi"].fiscalPeriod is None       # ambiguous → unknown
    assert citations["ev_single"].fiscalPeriod == "FY2024"  # unambiguous kept


def obj(
    name="revenue",
    value=1000.0,
    *,
    period="FY2024",
    basis=None,
    unit=None,
    currency="USD",
    instrument="TEST",
    category="structured",
    data_timestamp="2024-12-31",
    published_at=None,
):
    return NormalizedFinancialObject(
        name=name,
        value=value,
        period=period,
        basis=basis,
        unit=unit,
        currency=currency,
        instrument=instrument,
        dataTimestamp=data_timestamp,
        publishedAt=published_at,
        source=SourceReference(source="JDDS", sourceType=category, validationStatus="valid"),
    )


def evidence(eid, objects, *, kind="structured", source_type="structured", url=None):
    return EvidenceItem(
        id=eid,
        kind=kind,
        summary=f"{eid} evidence",
        objects=objects,
        source=SourceReference(source="JDDS", sourceType=source_type, url=url, validationStatus="valid"),
    )


def comparison_mandate(period_a="FY2023", period_b="FY2024", **kwargs):
    return parse_mandate(
        f"Compare TEST revenue in {period_a} vs {period_b}", ticker="TEST", **kwargs
    )


# ── Milestone 2 — mandate parsing ───────────────────────────────────────────


def test_mandate_classifies_financial_comparison():
    mandate = parse_mandate("Compare AAPL revenue in FY2023 vs FY2024", ticker="AAPL")
    assert mandate.taskType == "financial_comparison"
    assert mandate.supported
    assert mandate.entities[0].symbol == "AAPL"
    assert {leg.metric for leg in mandate.factLegs} == {"revenue"}
    assert {leg.period for leg in mandate.factLegs} == {"FY2023", "FY2024"}


def test_mandate_general_chat_is_unsupported():
    mandate = parse_mandate("What is a stock?")
    assert mandate.taskType == "general"
    assert not mandate.supported
    assert mandate.factLegs == []


def test_mandate_detects_quarter_and_basis_and_currency():
    mandate = parse_mandate(
        "Compare TEST net income Q1 2025 vs Q1 2024 on a standalone basis in EUR",
        ticker="TEST",
    )
    assert mandate.taskType == "financial_comparison"
    assert any(leg.basis == "standalone" for leg in mandate.factLegs)
    assert any(leg.currency == "EUR" for leg in mandate.factLegs)
    assert any(leg.period == "FY2025-Q1" for leg in mandate.factLegs)


def test_mandate_records_ambiguity_when_period_missing():
    mandate = parse_mandate("Compare TEST revenue quarter over quarter", ticker="TEST")
    assert mandate.taskType == "financial_comparison"
    assert mandate.ambiguity in ("period", "entity")


def test_mandate_unknown_metric_not_invented():
    mandate = parse_mandate("Compare TEST frobnitz FY2023 vs FY2024", ticker="TEST")
    # No known metric → not a supported comparison, no invented leg.
    assert mandate.taskType == "general"
    assert mandate.factLegs == []


def test_model_mandate_cannot_author_canonical_identity():
    payload = {
        "taskType": "financial_comparison",
        "objective": "x",
        "entities": [{"raw": "TEST", "symbol": "TEST", "canonical": {"market": "XX"}}],
        "factLegs": [
            {"id": "leg_revenue", "metric": "revenue", "entityRaw": "TEST", "period": "FY2024"}
        ],
    }
    mandate = from_model(payload, objective="x")
    assert mandate.source == "model"
    assert mandate.entities[0].canonical is None


def test_model_mandate_invalid_falls_back_to_deterministic():
    mandate = from_model({"taskType": "nonsense"}, objective="Compare TEST revenue FY2023 vs FY2024")
    assert "deterministic parse" in " ".join(mandate.parseWarnings)
    assert mandate.taskType == "financial_comparison"


# ── Milestone 3 — coverage gate ─────────────────────────────────────────────


def test_coverage_complete_for_correct_entity_and_facts():
    mandate = comparison_mandate()
    items = [
        evidence("ev_rev_23", [obj(value=800.0, period="FY2023")]),
        evidence("ev_rev_24", [obj(value=1000.0, period="FY2024")]),
    ]
    report = build_coverage(mandate, items)
    assert report.status == "accepted"
    assert report.coveredCount == 2
    assert all(leg.status == "covered" for leg in report.legs)


def test_coverage_unavailable_when_no_evidence():
    mandate = comparison_mandate()
    report = build_coverage(mandate, [])
    assert report.status == "rejected"
    assert report.missingCount >= 1


def test_coverage_wrong_period_is_no_matching_period_not_covered():
    mandate = comparison_mandate()
    items = [evidence("ev", [obj(value=800.0, period="FY2019")])]
    report = build_coverage(mandate, items)
    # The metric exists but no observation matches the requested fiscal period —
    # a distinct, precise status (not a generic "unknown").
    assert all(leg.status == "no_matching_period" for leg in report.legs)
    assert report.status == "partial"


def test_coverage_basis_mismatch_is_not_covered():
    mandate = parse_mandate(
        "Compare TEST revenue FY2023 vs FY2024 standalone", ticker="TEST"
    )
    items = [
        evidence("ev_c", [obj(value=800.0, period="FY2023", basis="consolidated")]),
        evidence("ev_c2", [obj(value=1000.0, period="FY2024", basis="consolidated")]),
    ]
    report = build_coverage(mandate, items)
    assert all(leg.status != "covered" for leg in report.legs)


def test_coverage_currency_mismatch_is_not_covered():
    mandate = parse_mandate(
        "Compare TEST revenue FY2023 vs FY2024 in EUR", ticker="TEST"
    )
    items = [
        evidence("ev_u", [obj(value=800.0, period="FY2023", currency="USD")]),
        evidence("ev_u2", [obj(value=1000.0, period="FY2024", currency="USD")]),
    ]
    report = build_coverage(mandate, items)
    assert all(leg.status != "covered" for leg in report.legs)


def test_coverage_wrong_instrument_is_not_covered():
    mandate = comparison_mandate()
    items = [
        evidence("ev_x", [obj(value=800.0, period="FY2023", instrument="OTHER")]),
        evidence("ev_x2", [obj(value=1000.0, period="FY2024", instrument="OTHER")]),
    ]
    report = build_coverage(mandate, items)
    assert all(leg.status != "covered" for leg in report.legs)


def test_coverage_web_snippet_never_satisfies_numeric_leg():
    mandate = comparison_mandate()
    # A web item carrying a revenue object must not satisfy a numeric leg.
    items = [
        evidence("ev_web", [obj(value=800.0, period="FY2023")], kind="web", source_type="secondary"),
        evidence("ev_web2", [obj(value=1000.0, period="FY2024")], kind="web", source_type="secondary"),
    ]
    report = build_coverage(mandate, items)
    assert all(leg.status != "covered" for leg in report.legs)


def test_coverage_conflict_marks_leg_conflicting():
    mandate = comparison_mandate()
    items = [
        evidence("ev_a", [obj(value=800.0, period="FY2023")]),
        evidence("ev_b", [obj(value=1200.0, period="FY2023")]),
        evidence("ev_24", [obj(value=1000.0, period="FY2024")]),
    ]
    conflicts = [{"metric": "revenue", "period": "FY2023", "candidates": [{"value": 800}, {"value": 1200}]}]
    report = build_coverage(mandate, items, conflicts=conflicts)
    assert report.conflictingCount >= 1
    assert report.status == "partial"


# ── Milestone 5 — point-in-time ─────────────────────────────────────────────


def test_asof_excludes_evidence_published_after_cutoff():
    mandate = comparison_mandate(as_of="2024-06-01")
    items = [
        evidence("ev_late", [obj(value=800.0, period="FY2023", published_at="2024-09-01")]),
        evidence("ev_ok", [obj(value=800.0, period="FY2023", published_at="2024-02-01")]),
    ]
    report = build_coverage(mandate, items)
    late_leg = next(l for l in report.legs if l.period == "FY2023")
    assert "ev_late" not in late_leg.evidenceIds
    assert "ev_ok" in late_leg.evidenceIds


def test_asof_unknown_publication_time_is_not_admissible():
    mandate = comparison_mandate(as_of="2024-06-01")
    items = [evidence("ev_nodate", [obj(value=800.0, period="FY2023", published_at=None)])]
    report = build_coverage(mandate, items)
    assert all(leg.status != "covered" for leg in report.legs)
    assert any(leg.status == "unknown" for leg in report.legs)


# ── Milestone 4 — claims + validation ───────────────────────────────────────


def test_validator_accepts_supported_reported_fact():
    mandate = comparison_mandate()
    items = [
        evidence("ev_rev_23", [obj(value=800.0, period="FY2023")]),
        evidence("ev_rev_24", [obj(value=1000.0, period="FY2024")]),
    ]
    coverage = build_coverage(mandate, items)
    synthesis = Synthesis(
        claims=[
            {
                "text": "FY2024 revenue was 1000 USD.",
                "kind": "reported_fact",
                "evidenceIds": ["ev_rev_24"],
                "legId": next(l.id for l in mandate.factLegs if l.period == "FY2024"),
            }
        ]
    )
    outcome = validate_claims(mandate, synthesis, items, coverage)
    assert outcome.status == "accepted"
    assert outcome.claims[0].supportStatus == "supported"


def test_validator_rejects_nonexistent_evidence_id():
    mandate = comparison_mandate()
    items = [evidence("ev_rev_23", [obj(value=800.0, period="FY2023")])]
    coverage = build_coverage(mandate, items)
    synthesis = Synthesis(
        claims=[{"text": "Revenue was 999.", "kind": "reported_fact", "evidenceIds": ["ev_ghost"]}]
    )
    outcome = validate_claims(mandate, synthesis, items, coverage)
    assert outcome.claims[0].supportStatus == "unsupported"
    assert any("does not exist" in i for i in outcome.claims[0].issues)


def test_validator_rejects_fabricated_citation_url():
    mandate = comparison_mandate()
    items = [evidence("ev_rev_23", [obj(value=800.0, period="FY2023")], url="https://real.example/10k")]
    coverage = build_coverage(mandate, items)
    synthesis = Synthesis(
        claims=[
            {
                "text": "Per the filing.",
                "kind": "qualitative_fact",
                "evidenceIds": ["ev_rev_23"],
                "citations": ["https://fabricated.example/fake"],
            }
        ]
    )
    outcome = validate_claims(mandate, synthesis, items, coverage)
    assert outcome.claims[0].supportStatus == "unsupported"
    assert any("not present in retrieved evidence" in i for i in outcome.claims[0].issues)


def test_validator_rejects_unverified_snippet_as_reported_fact():
    mandate = comparison_mandate()
    items = [evidence("ev_snip", [obj(value=800.0, period="FY2023")], kind="unverified")]
    coverage = build_coverage(mandate, items)
    synthesis = Synthesis(
        claims=[{"text": "Revenue was 800.", "kind": "reported_fact", "evidenceIds": ["ev_snip"]}]
    )
    outcome = validate_claims(mandate, synthesis, items, coverage)
    assert outcome.claims[0].supportStatus == "unsupported"


def test_validator_marks_derived_claim_without_registered_calculation():
    mandate = comparison_mandate()
    items = [evidence("ev_rev_23", [obj(value=800.0, period="FY2023")])]
    coverage = build_coverage(mandate, items)
    synthesis = Synthesis(
        claims=[
            {
                "text": "Revenue grew 25%.",
                "kind": "derived_fact",
                "calculationId": "calc_ghost",
            }
        ]
    )
    outcome = validate_claims(mandate, synthesis, items, coverage)
    assert outcome.claims[0].supportStatus == "unsupported"
    assert any("not registered" in i for i in outcome.claims[0].issues)


def test_validator_interpreparation_is_needs_review_not_verified():
    mandate = comparison_mandate()
    items = [
        evidence("ev_rev_23", [obj(value=800.0, period="FY2023")]),
        evidence("ev_rev_24", [obj(value=1000.0, period="FY2024")]),
    ]
    coverage = build_coverage(mandate, items)
    synthesis = Synthesis(
        claims=[{"text": "Growth was driven by new products.", "kind": "interpretation"}]
    )
    outcome = validate_claims(mandate, synthesis, items, coverage)
    assert outcome.claims[0].supportStatus == "needs_review"


def test_validator_surfaces_unmet_requirement_as_gap():
    mandate = comparison_mandate()
    items = [evidence("ev_rev_24", [obj(value=1000.0, period="FY2024")])]
    coverage = build_coverage(mandate, items)
    outcome = validate_claims(mandate, Synthesis(), items, coverage)
    assert outcome.status == "partial"
    # The unmet FY2023 leg surfaces as an explicit gap the answer must disclose.
    assert any("unmet requirement" in g for g in outcome.unresolved)


# ── Milestone 8 — engine end-to-end ─────────────────────────────────────────


class FakeResult:
    """A FinancialRetrievalResult factory that maps a leg to evidence."""


async def _retrieve_from(items):
    async def _retrieve(request):
        # Return every item whose objects mention the requested metric.
        metric = request.metadata.get("metric") if request.metadata else None
        matched = [i for i in items if any(o.name == metric for o in i.objects)]
        return FinancialRetrievalResult(
            status="OK" if matched else "UNAVAILABLE",
            objective=request.objective,
            dataType=request.dataType,
            instrument=request.instrument,
            evidence=matched,
        )

    return _retrieve


@pytest.mark.asyncio
async def test_engine_accepted_flow_and_receipt():
    mandate = comparison_mandate()
    items = [
        evidence("ev_rev_23", [obj(value=800.0, period="FY2023")]),
        evidence("ev_rev_24", [obj(value=1000.0, period="FY2024")]),
    ]
    outcome = await run_research(mandate, await _retrieve_from(items), run_id="r_test")
    assert outcome.status == "accepted"
    assert outcome.receipt is not None
    assert outcome.receipt.finalStatus == "accepted"
    assert outcome.receipt.runId == "r_test"
    assert len(outcome.receipt.coverage) == 2


@pytest.mark.asyncio
async def test_engine_partial_when_leg_missing():
    mandate = comparison_mandate()
    items = [evidence("ev_rev_24", [obj(value=1000.0, period="FY2024")])]
    outcome = await run_research(mandate, await _retrieve_from(items), run_id="r_partial")
    assert outcome.status == "partial"
    assert outcome.receipt.finalStatus == "partial"


@pytest.mark.asyncio
async def test_engine_general_mandate_returns_untouched():
    mandate = parse_mandate("Hello there")
    outcome = await run_research(mandate, await _retrieve_from([]), run_id="r_general")
    assert outcome.receipt is None
    assert not mandate.supported


@pytest.mark.asyncio
async def test_engine_synthesis_failure_is_honest_partial():
    mandate = comparison_mandate()

    async def _boom(*args, **kwargs):
        raise RuntimeError("model exploded")

    items = [
        evidence("ev_rev_23", [obj(value=800.0, period="FY2023")]),
        evidence("ev_rev_24", [obj(value=1000.0, period="FY2024")]),
    ]
    outcome = await run_research(
        mandate, await _retrieve_from(items), synthesize=_boom, run_id="r_boom"
    )
    assert outcome.status == "partial"
    assert any("synthesis failed" in g for g in outcome.validation.unresolved)


@pytest.mark.asyncio
async def test_engine_retrieval_error_is_unavailable_not_crash():
    mandate = comparison_mandate()

    async def _raise(request):
        raise RuntimeError("provider timeout")

    outcome = await run_research(mandate, _raise, run_id="r_err")
    assert outcome.status == "rejected"
    assert outcome.receipt.finalStatus == "rejected"

"""Universal Financial Data Accuracy — foundation test suite (§30).

A DIVERSE regression suite: the same engines are exercised across accounting and
business structures. No fixture is special-cased by ticker; KCHOL is simply one
row among many, and the assertions are about the RULES (definition, period,
consolidation, attribution, freshness, conflict, sector), never about a symbol.

Every fixture is synthetic. Nothing touches JDdS, the network, or a provider.
"""

from __future__ import annotations

import datetime as dt

import pytest

from harness.finance_facts import confidence, conflicts, freshness, fx, periods_ext, quality, sector, semantics, ttm
from harness.finance_facts.model import FinancialFact, FinancialPeriod


def _fact(
    metric: str,
    value,
    *,
    definition: str | None = None,
    period_type: str = "fy",
    period_end: str = "2025-12-31",
    fy: int | None = 2025,
    fq: int | None = None,
    currency: str | None = "USD",
    unit: str | None = "billions",
    source: str = "company annual report",
    source_type: str = "company_report",
    consolidation: str = "full",
    attribution: str = "group",
    entity_id: str = "US:TEST",
    pub: str | None = "2026-02-11T00:00:00Z",
    src_ts: str | None = None,
    definition_resolved: bool = True,
) -> FinancialFact:
    return FinancialFact(
        fact_id=f"{entity_id}:{metric}:{period_type}:{period_end}",
        metric=metric,
        definition=definition,
        value=value,
        currency=currency,
        unit=unit,
        entity_id=entity_id,
        ticker=entity_id.split(":")[-1],
        period=FinancialPeriod(period_type=period_type, period_end=period_end, fiscal_year=fy, fiscal_quarter=fq),
        publication_timestamp=pub,
        source_timestamp=src_ts,
        source=source,
        source_type=source_type,
        consolidation_level=consolidation,
        attribution=attribution,
        reported_or_derived="reported",
    )


# ── §3/§4: accounting semantics — related concepts are NOT interchangeable ──


def test_ambiguous_revenue_label_is_not_silently_resolved():
    assert semantics.is_ambiguous_label("revenue")
    # "net sales" is unambiguous; "revenue" could be any of several concepts.
    assert semantics.resolve_definition("net sales") == "net_sales"
    assert semantics.resolve_definition("revenue") is None


def test_revenue_and_net_sales_are_different_definitions():
    assert semantics.definitions_differ("revenue", "net_sales")


def test_net_income_family_is_separated_not_merged():
    assert semantics.resolve_definition("net income attributable to non-controlling interests") == "net_income_nci"
    assert semantics.resolve_definition("net income attributable to owners of the parent") == "net_income_parent"
    assert semantics.definitions_differ("net_income", "net_income_parent")
    assert semantics.definitions_differ("net_income_parent", "net_income_nci")


def test_debt_family_and_cash_family_are_distinct():
    for a, b in (
        ("gross_debt", "net_debt"),
        ("gross_debt", "financial_debt"),
        ("net_debt", "net_financial_debt"),
    ):
        assert semantics.definitions_differ(a, b)
    assert semantics.definitions_differ("cash", "restricted_cash")


# ── §3: period type ──────────────────────────────────────────────────────────


def test_fy_is_not_comparable_to_ttm():
    assert periods_ext.parse_period_type("FY2025") == "fy"
    assert periods_ext.parse_period_type("TTM") == "ttm"
    assert not periods_ext.periods_comparable("fy", "ttm")


def test_half_year_is_not_full_year():
    assert periods_ext.parse_period_type("H1 2026") == "half"
    assert not periods_ext.periods_comparable("half", "fy")


def test_ttm_window_spans_twelve_months():
    start, end = periods_ext.window_for("ttm", "2026-06-30")
    assert end == "2026-06-30"
    assert start == "2025-07-01"


# ── §5/§6: consolidation & attribution — two numbers can both be correct ────


def test_consolidated_vs_parent_earnings_is_a_semantic_conflict_not_an_error():
    consolidated = _fact("net_income", 46.9, definition="net_income", attribution="group")
    parent = _fact("net_income", 20.3, definition="net_income_parent", attribution="parent",
                   source="IFRS annual report")
    c = conflicts.detect_conflict(consolidated, parent)
    assert c is not None
    assert c.semantic is True, "different definitions are a semantic difference, not an error"
    assert c.preferred is None
    assert "definition" in c.explanation.lower()


def test_same_definition_different_values_is_a_real_conflict():
    a = _fact("revenue", 100.0, definition="net_sales", source="SEC filing", source_type="regulatory_filing")
    b = _fact("revenue", 130.0, definition="net_sales", source="aggregator", source_type="aggregator")
    c = conflicts.detect_conflict(a, b)
    assert c is not None and c.semantic is False
    # Higher-authority source is preferred, and the reason is stated.
    assert c.preferred == "a"
    assert c.reason


def test_reconcile_refuses_to_choose_on_a_hard_numeric_disagreement():
    a = _fact("revenue", 100.0, definition="net_sales", source="A", source_type="aggregator")
    b = _fact("revenue", 130.0, definition="net_sales", source="B", source_type="aggregator")
    chosen, cs = conflicts.reconcile([a, b])
    assert chosen is None
    assert cs and cs[0].semantic is False


def _bar(date: str, value: float, source: str = "yf") -> FinancialFact:
    return FinancialFact(
        fact_id=f"close:{date}", metric="close", definition=None, value=value, currency="USD", unit="USD",
        entity_id="US:X", period=FinancialPeriod(period_type="daily", period_end=date),
        source=source, source_type="market_data",
    )


def test_two_series_bars_are_not_a_conflict():
    """Regression: a different date is a different observation, not a disagreement."""
    assert conflicts.detect_conflict(_bar("2026-09-18", 1.5), _bar("2026-09-19", 2.5)) is None


def test_a_source_repeating_itself_is_not_a_conflict():
    a = _fact("revenue", 100.0, definition="revenue", source="JDDS", source_type="vault")
    b = _fact("revenue", 100.0, definition="revenue", source="JDDS", source_type="vault")
    assert conflicts.detect_conflict(a, b) is None


def test_two_labels_of_the_same_definition_are_comparable():
    a = _fact("total revenue", 100.0, definition="revenue", source="A", source_type="aggregator")
    b = _fact("revenue", 130.0, definition="revenue", source="B", source_type="aggregator")
    c = conflicts.detect_conflict(a, b)
    assert c is not None and not c.semantic


# ── §8: TTM engine ───────────────────────────────────────────────────────────


def _quarter(entity: str, end: str, value: float, *, metric="revenue", definition="revenue") -> FinancialFact:
    return FinancialFact(
        fact_id=f"{entity}:{metric}:{end}",
        metric=metric, definition=definition, value=value, currency="USD", unit="billions",
        entity_id=entity,
        period=FinancialPeriod(period_type="quarter", period_end=end),
        source="SEC filing", source_type="regulatory_filing", consolidation_level="full",
    )


def test_independent_ttm_sums_four_adjacent_quarters():
    quarters = [
        _quarter("E", "2025-09-30", 10.0),
        _quarter("E", "2025-12-31", 11.0),
        _quarter("E", "2026-03-31", 12.0),
        _quarter("E", "2026-06-30", 13.0),
    ]
    r = ttm.compute_ttm(quarters, "revenue", definition="revenue")
    assert r.status == "ok"
    assert r.ttm_value == 46.0
    assert len(r.quarters_used) == 4


def test_ttm_reconciles_against_vendor_and_flags_a_material_difference():
    quarters = [
        _quarter("E", "2025-09-30", 10.0),
        _quarter("E", "2025-12-31", 11.0),
        _quarter("E", "2026-03-31", 12.0),
        _quarter("E", "2026-06-30", 13.0),
    ]
    r = ttm.compute_ttm(quarters, "revenue", definition="revenue", vendor_value=40.0, vendor_source="vendorX")
    assert r.status == "conflict"
    assert r.checklist, "a TTM conflict must list what to investigate"


def test_ttm_refuses_mixed_currencies():
    quarters = [
        _quarter("E", "2025-09-30", 10.0),
        _quarter("E", "2025-12-31", 11.0),
        FinancialFact(fact_id="x", metric="revenue", definition="revenue", value=12.0, currency="EUR",
                      entity_id="E", period=FinancialPeriod(period_type="quarter", period_end="2026-03-31"),
                      source="s", source_type="regulatory_filing", consolidation_level="full"),
        _quarter("E", "2026-06-30", 13.0),
    ]
    r = ttm.compute_ttm(quarters, "revenue", definition="revenue")
    assert r.status == "not_comparable"


def test_ttm_refuses_a_missing_quarter():
    quarters = [
        _quarter("E", "2025-03-31", 10.0),
        _quarter("E", "2025-12-31", 11.0),  # a quarter is missing between these
        _quarter("E", "2026-03-31", 12.0),
        _quarter("E", "2026-06-30", 13.0),
    ]
    r = ttm.compute_ttm(quarters, "revenue", definition="revenue")
    assert r.status == "not_comparable"


# ── §14: per-metric freshness ────────────────────────────────────────────────


def test_price_goes_stale_quickly_but_a_filed_statement_does_not():
    now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc).timestamp()
    old_price = _fact("price", 100.0, period_type="daily", source_type="market_data",
                      source="feed", pub="2026-10-02T09:00:00Z")
    assert freshness.freshness_for(old_price, now=now) in ("STALE", "VERY_STALE", "RECENT")

    filed = _fact("revenue", 100.0, definition="revenue", pub="2020-02-11T00:00:00Z")
    # A reported historical revenue does not expire on a wall clock.
    assert freshness.freshness_for(filed, now=now) == "CURRENT"


# ── §20: confidence is derived, not felt ──────────────────────────────────────


def test_high_confidence_requires_a_strong_source_fresh_definition_period():
    f = _fact("revenue", 100.0, definition="revenue", source_type="regulatory_filing",
              pub=dt.datetime.now(dt.timezone.utc).isoformat())
    breakdown = confidence.confidence_for(f)
    assert breakdown.level == "high"


def test_confidence_drops_when_definition_is_ambiguous():
    f = _fact("revenue", 100.0, definition=None)  # unresolved definition
    breakdown = confidence.confidence_for(f)
    assert breakdown.level in ("low", "unverified")
    assert any("definition" in r for r in breakdown.reasons)


def test_conflicting_sources_cap_confidence():
    f = _fact("revenue", 100.0, definition="revenue", source_type="regulatory_filing")
    breakdown = confidence.confidence_for(f, cross_source_agreement=False)
    assert breakdown.level == "low"


# ── §12: sector awareness ─────────────────────────────────────────────────────


def test_bank_is_classified_and_flagged_financial():
    c = sector.classify("Acme Bank", "Banking")
    assert c.sector == "bank"
    assert c.contains_financial
    assert sector.financial_framework_warning(c)


def test_reit_and_crypto_and_insurance_classify_without_a_ticker():
    assert sector.classify("Some Real Estate Investment Trust").sector == "reit"
    assert sector.classify("Bitcoin", asset_type="crypto").sector == "crypto"
    assert sector.classify("Global Insurance Group").sector == "insurance"


def test_a_conglomerate_with_a_bank_is_flagged_financial():
    c = sector.classify("Diversified Holding Conglomerate", "banking and industrial operations")
    assert c.contains_financial


def test_unknown_entity_defaults_to_generic_not_a_guess():
    c = sector.classify("Unlabelled Thing")
    assert c.sector == "generic"
    assert c.confidence == "low"


def test_sector_metric_sets_are_distinct():
    assert "cet1" in sector.SECTOR_METRICS["bank"]
    assert "combined_ratio" in sector.SECTOR_METRICS["insurance"]
    assert "ffo" in sector.SECTOR_METRICS["reit"]
    assert "cet1" not in sector.SECTOR_METRICS["industrial"]


# ── §18: currency & unit ───────────────────────────────────────────────────────


def test_scale_words_convert_and_retain_the_original():
    nv = fx.normalize_scale(2.7, "trillions")
    assert nv.unit == "billions"
    assert nv.value == pytest.approx(2700.0)
    assert nv.original_value == 2.7 and nv.original_unit == "trillions"


def test_currency_conversion_requires_a_rate_and_basis():
    no_rate = fx.FXConversion("TRY", 100.0, "USD", None, None, None, "spot")
    assert fx.convert(100.0, no_rate) is None
    with_rate = fx.FXConversion("TRY", 100.0, "USD", 0.03, "2026-06-30", "cb", "spot")
    assert fx.convert(100.0, with_rate) == pytest.approx(3.0)


def test_unknown_currency_is_not_equal_to_a_known_one():
    assert not fx.same_currency(None, "USD")
    assert fx.same_currency("usd", "USD")


# ── §19/§23: N/A reasons and the ordered gate chain ───────────────────────────


def test_na_reason_distinguishes_negative_earnings_from_missing_data():
    neg = _fact("eps", -1.2, definition="eps")
    assert quality.na_reason(neg) == "negative_earnings"
    missing = _fact("eps", None, definition="eps")
    assert quality.na_reason(missing) == "missing_data"


def test_gate_chain_passes_a_complete_fact():
    f = _fact("revenue", 100.0, definition="revenue", source_type="regulatory_filing")
    report = quality.evaluate(f)
    assert report.passed
    assert [g.gate for g in report.gates] == list(quality.GATE_ORDER)


def test_gate_chain_excludes_a_fact_with_no_period():
    f = _fact("revenue", 100.0, definition="revenue")
    f = FinancialFact(**{**f.__dict__, "period": None})
    report = quality.evaluate(f)
    assert not report.passed
    assert "revenue" in report.exclusions


def test_gate_chain_discloses_stale_but_does_not_exclude_by_default():
    f = _fact("price", 100.0, period_type="daily", source_type="market_data",
              source="feed", pub="2020-01-01T00:00:00Z")
    report = quality.evaluate(f)
    # Staleness is a disclosure, not an exclusion, when allow_stale=True.
    assert "price" not in report.exclusions
    assert any(g.gate == "freshness" and g.disclosure for g in report.gates)


# ── §1: JDdS is not the source of truth — a vault fact loses to a filing ────


def test_vault_fact_is_not_authoritative_against_a_filing():
    from_vault = _fact("revenue", 90.0, definition="revenue", source="JDDS", source_type="vault")
    from_filing = _fact("revenue", 100.0, definition="revenue", source="SEC 10-K", source_type="regulatory_filing")
    c = conflicts.detect_conflict(from_vault, from_filing)
    assert c is not None
    assert c.preferred == "b", "the filing must outrank the vault when they disagree"
    assert "authoritative" in (c.reason or "").lower()


# ── §7: P/B must use COMMON equity, not total equity ─────────────────────────


def test_pb_should_use_common_equity_definition():
    assert semantics.definitions_differ("total_equity", "common_equity")
    d = semantics.definition("common_equity")
    assert d is not None and d.is_shareholder_attributable


# ── wiring: a retrieval result summary carries the data-quality notes ────────


def test_summary_surfaces_definition_ambiguity_and_sector_but_not_metadata():
    from harness.retrieval.contract import (
        EvidenceItem, FinancialRetrievalResult, InstrumentIdentity,
        NormalizedFinancialObject, SourceReference,
    )
    from harness.retrieval_tools import _summarize

    ident = InstrumentIdentity(market="TR", symbol="TEST", currency="TRY",
                                assetClass="equity", name="Anadolu Holding", securityType="Holding")
    ref = SourceReference(source="annual report", sourceType="primary")
    objs = [
        NormalizedFinancialObject(name="revenue", value=2.7e12, unit="TRY", currency="TRY",
                                  period="FY2025", dataTimestamp="2025-12-31", identity=ident,
                                  source=ref, basis="consolidated"),
        NormalizedFinancialObject(name="sector", value="Holding", identity=ident, source=ref),
    ]
    ev = EvidenceItem(id="e1", kind="structured", summary="snapshot", objects=objs, source=ref)
    r = FinancialRetrievalResult(status="OK", objective="x", dataType="company_profile",
                                 instrument="TEST", identity=ident, evidence=[ev],
                                 sourceReferences=[ref], strategy=["JDDS"], freshness="slow", quality="valid")
    text = _summarize(r)
    assert "Data-quality notes:" in text
    assert "revenue" in text and "definition" in text.lower()
    # The metadata field `sector` is NOT reported as an ambiguous financial metric.
    assert "sector" not in text.split("Data-quality notes:")[1]
    # A holding company is classified (the framework warning is present).
    assert "financial" in text.lower() or "holding" in text.lower()


def test_analysis_returns_validated_facts_and_gate_verdicts():
    from harness.finance_facts.analysis import analyze_result
    from harness.retrieval.contract import (
        EvidenceItem, FinancialRetrievalResult, InstrumentIdentity,
        NormalizedFinancialObject, SourceReference,
    )

    ident = InstrumentIdentity(market="US", symbol="TEST", currency="USD", assetClass="equity")
    ref = SourceReference(source="SEC 10-K", sourceType="primary")
    objs = [
        NormalizedFinancialObject(name="total revenue", value=400.0, unit="USD", currency="USD",
                                  period="FY2025", dataTimestamp="2025-12-31", identity=ident, source=ref),
        NormalizedFinancialObject(name="price", value=100.0, unit="USD", currency="USD",
                                  dataTimestamp=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  identity=ident, source=SourceReference(source="feed", sourceType="structured")),
    ]
    ev = EvidenceItem(id="e1", kind="structured", summary="s", objects=objs, source=ref)
    r = FinancialRetrievalResult(status="OK", objective="x", dataType="company_profile",
                                 instrument="TEST", identity=ident, evidence=[ev],
                                 sourceReferences=[ref], strategy=["JDDS"], freshness="slow", quality="valid")
    a = analyze_result(r)
    metrics = {f.metric: f for f in a.facts}
    # A fully-described revenue fact passes; the price (live, unit present) too.
    assert metrics["total revenue"].quality_passed
    assert metrics["total revenue"].definition == "revenue"
    assert metrics["total revenue"].confidence in ("high", "medium")
    assert metrics["price"].quality_passed
    assert a.presentable, a.excluded
    payload = a.to_dict()
    assert payload["facts"] and "confidence" in payload["facts"][0]


def test_analysis_excludes_an_ambiguous_revenue_from_a_clean_answer():
    from harness.finance_facts.analysis import analyze_result
    from harness.retrieval.contract import (
        EvidenceItem, FinancialRetrievalResult, InstrumentIdentity,
        NormalizedFinancialObject, SourceReference,
    )

    ident = InstrumentIdentity(market="TR", symbol="TEST", currency="TRY", assetClass="equity")
    ref = SourceReference(source="annual report", sourceType="primary")
    # Bare "revenue" is ambiguous → must be withheld, not presented as a clean fact.
    objs = [NormalizedFinancialObject(name="revenue", value=2.7e12, unit="TRY", currency="TRY",
                                      period="FY2025", dataTimestamp="2025-12-31", identity=ident, source=ref)]
    ev = EvidenceItem(id="e1", kind="structured", summary="s", objects=objs, source=ref)
    r = FinancialRetrievalResult(status="OK", objective="x", dataType="company_profile",
                                 instrument="TEST", identity=ident, evidence=[ev],
                                 sourceReferences=[ref], strategy=["JDDS"], freshness="slow", quality="valid")
    a = analyze_result(r)
    assert not a.presentable
    assert "revenue" in a.excluded





# ── adapter: the existing retrieval contract lifts into a fact ───────────────


def test_adapter_lifts_a_normalized_object_into_a_fact_without_guessing():
    from harness.finance_facts.adapter import to_fact
    from harness.retrieval.contract import NormalizedFinancialObject, SourceReference

    obj = NormalizedFinancialObject(
        name="net sales",
        value=2.7e12,
        unit="billions",
        currency="TRY",
        dataTimestamp="2025-12-31",
        period="FY2025",
        basis="consolidated",
        publishedAt="2026-02-11",
        instrument="TEST",
        source=SourceReference(source="annual report", sourceType="primary"),
    )
    f = to_fact(obj)
    assert f.definition == "net_sales"
    assert f.period is not None and f.period.period_type == "fy"
    assert f.consolidation_level == "full"
    assert f.source_type in ("regulatory_filing", "company_report")
    # The adapter never fabricates a definition for an ambiguous label.
    obj2 = NormalizedFinancialObject(name="revenue", value=1.0, source=SourceReference(source="x"))
    assert to_fact(obj2).definition is None


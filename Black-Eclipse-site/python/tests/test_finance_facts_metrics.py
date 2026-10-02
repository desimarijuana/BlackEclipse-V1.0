"""Universal Financial Data Accuracy — derived metrics, corporate actions, evidence
graph (foundation suite continued, §9/§17/§21).

Same principle as test_finance_facts.py: rules, not tickers. All synthetic.
"""

from __future__ import annotations

import pytest

from harness.finance_facts import corporate_actions as ca
from harness.finance_facts import evidence, metrics
from harness.finance_facts.model import CorporateAction, FinancialFact, FinancialPeriod


def _fact(metric, definition, value, *, currency="USD", period_type="fy", period_end="2025-12-31",
          source="SEC", source_type="regulatory_filing", attribution="group") -> FinancialFact:
    return FinancialFact(
        fact_id=f"{metric}:{definition}:{period_end}",
        metric=metric, definition=definition, value=value, currency=currency, unit="billions",
        entity_id="US:TEST",
        period=FinancialPeriod(period_type=period_type, period_end=period_end, fiscal_year=2025),
        source=source, source_type=source_type, consolidation_level="full", attribution=attribution,
    )


# ── §9: derived metrics expose formula + inputs + periods + sources ───────────


def test_pb_uses_common_equity_not_total_equity():
    facts = [
        _fact("marketCap", "market_cap", 1000.0),
        _fact("totalEquity", "total_equity", 800.0),
        _fact("commonEquity", "common_equity", 500.0),
    ]
    d = metrics.derive("pb_ratio", facts)
    assert d.value == pytest.approx(2.0)  # 1000 / 500 (common), NOT 1000/800
    assert d.formula == "market_cap / common_equity"
    assert d.input_periods and d.input_sources
    assert d.calculated_at


def test_roe_uses_parent_attributable_earnings():
    facts = [
        _fact("netIncome", "net_income_parent", 50.0, attribution="parent"),
        _fact("equity", "parent_equity", 500.0, attribution="parent"),
    ]
    d = metrics.derive("roe", facts)
    assert d.value == pytest.approx(10.0)
    assert "%" == d.unit


def test_derivation_refuses_mixed_currencies():
    facts = [
        _fact("marketCap", "market_cap", 1000.0, currency="USD"),
        _fact("eps", "eps", 10.0, currency="EUR"),
    ]
    with pytest.raises(metrics.DerivationError):
        metrics.derive("pe_ratio", facts)


def test_derivation_refuses_mixed_period_types():
    facts = [
        _fact("marketCap", "market_cap", 1000.0, period_type="fy"),
        _fact("eps", "eps", 10.0, period_type="quarter"),
    ]
    with pytest.raises(metrics.DerivationError):
        metrics.derive("pe_ratio", facts)


def test_pe_is_undefined_for_negative_earnings():
    facts = [_fact("price", "price", 100.0, period_type="daily"), _fact("eps", "eps", -2.0)]
    with pytest.raises(metrics.DerivationError):
        metrics.derive("pe_ratio", facts)


def test_growth_rate_validates_both_periods_and_sources():
    prior = _fact("revenue", "revenue", 100.0, period_end="2024-12-31")
    current = _fact("revenue", "revenue", 147.0, period_end="2025-12-31")
    d = metrics.growth_rate(current, prior)
    assert d.value == pytest.approx(47.0)
    assert len(d.input_periods) == 2
    assert len(d.input_fact_ids) == 2


def test_growth_rate_refuses_across_different_definitions():
    prior = _fact("revenue", "revenue", 100.0)
    current = _fact("revenue", "net_sales", 147.0)
    with pytest.raises(metrics.DerivationError):
        metrics.growth_rate(current, prior)


# ── §17: corporate actions ────────────────────────────────────────────────────


def test_split_adjustment_halves_a_pre_split_price():
    assert ca.adjust_for_split(200.0, 2.0) == pytest.approx(100.0)
    assert ca.adjust_for_split(100.0, 2.0, reverse=True) == pytest.approx(200.0)
    assert ca.adjust_for_split(100.0, None) is None


def test_a_split_is_disclosed_as_a_basis_change():
    action = CorporateAction(kind="split", effective_date="2026-03-01", ratio=2.0)
    notices = ca.comparability_disclosure([action], "2025-01-01", "2026-06-30")
    assert notices and notices[0].affects == "price"


def test_a_spinoff_changes_identity_not_just_price():
    action = CorporateAction(kind="spinoff", effective_date="2026-01-15")
    notices = ca.comparability_disclosure([action], "2025-01-01", "2026-06-30")
    assert notices and notices[0].affects == "identity"


def test_no_action_in_window_yields_no_disclosure():
    action = CorporateAction(kind="split", effective_date="2020-01-01", ratio=2.0)
    assert ca.comparability_disclosure([action], "2025-01-01", "2026-06-30") == []


# ── §21: evidence graph ────────────────────────────────────────────────────────


def test_evidence_graph_traces_a_claim_to_its_source():
    g = evidence.EvidenceGraph()
    price = _fact("price", "price", 206.80, period_type="daily", source="MarketFeed", source_type="market_data")
    eps = _fact("eps", "eps", 13.79, source="SEC")
    pf = evidence.add_fact(g, price)
    ef = evidence.add_fact(g, eps)
    d = metrics.derive("pe_ratio", [price, eps])
    did = evidence.add_derived(g, d)
    cid = evidence.add_claim(g, "claim1", "P/E is about 15x", [did])

    sources = g.trace_to_sources(cid)
    assert any("MarketFeed" in s for s in sources)
    assert any("SEC" in s for s in sources)
    assert g.orphans() == []


def test_evidence_graph_flags_an_unsupported_claim():
    g = evidence.EvidenceGraph()
    evidence.add_claim(g, "lonely", "Revenue grew 147%", [])
    defects = g.orphans()
    assert defects and "lonely" in defects[0]


def test_evidence_graph_flags_a_fact_with_no_source():
    g = evidence.EvidenceGraph()
    f = FinancialFact(fact_id="nosrc", metric="revenue", value=1.0, entity_id="US:X")
    g.add_node(evidence.Node("nosrc", "fact", "revenue=1"))
    defects = g.orphans()
    assert any("nosrc" in d for d in defects)

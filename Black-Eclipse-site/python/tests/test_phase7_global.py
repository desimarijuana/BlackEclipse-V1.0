"""Phase 7 — global market research.

Deterministic and offline. Covers:
  * exchange-suffix → market inference and the SEC eligibility gate (no SEC for
    non-US issuers),
  * market-aware escalation queries (no US 10-K assumption for non-US issuers),
  * provider-switch when a structured source is ineligible,
  * cross-region coverage classification (fiscal label ≠ calendar year, currency).

All fixtures are synthetic and never touch production/JDdS data.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.research.escalation import _build_query
from harness.research.mandate import parse_mandate
from harness.retrieval.contract import FinancialRetrievalRequest
from harness.retrieval.planner import SEC_FILINGS, STRUCTURED_VAULT, WEB, plan_retrieval
from harness.retrieval.structured import SecFilingsSource, infer_market_from_symbol
from harness.tools import DataBridge


# ── Exchange-suffix inference ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "symbol,market",
    [
        ("2330.TW", "TW"),
        ("005930.KS", "KR"),
        ("PETR4.SA", "BR"),
        ("BHP.AX", "AU"),
        ("SHEL.L", "UK"),
        ("7203.T", "JP"),
        ("RELIANCE.NS", "IN"),
        ("0700.HK", "HK"),
        ("6758.T", "JP"),
    ],
)
def test_suffix_infers_market(symbol, market):
    assert infer_market_from_symbol(symbol) == market


def test_unknown_suffix_is_not_guessed():
    assert infer_market_from_symbol("BRK.B") is None
    assert infer_market_from_symbol("PLAIN") is None
    assert infer_market_from_symbol(None) is None


# ── SEC eligibility gate (Workstream C) ─────────────────────────────────────


@pytest.mark.parametrize(
    "symbol,market",
    [
        ("2330.TW", None),
        ("005930.KS", None),
        ("PETR4.SA", None),
        ("SHEL.L", None),
        ("RELIANCE.NS", None),
        ("BHP", "AU"),
        ("XYZ", "JP"),
    ],
)
def test_sec_ineligible_for_non_us(symbol, market):
    source = SecFilingsSource(bridge=_StubBridge())
    request = FinancialRetrievalRequest(
        objective="revenue", dataType="financial_statements", instrument=symbol, market=market,
    )
    assert source.eligible(request) is False
    assert source.available(request) is False


@pytest.mark.parametrize(
    "symbol,market",
    [("NVDA", "US"), ("AAPL", None), ("TSM", "US")],
)
def test_sec_eligible_for_us(symbol, market):
    source = SecFilingsSource(bridge=_StubBridge())
    request = FinancialRetrievalRequest(
        objective="revenue", dataType="financial_statements", instrument=symbol, market=market,
    )
    assert source.eligible(request) is True


def test_sec_not_eligible_for_non_statement_types():
    source = SecFilingsSource(bridge=_StubBridge())
    request = FinancialRetrievalRequest(objective="price", dataType="current_quote", instrument="NVDA", market="US")
    assert source.available(request) is False


# ── Provider routing: ineligible SEC does not run; the next route does ───────


class _StubBridge(DataBridge):
    def __init__(self, payloads: dict[str, dict] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._payloads = payloads or {}

    async def fetch(self, capability: str, params: dict):
        self.calls.append((capability, params))
        return self._payloads.get(capability, {"status": "OK", "symbol": params.get("symbol"), "currency": "TWD", "periods": [{"endDate": "2025-12-31", "revenue": 1}]})


def test_sec_skipped_for_non_us_and_planner_continues():
    """A non-US statement request must not call sec_filings; it reaches the vault."""
    bridge = _StubBridge()
    from harness.retrieval.layer import FinancialRetrievalLayer

    layer = FinancialRetrievalLayer(bridge)
    request = FinancialRetrievalRequest(
        objective="revenue for 2330.TW", dataType="financial_statements", instrument="2330.TW",
        market="TW", metadata={"metric": "revenue", "period": "FY2024"},
    )
    result = asyncio.run(layer.retrieve(request))
    capabilities = [c for c, _ in bridge.calls]
    assert "sec_filings" not in capabilities, capabilities
    # The vault was still tried.
    assert "financial_statements" in capabilities
    assert result.status in ("OK", "UNAVAILABLE")


def test_planner_lists_sec_first_but_eligibility_filters_it():
    request = FinancialRetrievalRequest(objective="x", dataType="financial_statements", instrument="2330.TW", market="TW")
    plan = plan_retrieval(request)
    assert plan.sources == [SEC_FILINGS, STRUCTURED_VAULT, WEB]


# ── Market-aware escalation queries ─────────────────────────────────────────


def _mandate(entity: str, market: str | None = None):
    return parse_mandate(f"Compare {entity} revenue for FY2024 in USD", ticker=entity, market=market)


def test_escalation_query_uses_10k_only_for_us():
    mandate = _mandate("AAA")
    mandate.entities[0].market = "US"
    leg = mandate.factLegs[0]
    assert "10-K" in _build_query(leg, mandate)


@pytest.mark.parametrize(
    "market,hint_marker",
    [
        ("TW", "MOPS"),
        ("KR", "DART"),
        ("JP", "TDnet"),
        ("UK", "Companies House"),
        ("BR", "CVM"),
        ("CA", "SEDAR"),
        ("AU", "ASX"),
    ],
)
def test_escalation_query_uses_local_filing_hint(market, hint_marker):
    """Each market asks for its OWN locally authoritative filing system."""
    mandate = _mandate("AAA")
    mandate.entities[0].market = market
    leg = mandate.factLegs[0]
    query = _build_query(leg, mandate)
    assert "10-K" not in query
    assert hint_marker in query


def test_escalation_query_generic_fallback_for_market_without_hint():
    mandate = _mandate("AAA")
    mandate.entities[0].market = "ZZ"
    leg = mandate.factLegs[0]
    query = _build_query(leg, mandate)
    assert "10-K" not in query
    assert "annual report regulatory filing" in query


def test_classifier_labels_local_filing_hosts_as_primary():
    from harness.retrieval.web import classify_source_tier

    assert classify_source_tier("mops.twse.com.tw", "https://mops.twse.com.tw/x") == "primary"
    assert classify_source_tier("dart.fss.or.kr", "https://dart.fss.or.kr/x") == "primary"
    assert classify_source_tier("www.sedar.com", "https://www.sedar.com/x") == "primary"
    # A random blog is never promoted to primary.
    assert classify_source_tier("randomblog.example", "https://randomblog.example/x") == "secondary"


# ── Cross-region coverage classification (label vs calendar; currency) ───────


def test_fiscal_label_does_not_equal_calendar_year():
    """A TWD issuer with a Dec year-end still requires its own label, not a guess."""
    from harness.research.coverage import evaluate_leg
    from harness.research.mandate import FactLeg
    from harness.retrieval.contract import (
        EvidenceItem, NormalizedFinancialObject, SourceReference,
    )

    leg = FactLeg(
        id="leg_revenue_FY2024", metric="revenue", entityRaw="2330.TW", entitySymbol="2330.TW",
        market="TW", period="FY2024", currency="TWD", required=True,
    )
    source = SourceReference(source="TWSE", sourceType="primary")
    obj = NormalizedFinancialObject(
        name="revenue", value=2894310000000, currency="TWD",
        period=None, dataTimestamp="2024-12-31", instrument="2330.TW", source=source,
    )
    item = EvidenceItem(id="ev", kind="filing", summary="s", objects=[obj], source=source)
    coverage = evaluate_leg(leg, [item], asof=None, conflicts=[])
    assert coverage.status in ("covered", "qualified")


def test_currency_mismatch_rejected_cross_region():
    from harness.research.coverage import evaluate_leg
    from harness.research.mandate import FactLeg
    from harness.retrieval.contract import (
        EvidenceItem, NormalizedFinancialObject, SourceReference,
    )

    leg = FactLeg(
        id="leg_revenue_FY2024", metric="revenue", entityRaw="2330.TW", entitySymbol="2330.TW",
        market="TW", period="FY2024", currency="TWD", required=True,
    )
    source = SourceReference(source="x", sourceType="primary")
    obj = NormalizedFinancialObject(
        name="revenue", value=100, currency="USD",  # wrong currency
        period=None, dataTimestamp="2024-12-31", instrument="2330.TW", source=source,
    )
    item = EvidenceItem(id="ev", kind="filing", summary="s", objects=[obj], source=source)
    coverage = evaluate_leg(leg, [item], asof=None, conflicts=[])
    assert coverage.status != "covered"

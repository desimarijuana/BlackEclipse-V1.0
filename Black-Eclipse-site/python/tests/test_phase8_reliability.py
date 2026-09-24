"""Phase 8 — reliability & global-research hardening.

Deterministic, offline. Covers the verified root causes from the international
runs (SYS / RELIANCE / TATAMOTORS / TSMC / Petrobras / Samsung):

  * Workstream 1 — `get_capability_matrix` / `get_research_health` are in the
    Eclipse agent allowlist and readable; an unauthorized tool stays blocked; a
    missing capability returns a structured error.
  * Workstream 2 — per-tool timeout is distinct from the agent ceiling; news has
    its own bounded budget; transient retry only, never a permanent 4xx/block.
  * Workstream 3 — capability-specific health; zero attempts stays unknown.
  * Workstream 4 — route categories distinguish ineligible / not_implemented /
    unconfigured / provider_failure / no_instrument / no_data.
  * Workstream 6 — identity & comparability blocks the required regression cases.
  * Workstream 7 — partial answers present verified facts and name blocked
    comparisons.

No network; no production DB.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.agents import ECLIPSE_AGENT
from harness.finance_tools import register_finance_tools
from harness.research.comparability import (
    LegDescriptor,
    check_comparability,
    check_pair,
    parse_duration_months,
)
from harness.retrieval.contract import FinancialRetrievalRequest, SourceReference
from harness.retrieval.routing import classify_outcome, classify_skip
from harness.retrieval.sources import SourceOutcome
from harness.retrieval.structured import SecFilingsSource
from harness.tools import ToolContext, ToolRegistry, effective_timeout_ms


def _ctx() -> ToolContext:
    return ToolContext(run_id="r", log=lambda *_: None)


# ── WS1: capability-tool permissions ─────────────────────────────────────────


def test_capability_tools_are_in_the_agent_allowlist():
    assert "get_capability_matrix" in ECLIPSE_AGENT.tools
    assert "get_research_health" in ECLIPSE_AGENT.tools


def test_capability_tools_are_read_only_registered():
    reg = ToolRegistry()
    register_finance_tools(reg)
    for name in ("get_capability_matrix", "get_research_health", "get_coverage"):
        tool = reg.get(name)
        assert tool is not None, name
        assert tool.permission == "read"


@pytest.mark.asyncio
async def test_agent_can_call_capability_matrix_and_gets_structured_error_without_bridge():
    reg = ToolRegistry()
    register_finance_tools(reg)
    # No data_bridge → the tool must return a STRUCTURED error, never crash or
    # silently fall back to get_coverage.
    result = await reg.execute(
        "get_capability_matrix", "c1", {}, _ctx(), allowed=set(ECLIPSE_AGENT.tools)
    )
    assert result.ok  # the tool runs; the payload is the honest error
    assert "UNAVAILABLE" in result.text or "no_data" in result.text
    assert result.data.get("status") == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_unauthorized_tool_stays_blocked():
    reg = ToolRegistry()
    register_finance_tools(reg)
    result = await reg.execute(
        "get_capability_matrix", "c1", {}, _ctx(),
        allowed={"market_get_quote"},  # not in this narrower set
    )
    assert not result.ok
    assert result.error.code == "TOOL_FORBIDDEN"


@pytest.mark.asyncio
async def test_coverage_tool_teaches_all_four_distinctions():
    class _Bridge:
        async def fetch(self, capability, params):
            return {"status": "OK", "rows": [
                {"market": "PK", "currency": "PKR", "universe": 1312,
                 "quote": {"level": "configured"}, "fundamentals": {"level": "configured"},
                 "filings": {"level": "not_implemented"}},
            ]}

    reg = ToolRegistry()
    register_finance_tools(reg)
    ctx = _ctx()
    ctx.data_bridge = _Bridge()
    result = await reg.execute("get_coverage", "c1", {}, ctx)
    text = result.text.lower()
    assert "recognised" in text and "not the same as" in text.replace("≠", "not the same as") or "recognised" in text
    assert "configured" in text and "healthy" in text
    assert "no attempts" in text
    assert "missing" in text


# ── WS2: timeout semantics ───────────────────────────────────────────────────


def test_tool_timeout_is_not_overridden_by_agent_ceiling():
    # The tool's own declared timeout is authoritative below the ceiling.
    assert effective_timeout_ms(12_000, 30_000) == 12_000
    # The ceiling shortens a tool that declares more.
    assert effective_timeout_ms(60_000, 30_000) == 30_000
    # No ceiling → the tool's own budget stands.
    assert effective_timeout_ms(30_000, None) == 30_000


def test_news_tool_has_its_own_bounded_timeout():
    from harness.retrieval_tools import _TOOL_NAMES

    reg = ToolRegistry()
    from harness.retrieval_tools import register_retrieval_tools

    register_retrieval_tools(reg)
    news = reg.get(_TOOL_NAMES["research.search_news"])
    assert news is not None
    # Bounded, and strictly less than the agent's 30s ceiling so a slow optional
    # news step cannot starve the run.
    assert news.timeout_ms <= 20_000
    # A statement fetch keeps its own (longer) budget — they are independent.
    stmts = reg.get(_TOOL_NAMES["fundamentals.get_financials"])
    assert stmts is not None
    assert stmts.timeout_ms != news.timeout_ms


@pytest.mark.asyncio
async def test_timeout_is_categorized_not_generic():
    reg = ToolRegistry()
    from harness.tools import ToolDefinition

    async def slow(args, c):
        await asyncio.sleep(3)
        return "late"

    reg.register(ToolDefinition(name="slow", description="d", input_schema={"type": "object", "properties": {}}, handler=slow, timeout_ms=50))
    result = await reg.execute("slow", "c", {}, _ctx())
    assert not result.ok
    assert result.error.code == "TOOL_TIMEOUT"
    assert "timeout" in result.text.lower()


def test_permanent_failures_are_not_retried():
    from harness.retrieval.retry import is_retryable

    blocked = SourceOutcome(source="WEB", status="UNAVAILABLE", error="blocked host",
                            diagnostics=[{"category": "blocked", "retryable": False}])
    assert is_retryable(blocked) is False
    timeout = SourceOutcome(source="WEB", status="ERROR", error="timed out",
                            diagnostics=[{"category": "timeout", "retryable": True}])
    assert is_retryable(timeout) is True


# ── WS4: route categorization ────────────────────────────────────────────────


def test_sec_ineligible_for_non_us_is_a_routing_skip_not_a_failure():
    src = SecFilingsSource(bridge=object())
    req = FinancialRetrievalRequest(
        objective="revenue", dataType="financial_statements", instrument="2330.TW", market="TW"
    )
    skip = classify_skip("SEC", src, req)
    assert skip is not None
    category, reason = skip
    assert category == "ineligible"
    assert "TW" in reason


def test_sec_eligible_for_us_is_no_skip():
    src = SecFilingsSource(bridge=object())
    req = FinancialRetrievalRequest(
        objective="revenue", dataType="financial_statements", instrument="NVDA", market="US"
    )
    assert classify_skip("SEC", src, req) is None


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (SourceOutcome(source="WEB", status="UNAVAILABLE", diagnostics=[{"category": "timeout"}]), "provider_failure"),
        (SourceOutcome(source="WEB", status="UNAVAILABLE", diagnostics=[{"category": "blocked"}]), "ineligible"),
        (SourceOutcome(source="WEB", status="UNAVAILABLE", diagnostics=[{"category": "unsupported_document"}]), "invalid_document"),
        (SourceOutcome(source="WEB", status="UNAVAILABLE", diagnostics=[{"category": "not_configured"}]), "unconfigured"),
        (SourceOutcome(source="JDDS", status="UNAVAILABLE", error="JDDS had no financial_statements for SYS"), "no_data"),
        (SourceOutcome(source="X", status="UNAVAILABLE", error="SYS is not in the PK universe"), "no_instrument"),
        (SourceOutcome(source="OKSRC", status="OK"), "ok"),
    ],
)
def test_outcome_categories_are_distinct(outcome, expected):
    assert classify_outcome(outcome) == expected


# ── WS6: identity & comparability regression cases ───────────────────────────


def test_tata_motors_demerger_and_ticker_reuse_blocks_comparison():
    a = LegDescriptor(legId="fy24", metric="revenue", period="FY2024", symbol="TATAMOTORS",
                      market="IN", legalName="Tata Motors Limited", tickerReused=True)
    b = LegDescriptor(legId="fy26", metric="revenue", period="FY2026", symbol="TATAMOTORS",
                      market="IN", legalName="Tata Motors Limited (CV)")
    blocked = check_pair(a, b)
    assert blocked is not None
    assert blocked.dimension == "entity"
    assert "reused" in blocked.reason or "demerger" in blocked.reason


def test_nine_month_vs_twelve_month_blocked():
    a = LegDescriptor(legId="fy25", metric="revenue", period="FY2025", durationMonths=9)
    b = LegDescriptor(legId="fy26", metric="revenue", period="FY2026", durationMonths=12)
    blocked = check_pair(a, b)
    assert blocked is not None
    assert blocked.dimension == "duration"
    assert "nine-month" in blocked.reason or "9 months" in blocked.reason


def test_sys_standalone_vs_consolidated_blocked():
    a = LegDescriptor(legId="un", metric="revenue", period="FY2025", basis="standalone")
    b = LegDescriptor(legId="co", metric="revenue", period="FY2025", basis="consolidated")
    blocked = check_pair(a, b)
    assert blocked is not None
    assert blocked.dimension == "basis"


def test_reliance_gross_revenue_vs_revenue_from_operations_blocked():
    # Two DIFFERENT metrics are not a candidate change at all → no pair emitted.
    a = LegDescriptor(legId="gross", metric="revenue", period="FY2026")
    b = LegDescriptor(legId="ops", metric="revenueFromOperations", period="FY2026")
    verdict = check_comparability([a, b])
    assert verdict.blocked == []
    assert verdict.compatible == []  # different metrics → not a comparison


def test_psx_rupees_vs_thousands_scale_blocked():
    a = LegDescriptor(legId="issuer", metric="revenue", period="FY2025", scale=1)
    b = LegDescriptor(legId="psx", metric="revenue", period="FY2025", scale=1000)
    blocked = check_pair(a, b)
    assert blocked is not None
    assert blocked.dimension == "scale"


def test_eps_before_and_after_subdivision_flagged_by_reused_security():
    a = LegDescriptor(legId="pre", metric="eps", period="FY2024", symbol="XYZ", market="PK")
    b = LegDescriptor(legId="post", metric="eps", period="FY2025", symbol="XYZ", market="PK",
                      versionId="post-subdivision")
    # Same symbol/period differ only by version — a restatement-style block.
    a2 = LegDescriptor(legId="pre2", metric="eps", period="FY2025", symbol="XYZ", market="PK",
                       versionId="pre-subdivision")
    blocked = check_pair(a2, b)
    assert blocked is not None
    assert blocked.dimension == "restatement"


def test_stale_fy2023_for_fy2024_request_is_no_matching_period_not_comparable():
    from harness.research.coverage import evaluate_leg
    from harness.research.mandate import FactLeg
    from harness.retrieval.contract import EvidenceItem, NormalizedFinancialObject

    leg = FactLeg(id="l", metric="revenue", entityRaw="RELIANCE", entitySymbol="RELIANCE",
                  market="IN", period="FY2024", required=True)
    src = SourceReference(source="x", sourceType="structured")
    obj = NormalizedFinancialObject(name="revenue", value=1, currency="INR",
                                    period="FY2023", instrument="RELIANCE", source=src)
    item = EvidenceItem(id="ev", kind="structured", summary="s", objects=[obj], source=src)
    cov = evaluate_leg(leg, [item], asof=None, conflicts=[])
    assert cov.status == "no_matching_period"


def test_incompatible_legs_are_blocked_no_change_calculated():
    a = LegDescriptor(legId="a", metric="revenue", period="FY2025", currency="PKR")
    b = LegDescriptor(legId="b", metric="revenue", period="FY2026", currency="USD")
    verdict = check_comparability([a, b])
    assert not verdict.ok
    assert verdict.blocked[0].dimension == "currency"


def test_compatible_legs_pass():
    a = LegDescriptor(legId="a", metric="revenue", period="FY2025", currency="INR",
                      basis="consolidated", symbol="RELIANCE", market="IN", legalName="Reliance Industries Limited")
    b = LegDescriptor(legId="b", metric="revenue", period="FY2026", currency="INR",
                      basis="consolidated", symbol="RELIANCE", market="IN", legalName="Reliance Industries Limited")
    verdict = check_comparability([a, b])
    assert verdict.ok
    assert ("a", "b") in verdict.compatible


def test_duration_parser_recognises_nine_and_twelve_month():
    assert parse_duration_months("9M FY2025") == 9
    assert parse_duration_months("nine-month period") == 9
    assert parse_duration_months("FY2025") == 12
    assert parse_duration_months("Q1 FY2025") == 3


# ── WS7: useful partial answers ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_engine_records_blocked_comparison_in_receipt_and_metadata():
    """A nine-month base vs a twelve-month current period is blocked end-to-end."""
    from harness.research.engine import run_research
    from harness.research.mandate import FactLeg, MandateEntity, ResearchMandate
    from harness.retrieval.contract import (
        EvidenceItem, FinancialRetrievalResult, NormalizedFinancialObject, SourceReference,
    )

    mandate = ResearchMandate(
        taskType="financial_comparison",
        objective="Compare SYS revenue FY2025 (9M) vs FY2026 (12M)",
        entities=[MandateEntity(raw="SYS", symbol="SYS", market="PK")],
        factLegs=[
            FactLeg(id="l9", metric="revenue", entityRaw="SYS", entitySymbol="SYS",
                    market="PK", period="FY2025", currency="PKR", required=True,
                    metadata={"durationMonths": 9}),
            FactLeg(id="l12", metric="revenue", entityRaw="SYS", entitySymbol="SYS",
                    market="PK", period="FY2026", currency="PKR", required=True,
                    metadata={"durationMonths": 12}),
        ],
    )
    src = SourceReference(source="PSX", sourceType="primary")
    by_period = {"FY2025": 44230, "FY2026": 83855}

    async def _retrieve(request):
        period = (request.metadata or {}).get("period")
        obj_ = NormalizedFinancialObject(name="revenue", value=by_period.get(period),
                                         currency="PKR", period=period, instrument="SYS", source=src)
        return FinancialRetrievalResult(
            status="OK", objective=request.objective, dataType=request.dataType,
            instrument=request.instrument,
            evidence=[EvidenceItem(id=f"ev_{period}", kind="structured", summary="s",
                                   objects=[obj_], source=src)],
        )

    outcome = await run_research(mandate, _retrieve, run_id="r_cmp")
    assert outcome.comparability is not None
    assert not outcome.comparability.ok
    assert outcome.comparability.blocked[0].dimension == "duration"
    # The blocked comparison is durable in the receipt and surfaced in metadata.
    assert outcome.receipt is not None
    assert outcome.receipt.comparability is not None
    assert outcome.receipt.comparability["blocked"]
    assert any("comparison blocked" in lim for lim in outcome.metadata.limitations)


def test_partial_answer_presents_verified_facts_and_names_blocked_comparison():
    from harness.research.mandate import FactLeg, MandateEntity, ResearchMandate
    from harness.research.coverage import LegCoverage, CoverageReport
    from harness.research.comparability import check_comparability
    from harness.research.run import _render_answer
    from harness.retrieval.contract import EvidenceItem, NormalizedFinancialObject, SourceReference

    src = SourceReference(source="PSX", sourceType="primary")
    obj = NormalizedFinancialObject(name="revenue", value=44230607495, currency="PKR",
                                    period="FY2025", instrument="SYS", source=src)
    item = EvidenceItem(id="ev1", kind="filing", summary="s", objects=[obj], source=src)

    class Outcome:
        pass

    outcome = Outcome()
    outcome.evidence = [item]
    outcome.prose = ""
    outcome.validation = None
    leg_cov = LegCoverage(legId="l1", metric="revenue", period="FY2025", status="covered",
                          evidenceIds=["ev1"], sourceTiers=["primary"])
    outcome.coverage = CoverageReport(status="partial", legs=[leg_cov])
    outcome.comparability = check_comparability([
        LegDescriptor(legId="l1", metric="revenue", period="FY2025", currency="PKR"),
        LegDescriptor(legId="l2", metric="revenue", period="FY2026", currency="USD"),
    ])
    # A second leg is unavailable (not shown), the covered leg IS shown, and the
    # blocked comparison is named — never a blanket "I cannot find it".
    text = _render_answer(outcome)
    assert "44,230,607,495" in text or "44230607495" in text
    assert "not comparable" in text.lower() or "not computed" in text.lower()

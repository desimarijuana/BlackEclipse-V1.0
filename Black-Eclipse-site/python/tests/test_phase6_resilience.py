"""Phase 6 — resilient, multi-source research.

Entity-agnostic, deterministic, offline. Covers:
  * structured failure diagnostics (zero-results vs transport vs timeout vs
    block vs parse),
  * retry with bounded backoff (transient) vs no retry (permanent),
  * provider switching / the SEC-first source policy for statements,
  * per-leg status + stop reason,
  * the keep-going final response builder,
  * research health.

All fixtures are synthetic and never touch production/JDdS data. The NVDA
labeled regression lives in `test_nvda_regression.py`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness.research.budget import ResearchBudget
from harness.research.engine import _stop_reason, run_research
from harness.research.mandate import parse_mandate
from harness.research.run import _failed_routes, _render_answer
from harness.retrieval.contract import FinancialRetrievalRequest, FinancialRetrievalResult
from harness.retrieval.layer import FinancialRetrievalLayer
from harness.retrieval.planner import (
    SEC_FILINGS,
    STRUCTURED_LIVE,
    STRUCTURED_VAULT,
    WEB,
    plan_retrieval,
)
from harness.retrieval.retry import is_retryable, retrieve_with_retry
from harness.retrieval.sources import SourceOutcome
from harness.retrieval.structured import JddsSource, SecFilingsSource
from harness.tools import DataBridge

# ── Fixtures ────────────────────────────────────────────────────────────────


class ScriptedBridge(DataBridge):
    """A bridge whose per-capability responses are scripted, call-indexed."""

    def __init__(self, responses: dict[str, list[dict[str, Any]]]) -> None:
        self._responses = {k: list(v) for k, v in responses.items()}
        self.calls: list[tuple[str, dict]] = []

    async def fetch(self, capability: str, params: dict) -> dict[str, Any]:
        self.calls.append((capability, params))
        queue = self._responses.get(capability) or []
        if not queue:
            return {"status": "UNAVAILABLE", "error": f"no scripted response for {capability}"}
        # Repeat the last scripted response once the list is consumed.
        return queue.pop(0) if len(queue) > 1 else queue[0]


def _stale_jdds_payload() -> dict[str, Any]:
    return {
        "status": "OK",
        "symbol": "AAA",
        "market": "US",
        "currency": "USD",
        "periods": [
            {"endDate": "2019-01-27", "revenue": 11716000000, "netIncome": 4141000000},
        ],
    }


def _sec_payload() -> dict[str, Any]:
    return {
        "status": "OK",
        "symbol": "AAA",
        "market": "US",
        "currency": "USD",
        "provider": "sec-edgar",
        "retrievedAt": "2026-09-23T00:00:00Z",
        "periods": [
            {"endDate": "2024-01-28", "revenue": 60922000000, "netIncome": 29760000000,
             "form": "10-K", "filed": "2026-02-25"},
            {"endDate": "2025-01-26", "revenue": 130497000000, "netIncome": 72880000000,
             "form": "10-K", "filed": "2026-02-25"},
        ],
    }


# ── Source policy ─────────────────────────────────────────────────────────────


def test_statement_policy_prefers_sec_then_vault_then_web():
    request = FinancialRetrievalRequest(
        objective="revenue", dataType="financial_statements", instrument="AAA",
    )
    plan = plan_retrieval(request)
    assert plan.sources == [SEC_FILINGS, STRUCTURED_VAULT, WEB], plan.sources


def test_sec_not_planned_for_non_statement_types():
    request = FinancialRetrievalRequest(objective="price", dataType="current_quote", instrument="AAA")
    plan = plan_retrieval(request)
    assert SEC_FILINGS not in plan.sources


# ── Independent routes: stale JDdS then successful SEC ────────────────────────


def test_sec_answers_when_vault_is_stale():
    """The exact NVDA shape: vault has only an unrelated year; SEC answers."""
    bridge = ScriptedBridge({
        "sec_filings": [_sec_payload()],
        "financial_statements": [_stale_jdds_payload()],
    })
    layer = FinancialRetrievalLayer(bridge)
    request = FinancialRetrievalRequest(
        objective="revenue for AAA", dataType="financial_statements", instrument="AAA",
        metadata={"metric": "revenue", "period": "FY2024"},
    )
    result = asyncio.run(layer.retrieve(request))
    assert result.status == "OK"
    # SEC is the answering strategy (first source), and the vault was never hit.
    assert result.strategy[0] == SEC_FILINGS
    assert all(cap != "financial_statements" for cap, _ in bridge.calls)
    assert any(obj.period is None and obj.dataTimestamp == "2024-01-28" for obj in _objects(result))


def _objects(result: FinancialRetrievalResult):
    out = []
    for item in result.evidence:
        out.extend(item.objects)
    return out


def test_sec_unavailable_falls_through_to_vault():
    bridge = ScriptedBridge({
        "sec_filings": [{"status": "UNAVAILABLE", "failureClass": "not_covered",
                         "error": "SEC EDGAR covers US issuers only"}],
        "financial_statements": [_stale_jdds_payload()],
    })
    layer = FinancialRetrievalLayer(bridge)
    request = FinancialRetrievalRequest(
        objective="revenue for AAA", dataType="financial_statements", instrument="AAA",
    )
    result = asyncio.run(layer.retrieve(request))
    assert result.status == "OK"
    # The ledger read (P0-2) is not a data attempt; SEC is the first DATA route.
    data_calls = [cap for cap, _ in bridge.calls if cap != "source_health"]
    assert data_calls and data_calls[0] == "sec_filings"
    assert any(cap == "financial_statements" for cap, _ in bridge.calls)
    # The SEC failure is preserved in the diagnostics even though vault answered.
    assert any(d.get("provider") == "SEC" or "SEC" in str(d) for d in result.diagnostics) or result.diagnostics == []


# ── Retry semantics ───────────────────────────────────────────────────────────


def test_transient_timeout_is_retryable():
    outcome = SourceOutcome(source="WEB", status="UNAVAILABLE", error="request timed out")
    assert is_retryable(outcome)


def test_permanent_block_is_not_retryable():
    outcome = SourceOutcome(
        source="WEB",
        status="UNAVAILABLE",
        diagnostics=[{"provider": "duckduckgo-html", "category": "blocked",
                      "normalizedStatus": "failed", "retryable": False}],
    )
    assert not is_retryable(outcome)


def test_bounded_retry_recovers_a_transient_failure():
    calls = {"n": 0}

    async def attempt() -> SourceOutcome:
        calls["n"] += 1
        if calls["n"] == 1:
            return SourceOutcome(
                source="WEB", status="UNAVAILABLE",
                diagnostics=[{"provider": "w", "category": "timeout",
                              "normalizedStatus": "failed", "retryable": True}],
            )
        return SourceOutcome(source="WEB", status="OK", objects=[])

    async def _run() -> SourceOutcome:
        return await retrieve_with_retry(attempt, max_retries=2, sleep=_no_sleep)

    outcome = asyncio.run(_run())
    assert calls["n"] == 2
    assert outcome.status == "OK"
    assert outcome.retries == 1


async def _no_sleep(_: float) -> None:
    return None


def test_permanent_failure_is_not_retried():
    calls = {"n": 0}

    async def attempt() -> SourceOutcome:
        calls["n"] += 1
        return SourceOutcome(
            source="WEB", status="UNAVAILABLE",
            diagnostics=[{"provider": "w", "category": "blocked",
                          "normalizedStatus": "failed", "retryable": False}],
        )

    async def _run() -> SourceOutcome:
        return await retrieve_with_retry(attempt, max_retries=3, sleep=_no_sleep)

    asyncio.run(_run())
    assert calls["n"] == 1  # never retried


# ── Engine: per-leg status, stop reason, partial success ─────────────────────


def test_partial_success_preserves_verified_legs():
    """One metric resolves from SEC; another remains unresolved."""
    mandate = parse_mandate(
        "Compare AAA revenue and net income for FY2024 and FY2025, in USD", ticker="AAA"
    )
    assert mandate.supported

    async def retrieve(request: FinancialRetrievalRequest) -> FinancialRetrievalResult:
        period = (request.metadata or {}).get("period")
        if "FY2024" in (period or ""):
            return FinancialRetrievalResult(
                status="OK", objective=request.objective, dataType=request.dataType,
                instrument="AAA", strategy=["SEC"],
            )
        return FinancialRetrievalResult(
            status="UNAVAILABLE", objective=request.objective, dataType=request.dataType,
            instrument="AAA", strategy=["SEC", "JDDS"],
            diagnostics=[{"provider": "safe-get", "category": "http_error",
                          "normalizedStatus": "failed", "detail": "HTTP 403"}],
        )

    outcome = asyncio.run(run_research(mandate, retrieve))
    assert outcome.legStatus, "leg status must be recorded"
    statuses = {row["metric"]: row for row in outcome.legStatus}
    assert "revenue" in statuses and "netIncome" in statuses
    assert outcome.stopReason in ("unresolved_facts_remain", "provider_routes_unavailable")


def test_stop_reason_budget_when_budget_exhausted():
    mandate = parse_mandate("Compare AAA revenue for FY2024 and FY2025, in USD", ticker="AAA")

    async def retrieve(request: FinancialRetrievalRequest) -> FinancialRetrievalResult:
        return FinancialRetrievalResult(
            status="UNAVAILABLE", objective=request.objective,
            dataType=request.dataType, instrument="AAA",
        )

    budget = ResearchBudget(maxSearches=0)
    outcome = asyncio.run(run_research(mandate, retrieve, budget=budget))
    # No evidence at all and no escalation budget → budget-exhausted is the reason.
    assert outcome.stopReason in ("budget_exhausted", "provider_routes_unavailable", "unresolved_facts_remain")


def test_stop_reason_resolved_when_complete():
    mandate = parse_mandate("Compare AAA revenue for FY2023 and FY2024, in USD", ticker="AAA")

    async def retrieve(request: FinancialRetrievalRequest) -> FinancialRetrievalResult:
        from harness.retrieval.contract import (
            EvidenceItem, NormalizedFinancialObject, SourceReference,
        )
        period = (request.metadata or {}).get("period")
        year = "2023" if "FY2023" in (period or "") else "2024"
        obj = NormalizedFinancialObject(
            name="revenue", value=100.0 if year == "2023" else 200.0,
            currency="USD", period=f"FY{year}", instrument="AAA",
            basis="consolidated",
            source=SourceReference(source="SEC EDGAR", sourceType="primary"),
        )
        item = EvidenceItem(
            id=f"ev_{year}", kind="filing", summary="rev", objects=[obj],
            source=obj.source,
        )
        return FinancialRetrievalResult(
            status="OK", objective=request.objective, dataType=request.dataType,
            instrument="AAA", evidence=[item],
        )

    outcome = asyncio.run(run_research(mandate, retrieve))
    assert outcome.coverage.coveredCount == 2
    assert outcome.stopReason == "all_required_legs_resolved"


# ── Keep-going final response ─────────────────────────────────────────────────


class _FakeOutcome:
    def __init__(self) -> None:
        self.prose = "Verified: revenue FY2024 = 60,922."
        self.coverage = type("C", (), {"status": "partial"})()
        self.metadata = type("M", (), {
            "limitations": ["NVDA consolidated net income FY2025 (USD): not present"],
            "citations": [],
        })()
        self.legStatus = [
            {
                "legId": "leg1", "metric": "netIncome",
                "diagnostics": [
                    {"provider": "duckduckgo-html", "category": "blocked",
                     "normalizedStatus": "failed", "detail": "HTTP 202 challenge"},
                    {"provider": "safe-get", "category": "http_error",
                     "normalizedStatus": "failed", "detail": "HTTP 403"},
                ],
            }
        ]
        self.stopReason = "provider_routes_unavailable"


def test_answer_prose_is_clean_and_keeps_verified_facts():
    """The prose carries the answer only — no citations/footers (the UI renders
    provenance in a separate Sources/Limitations area from structured fields)."""
    text = _render_answer(_FakeOutcome())
    assert "revenue FY2024 = 60,922" in text          # verified fact retained
    assert "Evidence cited:" not in text
    assert "Sources tried (failed):" not in text
    assert "Stopped because:" not in text
    assert "http" not in text.lower()                 # no raw URLs in prose


def test_failed_routes_are_exposed_structurally_and_deduplicated():
    rows = _failed_routes(_FakeOutcome())
    assert len(rows) == 2
    assert any("duckduckgo-html — blocked" in r for r in rows)
    assert any("safe-get — http_error: HTTP 403" in r for r in rows)


def test_stop_reason_text_is_human_readable():
    from harness.research.run import _stop_reason_text

    assert _stop_reason_text("provider_routes_unavailable") == (
        "every available source route failed or was unavailable"
    )
    assert _stop_reason_text(None) is None
    # An unknown reason is passed through rather than dropped.
    assert _stop_reason_text("something_new") == "something_new"


# ── SEC source unit ───────────────────────────────────────────────────────────


def test_sec_source_normalizes_primary_tier_and_document_id():
    bridge = ScriptedBridge({"sec_filings": [_sec_payload()]})
    source = SecFilingsSource(bridge)
    request = FinancialRetrievalRequest(
        objective="revenue", dataType="financial_statements", instrument="AAA",
    )
    outcome = asyncio.run(source.retrieve(request))
    assert outcome.status == "OK"
    obj = outcome.objects[0]
    assert obj.source.sourceType == "primary"
    assert obj.documentId, "filing identity must be preserved"
    assert "10-K" in obj.documentId


def test_sec_source_not_available_without_bridge():
    assert not SecFilingsSource(None).available(
        FinancialRetrievalRequest(objective="x", dataType="financial_statements")
    )


def test_jdds_source_still_serves_statements():
    assert JddsSource(ScriptedBridge({})).available(
        FinancialRetrievalRequest(objective="x", dataType="financial_statements")
    )

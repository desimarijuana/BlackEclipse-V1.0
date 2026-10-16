"""The Fiduciary Gate — deterministic verification of actionable advice.

A recommendation with no portfolio computation and no consulted source behind it
is disclosed as unverified advice; a computed or consulted one is not. Pure and
synthetic — no ticker-specific logic.
"""

from __future__ import annotations

import asyncio

from harness.advisory.claims import extract_claims
from harness.advisory.collector import AdvisoryCollector
from harness.advisory.gate import apply, enforce_advisory_answer
from harness.advisory.model import COMPUTED, SOURCED, UNVERIFIED


# ── extraction ────────────────────────────────────────────────────────────────


def test_ordinary_prose_has_no_claims():
    assert extract_claims("Apple reported strong revenue growth this quarter.") == []


def test_a_named_concept_without_a_directive_is_not_a_claim():
    # "revenue" has no actionable verb.
    assert extract_claims("Revenue was 2.7 trillion TRY in FY2025.") == []


def test_a_bare_directive_with_a_symbol_is_a_claim():
    claims = extract_claims("I would sell AAPL here.")
    assert len(claims) == 1
    assert claims[0].action == "sell"
    assert claims[0].symbols == ("AAPL",)


def test_a_rebalance_with_a_weight_target_is_a_claim():
    claims = extract_claims("Rebalance the portfolio to 60/40 stocks and bonds.")
    assert len(claims) == 1
    assert claims[0].action == "rebalance"
    assert claims[0].values == (60.0, 40.0)


def test_a_percent_target_is_parsed():
    claims = extract_claims("Trim NVDA by 5% to lock in gains.")
    assert claims[0].action == "trim"
    assert 5.0 in claims[0].values


def test_dollar_target_is_parsed():
    claims = extract_claims("Buy $10k of VTI in the brokerage account.")
    assert claims[0].action == "buy"
    assert 10000.0 in claims[0].values


def test_stopword_acronyms_are_not_symbols():
    # "EPS", "AI", "USD" are not tickers; a sentence with only those yields no claim.
    assert extract_claims("The AI sector beat EPS and USD estimates.") == []


# ── gate classification ───────────────────────────────────────────────────────


def _computation(symbols, numbers, *, compute=True, tool="portfolio_rebalance"):
    return {"tool": tool, "compute": compute, "portfolioId": "pf_1",
            "symbols": list(symbols), "numbers": list(numbers), "actions": []}


def test_a_recommendation_with_no_backing_is_unverified_and_disclosed():
    verdict = enforce_advisory_answer("Buy AAPL now.")
    assert verdict.unverified
    assert verdict.disclosure is not None
    assert "AAPL" in verdict.disclosure
    assert verdict.verdicts[0].status == UNVERIFIED


def test_a_recommendation_backed_by_a_computation_is_computed():
    verdict = enforce_advisory_answer(
        "Rebalance to 60% AAPL and 40% cash.",
        [_computation(["AAPL"], [0.6, 0.4])],
    )
    assert verdict.verdicts[0].status == COMPUTED
    assert verdict.disclosure is None


def test_a_numeric_target_that_contradicts_the_computation_is_unverified():
    verdict = enforce_advisory_answer(
        "Rebalance to 90% AAPL.",
        [_computation(["AAPL"], [0.6])],
    )
    assert verdict.verdicts[0].status == UNVERIFIED


def test_a_symbol_only_claim_grounded_in_a_consult_is_sourced():
    verdict = enforce_advisory_answer("I would sell AAPL here.", consulted={"AAPL"})
    assert verdict.verdicts[0].status == SOURCED
    assert verdict.disclosure is None


def test_a_symbol_only_claim_with_no_consult_is_unverified():
    verdict = enforce_advisory_answer("I would sell AAPL here.", consulted={"MSFT"})
    assert verdict.verdicts[0].status == UNVERIFIED


def test_no_claims_is_a_clean_noop():
    verdict = enforce_advisory_answer("Markets were volatile today.")
    assert verdict.verdicts == []
    assert verdict.released is True


# ── apply (async seam) ────────────────────────────────────────────────────────


def test_apply_appends_disclosure_and_emits():
    emitted = []

    class Emitter:
        async def emit(self, kind, data):
            emitted.append((kind, data))

    answer, blob = asyncio.run(
        apply("Buy TSLA.", [], emitter=Emitter())
    )
    assert "Advisory note:" in answer
    assert blob is not None and blob["status"] == "unverified"
    assert emitted and emitted[0][0] == "advisory.gate"


def test_apply_returns_none_when_there_is_no_claim():
    answer, blob = asyncio.run(apply("Just an observation.", []))
    assert answer == "Just an observation."
    assert blob is None


# ── collector ─────────────────────────────────────────────────────────────────


def test_collector_ignores_non_portfolio_tools():
    collector = AdvisoryCollector()
    collector.add("market_quote", {"symbol": "AAPL"}, {"symbol": "AAPL", "price": 200})
    assert collector.has_content() is False


def test_collector_normalises_a_portfolio_computation():
    collector = AdvisoryCollector()
    collector.add(
        "portfolio_rebalance",
        {"portfolio_id": "pf_1"},
        {"trades": [{"symbol": "AAPL", "action": "SELL", "targetWeight": 0.6}],
         "status": "PROPOSED"},
    )
    comps = collector.computations()
    assert comps and comps[0]["compute"] is True
    assert "AAPL" in comps[0]["symbols"]
    assert 0.6 in comps[0]["numbers"]
    assert collector.consulted_symbols() == {"AAPL"}


def test_collector_dedupes_repeated_calls():
    collector = AdvisoryCollector()
    args = {"portfolio_id": "pf_1"}
    data = {"symbol": "AAPL", "value": 1.0}
    collector.add("portfolio_get", args, data)
    collector.add("portfolio_get", args, data)
    assert len(collector.computations()) == 1

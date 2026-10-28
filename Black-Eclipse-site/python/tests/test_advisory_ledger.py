"""The Advisory Ledger — durable decisions, basis, outcomes and the scorecard.

Every Fiduciary Gate verdict becomes a decision; an outcome is appended later.
Pure and synthetic; no ticker-specific logic.
"""

from __future__ import annotations

import os

from harness.advisory.service import AdvisoryService, classify_outcome
from harness.advisory.tools import register_advisory_tools
from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolRegistry


def _service(tmp_path) -> AdvisoryService:
    store = AgentMemoryStore(os.path.join(str(tmp_path), "advisory-test.db"))
    return AdvisoryService(store)


def _verdict(status: str = "computed", action: str = "rebalance", symbols=None, target=None):
    return {
        "status": "ok" if status != "unverified" else "unverified",
        "claims": [{
            "action": action, "symbols": symbols or ["AAPL"], "target": target,
            "values": [], "status": status, "reason": f"reason for {status}",
        }],
        "unverified": [] if status != "unverified" else ["stub"],
    }


# ── classification ────────────────────────────────────────────────────────────


def test_classify_outcome_against_a_benchmark():
    assert classify_outcome(0.10, 0.05) == "right"
    assert classify_outcome(0.02, 0.05) == "wrong"
    assert classify_outcome(0.05, 0.05) == "neutral"


def test_classify_outcome_without_a_benchmark_uses_zero():
    assert classify_outcome(0.01, None) == "right"
    assert classify_outcome(-0.01, None) == "wrong"
    assert classify_outcome(0.0, None) == "neutral"


# ── recording ─────────────────────────────────────────────────────────────────


def test_record_verdict_persists_a_decision(tmp_path):
    svc = _service(tmp_path)
    recorded = svc.record_verdict(run_id="run_1", verdict=_verdict(), portfolio_id="pf_1",
                                 owner_id="u1", sources=["https://sec.gov/x"])
    assert len(recorded) == 1
    decision = recorded[0]
    assert decision["status"] == "computed"
    assert decision["symbols"] == ["AAPL"]
    assert decision["portfolioId"] == "pf_1"
    kinds = {b["kind"] for b in decision["basis"]}
    assert "computation" in kinds and "source" in kinds


def test_recording_the_same_verdict_is_idempotent(tmp_path):
    svc = _service(tmp_path)
    v = _verdict()
    first = svc.record_verdict(run_id="run_1", verdict=v, portfolio_id="pf_1")
    second = svc.record_verdict(run_id="run_1", verdict=v, portfolio_id="pf_1")
    assert first[0]["id"] == second[0]["id"]
    assert len(svc.list_decisions()) == 1


def test_unverified_decision_records_a_none_basis(tmp_path):
    svc = _service(tmp_path)
    recorded = svc.record_verdict(run_id="run_1", verdict=_verdict(status="unverified"))
    kinds = {b["kind"] for b in recorded[0]["basis"]}
    assert "none" in kinds
    # A method and a stated horizon are recorded at issue time.
    assert "method" in kinds and "horizon" in kinds


# ── listing / filtering ───────────────────────────────────────────────────────


def test_list_decisions_filters_by_status_and_portfolio(tmp_path):
    svc = _service(tmp_path)
    svc.record_verdict(run_id="r1", verdict=_verdict(status="computed"), portfolio_id="pf_1")
    svc.record_verdict(run_id="r2", verdict=_verdict(status="unverified", action="sell"),
                       portfolio_id="pf_2")
    assert len(svc.list_decisions()) == 2
    assert len(svc.list_decisions(portfolio_id="pf_1")) == 1
    assert len(svc.list_decisions(status="unverified")) == 1


# ── outcomes ──────────────────────────────────────────────────────────────────


def test_record_outcome_attaches_a_verdict(tmp_path):
    svc = _service(tmp_path)
    did = svc.record_verdict(run_id="r1", verdict=_verdict())[0]["id"]
    outcome = svc.record_outcome(did, realized_return=0.12, benchmark_return=0.04, horizon="3m")
    assert outcome["verdict"] == "right"
    assert svc.get_decision(did)["outcome"]["realizedReturn"] == 0.12


def test_record_outcome_for_a_missing_decision_is_none(tmp_path):
    svc = _service(tmp_path)
    assert svc.record_outcome("adv_missing", realized_return=0.1) is None


# ── scorecard ─────────────────────────────────────────────────────────────────


def test_scorecard_summarises_decisions_and_hit_rate(tmp_path):
    svc = _service(tmp_path)
    a = svc.record_verdict(run_id="r1", verdict=_verdict(), portfolio_id="pf_1")[0]["id"]
    b = svc.record_verdict(run_id="r2", verdict=_verdict(action="sell"), portfolio_id="pf_1")[0]["id"]
    svc.record_verdict(run_id="r3", verdict=_verdict(status="unverified", action="buy"), portfolio_id="pf_1")
    svc.record_outcome(a, realized_return=0.10, benchmark_return=0.02)
    svc.record_outcome(b, realized_return=-0.05, benchmark_return=0.01)

    card = svc.scorecard(portfolio_id="pf_1")
    assert card["total"] == 3
    assert card["byStatus"]["computed"] == 2
    assert card["byStatus"]["unverified"] == 1
    assert card["evaluated"] == 2
    assert card["outcomes"]["right"] == 1 and card["outcomes"]["wrong"] == 1
    assert card["hitRate"] == 0.5
    assert abs(card["avgRealizedReturn"] - 0.025) < 1e-9


def test_empty_scorecard_is_honest(tmp_path):
    card = _service(tmp_path).scorecard()
    assert card["total"] == 0
    assert card["evaluated"] == 0
    assert card["hitRate"] is None


# ── auto evaluation ─────────────────────────────────────────────────────────────


def test_entry_price_is_captured_when_provided(tmp_path):
    svc = _service(tmp_path)
    decision = svc.record_verdict(run_id="r1", verdict=_verdict(), entry_prices={"AAPL": 100.0})[0]
    kinds = {b["kind"] for b in decision["basis"]}
    assert "entry_price" in kinds


def test_evaluate_outcome_computes_the_return(tmp_path):
    svc = _service(tmp_path)
    did = svc.record_verdict(run_id="r1", verdict=_verdict(), entry_prices={"AAPL": 100.0})[0]["id"]
    outcome = svc.evaluate_outcome(did, current_price=110.0, benchmark_return=0.05)
    assert abs(outcome["realizedReturn"] - 0.10) < 1e-9
    assert outcome["verdict"] == "right"


def test_evaluate_outcome_without_an_entry_price_is_none(tmp_path):
    svc = _service(tmp_path)
    did = svc.record_verdict(run_id="r1", verdict=_verdict())[0]["id"]
    assert svc.evaluate_outcome(did, current_price=110.0) is None


def test_evaluate_decisions_skips_unpriced_and_evaluates_matched(tmp_path):
    svc = _service(tmp_path)
    priced = svc.record_verdict(run_id="r1", verdict=_verdict(),
                                entry_prices={"AAPL": 100.0})[0]["id"]
    svc.record_verdict(run_id="r2", verdict=_verdict(action="sell"))  # no entry price
    results = svc.evaluate_decisions({"AAPL": 90.0}, benchmark_return=0.0)
    assert len(results) == 1
    assert results[0]["decisionId"] == priced
    assert results[0]["verdict"] == "wrong"
    # A second pass does not double-evaluate (already has an outcome).
    assert svc.evaluate_decisions({"AAPL": 90.0}) == []


# ── auto evaluation via the gateway ──────────────────────────────────────────────


class _Gateway:
    def __init__(self, prices):
        self._prices = prices

    async def get_quote(self, symbol):
        return {"price": self._prices.get(symbol)}


def test_auto_evaluate_fetches_prices_and_records_outcomes(tmp_path):
    import asyncio

    svc = _service(tmp_path)
    svc.record_verdict(
        run_id="r1", verdict=_verdict(), entry_prices={"AAPL": 100.0},
        horizon="0d",
    )
    result = asyncio.run(svc.auto_evaluate(_Gateway({"AAPL": 120.0}), benchmark_return=0.0))
    assert result["evaluated"] == 1
    assert result["outcomes"][0]["verdict"] == "right"
    assert svc.scorecard()["hitRate"] == 1.0


def test_auto_evaluate_skips_a_recommendation_without_a_price(tmp_path):
    import asyncio

    svc = _service(tmp_path)
    svc.record_verdict(
        run_id="r1", verdict=_verdict(), entry_prices={"AAPL": 100.0},
        horizon="0d",
    )
    result = asyncio.run(svc.auto_evaluate(_Gateway({})))  # no quote
    assert result["evaluated"] == 0
    assert len(result["skipped"]) == 1


# ── seam pipeline (collector → gate → record → attach) ──────────────────────────


def test_seam_pipeline_records_a_computed_decision_with_an_entry_price(tmp_path):
    import asyncio

    from harness.advisory import integration
    from harness.advisory.collector import AdvisoryCollector

    collector = AdvisoryCollector()
    collector.add("portfolio_rebalance", {"portfolio_id": "pf_1"},
                  {"trades": [{"symbol": "AAPL", "targetWeight": 0.6, "price": 100.0}]})

    answer, verdict = asyncio.run(
        integration.verify("Rebalance AAPL to 60%.", collector)
    )
    assert verdict is not None
    assert verdict["claims"][0]["status"] == "computed"
    assert "Advisory note:" not in answer  # computed advice needs no disclosure

    svc = _service(tmp_path)
    svc.record_verdict(run_id="r1", verdict=verdict, portfolio_id="pf_1",
                       entry_prices=collector.prices())
    decision = svc.get_decision(svc.list_decisions()[0]["id"])
    kinds = {b["kind"] for b in decision["basis"]}
    assert "computation" in kinds and "entry_price" in kinds

    blob = integration.attach(None, verdict)
    assert blob["metadata"]["advisoryIntegrity"]["status"] == "ok"


def test_seam_pipeline_discloses_unsupported_advice(tmp_path):
    import asyncio

    from harness.advisory import integration
    from harness.advisory.collector import AdvisoryCollector

    collector = AdvisoryCollector()  # no portfolio computation
    answer, verdict = asyncio.run(integration.verify("Buy TSLA.", collector))
    assert "Advisory note:" in answer
    assert verdict["claims"][0]["status"] == "unverified"


# ── tools ─────────────────────────────────────────────────────────────────────


def _registry():
    reg = ToolRegistry()
    register_advisory_tools(reg)
    return reg


def test_advisory_tools_register_read_only():
    reg = _registry()
    names = set(reg.names())
    assert {"advisory_list", "advisory_get", "advisory_scorecard"} <= names
    for name in names:
        assert reg.get(name).permission == "read"


async def test_advisory_tools_execute(tmp_path):
    svc = _service(tmp_path)
    did = svc.record_verdict(run_id="r1", verdict=_verdict())[0]["id"]
    reg = _registry()
    ctx = ToolContext(run_id="r", log=lambda *_: None, advisory_service=svc)

    listed = await reg.execute("advisory_list", "c1", {}, ctx)
    assert listed.ok and listed.data["decisions"]

    got = await reg.execute("advisory_get", "c2", {"decision_id": did}, ctx)
    assert got.ok and got.data["id"] == did

    card = await reg.execute("advisory_scorecard", "c3", {}, ctx)
    assert card.ok and card.data["total"] == 1

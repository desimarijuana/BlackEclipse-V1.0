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
    assert kinds == {"none"}


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

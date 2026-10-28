"""Phase 1: bounded, unattended advisory-outcome scoring."""

from __future__ import annotations

import asyncio
import os

from harness.advisory.cadence import (
    AdvisoryCadenceConfig,
    run_once,
)
from harness.advisory.service import AdvisoryService
from harness.advisory.store import AdvisoryStore
from harness.persistence import AgentMemoryStore


def _service(tmp_path):
    return AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))


def _decision(store, decision_id, *, price, due_at, symbols=("AAPL",)):
    advisory = AdvisoryStore(store)
    advisory.upsert_decision({
        "id": decision_id, "runId": f"run_{decision_id}",
        "createdAt": "2026-10-28T00:00:00Z", "action": "buy",
        "symbols": list(symbols), "target": "test", "thesis": "fixture",
        "status": "unverified", "method": "model_advice",
        "horizon": "30d", "dueAt": due_at,
    })
    if price is not None:
        advisory.add_basis(decision_id, [{"kind": "entry_price", "ref": price}])


class _Service:
    def __init__(self, advisory, gateway):
        self.advisory = advisory
        self._gateway = gateway
        self.quotes = 0

    def server_market_gateway(self):
        return self._gateway

    async def get_quote(self, symbol):
        self.quotes += 1
        return {"price": 110.0}


class _Gateway:
    def __init__(self):
        self.calls = 0

    async def get_quote(self, symbol):
        self.calls += 1
        return {"price": 110.0}


def test_cadence_scores_due_priced_and_counts_both_skips(tmp_path):
    store = _service(tmp_path)
    try:
        _decision(store, "adv_due", price="100", due_at="2026-10-27T00:00:00Z")
        _decision(store, "adv_no_price", price=None, due_at="2026-10-27T00:00:00Z")
        _decision(store, "adv_not_due", price="100", due_at="2026-10-29T00:00:00Z")
        gateway = _Gateway()
        service = _Service(AdvisoryService(store), gateway)
        result = asyncio.run(run_once(
            service,
            AdvisoryCadenceConfig(enabled=True, max_per_tick=50),
            now="2026-10-28T00:00:00Z",
        ))
        assert result["evaluated"] == 1
        assert result["skippedNoPrice"] == 1
        assert result["skippedNotDue"] == 1
        assert result["reason"] == "evaluated"
    finally:
        store.close()


def test_cadence_nothing_due_makes_no_market_call(tmp_path):
    store = _service(tmp_path)
    try:
        _decision(store, "adv_future", price="100", due_at="2099-01-01T00:00:00Z")
        gateway = _Gateway()
        service = _Service(AdvisoryService(store), gateway)
        result = asyncio.run(run_once(
            service,
            AdvisoryCadenceConfig(enabled=True),
            now="2026-10-28T00:00:00Z",
        ))
        assert result["reason"] == "nothing_due"
        assert result["evaluated"] == 0
        assert gateway.calls == 0
    finally:
        store.close()


def test_cadence_kill_switch_does_nothing(tmp_path):
    store = _service(tmp_path)
    try:
        _decision(store, "adv_due", price="100", due_at="2026-10-27T00:00:00Z")
        gateway = _Gateway()
        service = _Service(AdvisoryService(store), gateway)
        result = asyncio.run(run_once(
            service, AdvisoryCadenceConfig(enabled=False),
            now="2026-10-28T00:00:00Z",
        ))
        assert result["reason"] == "disabled"
        assert gateway.calls == 0
    finally:
        store.close()

"""One canonical advisory scoring definition used by gate and scorecard."""

from __future__ import annotations

import asyncio
import os
import tempfile

from harness.advisory.service import AdvisoryService
from harness.advisory.store import AdvisoryStore
from harness.persistence import AgentMemoryStore
from harness.self_improvement.loop_health import gate_report

NOW = "2026-10-28T00:00:00Z"


def _service(tmp_path):
    return AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))


def _decision(
    store: AgentMemoryStore,
    decision_id: str,
    *,
    price: str | None,
    due_at: str,
) -> None:
    advisory = AdvisoryStore(store)
    advisory.upsert_decision({
        "id": decision_id,
        "runId": f"run_{decision_id}",
        "createdAt": "2026-10-28T00:00:00Z",
        "action": "buy",
        "symbols": ["AAPL"],
        "target": "test",
        "thesis": "fixture",
        "status": "unverified",
        "method": "model_advice",
        "horizon": "30d",
        "dueAt": due_at,
    })
    if price is not None:
        advisory.add_basis(decision_id, [{"kind": "entry_price", "ref": price}])


def test_gate_and_scorecard_agree_on_canonical_counts(tmp_path):
    store = _service(tmp_path)
    try:
        _decision(store, "adv_scorable", price="100", due_at="2026-10-27T00:00:00Z")
        _decision(store, "adv_no_price", price=None, due_at="2026-10-27T00:00:00Z")
        _decision(store, "adv_not_due", price="100", due_at="2026-10-29T00:00:00Z")

        service = AdvisoryService(store)
        card = service.scorecard(now=NOW)
        gate = gate_report(store, advisory_service=service, now=NOW)["advisory"]

        assert card["scorable"] == gate["scorable"] == 1
        assert card["noEntryPrice"] == gate["no_entry_price"] == 1
        assert card["notDue"] == gate["not_due"] == 1
        assert card["unscored"] == gate["unscored"] == 0
        assert card["needsBackfill"] == gate["needsBackfill"] == 1
    finally:
        store.close()


def test_auto_evaluate_scores_only_due_rows_with_a_price(tmp_path):
    store = _service(tmp_path)
    try:
        _decision(store, "adv_due", price="100", due_at="2026-10-27T00:00:00Z")
        _decision(store, "adv_no_price", price=None, due_at="2026-10-27T00:00:00Z")
        _decision(store, "adv_not_due", price="100", due_at="2026-10-29T00:00:00Z")

        class _Gateway:
            async def get_quote(self, symbol: str):
                return {"price": 110.0}

        service = AdvisoryService(store)
        result = asyncio.run(service.auto_evaluate(_Gateway()))
        assert result["evaluated"] == 1
        assert result["skippedNoPrice"] == 1
        assert result["skippedNotDue"] == 1
        assert result["outcomes"][0]["decisionId"] == "adv_due"
    finally:
        store.close()

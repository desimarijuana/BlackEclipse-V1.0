"""Legacy advisory debt: reasons + provenance-bound historical backfill."""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

from harness.advisory.backfill import backfill_entry_prices, legacy_report
from harness.advisory.service import AdvisoryService
from harness.advisory.store import AdvisoryStore
from harness.persistence import AgentMemoryStore


def _service(tmp_path):
    store = AgentMemoryStore(os.path.join(str(tmp_path), "agent-memory.db"))
    return store, AdvisoryService(store)


def _decision(store, decision_id, *, symbols, horizon, price=None, created="2026-10-01T00:00:00Z"):
    advisory = AdvisoryStore(store)
    advisory.upsert_decision({
        "id": decision_id, "runId": f"run_{decision_id}", "createdAt": created,
        "action": "buy", "symbols": list(symbols), "target": "t",
        "thesis": "fixture", "status": "unverified", "method": None,
        "horizon": horizon, "dueAt": None,
    })
    if price is not None:
        advisory.add_basis(decision_id, [{"kind": "entry_price", "ref": price}])
    store._db.execute(
        "UPDATE AdvisoryDecision SET legacyUnscored=1 WHERE id=?", (decision_id,),
    )
    store._db.commit()


class _Gateway:
    def __init__(self, bars=True):
        self.bars = bars

    async def get_historical_prices(self, symbol, **kwargs):
        if not self.bars:
            return SimpleNamespace(bars=[], meta=SimpleNamespace(provider="test"))
        return SimpleNamespace(
            bars=[SimpleNamespace(close=100.0, timestamp="2026-10-01T00:00:00Z")],
            meta=SimpleNamespace(provider="test"),
        )


def test_legacy_report_explains_unscorable_rows(tmp_path):
    store, svc = _service(tmp_path)
    try:
        _decision(store, "adv_no_horizon", symbols=["SPY"], horizon=None)
        _decision(store, "adv_backfillable", symbols=["AAPL"], horizon="30d")
        _decision(store, "adv_has_price", symbols=["MSFT"], horizon="30d", price="10")
        report = legacy_report(svc.store)
        by_id = {row["id"]: row for row in report["rows"]}
        assert by_id["adv_no_horizon"]["status"] == "unscorable"
        assert "no_horizon" in by_id["adv_no_horizon"]["reasons"]
        assert by_id["adv_backfillable"]["status"] == "scorable_if_backfilled"
        assert by_id["adv_has_price"]["status"] == "unscorable"
    finally:
        store.close()


def test_backfill_is_dry_run_first_and_stores_provenance(tmp_path):
    store, svc = _service(tmp_path)
    try:
        _decision(store, "adv_backfill", symbols=["AAPL"], horizon="30d")
        dry = asyncio.run(backfill_entry_prices(svc, _Gateway(), dry_run=True))
        assert dry["dryRun"] is True
        assert dry["actions"] and dry["backfilled"] == 0
        assert not any(
            b["kind"] == "entry_price"
            for b in (svc.store.get_decision("adv_backfill") or {}).get("basis") or []
        )

        applied = asyncio.run(backfill_entry_prices(svc, _Gateway(), dry_run=False))
        assert applied["backfilled"] == 1
        basis = (svc.store.get_decision("adv_backfill") or {}).get("basis") or []
        kinds = {b["kind"] for b in basis}
        assert {"entry_price", "entry_price_source", "entry_price_asof"} <= kinds
    finally:
        store.close()


def test_backfill_skips_when_no_historical_bar(tmp_path):
    store, svc = _service(tmp_path)
    try:
        _decision(store, "adv_nobar", symbols=["AAPL"], horizon="30d")
        result = asyncio.run(backfill_entry_prices(svc, _Gateway(bars=False), dry_run=False))
        assert result["backfilled"] == 0
        assert any(item["id"] == "adv_nobar" for item in result["skipped"])
    finally:
        store.close()

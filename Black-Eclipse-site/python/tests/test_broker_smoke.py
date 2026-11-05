"""Broker smoke test: probe → reads → sync, with honest checks."""

from __future__ import annotations

import os

from harness.persistence import AgentMemoryStore
from harness.trade.adapter import BrokerAdapter
from harness.trade.model import BrokerKind
from harness.trade.registry import register_kind
from harness.trade.service import BrokerService

DEAL = {
    "dealTicket": 1, "orderTicket": 2, "positionTicket": 3,
    "symbol": "EURUSD", "side": "buy", "entry": "in", "volume": 0.1,
    "price": 1.1, "commission": 0, "swap": 0, "profit": 0,
    "magic": 0, "comment": "", "dealtAt": 1_700_000_000_000,
}


class SmokeAdapter(BrokerAdapter):
    kind = "fake-smoke"

    @classmethod
    def availability(cls):
        return True, None

    def probe(self):
        return {"available": True, "connected": True, "account": {
            "mode": "demo", "currency": "USD"}}

    def account(self):
        return {"login": 1, "mode": "demo", "currency": "USD", "balance": 1000,
                "equity": 1000, "margin": 0, "marginFree": 1000, "marginLevel": 0,
                "profit": 0, "leverage": 1, "marginMode": "unknown",
                "tradeAllowed": True, "expertAllowed": True}

    def positions(self):
        return []

    def orders(self):
        return []

    def quote(self, symbol):
        return {"symbol": symbol}

    def deals_window(self, days):
        return [DEAL]


class OfflineAdapter(SmokeAdapter):
    kind = "fake-smoke-offline"

    def probe(self):
        return {"available": True, "connected": False, "code": "NO_IPC",
                "reason": "terminal is closed", "account": None}


def _service(tmp_path, cls, kind):
    store = AgentMemoryStore(os.path.join(str(tmp_path), f"{kind}.db"))
    register_kind(BrokerKind(id=kind, label=kind, auth="attach"), cls, replace=True)
    service = BrokerService(store)
    connection = service.create_connection(kind=kind, label="Smoke", mode="demo", config={})
    return service, connection["id"]


def test_smoke_runs_reads_and_sync(tmp_path):
    service, connection_id = _service(tmp_path, SmokeAdapter, "fake-smoke")
    report = service.smoke_connection(connection_id, days=7)
    assert report["ok"] is True
    assert report["counts"]["deals"] == 1
    assert {c["name"] for c in report["checks"]} >= {"probe", "account", "positions", "orders", "deals", "sync", "mirror"}
    assert report["sync"]["ok"] is True


def test_smoke_reports_an_offline_broker_honestly(tmp_path):
    service, connection_id = _service(tmp_path, OfflineAdapter, "fake-smoke-offline")
    report = service.smoke_connection(connection_id)
    assert report["ok"] is False
    assert report["error"] == "terminal is closed"
    assert report["sync"] is None
    assert report["checks"][0]["name"] == "probe"

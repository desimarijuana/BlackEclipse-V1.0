"""Broker reconciliation: durable fills, positions and order-state sync.

No terminal, no network: a fake adapter proves dedupe, snapshot replacement and
the ledger-status update. A failed sync must record an honest error, never a fake
success.
"""

from __future__ import annotations

import os

from harness.persistence import AgentMemoryStore
from harness.trade.adapter import AdapterUnavailable, TradingAdapter
from harness.trade.model import BrokerKind
from harness.trade.reconcile import BrokerReconciler
from harness.trade.registry import register_kind
from harness.trade.service import BrokerService

DEALS = [
    {
        "dealTicket": 11, "orderTicket": 901, "positionTicket": 5,
        "symbol": "EURUSD", "side": "buy", "entry": "in", "volume": 0.1,
        "price": 1.1, "commission": -1.0, "swap": 0.0, "profit": 0.0,
        "magic": 99, "comment": "", "dealtAt": 1_700_000_000_000,
        "eclipseOwned": True,
    },
    {
        "dealTicket": 12, "orderTicket": 902, "positionTicket": 5,
        "symbol": "EURUSD", "side": "sell", "entry": "out", "volume": 0.1,
        "price": 1.2, "commission": -1.0, "swap": 0.0, "profit": 100.0,
        "magic": 99, "comment": "", "dealtAt": 1_700_000_060_000,
        "eclipseOwned": True,
    },
]

POSITIONS = [
    {
        "ticket": 5, "symbol": "EURUSD", "side": "buy", "volume": 0.1,
        "openPrice": 1.1, "currentPrice": 1.15, "stopLoss": 1.09,
        "takeProfit": 1.2, "profit": 50.0, "swap": 0.0, "magic": 99,
        "comment": "", "openedAt": 1_700_000_000,
    }
]


class ReconcileAdapter(TradingAdapter):
    kind = "fake-reconcile"

    @classmethod
    def availability(cls):
        return True, None

    def probe(self):
        return {"available": True, "connected": True, "account": {"mode": "demo",
                "tradeAllowed": True, "expertAllowed": True, "currency": "USD"},
                "terminal": {"tradeAllowed": True}, "warnings": []}

    def account(self):
        return {"login": 7, "mode": "demo", "currency": "USD",
                "tradeAllowed": True, "expertAllowed": True}

    def positions(self):
        return list(POSITIONS)

    def orders(self):
        return [{"ticket": 900, "symbol": "GBPUSD", "magic": 99}]

    def quote(self, symbol):
        return {"symbol": symbol}

    def order_preview(self, intent):
        return {"ok": True}

    def submit_order(self, intent):
        return {"ok": True, "status": "FILLED", "ticket": 999}

    def cancel_order(self, ticket):
        return {"ok": True, "ticket": ticket}

    def cancel_all(self, magic):
        return {"ok": True, "magic": magic, "matched": 0, "cancelled": 0}

    def deals_since(self, since_ms):
        return [deal for deal in DEALS if int(deal["dealtAt"]) >= int(since_ms or 0)]

    def order_status(self, ticket):
        if int(ticket) == 901:
            return {"found": True, "ticket": 901, "state": 4, "stateName": "filled"}
        return {"found": False, "ticket": int(ticket)}


class HistoryAdapter(ReconcileAdapter):
    kind = "fake-reconcile-history"
    last_window: int | None = None

    def deals_window(self, days):
        HistoryAdapter.last_window = int(days)
        old = {
            "dealTicket": 10, "orderTicket": 900, "positionTicket": 4,
            "symbol": "EURUSD", "side": "buy", "entry": "in", "volume": 0.1,
            "price": 1.0, "commission": 0.0, "swap": 0.0, "profit": 0.0,
            "magic": 99, "comment": "", "dealtAt": 1_690_000_000_000,
            "eclipseOwned": True,
        }
        return [old] + list(DEALS)


class FailingAdapter(ReconcileAdapter):
    kind = "fake-reconcile-fail"

    def positions(self):
        raise AdapterUnavailable("NO_IPC", "no IPC connection to the terminal")


def _service(tmp_path, adapter_cls=ReconcileAdapter, kind="fake-reconcile"):
    store = AgentMemoryStore(os.path.join(str(tmp_path), f"{kind}.db"))
    register_kind(
        BrokerKind(id=kind, label=kind, auth="attach", execution=True,
                   execution_modes=("demo", "live")),
        adapter_cls,
        replace=True,
    )
    service = BrokerService(store)
    connection = service.create_connection(
        kind=kind, label="Reconcile", mode="demo", config={"magic": 99}
    )
    service.connections.set_status(connection["id"], status="connected")
    return service, connection["id"]


def test_sync_is_deduped_and_updates_ledger_state(tmp_path):
    service, connection_id = _service(tmp_path)
    order = service.connections.create_order(
        connection_id=connection_id,
        intent={"symbol": "EURUSD"},
        digest="digest-1",
    )
    service.connections.update_order(order["id"], ticket=901, status="placed")

    reconciler = BrokerReconciler(service)
    first = reconciler.sync(connection_id)
    assert first["ok"] is True
    assert first["fillsAdded"] == 2
    assert first["positions"] == 1
    assert first["ordersUpdated"] == 1
    assert service.connections.get_order(order["id"])["status"] == "filled"
    assert service.connections.get_sync_state(connection_id)["status"] == "ok"
    assert service.connections.list_positions(connection_id)[0]["profit"] == 50.0
    assert len(service.connections.list_fills(connection_id)) == 2

    second = reconciler.sync(connection_id)
    assert second["ok"] is True
    assert second["fillsAdded"] == 0
    assert len(service.connections.list_fills(connection_id)) == 2


def test_sync_failure_is_recorded_not_faked(tmp_path):
    service, connection_id = _service(tmp_path, FailingAdapter, "fake-reconcile-fail")
    result = BrokerReconciler(service).sync(connection_id)
    assert result["ok"] is False
    assert result["error"]["code"] == "NO_IPC"
    state = service.connections.get_sync_state(connection_id)
    assert state["status"] == "unavailable"
    assert service.connections.list_fills(connection_id) == []


def test_history_backfill_uses_an_explicit_window_and_dedupes(tmp_path):
    service, connection_id = _service(
        tmp_path, HistoryAdapter, "fake-reconcile-history"
    )
    reconciler = BrokerReconciler(service)

    first = reconciler.sync(connection_id, history_days=120)
    assert first["ok"] is True
    assert HistoryAdapter.last_window == 120
    assert first["fillsAdded"] == 3  # the old deal + the two current deals
    assert len(service.connections.list_fills(connection_id)) == 3

    # A normal incremental sync ignores the backfill window and the unique
    # (connectionId, dealTicket) key absorbs the overlap.
    second = reconciler.sync(connection_id)
    assert second["ok"] is True
    assert second["fillsAdded"] == 0
    assert len(service.connections.list_fills(connection_id)) == 3


def test_fills_page_with_a_stable_dealt_at_cursor(tmp_path):
    service, connection_id = _service(tmp_path)
    service.connections.save_fills(connection_id, DEALS)
    older = []
    for deal in DEALS:
        copy = dict(deal)
        copy["dealTicket"] += 100
        copy["dealtAt"] -= 1_000
        older.append(copy)
    service.connections.save_fills(connection_id, older)

    page1 = service.connections.list_fills(connection_id, limit=2)
    assert len(page1) == 2
    page2 = service.connections.list_fills(
        connection_id,
        limit=2,
        before_dealt_at=page1[-1]["dealtAt"],
        before_id=page1[-1]["id"],
    )
    assert len(page2) == 2
    tickets = {row["dealTicket"] for row in page1 + page2}
    assert len(tickets) == 4  # no overlap across the cursor


def test_sync_all_skips_unconfigured_connections(tmp_path):
    service, connection_id = _service(tmp_path)
    service.connections.set_status(connection_id, status="unconfigured")
    assert BrokerReconciler(service).sync_all() == []

"""Phase 10: awaiting fills, reconciliation, drift reporting, paper valuation and
the idempotency guard that stops a scheduled graph double-sending."""

from __future__ import annotations

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.paper_store import PaperAccountStore
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.trading_nodes import set_paper_store
from harness.persistence import AgentMemoryStore
from harness.trade import bootstrap

REGISTRY = build_default_registry()


class FakeService:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []
        self.statuses: list[str] = ["filled"]
        self.sync = {"ok": True, "connectionId": "brk_1", "positions": 2,
                     "workingOrders": 1, "fillsAdded": 3}
        self.ledger: list[dict] = []
        self.working: list[dict] = []
        self.recon = {"positions": [], "fills": [], "state": {}}
        self.submitted: list[dict] = []

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def get_ledger_order(self, order_id):
        self._record("get_ledger_order", order_id)
        if order_id == "missing":
            raise KeyError(order_id)
        status = self.statuses.pop(0) if self.statuses else "filled"
        return {"id": order_id, "status": status, "ticket": 11}

    def sync_connection(self, connection_id):
        self._record("sync_connection", connection_id)
        return self.sync

    def ledger_orders(self, connection_id=None, limit=50):
        self._record("ledger_orders", connection_id, limit=limit)
        return self.ledger

    def orders(self, connection_id):
        self._record("orders", connection_id)
        return {"available": True, "data": self.working}

    def reconciliation(self, connection_id, limit=100):
        self._record("reconciliation", connection_id, limit=limit)
        return self.recon

    def submit_order(self, connection_id, payload, **kwargs):
        self._record("submit_order", connection_id, payload, **kwargs)
        self.submitted.append(payload)
        return {"status": "filled", "orderId": f"ord_{len(self.submitted)}", "sent": True}


@pytest.fixture
def service():
    fake = FakeService()
    bootstrap.set_service(fake)
    try:
        yield fake
    finally:
        bootstrap.set_service(None)


@pytest.fixture
def paper_store(tmp_path):
    memory = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    store = PaperAccountStore(memory)
    set_paper_store(store)
    try:
        yield store
    finally:
        set_paper_store(None)
        memory.close()


def _exec(node_type: str, config: dict, inputs: dict, node_id: str = "n1"):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_id, run_id="run", mode=ExecutionMode.PAPER,
        inputs=inputs, config=config,
    ))


def _intent(**overrides):
    base = {"symbol": "TESTUSDT", "side": "buy", "quantity": 10.0}
    base.update(overrides)
    return base


# ── await fill ──────────────────────────────────────────────────────────────


def test_await_fill_returns_a_filled_order_immediately(service):
    result = _exec("trading.await_fill", {"timeoutSeconds": 1.0}, {"orderId": "ord_1"})
    assert result["filled"] is True
    assert result["timedOut"] is False
    assert result["ok"] is True


def test_await_fill_times_out_on_a_still_working_order(service):
    service.statuses = ["placed"] * 50
    result = _exec(
        "trading.await_fill",
        {"timeoutSeconds": 0.1, "pollSeconds": 0.05},
        {"orderId": "ord_1"},
    )
    assert result["filled"] is False
    assert result["timedOut"] is True
    assert result["ok"] is True
    assert "still placed" in result["reason"]


def test_await_fill_reports_a_terminal_refusal(service):
    service.statuses = ["rejected"]
    result = _exec("trading.await_fill", {"timeoutSeconds": 1.0}, {"orderId": "ord_1"})
    assert result["filled"] is False
    assert result["timedOut"] is False
    assert result["reason"] == "the order ended rejected"


def test_await_fill_names_a_missing_ledger_row(service):
    result = _exec("trading.await_fill", {"timeoutSeconds": 1.0}, {"orderId": "missing"})
    assert result["ok"] is False
    assert "no ledger order" in result["reason"]


# ── reconcile ───────────────────────────────────────────────────────────────


def test_reconcile_passes_through_the_sync_summary(service):
    result = _exec("trading.reconcile", {"connectionId": "brk_1"}, {})
    assert result["ok"] is True
    assert result["status"] == "synced"
    assert result["result"]["fillsAdded"] == 3


def test_a_failed_sync_is_not_ok_and_keeps_the_reason(service):
    service.sync = {"ok": False, "connectionId": "brk_1",
                    "error": {"code": "TERMINAL_NOT_RUNNING", "reason": "no terminal"}}
    result = _exec("trading.reconcile", {"connectionId": "brk_1"}, {})
    assert result["ok"] is False
    assert result["reason"] == "TERMINAL_NOT_RUNNING: no terminal"


# ── drift check ─────────────────────────────────────────────────────────────


def _clean(service):
    from datetime import datetime, timezone

    service.ledger = [
        {"id": "ord_1", "status": "filled", "ticket": 11, "intent": {"symbol": "EURUSD"}},
    ]
    service.working = [{"ticket": 21, "symbol": "EURUSD"}]
    service.recon = {
        "positions": [{"ticket": 11, "symbol": "EURUSD"}],
        "fills": [{"orderTicket": 11, "positionTicket": 11}],
        "state": {"lastSyncedAt": datetime.now(timezone.utc).isoformat()},
    }


def test_a_consistent_book_reports_no_drift(service):
    _clean(service)
    result = _exec("trading.drift_check", {"connectionId": "brk_1", "maxAgeSeconds": 300}, {})
    assert result["ok"] is True
    assert result["drift"] is False
    assert result["stale"] is False
    assert result["reason"] == ""
    assert result["summary"]["ledgerRows"] == 1


def test_an_in_flight_order_with_no_broker_match_is_drift(service):
    _clean(service)
    service.ledger.append({"id": "ord_2", "status": "placed", "ticket": 99,
                           "intent": {"symbol": "XAUUSD"}})
    result = _exec("trading.drift_check", {"connectionId": "brk_1"}, {})
    assert result["drift"] is True
    assert [row["orderId"] for row in result["unmatchedOrders"]] == ["ord_2"]
    assert "in-flight ledger order" in result["reason"]


def test_a_position_the_ledger_never_recorded_is_drift(service):
    _clean(service)
    service.recon["positions"].append({
        "ticket": 33, "symbol": "GBPUSD", "side": "sell", "volume": 0.1, "magic": 7,
    })
    result = _exec("trading.drift_check", {"connectionId": "brk_1"}, {})
    assert result["drift"] is True
    assert result["untrackedPositions"][0]["ticket"] == 33


def test_an_old_mirror_is_stale(service):
    _clean(service)
    service.recon["state"] = {"lastSyncedAt": "2020-01-01T00:00:00+00:00"}
    result = _exec("trading.drift_check", {"connectionId": "brk_1", "maxAgeSeconds": 60}, {})
    assert result["stale"] is True
    assert result["drift"] is False
    assert "mirror is" in result["reason"]


def test_a_never_synced_connection_is_stale(service):
    _clean(service)
    service.recon["state"] = {}
    result = _exec("trading.drift_check", {"connectionId": "brk_1"}, {})
    assert result["stale"] is True
    assert "never been synced" in result["reason"]


def test_drift_check_refuses_to_compare_against_an_unreadable_broker(service):
    service.orders = lambda connection_id: {
        "available": False, "error": {"code": "TERMINAL_NOT_RUNNING"},
    }
    with pytest.raises(ValueError, match="working orders"):
        _exec("trading.drift_check", {"connectionId": "brk_1"}, {})


def test_drift_check_can_refresh_the_mirror_before_comparing(service):
    _clean(service)
    service.recon["state"] = {}  # stale until the pre-check sync runs

    def sync(connection_id):
        service.calls.append(("sync_connection", (connection_id,), {}))
        from datetime import datetime, timezone

        service.recon["state"] = {"lastSyncedAt": datetime.now(timezone.utc).isoformat()}
        return {"ok": True, "connectionId": connection_id}

    service.sync_connection = sync
    result = _exec("trading.drift_check", {"connectionId": "brk_1", "syncFirst": True}, {})
    assert service.calls[0][0] == "sync_connection"
    assert result["stale"] is False


def test_a_failed_pre_sync_is_named_and_stops_the_check(service):
    service.sync_connection = lambda connection_id: {
        "ok": False, "error": {"code": "TERMINAL_NOT_RUNNING", "reason": "no terminal"},
    }
    with pytest.raises(ValueError, match="pre-check sync failed"):
        _exec("trading.drift_check", {"connectionId": "brk_1", "syncFirst": True}, {})


# ── paper valuation ─────────────────────────────────────────────────────────


def test_valuation_marks_the_paper_book_to_supplied_prices(paper_store):
    _exec("trading.paper_order", {"price": 100.0, "accountId": "main"},
          {"intent": _intent(quantity=10.0)})
    result = _exec(
        "trading.paper_valuation", {"accountId": "main"},
        {"prices": {"TESTUSDT": 110.0}},
    )
    assert result["ok"] is True
    assert result["equity"] == pytest.approx(100_100.0)
    assert result["unrealizedPnl"] == pytest.approx(100.0)
    assert result["valuation"]["totalPnl"] == pytest.approx(100.0)


def test_valuation_reports_an_unpriced_symbol_instead_of_zeroing_it(paper_store):
    _exec("trading.paper_order", {"price": 100.0, "accountId": "main"},
          {"intent": _intent(quantity=10.0)})
    result = _exec("trading.paper_valuation", {"accountId": "main"}, {"prices": {}})
    assert result["ok"] is False
    assert "no prices" in result["reason"]

    result = _exec(
        "trading.paper_valuation", {"accountId": "main"},
        {"prices": {"OTHER": 5.0}},
    )
    assert result["ok"] is True
    assert result["valuation"]["unpriced"] == ["TESTUSDT"]
    assert result["equity"] == pytest.approx(99_000.0)
    assert "no price for TESTUSDT" in result["reason"]


def test_valuation_accepts_one_symbol_and_price(paper_store):
    _exec("trading.paper_order", {"price": 100.0, "accountId": "main"},
          {"intent": _intent(quantity=2.0)})
    result = _exec(
        "trading.paper_valuation", {"accountId": "main"},
        {"symbol": "testusdt", "price": 90.0},
    )
    assert result["unrealizedPnl"] == pytest.approx(-20.0)


# ── idempotency guard ───────────────────────────────────────────────────────


def test_dedupe_day_fills_once_and_skips_the_second_run(paper_store):
    first = _exec(
        "trading.paper_order",
        {"price": 100.0, "dedupe": "day"},
        {"intent": _intent()},
        node_id="entry",
    )
    assert first["status"] == "FILLED"
    second = _exec(
        "trading.paper_order",
        {"price": 100.0, "dedupe": "day"},
        {"intent": _intent()},
        node_id="entry",
    )
    assert second["status"] == "SKIPPED"
    assert second["skipped"] is True
    assert paper_store.snapshot("paper")["positions"]["TESTUSDT"]["quantity"] == 10.0


def test_dedupe_key_is_independent_per_key(paper_store):
    config = {"price": 100.0, "dedupe": "key", "idempotencyKey": "desk-A"}
    assert _exec("trading.paper_order", config, {"intent": _intent()})["status"] == "FILLED"
    assert _exec("trading.paper_order", config, {"intent": _intent()})["status"] == "SKIPPED"
    other = dict(config, idempotencyKey="desk-B")
    assert _exec("trading.paper_order", other, {"intent": _intent()})["status"] == "FILLED"


def test_dedupe_key_requires_a_key(paper_store):
    with pytest.raises(ValueError, match="idempotencyKey"):
        _exec(
            "trading.paper_order",
            {"price": 100.0, "dedupe": "key"},
            {"intent": _intent()},
        )


def test_without_dedupe_every_run_fills(paper_store):
    for _ in range(2):
        result = _exec("trading.paper_order", {"price": 100.0}, {"intent": _intent()})
        assert result["status"] == "FILLED"
    assert paper_store.snapshot("paper")["positions"]["TESTUSDT"]["quantity"] == 20.0


def test_broker_order_dedupe_sends_only_once(service, paper_store):
    config = {
        "connectionId": "brk_1", "mandateId": "mnd_1",
        "dedupe": "key", "idempotencyKey": "open-long",
    }
    first = _exec("trading.broker_order", config, {"intent": _intent()})
    assert first["status"] == "filled"
    second = _exec("trading.broker_order", config, {"intent": _intent()})
    assert second["status"] == "SKIPPED"
    assert second["skipped"] is True
    assert len(service.submitted) == 1

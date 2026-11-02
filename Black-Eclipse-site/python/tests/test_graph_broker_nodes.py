"""Broker graph nodes: honest read envelopes, a derived bar summary, a
symbol-wide close, and the risk-decision gate on an unattended order."""

from __future__ import annotations

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.trade import bootstrap

REGISTRY = build_default_registry()


class FakeService:
    """The subset of `BrokerService` these nodes call, with no broker."""

    def __init__(self, **overrides):
        self.calls: list[tuple[str, tuple, dict]] = []
        self._account = {"available": True, "data": {"equity": 10_000.0, "mode": "demo"}}
        self._positions = {"available": True, "data": [
            {"ticket": 11, "symbol": "EURUSD", "volume": 0.1},
            {"ticket": 12, "symbol": "EURUSD", "volume": 0.2},
            {"ticket": 13, "symbol": "XAUUSD", "volume": 0.1},
        ]}
        self._bars = {"available": True, "data": {
            "symbol": "XAUUSD", "timeframe": "H1", "contractSize": 100, "tickSize": 0.01,
            "bars": [
                {"high": 10.0 + index, "low": 9.0 + index, "close": 9.5 + index}
                for index in range(30)
            ],
        }}
        for key, value in overrides.items():
            setattr(self, key, value)

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def account(self, connection_id):
        self._record("account", connection_id)
        return self._account

    def positions(self, connection_id):
        self._record("positions", connection_id)
        return self._positions

    def bars(self, connection_id, symbol, timeframe="H1", count=120):
        self._record("bars", connection_id, symbol, timeframe=timeframe, count=count)
        return self._bars

    def close_positions(self, connection_id, *, tickets=None, deviation=20):
        self._record("close_positions", connection_id, tickets=tickets, deviation=deviation)
        results = [{"ok": True, "ticket": ticket} for ticket in (tickets or [])]
        return {
            "available": True,
            "closed": len(results),
            "failed": 0,
            "requested": len(results),
            "results": results,
        }

    def close_position(self, connection_id, ticket, *, volume=None, deviation=20):
        self._record("close_position", connection_id, ticket, volume=volume, deviation=deviation)
        return {
            "available": True,
            "closed": True,
            "result": {"ok": True, "ticket": ticket, "verified": True},
        }

    def modify_position(self, connection_id, ticket, *, stop_loss=None, take_profit=None):
        self._record("modify_position", connection_id, ticket, stop_loss=stop_loss)
        return {
            "available": True,
            "modified": False,
            "result": {"ok": False, "retcodeName": "INVALID_STOPS", "reasons": ["invalid stops"]},
        }

    def submit_order(self, connection_id, payload, **kwargs):
        self._record("submit_order", connection_id, payload, **kwargs)
        return {"status": "filled", "orderId": "ord_1", "sent": True, "filled": True}


@pytest.fixture
def service():
    fake = FakeService()
    bootstrap.set_service(fake)
    try:
        yield fake
    finally:
        bootstrap.set_service(None)


def _exec(node_type: str, config: dict, inputs: dict, node_id: str = "n1"):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_id, run_id="run", mode=ExecutionMode.PAPER,
        inputs=inputs, config=config,
    ))


def test_a_read_is_ok_only_when_the_broker_answered(service):
    assert _exec("trading.broker_account", {"connectionId": "brk_1"}, {})["ok"] is True

    service._account = {
        "available": False,
        "status": "UNAVAILABLE",
        "error": {"code": "TERMINAL_NOT_RUNNING", "reason": "no terminal"},
    }
    result = _exec("trading.broker_account", {"connectionId": "brk_1"}, {})
    assert result["ok"] is False
    assert result["reason"] == "TERMINAL_NOT_RUNNING: no terminal"
    assert result["account"]["available"] is False


def test_broker_positions_returns_the_rows_and_a_count(service):
    result = _exec("trading.broker_positions", {"connectionId": "brk_1"}, {})
    assert result["ok"] is True
    assert result["count"] == 3
    assert result["positions"]["data"][0]["ticket"] == 11


def test_broker_bars_adds_the_same_atr_the_chat_tool_computes(service):
    result = _exec(
        "trading.broker_bars", {"connectionId": "brk_1", "symbol": "XAUUSD"}, {},
    )
    assert result["ok"] is True
    assert result["atr"] == pytest.approx(1.5)
    assert result["contractSize"] == 100
    assert result["summary"]["lookback"] == 20
    assert result["summary"]["atrPeriod"] == 14


def test_broker_bars_is_not_ok_without_a_series(service):
    service._bars = {"available": False, "error": {"code": "BARS_UNAVAILABLE"}}
    result = _exec("trading.broker_bars", {"connectionId": "brk_1", "symbol": "XAUUSD"}, {})
    assert result["ok"] is False
    assert result["reason"] == "BARS_UNAVAILABLE"
    assert result["atr"] is None


def test_close_by_symbol_closes_only_that_symbol(service):
    result = _exec(
        "trading.broker_close", {"connectionId": "brk_1"}, {"symbol": "eurusd"},
    )
    assert result["ok"] is True
    name, args, kwargs = service.calls[-1]
    assert name == "close_positions"
    assert kwargs["tickets"] == [11, 12]


def test_close_by_symbol_is_a_named_outcome_when_nothing_is_held(service):
    result = _exec("trading.broker_close", {"connectionId": "brk_1"}, {"symbol": "GBPUSD"})
    assert result["ok"] is False
    assert result["status"] == "no_position"
    assert "GBPUSD" in result["reason"]


def test_a_refused_modify_surfaces_the_broker_reason(service):
    result = _exec(
        "trading.broker_modify", {"connectionId": "brk_1"},
        {"ticket": 11, "stopLoss": 1.2},
    )
    assert result["ok"] is False
    assert result["reason"] == "invalid stops"
    assert result["status"] == "rejected"


def test_a_rejected_risk_decision_stops_the_order_before_the_broker(service):
    result = _exec(
        "trading.broker_order",
        {"connectionId": "brk_1", "mandateId": "mnd_1"},
        {
            "intent": {"symbol": "EURUSD", "side": "buy", "quantity": 0.1},
            "decision": {"allowed": False, "reasons": ["daily loss brake"]},
        },
    )
    assert result["status"] == "REJECTED"
    assert result["ok"] is False
    assert result["reason"] == "daily loss brake"
    assert service.calls == []


def test_an_approved_decision_reaches_the_broker_with_its_traceability(service):
    result = _exec(
        "trading.broker_order",
        {"connectionId": "brk_1", "mandateId": "mnd_1"},
        {
            "intent": {"symbol": "EURUSD", "side": "buy", "quantity": 0.1},
            "decision": {"allowed": True},
        },
        node_id="order_node",
    )
    assert result["ok"] is True
    assert result["orderId"] == "ord_1"
    name, args, kwargs = service.calls[-1]
    assert name == "submit_order"
    assert kwargs["node_id"] == "order_node"
    assert kwargs["mandate_id"] == "mnd_1"


def test_a_refused_order_is_not_ok(service):
    def refused(connection_id, payload, **kwargs):
        return {"status": "REFUSED", "sent": False, "reasons": ["margin cap exceeded"]}

    service.submit_order = refused
    result = _exec(
        "trading.broker_order",
        {"connectionId": "brk_1", "mandateId": "mnd_1"},
        {"intent": {"symbol": "EURUSD", "side": "buy", "quantity": 0.1}},
    )
    assert result["ok"] is False
    assert result["reason"] == "margin cap exceeded"

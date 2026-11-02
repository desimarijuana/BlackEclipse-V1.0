"""Static symbol facts and working-order modify at the SERVICE layer.

Synthetic adapters only: no terminal, no network. The point is the service
contract — an honest UNAVAILABLE for an unsupported read, the demo/live mode gate
on a modify, and the adapter's own read-back verdict passed through untouched.
"""

from __future__ import annotations

import os

import pytest

from harness.persistence import AgentMemoryStore
from harness.trade.adapter import BrokerAdapter, TradingAdapter
from harness.trade.model import BrokerKind, TradeRefused
from harness.trade.registry import register_kind
from harness.trade.service import BrokerService


class ReadOnlyAdapter(BrokerAdapter):
    kind = "fake-read"

    @classmethod
    def availability(cls):
        return True, None

    def probe(self):
        return {"available": True, "connected": True,
                "terminal": {"connected": True, "tradeAllowed": True},
                "account": self.account(), "warnings": []}

    def account(self):
        return {"login": 1, "mode": "demo", "currency": "USD", "balance": 1.0,
                "equity": 1.0, "leverage": 100}

    def positions(self):
        return []

    def orders(self):
        return []

    def quote(self, symbol):
        return {"symbol": symbol.upper(), "bid": 1.0, "ask": 1.0001}


class SymbolAdapter(ReadOnlyAdapter):
    kind = "fake-symbol"

    def symbol_info(self, symbol):
        return {"symbol": symbol.upper(), "tradeMode": "full", "contractSize": 100_000,
                "volumeStep": 0.01, "sessionsAvailable": False}


class ModifyAdapter(TradingAdapter):
    kind = "fake-modify"
    ACCOUNT_MODE = "demo"
    CALLS: list[tuple] = []

    @classmethod
    def availability(cls):
        return True, None

    def probe(self):
        return {"available": True, "connected": True,
                "terminal": {"connected": True, "tradeAllowed": True},
                "account": self.account(), "warnings": []}

    def account(self):
        return {"login": 2, "mode": type(self).ACCOUNT_MODE, "currency": "USD",
                "balance": 10_000.0, "equity": 10_000.0, "leverage": 100}

    def positions(self):
        return []

    def orders(self):
        return [{"ticket": 77, "symbol": "EURUSD", "type": "buy limit",
                 "openPrice": 1.09}]

    def quote(self, symbol):
        return {"symbol": symbol.upper(), "bid": 1.1, "ask": 1.1002}

    def symbol_info(self, symbol):
        raise NotImplementedError  # exercised elsewhere

    def order_preview(self, intent):  # pragma: no cover - not used here
        raise NotImplementedError

    def submit_order(self, intent):  # pragma: no cover - not used here
        raise NotImplementedError

    def cancel_order(self, ticket):  # pragma: no cover - not used here
        raise NotImplementedError

    def cancel_all(self, magic):  # pragma: no cover - not used here
        raise NotImplementedError

    def modify_order(self, ticket, price=None, stop_loss=None, take_profit=None):
        type(self).CALLS.append((int(ticket), price, stop_loss, take_profit))
        return {
            "ok": True, "ticket": int(ticket), "symbol": "EURUSD",
            "price": price or 1.09, "stopLoss": stop_loss or 0,
            "takeProfit": take_profit or 0,
            "retcode": 10009, "retcodeName": "DONE", "reasons": [],
            "verified": True, "verifyNote": None,
        }


def _service(tmp_path, adapter_cls, *, kind: str, trade: bool) -> BrokerService:
    store = AgentMemoryStore(os.path.join(str(tmp_path), f"{kind}.db"))
    register_kind(
        BrokerKind(id=kind, label=kind, auth="attach", execution=trade,
                   execution_modes=("demo", "live")),
        adapter_cls,
        replace=True,
    )
    service = BrokerService(store)
    service.create_connection(kind=kind, label=kind, mode="demo", config={})
    return service


def _connection_id(service: BrokerService) -> str:
    return service.list_connections()[0]["id"]


def test_symbol_info_is_an_honest_unavailable_when_the_adapter_cannot_report(tmp_path):
    service = _service(tmp_path, ReadOnlyAdapter, kind="fake-read", trade=False)
    result = service.symbol_info(_connection_id(service), "eurusd")
    assert result["available"] is False
    assert result["error"]["code"] == "SYMBOL_INFO_NOT_SUPPORTED"


def test_symbol_info_returns_the_adapters_facts(tmp_path):
    service = _service(tmp_path, SymbolAdapter, kind="fake-symbol", trade=False)
    result = service.symbol_info(_connection_id(service), "eurusd")
    assert result["available"] is True
    assert result["data"]["symbol"] == "EURUSD"
    assert result["data"]["tradeMode"] == "full"


def test_modify_order_passes_every_field_and_the_verdict_through(tmp_path):
    ModifyAdapter.CALLS = []
    service = _service(tmp_path, ModifyAdapter, kind="fake-modify", trade=True)
    connection_id = _connection_id(service)
    result = service.modify_order(connection_id, 77, price=1.091, stop_loss=1.085)
    assert result["modified"] is True
    assert result["result"]["verified"] is True
    assert ModifyAdapter.CALLS == [(77, 1.091, 1.085, None)]
    assert service.events(connection_id)[0]["outcome"] == "ok"


def test_modify_order_needs_something_to_change(tmp_path):
    service = _service(tmp_path, ModifyAdapter, kind="fake-modify", trade=True)
    with pytest.raises(TradeRefused) as excinfo:
        service.modify_order(_connection_id(service), 77)
    assert excinfo.value.code == "INVALID_REQUEST"


def test_modify_order_refuses_a_mode_mismatch(tmp_path):
    class RealAdapter(ModifyAdapter):
        ACCOUNT_MODE = "real"

    service = _service(tmp_path, RealAdapter, kind="fake-modify", trade=True)
    with pytest.raises(TradeRefused) as excinfo:
        service.modify_order(_connection_id(service), 77, price=1.091)
    assert excinfo.value.code == "DEMO_ACCOUNT_REQUIRED"


def test_modify_order_is_unsupported_when_the_adapter_has_no_such_path(tmp_path):
    class NoModifyAdapter(ModifyAdapter):
        modify_order = TradingAdapter.modify_order

    service = _service(tmp_path, NoModifyAdapter, kind="fake-modify", trade=True)
    with pytest.raises(TradeRefused) as excinfo:
        service.modify_order(_connection_id(service), 77, price=1.091)
    assert excinfo.value.code == "ORDER_MODIFY_NOT_SUPPORTED"

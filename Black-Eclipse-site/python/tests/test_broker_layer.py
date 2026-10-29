"""Broker connectivity (P0): adapter registry, connection store, read-only service.

Every test is synthetic. No terminal, no network, no model: a fake adapter proves
the contract, and the real MT5 adapter is only asked whether it is *honest* about
being unavailable on a host that has no terminal.
"""

from __future__ import annotations

import os

import pytest

from harness.persistence import AgentMemoryStore
from harness.tools import ToolRegistry
from harness.trade.adapter import AdapterUnavailable, BrokerAdapter
from harness.trade.model import (
    BrokerConfigError,
    BrokerKind,
    ConnectionMode,
    validate_config,
)
from harness.trade.registry import list_kinds, register_kind
from harness.trade.service import BrokerService
from harness.trade.store import BrokerConnectionStore
from harness.trade.tools import register_broker_tools


# ── config contract ─────────────────────────────────────────────────────────
def test_config_rejects_secret_values_and_unknown_keys():
    with pytest.raises(BrokerConfigError):
        validate_config({"password": "hunter2"})
    with pytest.raises(BrokerConfigError):
        validate_config({"nested": {"apiKey": "abc"}})  # unknown key AND a secret
    with pytest.raises(BrokerConfigError):
        validate_config({"terminalPath": "x", "token": "abc"})
    with pytest.raises(BrokerConfigError):
        validate_config({"madeUpSetting": "x"})
    assert validate_config({"terminalPath": "C:/MT5/terminal64.exe", "magic": "7"}) == {
        "terminalPath": "C:/MT5/terminal64.exe",
        "magic": 7,
    }


# ── store ───────────────────────────────────────────────────────────────────
def _store(tmp_path) -> BrokerConnectionStore:
    return BrokerConnectionStore(AgentMemoryStore(os.path.join(str(tmp_path), "broker.db")))


def test_store_crud_and_status(tmp_path):
    store = _store(tmp_path)
    connection = store.create(
        kind="mt5",
        label="Demo",
        mode=ConnectionMode.DEMO,
        config={"terminalPath": "C:/MT5/terminal64.exe"},
    )
    assert connection.id.startswith("brk_")
    assert store.get(connection.id).mode is ConnectionMode.DEMO

    updated = store.update(connection.id, {"label": "MT5 demo", "mode": "live"})
    assert updated.label == "MT5 demo"
    assert updated.mode is ConnectionMode.LIVE

    store.set_status(connection.id, status="connected", account={"login": 1}, mark_seen=True)
    fresh = store.get(connection.id)
    assert fresh.status == "connected"
    assert fresh.account == {"login": 1}
    assert fresh.last_seen_at

    store.record_event(connection.id, "test", "ok", {"code": None})
    assert store.list_events(connection.id)[0]["outcome"] == "ok"

    assert store.delete(connection.id) is True
    assert store.get(connection.id) is None


def test_store_refuses_a_secret_at_write_time(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(BrokerConfigError):
        store.create(kind="mt5", label="x", config={"password": "nope"})
    assert store.list() == []


# ── registry ────────────────────────────────────────────────────────────────
def test_registry_lists_mt5_honestly():
    kinds = {kind["id"]: kind for kind in list_kinds()}
    assert "mt5" in kinds
    mt5 = kinds["mt5"]
    assert mt5["auth"] == "attach"
    assert mt5["execution"] is True
    assert "demo" in mt5["executionModes"]
    assert "live" in mt5["executionModes"]
    # Availability depends on the host; if it is unavailable the reason must be
    # specific, never empty and never a fake success.
    if not mt5["available"]:
        assert mt5["unavailableReason"]


# ── service with a fake adapter ─────────────────────────────────────────────
class FakeAdapter(BrokerAdapter):
    kind = "fake"

    @classmethod
    def availability(cls):
        return True, None

    def probe(self):
        return {
            "available": True,
            "connected": True,
            "code": None,
            "reason": None,
            "terminalPath": "/fake",
            "terminal": {"connected": True, "tradeAllowed": True},
            "account": self.account(),
            "warnings": [],
        }

    def account(self):
        return {
            "login": 42,
            "mode": "demo",
            "server": "Fake-Server",
            "company": "Fake Brokers",
            "currency": "USD",
            "balance": 1000.0,
            "equity": 1010.0,
            "margin": 0.0,
            "marginFree": 1010.0,
            "marginLevel": 0.0,
            "profit": 10.0,
            "leverage": 100,
            "marginMode": "hedging",
            "tradeAllowed": True,
            "expertAllowed": True,
        }

    def positions(self):
        return [{"symbol": "EURUSD", "side": "buy", "volume": 0.1}]

    def orders(self):
        return [{"ticket": 7, "symbol": "EURUSD", "type": "buy_limit"}]

    def quote(self, symbol):
        return {"symbol": symbol.upper(), "bid": 1.1, "ask": 1.1002, "provider": "fake"}


class UnavailableAdapter(FakeAdapter):
    kind = "fake-unavailable"

    def account(self):
        raise AdapterUnavailable("NOT_LOGGED_IN", "no account is logged in")


def _fake_service(tmp_path, adapter_cls=FakeAdapter, kind="fake") -> BrokerService:
    register_kind(
        BrokerKind(id=kind, label="Fake broker", auth="attach", execution=False),
        lambda config: adapter_cls(config),
        replace=True,
    )
    return BrokerService(AgentMemoryStore(os.path.join(str(tmp_path), "service.db")))


def test_service_reads_account_positions_orders_and_quote(tmp_path):
    service = _fake_service(tmp_path)
    connection = service.create_connection(kind="fake", label="Fake", mode="demo")

    tested = service.test_connection(connection["id"])
    assert tested["available"] is True
    assert service.get_connection(connection["id"])["status"] == "connected"
    assert service.get_connection(connection["id"])["account"]["login"] == 42

    assert service.account(connection["id"])["data"]["currency"] == "USD"
    assert service.positions(connection["id"])["data"][0]["symbol"] == "EURUSD"
    assert service.orders(connection["id"])["data"][0]["ticket"] == 7
    assert service.quote(connection["id"], "eurusd")["data"]["symbol"] == "EURUSD"
    assert service.events(connection["id"])


def test_service_reports_unavailable_without_faking_state(tmp_path):
    service = _fake_service(tmp_path, UnavailableAdapter, "fake-unavailable")
    connection = service.create_connection(kind="fake-unavailable", label="Broken", mode="demo")
    result = service.account(connection["id"])
    assert result["available"] is False
    assert result["status"] == "UNAVAILABLE"
    assert result["error"]["code"] == "NOT_LOGGED_IN"
    assert service.get_connection(connection["id"])["status"] == "unavailable"


def test_service_rejects_unknown_kind_and_missing_connection(tmp_path):
    service = _fake_service(tmp_path)
    with pytest.raises(KeyError):
        service.create_connection(kind="not-a-broker", label="x")
    with pytest.raises(KeyError):
        service.account("brk_missing")


# ── tools ────────────────────────────────────────────────────────────────────
def test_broker_tools_have_one_mandate_authorized_submit_path():
    registry = ToolRegistry()
    register_broker_tools(registry)
    names = set(registry._tools)  # noqa: SLF001 - the registry is the contract
    assert {
        "broker_connections", "broker_account", "broker_positions",
        "broker_orders", "broker_quote", "order_preview", "order_submit",
        "broker_mandates", "order_ledger", "broker_reconciliation", "broker_fills",
    } <= names
    assert not any("cancel" in name for name in names)
    # `order_submit` is admitted by an ACTIVE MANDATE in its handler/service, not
    # by the generic approval gate; every tool still passes the registry's read
    # permission check, and the effect metadata records the real effect class.
    for name in names:
        assert registry.get(name).permission == "read"
    submit = registry.get("order_submit")
    assert submit.effect == "trading"
    assert submit.risk == "high"

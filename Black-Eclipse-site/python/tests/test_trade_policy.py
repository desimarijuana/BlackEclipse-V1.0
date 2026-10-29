"""Pre-trade risk limits: per-trade risk, per-symbol notional, 24h loss brake.

The policy is pure, so these tests feed it the exact preview the adapter builds.
The daily brake needs the broker's deal history, so it is exercised through the
service with the fake adapter.
"""

from __future__ import annotations

import pytest

from harness.trade.model import TradeRefused
from harness.trade.policy import TradePolicy

from test_broker_orders import (
    FakeTradingAdapter, _connection_id, _intent, _mandate, _service,
)


def _preview(**overrides):
    base = {
        "symbol": "XAUUSD",
        "volume": 0.01,
        "price": 4000.0,
        "stopLoss": 3990.0,
        "notional": 4000.0,
        "contractSize": 100.0,
        "margin": 40.0,
        "spreadPoints": 20.0,
        "openPositions": 0,
        "account": {"equity": 100_000.0, "profit": 0.0},
    }
    base.update(overrides)
    return base


def test_risk_per_trade_accepts_a_small_loss():
    policy = TradePolicy(risk_per_trade_pct=0.5)
    result = policy.evaluate(_preview())
    # 10 price points x 0.01 lot x 100 oz = 10.00 against a 500.00 cap.
    assert result["allowed"] is True
    assert result["rules"] == []


def test_risk_per_trade_refuses_an_oversized_stop_or_size():
    policy = TradePolicy(risk_per_trade_pct=0.5)
    result = policy.evaluate(_preview(volume=1.0))  # 10 x 1 x 100 = 1,000 > 500
    assert result["allowed"] is False
    assert "policy.risk-per-trade" in result["rules"]


def test_risk_per_trade_requires_a_defined_stop():
    policy = TradePolicy(risk_per_trade_pct=0.5)
    result = policy.evaluate(_preview(stopLoss=None))
    assert result["allowed"] is False
    assert "policy.risk-stop-required" in result["rules"]


def test_per_symbol_notional_cap():
    policy = TradePolicy(max_symbol_notional=2500)
    result = policy.evaluate(_preview(notional=4000))
    assert result["allowed"] is False
    assert "policy.max-symbol-notional" in result["rules"]


def test_daily_loss_brake_blocks_a_new_order(tmp_path):
    FakeTradingAdapter.DEALS = [{"profit": -2500.0}]
    service = _service(tmp_path)
    connection_id = _connection_id(service)
    service.update_connection(connection_id, {"config": {"maxDailyLossPct": 2}})
    connection = service.connections.get(connection_id)
    adapter = service._trading_adapter(connection)
    try:
        with pytest.raises(TradeRefused) as caught:
            service._assert_daily_loss(connection, adapter, _preview())
    finally:
        adapter.close()
    assert caught.value.code == "DAILY_LOSS_LIMIT"


def test_daily_loss_brake_refuses_before_any_send(tmp_path):
    FakeTradingAdapter.DEALS = [{"profit": -3000.0}]
    FakeTradingAdapter.SUBMIT_CALLS = 0
    service = _service(tmp_path)
    connection_id = _connection_id(service)
    service.update_connection(connection_id, {"config": {"maxDailyLossPct": 2}})
    mandate = _mandate(service, connection_id)
    with pytest.raises(TradeRefused) as caught:
        service.submit_order(connection_id, _intent(), mandate_id=mandate["id"])
    assert caught.value.code == "DAILY_LOSS_LIMIT"
    # The brake ran before the broker: nothing was sent, no mandate consumed.
    assert FakeTradingAdapter.SUBMIT_CALLS == 0
    assert service.mandates.get(mandate["id"])["ordersUsed"] == 0


def test_daily_loss_brake_allows_a_profitable_day(tmp_path):
    FakeTradingAdapter.DEALS = [{"profit": 500.0}]
    service = _service(tmp_path)
    connection_id = _connection_id(service)
    service.update_connection(connection_id, {"config": {"maxDailyLossPct": 2}})
    connection = service.connections.get(connection_id)
    adapter = service._trading_adapter(connection)
    try:
        service._assert_daily_loss(connection, adapter, _preview())
    finally:
        adapter.close()


def test_daily_brake_is_off_by_default(tmp_path):
    FakeTradingAdapter.DEALS = [{"profit": -90_000.0}]
    service = _service(tmp_path)
    connection_id = _connection_id(service)
    connection = service.connections.get(connection_id)
    adapter = service._trading_adapter(connection)
    try:
        service._assert_daily_loss(connection, adapter, _preview())
    finally:
        adapter.close()

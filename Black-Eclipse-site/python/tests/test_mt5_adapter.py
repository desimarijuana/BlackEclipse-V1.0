"""Pure MetaTrader request-builder tests (no package, no terminal).

The `MetaTrader5` module is imported lazily, so these helpers are testable on any
host. They encode the rules MT5 will reject later: volume steps, stop distance,
filling mode and pending-price side.
"""

from __future__ import annotations

from types import SimpleNamespace

from harness.trade.adapters.mt5 import (
    _build_request,
    _filling_mode,
    _normalise_volume,
    _notional,
    _retcode,
    _stops_reasons,
)
from harness.trade.model import OrderIntent


class FakeMT5:
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    TRADE_ACTION_REMOVE = 8
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TYPE_SELL_STOP = 5
    ORDER_TIME_GTC = 0
    ORDER_TIME_DAY = 1
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2


def _info(**overrides):
    base = dict(
        name="EURUSD", point=0.0001, digits=5, trade_stops_level=20,
        filling_mode=1, trade_mode=4, volume_step=0.01, volume_min=0.01,
        volume_max=100.0, trade_contract_size=100_000.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _tick(bid=1.1000, ask=1.1002):
    return SimpleNamespace(bid=bid, ask=ask, last=1.1, time_msc=1)


def _intent(**overrides):
    base = dict(
        connection_id="brk_1", symbol="EURUSD", side="buy",
        order_type="market", volume=0.1,
    )
    base.update(overrides)
    return OrderIntent(**base)


def test_volume_must_be_a_valid_step_not_silently_resized():
    volume, reasons = _normalise_volume(_info(), 0.1)
    assert volume == 0.1
    assert reasons == []
    volume, reasons = _normalise_volume(_info(), 0.105)
    assert volume == 0.1
    assert any("multiple" in reason for reason in reasons)
    _, reasons = _normalise_volume(_info(), 0.001)
    assert any("minimum" in reason for reason in reasons)


def test_stop_distance_uses_points_and_side():
    # 20 points * 0.0001 = 0.0020
    assert _stops_reasons("buy", 1.1, 0.0001, 20, 1.0995, 1.1005)
    assert _stops_reasons("buy", 1.1, 0.0001, 20, 1.097, 1.103) == []
    assert _stops_reasons("sell", 1.1, 0.0001, 20, 1.0995, 1.1005)
    assert _stops_reasons("sell", 1.1, 0.0001, 20, 1.103, 1.097) == []


def test_filling_mode_picks_an_allowed_mode():
    assert _filling_mode(FakeMT5, _info(filling_mode=1)) == (0, [])
    assert _filling_mode(FakeMT5, _info(filling_mode=2)) == (1, [])
    assert _filling_mode(FakeMT5, _info(filling_mode=4), "limit") == (3, [])
    mode, reasons = _filling_mode(FakeMT5, _info(filling_mode=4), "market")
    assert mode == 2
    assert reasons
    mode, reasons = _filling_mode(FakeMT5, _info(filling_mode=0))
    assert mode == 2
    assert reasons


def test_market_buy_uses_ask_and_deal_action():
    request, reasons, price = _build_request(
        FakeMT5, _intent(), _info(), _tick(), filling=1
    )
    assert reasons == []
    assert request["action"] == 1
    assert request["type"] == 0
    assert request["price"] == 1.1002
    assert price == 1.1002
    assert request["type_filling"] == 1


def test_buy_limit_must_be_below_the_ask():
    request, reasons, _ = _build_request(
        FakeMT5, _intent(order_type="limit", price=1.1010), _info(), _tick(), filling=2
    )
    assert request["action"] == 5
    assert request["type"] == 2
    assert any("below the current ask" in reason for reason in reasons)


def test_sell_stop_must_be_below_the_bid():
    _, reasons, _ = _build_request(
        FakeMT5,
        _intent(side="sell", order_type="stop", price=1.1010),
        _info(), _tick(), filling=2,
    )
    assert any("below the current bid" in reason for reason in reasons)


def test_disabled_symbol_is_refused():
    _, reasons, _ = _build_request(
        FakeMT5, _intent(), _info(trade_mode=0), _tick(), filling=1
    )
    assert any("disabled" in reason for reason in reasons)


def test_retcode_names_are_specific():
    assert _retcode(10019)[0] == "NO_MONEY"
    assert _retcode(10027)[0] == "CLIENT_DISABLES_AT"
    assert _retcode(10030)[0] == "INVALID_FILL"
    assert _retcode(123456)[0] == "UNKNOWN"


def test_notional_uses_contract_size():
    assert _notional(0.1, _info(), 1.1) == 11_000.0

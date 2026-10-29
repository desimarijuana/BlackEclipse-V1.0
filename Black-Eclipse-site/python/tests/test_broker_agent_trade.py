"""Agent trade authorization: a mandate, not a generic approval.

`order_submit` is the one effectful broker tool. This test proves the authorizer
admits it only for an active mandate that covers the connection and symbol, and
delegates every other tool unchanged.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from harness.trade.authorizers import wrap_trade_authorizer
from harness.trade.bootstrap import set_service


class FakeMandates:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    def covers(self, mandate_id: str, *, connection_id: str, symbol: str) -> bool:
        return (
            self.allowed
            and mandate_id == "mnd_ok"
            and connection_id == "brk_1"
            and symbol.upper() == "EURUSD"
        )


class FakeService:
    def __init__(self, allowed: bool = True) -> None:
        self.mandates = FakeMandates(allowed)


async def _never(tool, args, ctx=None):
    return False


def _tool(name: str):
    return SimpleNamespace(name=name)


def _args(**overrides):
    base = {
        "connectionId": "brk_1",
        "mandateId": "mnd_ok",
        "intent": {"symbol": "EURUSD", "side": "buy", "type": "market", "volume": 0.01},
    }
    base.update(overrides)
    return base


def test_order_submit_requires_an_active_mandate():
    set_service(FakeService(True))
    try:
        authorize = wrap_trade_authorizer(_never)
        assert asyncio.run(authorize(_tool("order_submit"), _args())) is True
    finally:
        set_service(None)

    set_service(FakeService(False))
    try:
        assert asyncio.run(authorize(_tool("order_submit"), _args())) is False
    finally:
        set_service(None)


def test_order_submit_refuses_mismatched_connection_or_symbol():
    set_service(FakeService(True))
    try:
        authorize = wrap_trade_authorizer(_never)
        assert asyncio.run(authorize(
            _tool("order_submit"), _args(connectionId="brk_2")
        )) is False
        assert asyncio.run(authorize(
            _tool("order_submit"), _args(intent={"symbol": "GBPUSD"})
        )) is False
        assert asyncio.run(authorize(_tool("order_submit"), {})) is False
    finally:
        set_service(None)


def test_other_tools_delegate_to_the_existing_authorizer():
    set_service(FakeService(True))
    try:
        authorize = wrap_trade_authorizer(_never)
        assert asyncio.run(authorize(_tool("broker_account"), _args())) is False
    finally:
        set_service(None)


def test_no_service_fails_closed():
    set_service(None)
    authorize = wrap_trade_authorizer(_never)
    assert asyncio.run(authorize(_tool("order_submit"), _args())) is False

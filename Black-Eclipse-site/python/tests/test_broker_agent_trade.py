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
        self.calls: list[dict[str, str]] = []

    def covers(
        self, mandate_id: str, *, connection_id: str, symbol: str, mode: str = "",
    ) -> bool:
        self.calls.append({"connectionId": connection_id, "symbol": symbol, "mode": mode})
        return (
            self.allowed
            and mode == "demo"
            and mandate_id == "mnd_ok"
            and connection_id == "brk_1"
            and symbol.upper() == "EURUSD"
        )


class FakeService:
    def __init__(
        self, allowed: bool = True, active: list[dict] | None = None,
        connections: list[dict] | None = None,
    ) -> None:
        self.mandates = FakeMandates(allowed)
        self.active = active if active is not None else [{"id": "mnd_ok"}]
        self.connections = connections if connections is not None else [
            {"id": "brk_1", "mode": "demo"}, {"id": "brk_2", "mode": "demo"},
        ]

    def list_mandates(self, connection_id: str, *, active_only: bool = False):
        if connection_id not in {item["id"] for item in self.connections}:
            return []
        return self.active

    def list_connections(self):
        return self.connections


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


def test_order_submit_resolves_the_single_active_mandate():
    set_service(FakeService(True))
    try:
        authorize = wrap_trade_authorizer(_never)
        args = _args()
        args.pop("mandateId")
        assert asyncio.run(authorize(_tool("order_submit"), args)) is True
    finally:
        set_service(None)


def test_order_submit_requires_an_explicit_id_when_several_are_active():
    set_service(FakeService(True, active=[{"id": "mnd_ok"}, {"id": "mnd_other"}]))
    try:
        authorize = wrap_trade_authorizer(_never)
        args = _args()
        args.pop("mandateId")
        assert asyncio.run(authorize(_tool("order_submit"), args)) is False
    finally:
        set_service(None)


def test_position_close_needs_no_mandate_but_a_target():
    set_service(None)  # closing must not touch the mandate store at all
    authorize = wrap_trade_authorizer(_never)
    assert asyncio.run(authorize(_tool("position_close"), {"ticket": 111})) is True
    assert asyncio.run(authorize(_tool("position_close"), {"all": True})) is True
    assert asyncio.run(authorize(_tool("position_close"), {})) is False


def test_position_close_without_a_target_is_denied_even_if_the_inner_gate_allows():
    async def allow(tool, args, ctx=None):
        return True

    authorize = wrap_trade_authorizer(allow)
    assert asyncio.run(authorize(_tool("position_close"), {})) is False


def test_position_modify_needs_a_ticket_and_a_level():
    set_service(None)
    authorize = wrap_trade_authorizer(_never)
    assert asyncio.run(authorize(
        _tool("position_modify"), {"ticket": 111, "stopLoss": 1.10}
    )) is True
    assert asyncio.run(authorize(_tool("position_modify"), {"ticket": 111})) is False
    assert asyncio.run(authorize(_tool("position_modify"), {"stopLoss": 1.10})) is False


def test_other_tools_still_delegate_to_the_inner_authorizer():
    async def allow(tool, args, ctx=None):
        return True

    authorize = wrap_trade_authorizer(allow)
    assert asyncio.run(authorize(_tool("broker_positions"), {})) is True


def test_order_submit_drops_a_stale_connection_id_when_one_is_saved():
    set_service(FakeService(True, connections=[{"id": "brk_1", "mode": "demo"}]))
    try:
        authorize = wrap_trade_authorizer(_never)
        assert asyncio.run(authorize(
            _tool("order_submit"), _args(connectionId="brk_from_another_db")
        )) is True
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


def test_order_submit_refuses_a_live_connection_even_with_an_active_mandate():
    """The live gate must be enforced by MODE, not by prompt wording.

    Regression: `wrap_trade_authorizer` used to check only mandate coverage, so a
    live mandate with an empty workflow pin on an armed connection could be
    submitted from an agent/bot run. The agent tool surface is demo-only.
    """
    set_service(FakeService(True, connections=[{"id": "brk_1", "mode": "live"}]))
    try:
        authorize = wrap_trade_authorizer(_never)
        assert asyncio.run(authorize(_tool("order_submit"), _args())) is False
    finally:
        set_service(None)


def test_order_submit_refuses_an_unknown_mode():
    # A connection whose mode cannot be read is refused: never guess "demo".
    set_service(FakeService(True, connections=[{"id": "brk_1"}]))
    try:
        authorize = wrap_trade_authorizer(_never)
        assert asyncio.run(authorize(_tool("order_submit"), _args())) is False
    finally:
        set_service(None)


def test_order_submit_passes_the_connection_mode_to_the_mandate_check():
    service = FakeService(True)
    set_service(service)
    try:
        authorize = wrap_trade_authorizer(_never)
        assert asyncio.run(authorize(_tool("order_submit"), _args())) is True
        assert service.mandates.calls[-1]["mode"] == "demo"
    finally:
        set_service(None)


def test_position_close_is_still_allowed_on_a_live_connection():
    # Exits must never be blocked by the live gate: an expired grant must not
    # trap the operator (or a bot) in a live position.
    set_service(FakeService(True, connections=[{"id": "brk_1", "mode": "live"}]))
    try:
        authorize = wrap_trade_authorizer(_never)
        assert asyncio.run(authorize(_tool("position_close"), {"ticket": 111})) is True
    finally:
        set_service(None)

"""A scriptable MetaTrader 5 terminal for chaos tests (no package, no IPC).

It implements only the slice the adapter calls, with knobs for the failures that
matter: a lost send reply, a rejected bracket, a dropped stop, a partial fill and
a modify the broker accepts but does not store. Keep it boring and inspectable —
a simulator that is cleverer than the adapter proves nothing.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class SimTerminal:
    # ── constants the adapter reads ──────────────────────────────────────────
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    TRADE_ACTION_SLTP = 6
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
    ORDER_FILLING_BOC = 3
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440
    TIMEFRAME_W1 = 10080

    def __init__(self, *, balance: float = 100_000.0) -> None:
        self.balance = balance
        self.equity = balance
        self.positions: dict[int, SimpleNamespace] = {}
        self.orders: dict[int, SimpleNamespace] = {}
        self.deals: list[SimpleNamespace] = []
        self.send_calls = 0
        self.initialize_calls = 0
        self._next_ticket = 1000
        self._next_deal = 5000
        # knobs
        self.disconnect = False
        self.ambiguous_once = False
        self.check_retcode = 0
        self.drop_bracket = False
        self.ignore_bracket = False
        self.fill_fraction = 1.0
        self.connected = True
        self.symbols = {
            "XAUUSD": self._symbol("XAUUSD", point=0.01, digits=2, contract=100.0),
            "EURUSD": self._symbol("EURUSD", point=0.0001, digits=5, contract=100_000.0),
        }
        self.ticks = {
            "XAUUSD": self._tick(4000.0, 4000.3),
            "EURUSD": self._tick(1.1000, 1.1002),
        }

    # ── construction helpers ─────────────────────────────────────────────────
    @staticmethod
    def _symbol(name: str, *, point: float, digits: int, contract: float):
        return SimpleNamespace(
            name=name, point=point, digits=digits, trade_contract_size=contract,
            trade_tick_size=point, trade_tick_value=0.1,
            volume_min=0.01, volume_max=100.0, volume_step=0.01,
            trade_stops_level=0, trade_mode=4, filling_mode=2,
            select=True, visible=True,
        )

    @staticmethod
    def _tick(bid: float, ask: float):
        return SimpleNamespace(
            bid=bid, ask=ask, last=bid, time=1_700_000_000,
            time_msc=1_700_000_000_000, flags=6, volume=1,
        )

    def _ticket(self) -> int:
        self._next_ticket += 1
        return self._next_ticket

    def _deal(self) -> int:
        self._next_deal += 1
        return self._next_deal

    # ── terminal / account ───────────────────────────────────────────────────
    def initialize(self, **kwargs: Any) -> bool:
        self.initialize_calls += 1
        return not self.disconnect

    def shutdown(self) -> None:
        return None

    def last_error(self) -> tuple[int, str]:
        if self.disconnect:
            return -10004, "IPC timeout"
        return 0, "ok"

    def terminal_info(self) -> Any:
        return SimpleNamespace(connected=not self.disconnect, trade_allowed=True)

    def account_info(self) -> Any:
        if self.disconnect:
            return None
        free = self.equity - self._used_margin()
        return SimpleNamespace(
            login=114826727, trade_mode=0, margin_mode=2,
            balance=self.balance, equity=self.equity, margin=self._used_margin(),
            margin_free=free, margin_level=0.0, profit=self._open_profit(),
            leverage=100, currency="USD", server="Sim", company="Sim",
            trade_allowed=True, trade_expert=True,
        )

    def _used_margin(self) -> float:
        total = 0.0
        for position in self.positions.values():
            info = self.symbols[position.symbol]
            total += position.volume * info.trade_contract_size * position.price_open / 100
        return round(total, 2)

    def _open_profit(self) -> float:
        total = 0.0
        for position in self.positions.values():
            info = self.symbols[position.symbol]
            tick = self.ticks[position.symbol]
            mark = tick.bid if position.type == 0 else tick.ask
            direction = 1 if position.type == 0 else -1
            total += (mark - position.price_open) * direction * position.volume * info.trade_contract_size
        return round(total, 2)

    # ── symbols ──────────────────────────────────────────────────────────────
    def symbols_get(self) -> list[Any]:
        return list(self.symbols.values())

    def symbol_info(self, name: str) -> Any:
        return self.symbols.get(name)

    def symbol_info_tick(self, name: str) -> Any:
        return self.ticks.get(name)

    def symbol_select(self, name: str, enable: bool = True) -> bool:
        return name in self.symbols

    # ── reads ────────────────────────────────────────────────────────────────
    def positions_get(self, *, ticket: int | None = None, symbol: str | None = None):
        rows = list(self.positions.values())
        if ticket is not None:
            rows = [row for row in rows if row.ticket == int(ticket)]
        if symbol is not None:
            rows = [row for row in rows if row.symbol == symbol]
        return tuple(rows)

    def orders_get(self, *, magic: int | None = None):
        rows = list(self.orders.values())
        if magic is not None:
            rows = [row for row in rows if row.magic == int(magic)]
        return tuple(rows)

    def history_deals_get(self, since: Any, until: Any):
        return tuple(self.deals)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start: int, count: int):
        base = self.ticks.get(symbol, self._tick(100.0, 100.1)).bid
        bars = []
        for index in range(int(count)):
            drift = ((index % 12) - 6) * 0.9
            close = base + drift
            bars.append({
                "time": 1_700_000_000 + index * 3600,
                "open": close - 0.4,
                "high": close + 1.1,
                "low": close - 1.3,
                "close": close,
                "tick_volume": 100 + index,
                "spread": 20,
            })
        return bars

    # ── execution ────────────────────────────────────────────────────────────
    def order_check(self, request: dict[str, Any]) -> Any:
        info = self.symbols.get(request.get("symbol"))
        price = float(request.get("price") or 0)
        volume = float(request.get("volume") or 0)
        margin = volume * info.trade_contract_size * price / 100 if info else 0.0
        free = self.equity - self._used_margin()
        if self.check_retcode:
            return SimpleNamespace(
                retcode=self.check_retcode, margin=margin, margin_free=free,
                balance=self.balance, equity=self.equity,
                comment="Invalid stops",
            )
        return SimpleNamespace(
            retcode=0, margin=margin + self._used_margin(),
            margin_free=max(free - margin, 0.0), balance=self.balance,
            equity=self.equity, comment="Done",
        )

    def order_send(self, request: dict[str, Any]) -> Any:
        self.send_calls += 1
        if self.disconnect:
            return None
        action = int(request.get("action") or 0)
        if action == self.TRADE_ACTION_REMOVE:
            self.orders.pop(int(request.get("order") or 0), None)
            return self._result(10009, 0, 0, 0.0, 0.0)
        if action == self.TRADE_ACTION_SLTP:
            ticket = int(request.get("position") or 0)
            if not self.ignore_bracket and ticket in self.positions:
                self.positions[ticket].sl = float(request.get("sl") or 0)
                self.positions[ticket].tp = float(request.get("tp") or 0)
            return self._result(10009, ticket, 0, 0.0, 0.0)
        if action == self.TRADE_ACTION_DEAL:
            return self._deal_send(request)
        return self._result(10030, 0, 0, 0.0, 0.0)

    def _deal_send(self, request: dict[str, Any]) -> Any:
        symbol = str(request.get("symbol") or "")
        info = self.symbols[symbol]
        volume = float(request.get("volume") or 0)
        price = float(request.get("price") or 0)
        closing = request.get("position")
        if closing is not None:
            ticket = int(closing)
            position = self.positions.get(ticket)
            if position is None:
                return self._result(10013, 0, 0, 0.0, 0.0)
            filled = min(volume, position.volume)
            if self.fill_fraction < 1.0:
                filled = max(info.volume_min, round(volume * self.fill_fraction, 2))
                filled = min(filled, position.volume)
            position.volume = round(position.volume - filled, 2)
            if position.volume <= 0:
                self.positions.pop(ticket, None)
            deal = self._deal()
            self.deals.append(SimpleNamespace(
                ticket=deal, order=ticket, position_id=ticket, symbol=symbol,
                type=1 if position.type == 0 else 0, entry=1, volume=filled,
                price=price, profit=0.0, magic=position.magic, comment="close",
            ))
            self._ambiguous_reply()
            return self._result(10009, ticket, deal, filled, price)
        ticket = self._ticket()
        stop_loss = float(request.get("sl") or 0)
        take_profit = float(request.get("tp") or 0)
        if self.drop_bracket:
            stop_loss = 0.0
            take_profit = 0.0
        position = SimpleNamespace(
            ticket=ticket, symbol=symbol, type=int(request.get("type") or 0),
            volume=volume, price_open=price, sl=stop_loss, tp=take_profit,
            profit=0.0, magic=int(request.get("magic") or 0), time=1_700_000_000,
        )
        self.positions[ticket] = position
        deal = self._deal()
        self.deals.append(SimpleNamespace(
            ticket=deal, order=ticket, position_id=ticket, symbol=symbol,
            type=position.type, entry=0, volume=volume, price=price, profit=0.0,
            magic=position.magic, comment="open",
        ))
        self._ambiguous_reply()
        return self._result(10009, ticket, deal, volume, price)

    def _ambiguous_reply(self) -> None:
        # The order DID reach the broker; only the reply is lost.
        if self.ambiguous_once:
            self.ambiguous_once = False
            self._lost_reply = True

    def _result(self, code: int, order: int, deal: int, volume: float, price: float):
        result = SimpleNamespace(
            retcode=code, order=order, deal=deal, volume=volume, price=price,
            comment="Request executed" if code == 10009 else "Rejected",
            request_id=1,
        )
        if getattr(self, "_lost_reply", False):
            self._lost_reply = False
            return None
        return result


__all__ = ["SimTerminal"]

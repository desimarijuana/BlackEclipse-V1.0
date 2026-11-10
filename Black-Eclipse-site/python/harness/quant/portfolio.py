"""Portfolio engine — cash, positions, realized/unrealized P&L, exposure.

One portfolio holds the shared capital for every symbol in a run, so
multi-symbol strategies draw on the *same* cash and are accounted together
(never each assuming independent capital). Accounting invariants:

    equity == cash + Σ position.market_value(last_price)
    net_pnl == realized + unrealized (tracked, tested)

Fill cost note: `Fill.price` already includes slippage/spread/impact (applied
adversely to the execution price). Those components are reported for audit but
are NOT charged again to cash — only `commission` is deducted separately.
"""

from __future__ import annotations

from typing import Optional

from .models import EquityPoint, Fill, Position, TradeRecord


class Portfolio:
    def __init__(
        self,
        initial_capital: float,
        *,
        allow_short: bool = True,
        max_leverage: Optional[float] = None,
    ) -> None:
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.positions: dict[str, Position] = {}
        self.last_prices: dict[str, float] = {}
        self.realized_pnl = 0.0
        self.total_commission = 0.0
        self.total_slippage = 0.0
        self.total_spread = 0.0
        self.total_impact = 0.0
        # Cost-of-carry and corporate-action ledgers. They are cash movements,
        # not trading P&L, and are reported separately so a strategy cannot hide
        # borrow/financing inside its "edge".
        self.total_financing = 0.0
        self.total_borrow = 0.0
        self.total_dividends = 0.0
        self.carry_events: list[dict] = []
        self.allow_short = allow_short
        self.max_leverage = max_leverage
        self._trade_seq = 0
        self.trades: list[TradeRecord] = []

    # ── Position access ──────────────────────────────────────────────────────
    def position(self, symbol: str) -> Position:
        pos = self.positions.get(symbol)
        if pos is None:
            pos = Position(symbol=symbol)
            self.positions[symbol] = pos
        return pos

    def open_positions(self) -> list[Position]:
        return [p for p in self.positions.values() if not p.is_flat]

    def is_flat(self, symbol: str) -> bool:
        return self.position(symbol).is_flat

    # ── Mark-to-market ───────────────────────────────────────────────────────
    def mark(self, symbol: str, price: float) -> None:
        if price is None or price <= 0:
            return
        self.last_prices[symbol] = price
        pos = self.positions.get(symbol)
        if pos is not None and not pos.is_flat:
            pos.last_price = price
            entry = pos.avg_entry_price
            if pos.quantity > 0:
                fav = price - entry
                adv = entry - price
            else:
                fav = entry - price
                adv = price - entry
            pos.mfe = fav if pos.mfe is None else max(pos.mfe, fav)
            pos.mae = adv if pos.mae is None else max(pos.mae, adv)

    def _positions_value(self) -> float:
        total = 0.0
        for pos in self.positions.values():
            if pos.is_flat:
                continue
            price = self.last_prices.get(pos.symbol, pos.last_price)
            if price is not None:
                total += pos.quantity * price
        return total

    @property
    def equity(self) -> float:
        return self.cash + self._positions_value()

    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl(self.last_prices.get(p.symbol)) for p in self.positions.values())

    def gross_exposure(self) -> float:
        return sum(
            abs(p.quantity * (self.last_prices.get(p.symbol) or p.last_price or 0.0))
            for p in self.positions.values() if not p.is_flat
        )

    def net_exposure(self) -> float:
        return sum(
            p.quantity * (self.last_prices.get(p.symbol) or p.last_price or 0.0)
            for p in self.positions.values() if not p.is_flat
        )

    def leverage(self) -> float:
        eq = self.equity
        if eq <= 0:
            return 0.0
        return self.gross_exposure() / eq

    def snapshot(self, index: int, ts: Optional[str]) -> EquityPoint:
        eq = self.equity
        return EquityPoint(
            index=index, ts=ts, equity=eq, cash=self.cash,
            positions_value=self._positions_value(),
            gross_exposure=self.gross_exposure(),
            net_exposure=self.net_exposure(),
            leverage=self.leverage(),
        )

    # ── Fill application ─────────────────────────────────────────────────────
    def apply_fill(self, fill: Fill) -> Optional[TradeRecord]:
        """Apply a fill; returns a TradeRecord if it closed (part of) a position."""
        symbol = fill.symbol
        price = fill.price
        signed = fill.quantity if fill.side == "buy" else -fill.quantity
        self.cash -= signed * price
        self.cash -= fill.commission
        self.total_commission += fill.commission
        self.total_slippage += fill.slippage
        self.total_spread += fill.spread_cost
        self.total_impact += fill.impact
        self.last_prices[symbol] = price

        pos = self.position(symbol)
        closed: Optional[TradeRecord] = None

        if pos.is_flat:
            pos.quantity = signed
            pos.avg_entry_price = price
            pos.entry_index = fill.index
            pos.entry_ts = fill.ts
            pos.commission_paid += fill.commission
            pos.last_price = price
            pos.mae = pos.mfe = 0.0
            return None

        same_direction = (pos.quantity > 0) == (signed > 0)
        if same_direction:
            total_qty = pos.quantity + signed
            pos.avg_entry_price = (
                (pos.avg_entry_price * pos.quantity + price * signed) / total_qty
            )
            pos.quantity = total_qty
            pos.commission_paid += fill.commission
            pos.last_price = price
            return None

        # Opposite direction: close (and possibly flip).
        close_qty = min(abs(pos.quantity), abs(signed))
        # P&L on the closed portion.
        if pos.quantity > 0:
            gross = (price - pos.avg_entry_price) * close_qty
        else:
            gross = (pos.avg_entry_price - price) * close_qty
        # Realized P&L is net of BOTH the entry commission attributable to the
        # closed quantity and the exit commission. `pos.commission_paid` holds the
        # entry-side commission accumulated while the position was open; allocate
        # the part belonging to this close proportionally (so scaled-in positions
        # stay correct) and release it from the position.
        entry_share = (
            pos.commission_paid * (close_qty / abs(pos.quantity))
            if abs(pos.quantity) > 0 else 0.0
        )
        trade_commission = entry_share + fill.commission
        net = gross - trade_commission
        entry_index = pos.entry_index if pos.entry_index is not None else fill.index
        bars = max(0, fill.index - entry_index)
        pnl_pct = 0.0
        if pos.avg_entry_price:
            direction_sign = 1.0 if pos.quantity > 0 else -1.0
            pnl_pct = (price - pos.avg_entry_price) / pos.avg_entry_price * 100.0 * direction_sign
        self._trade_seq += 1
        closed = TradeRecord(
            id=f"trade_{self._trade_seq:06d}", symbol=symbol,
            direction="long" if pos.quantity > 0 else "short",
            entry_ts=pos.entry_ts, exit_ts=fill.ts,
            entry_price=pos.avg_entry_price, exit_price=price,
            quantity=close_qty, gross_pnl=gross, net_pnl=net,
            commission=trade_commission, bars_held=bars, pnl_pct=pnl_pct,
            exit_reason=fill.reason, mae=pos.mae, mfe=pos.mfe,
        )
        self.trades.append(closed)
        self.realized_pnl += net
        pos.realized_pnl += net

        remaining = pos.quantity + signed  # signed result; may flip sign
        if abs(remaining) < 1e-12:
            # Fully closed: no cost basis or commission remains.
            pos.quantity = 0.0
            pos.avg_entry_price = 0.0
            pos.entry_index = None
            pos.entry_ts = None
            pos.mae = pos.mfe = 0.0
            pos.commission_paid = 0.0
        elif (remaining > 0) == (pos.quantity > 0):
            # Partial close: the remainder keeps the ORIGINAL cost basis and the
            # un-attributed share of its entry commission.
            pos.quantity = remaining
            pos.commission_paid = max(0.0, pos.commission_paid - entry_share)
            pos.mae = pos.mfe = 0.0
        else:
            # Flip: the remainder is a fresh position at this price. The exit
            # commission was fully expensed on the closed trade, so the new
            # position starts with no carry-over commission.
            pos.quantity = remaining
            pos.avg_entry_price = price
            pos.entry_index = fill.index
            pos.entry_ts = fill.ts
            pos.mae = pos.mfe = 0.0
            pos.commission_paid = 0.0
        pos.last_price = price
        return closed

    # ── Cost of carry & corporate actions ───────────────────────────────────
    def apply_cash(self, amount: float, *, kind: str, index: Optional[int] = None,
                   ts: Optional[str] = None, detail: Optional[dict] = None) -> None:
        """Apply a non-trade cash movement (financing, borrow, dividend).

        Positive = credit, negative = debit. The ledger keeps the component
        totals separate so the result envelope can report them honestly.
        """
        if amount == 0:
            return
        self.cash += float(amount)
        if kind == "financing":
            self.total_financing += float(amount)
        elif kind == "borrow":
            self.total_borrow += float(amount)
        elif kind == "dividend":
            self.total_dividends += float(amount)
        self.carry_events.append({
            "kind": kind, "amount": float(amount), "index": index, "ts": ts,
            "detail": detail or {},
        })

    def apply_corporate_action(self, action, *, index: Optional[int] = None,
                               ts: Optional[str] = None) -> Optional[dict]:
        """Apply one corporate action to this portfolio and return its effect."""
        from .corporate_actions import apply_to_position  # noqa: PLC0415

        pos = self.positions.get(action.symbol)
        if pos is None or pos.is_flat:
            return None
        effect = apply_to_position(
            action, quantity=pos.quantity, avg_entry_price=pos.avg_entry_price
        )
        if effect["kind"] == "split":
            pos.quantity = effect["newQuantity"]
            pos.avg_entry_price = effect["newAvgEntryPrice"]
        elif effect["cashDelta"]:
            self.apply_cash(
                effect["cashDelta"], kind="dividend", index=index, ts=ts,
                detail={"symbol": action.symbol, "perShare": action.amount,
                        "quantity": pos.quantity},
            )
        self.carry_events.append({
            "kind": f"corporate:{action.kind}", "amount": effect["cashDelta"],
            "index": index, "ts": ts, "detail": effect,
        })
        return effect

    # ── Reconstruct a snapshot series ────────────────────────────────────────
    def state_dict(self) -> dict:
        return {
            "cash": self.cash, "equity": self.equity,
            "realizedPnl": self.realized_pnl, "unrealizedPnl": self.unrealized_pnl(),
            "grossExposure": self.gross_exposure(), "netExposure": self.net_exposure(),
            "leverage": self.leverage(), "positions": [p.to_dict() for p in self.open_positions()],
            "fees": {
                "commission": self.total_commission, "slippage": self.total_slippage,
                "spread": self.total_spread, "impact": self.total_impact,
                "financing": self.total_financing, "borrow": self.total_borrow,
                "dividends": self.total_dividends,
                "total": (self.total_commission + self.total_slippage + self.total_spread
                          + self.total_impact + self.total_financing + self.total_borrow
                          - self.total_dividends),
            },
        }


__all__ = ["Portfolio"]

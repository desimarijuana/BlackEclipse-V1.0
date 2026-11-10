"""Execution simulator — realistic, measurable trading frictions.

Models commission, slippage, bid/ask spread and market impact, and decides
whether/how an order fills against a bar's OHLC range. Every cost is explicit
and reported: the fill carries the exact commission, slippage, spread and impact
it incurred, and the backtest result echoes the assumptions. A frictionless run
is only ever the result of an explicit `none` configuration.

Fill conventions (documented, tested):
  * market orders fill at the next bar's open by default (or the current close
    if `fill_at="close"`), adjusted adversely by half-spread + slippage + impact;
  * limit orders fill only if the bar's range crosses the limit, at the limit
    (or better); they never pay slippage beyond the limit;
  * stop orders trigger when the bar's range crosses the stop, then fill at the
    trigger price adjusted adversely;
  * protective stops (stop_loss/trailing_stop) and take_profit legs trigger on
    the bar range and fill at the trigger level adjusted adversely.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Optional

from .models import Fill, Order, OrderSide
from .strategy import ExecutionAssumptions


@dataclass
class BarContext:
    symbol: str
    index: int
    ts: Optional[str]
    open: float
    high: float
    low: float
    close: float
    volume: float
    atr: Optional[float] = None
    avg_volume: Optional[float] = None
    # Per-bar absolute bid/ask spread (price units), when the source supplies it.
    spread: Optional[float] = None


class ExecutionSimulator:
    def __init__(self, assumptions: ExecutionAssumptions, *, seed: Optional[int] = None) -> None:
        self.assumptions = assumptions
        self._rng = random.Random(assumptions.slippage.seed if assumptions.slippage.seed is not None else seed)
        # Honest, once-per-run diagnostics for inputs the model could not use.
        self._warnings: list[dict[str, Any]] = []
        self._warned: set[str] = set()

    def warn_once(self, code: str, message: str, detail: Optional[dict] = None) -> None:
        if code in self._warned:
            return
        self._warned.add(code)
        self._warnings.append({"code": code, "message": message, "detail": detail or {}})

    def consume_warnings(self) -> list[dict[str, Any]]:
        out = list(self._warnings)
        self._warnings.clear()
        return out

    # ── Commission ───────────────────────────────────────────────────────────
    def commission(self, quantity: float, price: float) -> float:
        m = self.assumptions.commission
        notional = abs(quantity) * abs(price)
        if m.type == "none":
            fee = 0.0
        elif m.type == "fixed":
            fee = m.value
        elif m.type == "percentage":
            fee = notional * m.value / 100.0
        elif m.type == "per_share":
            fee = abs(quantity) * m.value
        elif m.type == "per_contract":
            fee = abs(quantity) * m.value * m.contract_multiplier
        elif m.type == "tiered":
            fee = self._tiered_fee(notional, m.tiers or [])
        else:  # pragma: no cover
            fee = 0.0
        if m.minimum is not None:
            fee = max(fee, m.minimum)
        return fee

    @staticmethod
    def _tiered_fee(notional: float, tiers: list[dict[str, float]]) -> float:
        if not tiers:
            return 0.0
        ordered = sorted(tiers, key=lambda t: t.get("upTo", float("inf")))
        fee = 0.0
        lower = 0.0
        for tier in ordered:
            up_to = float(tier.get("upTo", float("inf")))
            rate = float(tier.get("rate", 0.0)) / 100.0
            slice_amount = max(0.0, min(notional, up_to) - lower)
            fee += slice_amount * rate
            lower = up_to
            if notional <= up_to:
                break
        return fee

    # ── Per-unit adverse price adjustments (in price terms) ──────────────────
    def spread_adjustment(self, price: float, bar_spread: Optional[float] = None) -> float:
        s = self.assumptions.spread
        if s.type == "none":
            return 0.0
        if s.type == "historical":
            # Use the bar's own absolute spread when the dataset carries it; a
            # missing value is zero here but the engine records a warning, so it
            # is never silently assumed away.
            return bar_spread / 2.0 if bar_spread is not None else 0.0
        if s.type == "fixed":
            return s.value / 2.0
        if s.type == "percentage":
            return price * s.value / 100.0 / 2.0
        if s.type == "bps":
            return price * s.value / 10000.0 / 2.0
        return 0.0

    def slippage_adjustment(self, price: float, quantity: float, bar: BarContext) -> float:
        m = self.assumptions.slippage
        if m.type == "none":
            return 0.0
        if m.type == "fixed":
            return abs(m.value)
        if m.type == "percentage":
            return price * m.value / 100.0
        if m.type == "volatility":
            ref = bar.atr if bar.atr is not None else (bar.high - bar.low)
            return abs(m.value) * max(ref, 0.0)
        if m.type == "volume":
            avg = bar.avg_volume or bar.volume
            if avg and avg > 0:
                return price * abs(m.value) * (abs(quantity) / avg)
            return 0.0
        if m.type == "randomized":
            base = abs(m.value)
            noise = self._rng.uniform(0.0, base) if base > 0 else 0.0
            return base + noise
        return 0.0

    def impact_adjustment(self, price: float, quantity: float, bar: BarContext) -> float:
        m = self.assumptions.market_impact
        if m.type == "none" or m.coefficient <= 0:
            return 0.0
        avg = bar.avg_volume or bar.volume
        if not avg or avg <= 0:
            return 0.0
        participation = abs(quantity) / avg
        if m.type == "sqrt":
            return price * (m.coefficient / 10000.0) * math.sqrt(participation)
        return price * (m.coefficient / 10000.0) * participation

    def _adverse(self, side: OrderSide, base_price: float, extra: float) -> float:
        return base_price + extra if side == "buy" else base_price - extra

    # ── Order evaluation ─────────────────────────────────────────────────────
    def try_fill(
        self,
        order: Order,
        bar: BarContext,
        *,
        current_index: int,
        allow_same_bar: bool = False,
    ) -> Optional[Fill]:
        """Return a Fill if the order fills on `bar`, else None.

        `allow_same_bar` is False for signal orders (they may only fill on a
        later bar than the one that produced the signal), preventing lookahead.
        """
        if order.status in ("rejected", "cancelled", "expired", "filled"):
            return None
        if not allow_same_bar and order.submitted_index is not None \
                and current_index <= order.submitted_index:
            return None

        otype = order.type
        side = order.side
        qty = order.remaining
        if qty <= 0:
            return None

        # Determine the trigger/base price for this bar.
        base: Optional[float] = None
        paid_slippage = True
        if otype == "market":
            base = bar.open if self.assumptions.fill_at == "next_open" else bar.close
        elif otype == "limit":
            assert order.limit_price is not None
            if side == "buy" and bar.low <= order.limit_price:
                base = min(order.limit_price, bar.open) if bar.open <= order.limit_price else order.limit_price
                paid_slippage = False
            elif side == "sell" and bar.high >= order.limit_price:
                base = max(order.limit_price, bar.open) if bar.open >= order.limit_price else order.limit_price
                paid_slippage = False
        elif otype in ("stop", "stop_loss"):
            stop = order.current_stop if order.type == "trailing_stop" else order.stop_price
            stop = stop if stop is not None else order.current_stop
            if stop is None:
                return None
            if side == "buy" and bar.high >= stop:
                base = max(stop, bar.open)
            elif side == "sell" and bar.low <= stop:
                base = min(stop, bar.open)
        elif otype == "trailing_stop":
            assert order.current_stop is not None
            if side == "buy" and bar.high >= order.current_stop:
                base = max(order.current_stop, bar.open)
            elif side == "sell" and bar.low <= order.current_stop:
                base = min(order.current_stop, bar.open)
        elif otype == "stop_limit":
            assert order.stop_price is not None and order.limit_price is not None
            triggered = (side == "buy" and bar.high >= order.stop_price) or \
                        (side == "sell" and bar.low <= order.stop_price)
            if triggered:
                if side == "buy" and bar.low <= order.limit_price:
                    base = order.limit_price
                    paid_slippage = False
                elif side == "sell" and bar.high >= order.limit_price:
                    base = order.limit_price
                    paid_slippage = False
        elif otype == "take_profit":
            assert order.stop_price is not None
            if side == "buy" and bar.low <= order.stop_price:
                base = order.stop_price
                paid_slippage = False
            elif side == "sell" and bar.high >= order.stop_price:
                base = order.stop_price
                paid_slippage = False

        if base is None:
            return None

        # Fill-quantity model. `full` is the historical behaviour; participation
        # caps the fill at a share of the bar's volume so a large order walks
        # across bars and a bar with no volume cannot fill at all.
        model = self.assumptions.fill_model
        if model.type == "participation":
            rate = model.participation_rate
            if rate is None or rate <= 0 or rate > 1:
                self.warn_once(
                    "FILL_PARTICIPATION_RATE_INVALID",
                    "participation fill model needs a rate in (0, 1]; no fill is assumed",
                    {"rate": rate},
                )
                return None
            if bar.volume is None:
                self.warn_once(
                    "FILL_VOLUME_UNAVAILABLE",
                    "participation fill model needs bar volume; no fill is assumed "
                    "rather than inventing liquidity",
                    {"symbol": order.symbol},
                )
                return None
            available = max(0.0, float(bar.volume) * float(rate))
            qty = min(qty, available)
            if qty <= 0 or qty + 1e-12 < float(model.min_quantity or 0.0):
                return None

        spread = self.spread_adjustment(base, bar.spread)
        slippage = self.slippage_adjustment(base, qty, bar) if paid_slippage else 0.0
        impact = self.impact_adjustment(base, qty, bar)
        fill_price = self._adverse(side, base, spread + slippage + impact)
        commission = self.commission(qty, fill_price)
        order_qty = float(order.quantity) or qty
        return Fill(
            id=f"fill_{order.id}_{bar.index}_{len(self._warnings)}",
            order_id=order.id, symbol=order.symbol, side=side, quantity=qty,
            price=fill_price, commission=commission,
            slippage=slippage * qty, spread_cost=spread * qty, impact=impact * qty,
            index=bar.index, ts=bar.ts, reason=order.reason,
            order_quantity=order_qty, fill_ratio=(qty / order_qty) if order_qty else 1.0,
        )

    def update_trailing(self, order: Order, bar: BarContext) -> None:
        """Advance a trailing-stop's trigger price using the favorable extreme."""
        if order.type != "trailing_stop":
            return
        if order.side == "sell":  # protecting a long
            candidate = bar.high - self._trail_distance(order, bar)
            current = order.current_stop if order.current_stop is not None else candidate
            order.current_stop = max(current, candidate)
        else:  # protecting a short
            candidate = bar.low + self._trail_distance(order, bar)
            current = order.current_stop if order.current_stop is not None else candidate
            order.current_stop = min(current, candidate)

    def _trail_distance(self, order: Order, bar: BarContext) -> float:
        if order.trail_amount is not None:
            return abs(order.trail_amount)
        if order.trail_percent is not None:
            ref = order.current_stop or bar.close
            return abs(ref) * order.trail_percent / 100.0
        return 0.0

    def assumptions_summary(self) -> dict:
        a = self.assumptions
        return {
            "commission": a.commission.model_dump(exclude_none=True),
            "slippage": a.slippage.model_dump(exclude_none=True),
            "spread": a.spread.model_dump(exclude_none=True),
            "marketImpact": a.market_impact.model_dump(exclude_none=True),
            "borrow": a.borrow.model_dump(exclude_none=True),
            "financing": a.financing.model_dump(exclude_none=True),
            "margin": a.margin.model_dump(exclude_none=True),
            "fillModel": a.fill_model.model_dump(exclude_none=True),
            "latencyBars": a.latency_bars,
            "fillAt": a.fill_at,
            "frictionless": a.is_frictionless(),
        }


__all__ = ["BarContext", "ExecutionSimulator"]

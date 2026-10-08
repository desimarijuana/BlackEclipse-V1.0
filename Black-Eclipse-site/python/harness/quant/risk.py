"""Risk engine — pre-trade limits and exposure caps.

Evaluated *before* an entry order is submitted. The engine may reduce a size to
fit a limit or reject the order outright, always returning the exact reason(s).
It never silently ignores a breached limit. A rejection is a first-class event
on the run, not an exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .strategy import RiskRules


@dataclass
class RiskContext:
    equity: float
    side: str                                # "buy" | "sell"
    price: float
    proposed_quantity: float
    is_opening: bool = True
    current_symbol_value: float = 0.0        # signed market value already held
    gross_exposure: float = 0.0              # portfolio gross exposure
    open_positions: int = 0
    stop_distance: Optional[float] = None
    has_stop: bool = False
    daily_pnl: float = 0.0
    daily_start_equity: Optional[float] = None


@dataclass
class RiskDecision:
    allowed: bool
    quantity: float
    adjustments: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return not self.allowed or self.quantity <= 0

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed, "quantity": self.quantity,
            "adjustments": self.adjustments, "reasons": self.reasons,
        }


class RiskEngine:
    def __init__(self, rules: RiskRules) -> None:
        self.rules = rules

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        r = self.rules
        qty = ctx.proposed_quantity
        adjustments: list[str] = []
        reasons: list[str] = []

        if ctx.is_opening:
            if ctx.side == "buy" and not r.allow_long:
                return RiskDecision(False, 0.0, reasons=["long entries disabled by risk rules"])
            if ctx.side == "sell" and not r.allow_short:
                return RiskDecision(False, 0.0, reasons=["short entries disabled by risk rules"])

        if qty <= 0:
            return RiskDecision(False, 0.0, reasons=["computed size is zero"])

        if r.require_stop and ctx.is_opening and not ctx.has_stop:
            return RiskDecision(False, 0.0, reasons=["a protective stop is required but none set"])

        # Daily loss circuit-breaker.
        if r.max_daily_loss_pct is not None and ctx.is_opening and ctx.daily_start_equity:
            limit = -abs(ctx.daily_start_equity) * r.max_daily_loss_pct / 100.0
            if ctx.daily_pnl <= limit:
                return RiskDecision(
                    False, 0.0,
                    reasons=[f"daily loss limit reached ({ctx.daily_pnl:.2f} <= {limit:.2f})"],
                )

        # Max concurrent positions.
        if r.max_open_positions is not None and ctx.is_opening \
                and ctx.current_symbol_value == 0 and ctx.open_positions >= r.max_open_positions:
            return RiskDecision(
                False, 0.0,
                reasons=[f"max open positions reached ({ctx.open_positions})"],
            )

        if ctx.price <= 0:
            return RiskDecision(False, 0.0, reasons=["non-positive price"])

        # Risk-per-trade cap (requires a stop distance).
        if r.max_risk_per_trade_pct is not None and ctx.stop_distance and ctx.stop_distance > 0:
            risk_budget = ctx.equity * r.max_risk_per_trade_pct / 100.0
            max_qty = risk_budget / ctx.stop_distance
            if max_qty < qty:
                qty = max_qty
                adjustments.append(f"risk-per-trade cap -> {qty:.4f}")

        # Per-position cap (absolute market value for this symbol).
        if r.max_position_pct is not None:
            cap_value = ctx.equity * r.max_position_pct / 100.0
            # Existing value counts toward the cap (signed → compare gross).
            allowed_value = max(0.0, cap_value - abs(ctx.current_symbol_value))
            max_qty = allowed_value / ctx.price
            if max_qty < qty:
                qty = max_qty
                adjustments.append(f"max position cap -> {qty:.4f}")
            if qty <= 0:
                return RiskDecision(False, 0.0, adjustments=adjustments,
                                    reasons=["position cap fully used"])

        # Gross exposure / leverage caps.
        for limit_value, label in (
            (r.max_gross_exposure, "max gross exposure"),
            (r.max_leverage, "max leverage"),
        ):
            if limit_value is None:
                continue
            cap_exposure = ctx.equity * limit_value
            headroom = max(0.0, cap_exposure - ctx.gross_exposure)
            max_qty = headroom / ctx.price
            if max_qty < qty:
                qty = max_qty
                adjustments.append(f"{label} cap -> {qty:.4f}")
            if qty <= 0:
                return RiskDecision(False, 0.0, adjustments=adjustments,
                                    reasons=[f"{label} reached"])

        if qty <= 0:
            return RiskDecision(False, 0.0, adjustments=adjustments,
                                reasons=["size reduced to zero by risk limits"])
        return RiskDecision(True, qty, adjustments=adjustments)


__all__ = ["RiskContext", "RiskDecision", "RiskEngine"]

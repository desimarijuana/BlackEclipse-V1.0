"""Position sizing engine — deterministic quantity from capital + risk.

Every sizing method returns an exact quantity (never a heuristic guess). When a
method's inputs are genuinely unavailable (e.g. Kelly with no trade history) the
engine returns `None` and the caller skips the entry with a warning — it never
silently substitutes a different method.

Venue constraints (`min_quantity`, `lot_size`, `quantity_precision`) are applied
after sizing, so a computed size that rounds below the minimum becomes no trade.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .strategy import PositionSizing


@dataclass
class SizingContext:
    equity: float
    price: float
    stop_distance: Optional[float] = None      # absolute price distance to stop
    atr: Optional[float] = None
    realized_vol: Optional[float] = None       # annualized or per-bar (consistent)
    kelly_win_rate: Optional[float] = None
    kelly_payoff: Optional[float] = None       # avg_win / avg_loss
    weight: Optional[float] = None             # portfolio weight (risk_parity/equal)


@dataclass
class SizingResult:
    quantity: float
    method: str
    notional: float
    detail: dict


def _apply_constraints(quantity: float, price: float, cfg: PositionSizing) -> float:
    qty = quantity
    if cfg.lot_size and cfg.lot_size > 0:
        qty = math.floor(qty / cfg.lot_size) * cfg.lot_size
    if cfg.quantity_precision is not None:
        qty = round(qty, cfg.quantity_precision)
    if cfg.min_quantity and qty < cfg.min_quantity:
        return 0.0
    return max(0.0, qty)


def compute_quantity(
    cfg: PositionSizing, ctx: SizingContext
) -> tuple[Optional[float], dict]:
    """Return (quantity, detail). `None` quantity = inputs unavailable."""
    price = ctx.price
    if price is None or price <= 0:
        return None, {"reason": "no price", "method": cfg.type}
    equity = max(0.0, ctx.equity)
    t = cfg.type
    raw: Optional[float] = None
    detail: dict = {"method": t}

    if t == "fixed_quantity":
        raw = cfg.value
    elif t == "fixed_dollar":
        raw = cfg.value / price
    elif t == "percent_equity":
        raw = equity * (cfg.value / 100.0) / price
        detail["equityPct"] = cfg.value
    elif t == "percent_risk":
        if not ctx.stop_distance or ctx.stop_distance <= 0:
            return None, {"reason": "percent_risk requires a stop distance", "method": t}
        risk_amount = equity * (cfg.value / 100.0)
        raw = risk_amount / ctx.stop_distance
        detail["riskAmount"] = risk_amount
    elif t == "atr":
        if not ctx.atr or ctx.atr <= 0:
            return None, {"reason": "atr sizing requires an ATR value", "method": t}
        risk_amount = equity * (cfg.value / 100.0)
        raw = risk_amount / (ctx.atr * cfg.atr_multiplier)
        detail["atr"] = ctx.atr
    elif t == "volatility":
        if not ctx.realized_vol or ctx.realized_vol <= 0:
            return None, {"reason": "volatility sizing requires a realized vol", "method": t}
        target = cfg.value / 100.0
        raw = (equity * target) / (price * ctx.realized_vol)
        detail["realizedVol"] = ctx.realized_vol
    elif t in ("kelly", "fractional_kelly"):
        if ctx.kelly_win_rate is None or ctx.kelly_payoff is None or ctx.kelly_payoff <= 0:
            return None, {"reason": "kelly sizing requires trade statistics", "method": t}
        w = max(0.0, min(1.0, ctx.kelly_win_rate))
        b = ctx.kelly_payoff
        kelly = w - (1.0 - w) / b
        kelly = max(0.0, kelly)
        fraction = cfg.kelly_fraction if t == "fractional_kelly" else 1.0
        if fraction is None:
            fraction = 1.0
        raw = equity * kelly * fraction / price
        detail.update({"kelly": kelly, "fraction": fraction, "winRate": w, "payoff": b})
    elif t == "risk_parity":
        if ctx.weight is None:
            return None, {"reason": "risk_parity requires a target weight", "method": t}
        raw = equity * ctx.weight / price
        detail["weight"] = ctx.weight
    elif t == "equal_weight":
        if ctx.weight is None:
            return None, {"reason": "equal_weight requires a target weight", "method": t}
        raw = equity * ctx.weight / price
        detail["weight"] = ctx.weight
    else:  # pragma: no cover - schema-validated
        return None, {"reason": f"unknown sizing type {t!r}", "method": t}

    if raw is None:
        return None, {"reason": "not computable", "method": t}

    # Cap by max_fraction of equity (converted to units).
    if cfg.max_fraction is not None and cfg.max_fraction > 0:
        max_units = equity * cfg.max_fraction / price
        raw = min(raw, max_units)

    qty = _apply_constraints(raw, price, cfg)
    detail["notional"] = qty * price
    if qty <= 0:
        detail["reason"] = detail.get("reason") or "size below venue minimum"
        return 0.0, detail
    return qty, detail


__all__ = ["SizingContext", "SizingResult", "compute_quantity"]

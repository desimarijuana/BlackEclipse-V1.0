"""Standalone execution-cost diagnostics.

These tools apply the **same** `ExecutionSimulator` models the backtest engine
uses — there is no second cost implementation to drift out of sync. They answer
"what would this cost?" for a set of hypothetical orders *without* running a full
backtest, so an agent can audit commission / slippage / spread / market-impact
assumptions in isolation and see exactly which inputs were observed vs. assumed.

Honesty rules (mirrors the engine's):
  * a missing input a model needs is reported as a warning and contributes zero —
    never silently treated as a real zero-cost observation;
  * a frictionless model is labelled `frictionless: true` so a zero total is
    never mistaken for a measured cost;
  * the per-order audit records the price basis each adjustment was applied to.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import ValidationError

from .errors import QuantError
from .execution import BarContext, ExecutionSimulator
from .models import OrderSide
from .strategy import ExecutionAssumptions


class CostModelError(QuantError):
    code = "COST_MODEL_ERROR"


def build_assumptions(execution: Optional[dict[str, Any]]) -> ExecutionAssumptions:
    """Validate an execution-assumptions block; a bad block is a typed error."""
    try:
        return ExecutionAssumptions.model_validate(execution or {})
    except ValidationError as exc:
        raise CostModelError(f"invalid execution assumptions: {exc.error_count()} problem(s)",
                             detail={"errors": exc.errors()}) from exc


def _bar(order: dict[str, Any], index: int) -> BarContext:
    price = float(order.get("price") or 0.0)
    high = order.get("high")
    low = order.get("low")
    volume = order.get("volume")
    return BarContext(
        symbol=str(order.get("symbol") or "?"),
        index=index,
        ts=order.get("ts"),
        open=float(order.get("open") or price),
        high=float(high if high is not None else price),
        low=float(low if low is not None else price),
        close=float(order.get("close") or price),
        volume=float(volume if volume is not None else 0.0),
        atr=(float(order["atr"]) if order.get("atr") is not None else None),
        avg_volume=(float(order["avgVolume"]) if order.get("avgVolume") is not None else None),
        spread=(float(order["barSpread"]) if order.get("barSpread") is not None else None),
    )


def _orders(args: dict[str, Any]) -> list[dict[str, Any]]:
    raw = args.get("orders")
    if not raw or not isinstance(raw, list):
        raise CostModelError("`orders` must be a non-empty array of order objects")
    out: list[dict[str, Any]] = []
    for i, order in enumerate(raw):
        if not isinstance(order, dict):
            raise CostModelError(f"order #{i} must be an object")
        side = str(order.get("side") or "buy").lower()
        if side not in ("buy", "sell"):
            raise CostModelError(f"order #{i} has invalid side {side!r}")
        qty = order.get("quantity")
        price = order.get("price")
        if qty is None or float(qty) <= 0:
            raise CostModelError(f"order #{i} needs a positive `quantity`")
        if price is None or float(price) <= 0:
            raise CostModelError(f"order #{i} needs a positive `price`")
        out.append({**order, "side": side, "quantity": float(qty), "price": float(price)})
    return out


def _summary(sim: ExecutionSimulator) -> dict[str, Any]:
    return sim.assumptions_summary()


def simulate_costs(
    kind: str,
    orders: list[dict[str, Any]],
    execution: Optional[dict[str, Any]] = None,
    *,
    seed: Optional[int] = None,
) -> dict[str, Any]:
    """Compute one cost family for a set of orders.

    `kind` is one of `transaction | slippage | spread | impact`; each maps onto a
    single `ExecutionSimulator` method. The return is a complete, auditable
    breakdown — per-order values, the total, the exact model used and any
    warnings where a model lacked a required input.
    """
    if kind not in ("transaction", "slippage", "spread", "impact"):
        raise CostModelError(f"unknown cost kind {kind!r}")
    assumptions = build_assumptions(execution)
    sim = ExecutionSimulator(assumptions, seed=seed)
    warnings: list[dict[str, Any]] = []

    if kind == "transaction" and assumptions.commission.type == "none":
        warnings.append({"code": "COMMISSION_MODEL_NONE",
                         "message": "commission model is `none`; total commission is zero by "
                                    "configuration, not a measured observation"})

    rows: list[dict[str, Any]] = []
    total = 0.0
    for index, order in enumerate(orders):
        side: OrderSide = order["side"]
        qty = order["quantity"]
        price = order["price"]
        bar = _bar(order, index)
        row: dict[str, Any] = {
            "index": index, "symbol": bar.symbol, "side": side,
            "quantity": qty, "price": price,
        }
        if kind == "transaction":
            value = sim.commission(qty, price)
            row["commission"] = round(value, 8)
        elif kind == "slippage":
            if assumptions.slippage.type in ("volatility", "volume"):
                needed = "atr" if assumptions.slippage.type == "volatility" else "avgVolume"
                provided = bar.atr if needed == "atr" else (bar.avg_volume or bar.volume)
                if not provided:
                    warnings.append({
                        "code": "SLIPPAGE_INPUT_MISSING",
                        "message": f"slippage model {assumptions.slippage.type!r} needs "
                                   f"{needed}; order #{index} contributes zero",
                        "detail": {"orderIndex": index}})
            per_unit = sim.slippage_adjustment(price, qty, bar)
            value = per_unit * qty
            row["slippagePerUnit"] = round(per_unit, 8)
            row["slippage"] = round(value, 8)
        elif kind == "spread":
            if assumptions.spread.type == "historical" and bar.spread is None:
                warnings.append({
                    "code": "HISTORICAL_SPREAD_UNAVAILABLE",
                    "message": f"spread model 'historical' but order #{index} has no "
                               "`barSpread`; contributes zero",
                    "detail": {"orderIndex": index}})
            per_unit = sim.spread_adjustment(price, bar.spread)
            value = per_unit * qty
            row["spreadPerUnit"] = round(per_unit, 8)
            row["spreadCost"] = round(value, 8)
        else:  # impact
            if assumptions.market_impact.type == "linear" and assumptions.market_impact.coefficient > 0 \
                    and not (bar.avg_volume or bar.volume):
                warnings.append({
                    "code": "IMPACT_INPUT_MISSING",
                    "message": f"market-impact model needs volume; order #{index} contributes zero",
                    "detail": {"orderIndex": index}})
            per_unit = sim.impact_adjustment(price, qty, bar)
            value = per_unit * qty
            row["impactPerUnit"] = round(per_unit, 8)
            row["impact"] = round(value, 8)
        total += value
        rows.append(row)

    return {
        "kind": kind,
        "model": _summary(sim),
        "frictionless": assumptions.is_frictionless(),
        "orders": rows,
        "orderCount": len(rows),
        "total": round(total, 8),
        "warnings": warnings,
        "observedInputs": sorted({k for o in orders for k in o
                                  if k in ("atr", "avgVolume", "volume", "barSpread")}),
    }


__all__ = [
    "CostModelError",
    "build_assumptions",
    "simulate_costs",
]

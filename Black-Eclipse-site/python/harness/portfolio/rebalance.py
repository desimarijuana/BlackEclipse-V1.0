"""Rebalancing engine — a PROPOSAL engine, never an executor (§27–§30).

Given the current portfolio and target weights it produces buy/sell
recommendations, allocation before/after, estimated fees and an optional
tax-impact estimate. It never writes a transaction and never calls a broker:
execution is the Trading/Execution layer's job and requires explicit user
approval.

Methods:
  * threshold — rebalance only holdings whose drift exceeds `allowed_drift`
  * calendar  — a scheduled full rebalance back to target
  * hybrid    — threshold, plus a hard correction for egregious drift

Tax rules are supplied by the caller (jurisdiction-neutral): `shortTermRate`
and `longTermRate` (fractions). With no rates configured, tax impact is
reported as UNKNOWN — never invented.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Sequence

from .money import ZERO, money_str

METHODS = ("threshold", "calendar", "hybrid")
DEFAULT_LONG_TERM_DAYS = 365


def _f(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


_CASH_KEYS = {"CASH", "$CASH", "CASH_USD", "USD_CASH"}


def _target_fractions(target: dict[str, Any]) -> dict[str, float]:
    cleaned: dict[str, float] = {}
    for symbol, weight in target.items():
        # A cash target is a residual, not a tradable instrument — the engine
        # never fabricates a "CASH" buy/sell recommendation.
        if str(symbol).upper() in _CASH_KEYS:
            continue
        w = _f(weight)
        if w > 0:
            cleaned[str(symbol)] = w
    total = sum(cleaned.values())
    if total > 1.5:  # supplied as percentages
        cleaned = {s: w / 100.0 for s, w in cleaned.items()}
    return cleaned


def _days_held(opened_at: Optional[str], now: datetime) -> Optional[int]:
    if not opened_at:
        return None
    try:
        dt = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (now - dt).days)
    except ValueError:
        return None


def estimate_sale_tax(
    lots: Sequence[dict[str, Any]],
    quantity: Decimal,
    price: Decimal,
    method: str,
    rules: Optional[dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Estimate realized gain (and tax, only when rates are configured) for a sale."""
    now = now or datetime.now(timezone.utc)
    remaining = quantity
    realized_cost = ZERO
    by_term = {"shortTermGain": ZERO, "longTermGain": ZERO}
    ordered = list(lots)
    if method == "AVERAGE_COST":
        total_qty = sum((Decimal(str(l["quantity"])) for l in ordered), ZERO)
        total_cost = sum((Decimal(str(l["quantity"])) * Decimal(str(l["costPerUnit"])) for l in ordered), ZERO)
        if total_qty > 0:
            avg = total_cost / total_qty
            take = min(remaining, total_qty)
            realized_cost += avg * take
            gain = price * take - avg * take
            by_term["shortTermGain"] += gain  # pooled basis: term is indeterminate
            remaining -= take
    else:
        reverse = method == "LIFO"
        for lot in sorted(ordered, key=lambda l: l.get("sequence", 0), reverse=reverse):
            if remaining <= 0:
                break
            lot_qty = Decimal(str(lot["quantity"]))
            take = min(lot_qty, remaining)
            cost = take * Decimal(str(lot["costPerUnit"]))
            realized_cost += cost
            gain = price * take - cost
            days = _days_held(lot.get("openedAt"), now)
            if days is not None and days < DEFAULT_LONG_TERM_DAYS:
                by_term["shortTermGain"] += gain
            else:
                by_term["longTermGain"] += gain
            remaining -= take
    proceeds = price * quantity
    total_gain = proceeds - realized_cost
    rates = rules or {}
    tax: Optional[Decimal] = None
    if rates.get("shortTermRate") is not None or rates.get("longTermRate") is not None:
        short_rate = Decimal(str(rates.get("shortTermRate") or 0))
        long_rate = Decimal(str(rates.get("longTermRate") or 0))
        tax = by_term["shortTermGain"] * short_rate + by_term["longTermGain"] * long_rate
        if tax < 0:
            tax = ZERO  # a loss yields no positive tax (a credit is not modelled)
    return {
        "proceeds": money_str(proceeds),
        "costBasis": money_str(realized_cost),
        "estimatedGain": money_str(total_gain),
        "shortTermGain": money_str(by_term["shortTermGain"]),
        "longTermGain": money_str(by_term["longTermGain"]),
        "estimatedTax": money_str(tax) if tax is not None else None,
        "taxKnown": tax is not None,
        "lotsConsumed": str(quantity - remaining),
        "basisInsufficient": remaining > 0,
    }


def _concentration(values: list[float]) -> Optional[float]:
    total = sum(abs(v) for v in values)
    if total <= 0:
        return None
    return round(sum((abs(v) / total) ** 2 for v in values), 6)


def compute_rebalance(
    *,
    base_currency: str,
    total_value: Decimal,
    cash: Decimal,
    positions: list[dict[str, Any]],
    target: dict[str, Any],
    allowed_drift: float = 0.05,
    method: str = "threshold",
    fee_rate: float = 0.0,
    tax_rules: Optional[dict[str, Any]] = None,
    lots_by_symbol: Optional[dict[str, list[dict[str, Any]]]] = None,
    cost_method: str = "FIFO",
    min_trade_value: float = 0.0,
    no_trade: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    if method not in METHODS:
        method = "threshold"
    fractions = _target_fractions(target)
    no_trade_set = {s.upper() for s in (no_trade or [])}
    total_value = total_value or ZERO
    lots_by_symbol = lots_by_symbol or {}

    current: dict[str, dict[str, Any]] = {}
    for p in positions:
        current[p["symbol"].upper()] = p

    warnings: list[str] = []
    recommendations: list[dict[str, Any]] = []

    universe = set(current) | set(fractions)
    for symbol in sorted(universe):
        pos = current.get(symbol)
        price_native = pos.get("price") if pos else None
        value_base = (pos.get("marketValueBase") if pos else ZERO) or ZERO
        current_weight = (value_base / total_value) if total_value else ZERO
        target_weight = Decimal(str(fractions.get(symbol, 0.0)))
        drift = current_weight - target_weight
        delta_value = (current_weight - target_weight) * total_value  # >0 = sell

        if symbol in no_trade_set:
            if abs(float(delta_value)) > 0:
                warnings.append(f"{symbol} is excluded from trading by constraint")
            continue

        should_trade = method == "calendar"
        if not should_trade:
            if abs(float(drift)) > allowed_drift:
                should_trade = True
            elif method == "hybrid" and abs(float(drift)) > allowed_drift * 1.5:
                should_trade = True
        if not should_trade:
            continue
        if delta_value == 0:
            continue

        action = "SELL" if delta_value > 0 else "BUY"
        trade_value = abs(delta_value)
        if float(trade_value) < min_trade_value:
            continue

        quantity: Optional[Decimal] = None
        if price_native and price_native > 0:
            native_trade_value = _native_value(trade_value, pos, base_currency) if pos else trade_value
            quantity = native_trade_value / price_native
            if action == "SELL" and pos is not None:
                held = Decimal(str(pos["quantity"]))
                if quantity > held:
                    warnings.append(
                        f"{symbol}: target requires selling {quantity} but only {held} held; "
                        "cannot short to reach target"
                    )
                    quantity = held
                    trade_value = _base_value(quantity * price_native, pos, base_currency)
        else:
            warnings.append(f"{symbol}: no price available; quantity cannot be estimated")

        est_fees = money_str(Decimal(str(trade_value)) * Decimal(str(fee_rate)))
        rec: dict[str, Any] = {
            "symbol": symbol,
            "action": action,
            "quantity": str(quantity) if quantity is not None else None,
            "price": money_str(price_native) if price_native is not None else None,
            "estimatedValue": money_str(trade_value),
            "estFees": est_fees,
            "currentWeight": round(float(current_weight) * 100, 6),
            "targetWeight": round(float(target_weight) * 100, 6),
            "reason": _reason(action, drift, allowed_drift, method),
            "taxImpact": None,
            "estRealizedPnl": None,
        }
        if action == "SELL" and price_native and symbol in lots_by_symbol:
            tax = estimate_sale_tax(
                lots_by_symbol[symbol], quantity or ZERO, price_native, cost_method, tax_rules
            )
            rec["taxImpact"] = tax.get("estimatedTax")
            rec["estRealizedPnl"] = tax.get("estimatedGain")
            rec["taxKnown"] = tax.get("taxKnown")
        recommendations.append(rec)

    before = {s: round(float((p.get("marketValueBase") or ZERO) / total_value) * 100, 6)
              for s, p in current.items()} if total_value else {}
    after = dict(before)
    for rec in recommendations:
        after[rec["symbol"]] = rec["targetWeight"]

    return {
        "baseCurrency": base_currency,
        "method": method,
        "allowedDrift": allowed_drift,
        "feeRate": fee_rate,
        "totalValue": money_str(total_value),
        "cash": money_str(cash or ZERO),
        "targetAllocation": {s: round(w * 100, 6) for s, w in fractions.items()},
        "allocationBefore": before,
        "allocationAfter": after,
        "recommendations": recommendations,
        "estimatedTotalFees": money_str(
            sum((Decimal(str(r["estFees"] or "0")) for r in recommendations), ZERO)
        ),
        "estimatedNetCash": money_str(sum(
            (Decimal(str(r["estimatedValue"] or "0")) * (1 if r["action"] == "SELL" else -1)
             for r in recommendations), ZERO)),
        "concentrationBefore": _concentration([float((p.get("marketValueBase") or ZERO)) for p in positions]),
        "concentrationAfter": _concentration(
            [float(after.get(s, 0)) / 100 * float(total_value) for s in after]
        ),
        "warnings": warnings,
        "execution": "proposal-only: no trades are placed; requires user approval",
    }


def _native_value(base_value: Decimal, pos: Optional[dict[str, Any]], base_currency: str) -> Decimal:
    if not pos:
        return base_value
    fx = pos.get("fxPerBase")
    if fx and fx > 0:
        return base_value * fx
    return base_value


def _base_value(native_value: Decimal, pos: Optional[dict[str, Any]], base_currency: str) -> Decimal:
    if not pos:
        return native_value
    fx = pos.get("fxPerBase")
    if fx and fx > 0:
        return native_value / fx
    return native_value


def _reason(action: str, drift: Decimal, allowed_drift: float, method: str) -> str:
    direction = "overweight" if action == "SELL" else "underweight"
    if method == "calendar":
        return f"scheduled ({method}) rebalance; currently {direction}"
    return f"drift {float(drift) * 100:.2f}% exceeds {allowed_drift * 100:.2f}% band ({direction})"


__all__ = ["compute_rebalance", "estimate_sale_tax", "METHODS"]

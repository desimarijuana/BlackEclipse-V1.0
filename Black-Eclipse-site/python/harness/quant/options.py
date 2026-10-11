"""Deterministic options analytics for the quant engine.

This does NOT re-implement pricing: it reuses the market layer's
`market.greeks.black_scholes` (the one options pricing model in the codebase) and
adds the pieces the engine was missing:

  * an **implied-volatility solver** (bisection over the same BS model),
  * **multi-leg strategy analytics** — expiry payoff, net premium, break-evens,
    max profit/loss (with an explicit *unbounded* verdict, never a fabricated
    grid maximum), and net Greeks.

The model assumptions are the market layer's and are reported with every result:
European exercise, no dividends by default, constant risk-free rate and vol.
A missing input yields a typed error or `available: false` — never a fake number.

Option *backtesting* is deliberately NOT claimed: it needs historical option
chains and expiry handling and remains unsupported. These tools are analytics.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from ..market.greeks import DEFAULT_RISK_FREE, black_scholes
from .errors import QuantError


class OptionError(QuantError):
    code = "OPTION_ERROR"


_ASSUMPTIONS = [
    "European exercise",
    "no dividends (unless dividendYield is supplied)",
    "constant risk-free rate and volatility",
]


def _side_sign(quantity: float) -> int:
    return 1 if quantity >= 0 else -1


def price_option(
    *,
    option_type: str,
    spot: float,
    strike: float,
    time_to_expiry: float,
    iv: float,
    risk_free: float = DEFAULT_RISK_FREE,
    dividend_yield: float = 0.0,
) -> dict[str, Any]:
    """Theoretical price + Greeks for one European option (reuses BS model)."""
    if not option_type or option_type.lower()[0] not in ("c", "p"):
        raise OptionError(f"option_type must be 'call' or 'put', got {option_type!r}")
    result = black_scholes(option_type=option_type, spot=float(spot), strike=float(strike),
                           time_to_expiry=float(time_to_expiry), iv=float(iv),
                           risk_free=float(risk_free), dividend_yield=float(dividend_yield))
    if result is None:
        return {"available": False,
                "reason": "unusable inputs (need spot>0, strike>0, iv>0, timeToExpiry>0)"}
    return {
        "available": True,
        "optionType": "call" if option_type.lower()[0] == "c" else "put",
        "spot": spot, "strike": strike, "timeToExpiry": time_to_expiry, "iv": iv,
        "riskFree": risk_free, "dividendYield": dividend_yield,
        **result,
        "model": "black-scholes", "assumptions": _ASSUMPTIONS,
    }


def implied_volatility(
    market_price: float,
    *,
    option_type: str,
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free: float = DEFAULT_RISK_FREE,
    dividend_yield: float = 0.0,
    low: float = 1e-4,
    high: float = 5.0,
    tol: float = 1e-6,
    max_iter: int = 200,
) -> dict[str, Any]:
    """Invert Black-Scholes for implied volatility by bisection.

    Robust to a wide bracket; refuses a price outside the no-arbitrage bounds so
    it never returns a fabricated vol. Returns `available: false` with a reason
    when the price is not reachable under the model.
    """
    spot = float(spot); strike = float(strike); t = float(time_to_expiry)
    price = float(market_price)
    if not (spot > 0 and strike > 0 and t > 0 and price > 0):
        return {"available": False, "reason": "spot/strike/timeToExpiry/price must be positive"}
    disc_r = math.exp(-risk_free * t)
    disc_q = math.exp(-dividend_yield * t)
    call = option_type.lower().startswith("c")
    if call:
        intrinsic = max(spot * disc_q - strike * disc_r, 0.0)
        upper = spot * disc_q
    else:
        intrinsic = max(strike * disc_r - spot * disc_q, 0.0)
        upper = strike * disc_r
    if price < intrinsic - 1e-9 or price > upper + 1e-9:
        return {"available": False,
                "reason": f"price {price} is outside the no-arbitrage bounds "
                          f"[{intrinsic:.6f}, {upper:.6f}]",
                "intrinsic": intrinsic, "upperBound": upper}

    def bs(sigma: float) -> float:
        out = black_scholes(option_type=option_type, spot=spot, strike=strike,
                            time_to_expiry=t, iv=sigma, risk_free=risk_free,
                            dividend_yield=dividend_yield)
        return out["price"] if out else intrinsic

    lo, hi = float(low), float(high)
    f_lo, f_hi = bs(lo) - price, bs(hi) - price
    if f_lo > 0 or f_hi < 0:
        return {"available": False,
                "reason": f"price is not reachable within vol bracket [{lo}, {hi}]"}
    for _ in range(int(max_iter)):
        mid = 0.5 * (lo + hi)
        diff = bs(mid) - price
        if abs(diff) <= tol or (hi - lo) <= tol:
            return {"available": True, "impliedVolatility": mid,
                    "price": price, "optionType": "call" if call else "put",
                    "residual": diff, "model": "black-scholes",
                    "method": "bisection", "assumptions": _ASSUMPTIONS}
        if diff > 0:
            hi = mid
        else:
            lo = mid
    return {"available": True, "impliedVolatility": 0.5 * (lo + hi), "price": price,
            "optionType": "call" if call else "put", "residual": bs(0.5 * (lo + hi)) - price,
            "converged": False, "method": "bisection", "model": "black-scholes",
            "assumptions": _ASSUMPTIONS}


def _validate_legs(legs: Any) -> list[dict[str, Any]]:
    if not legs or not isinstance(legs, list):
        raise OptionError("`legs` must be a non-empty array of leg objects")
    out: list[dict[str, Any]] = []
    for i, leg in enumerate(legs):
        if not isinstance(leg, dict):
            raise OptionError(f"leg #{i} must be an object")
        otype = str(leg.get("type") or leg.get("optionType") or "").lower()
        if otype[:1] not in ("c", "p"):
            raise OptionError(f"leg #{i} needs a call/put `type`")
        strike = leg.get("strike")
        qty = leg.get("quantity", leg.get("qty"))
        premium = leg.get("premium", leg.get("price"))
        if strike is None or float(strike) <= 0:
            raise OptionError(f"leg #{i} needs a positive `strike`")
        if qty is None or float(qty) == 0:
            raise OptionError(f"leg #{i} needs a non-zero `quantity`")
        if premium is None or float(premium) < 0:
            raise OptionError(f"leg #{i} needs a `premium` >= 0")
        out.append({
            "type": "call" if otype[0] == "c" else "put",
            "strike": float(strike), "quantity": float(qty), "premium": float(premium),
            "multiplier": float(leg.get("multiplier") or 100.0),
            "iv": (float(leg["iv"]) if leg.get("iv") is not None else None),
        })
    return out


def _intrinsic(otype: str, spot: float, strike: float) -> float:
    return max(spot - strike, 0.0) if otype == "call" else max(strike - spot, 0.0)


def analyze_option_strategy(
    legs: list[dict[str, Any]],
    *,
    spot_min: float,
    spot_max: float,
    points: int = 201,
    valuation_spot: Optional[float] = None,
    time_to_expiry: Optional[float] = None,
    iv: Optional[float] = None,
    risk_free: float = DEFAULT_RISK_FREE,
) -> dict[str, Any]:
    """Payoff/risk analytics for a multi-leg option strategy.

    Computes the expiry P&L curve, net premium, break-evens, and max profit/loss.
    When an extreme is *unbounded* it is reported as `null` with `bounded: false`
    (never a fabricated grid maximum). Net Greeks are computed when a valuation
    spot, time-to-expiry and IV are supplied.
    """
    clean = _validate_legs(legs)
    if not (spot_max > spot_min > 0):
        raise OptionError("need 0 < spotMin < spotMax")
    n = max(3, min(int(points), 2001))
    grid = [spot_min + (spot_max - spot_min) * i / (n - 1) for i in range(n)]

    # Cash paid at inception for each leg (long pays, short receives).
    net_premium_cost = sum(
        leg["quantity"] * leg["premium"] * leg["multiplier"] for leg in clean)

    def pnl(spot: float) -> float:
        total = -net_premium_cost
        for leg in clean:
            total += leg["quantity"] * leg["multiplier"] * _intrinsic(leg["type"], spot, leg["strike"])
        return total

    curve = [{"spot": round(s, 6), "pnl": round(pnl(s), 6)} for s in grid]
    values = [p["pnl"] for p in curve]

    # Break-evens: sign changes on the grid, linearly interpolated.
    break_evens: list[float] = []
    for i in range(1, n):
        a, b = values[i - 1], values[i]
        if a == 0:
            break_evens.append(grid[i - 1])
        elif a * b < 0:
            x0, x1 = grid[i - 1], grid[i]
            break_evens.append(x0 + (x1 - x0) * (-a) / (b - a))

    # Boundedness via the P&L slope at each tail (finite differences).
    #  * P&L increasing as S→+∞ (slope_high>0) or as S→0 (slope_low<0) => profit
    #    is unbounded above, so there is no finite max profit.
    #  * P&L decreasing in a tail => loss is unbounded, so no finite max loss.
    slope_low = (pnl(grid[1]) - pnl(grid[0])) / (grid[1] - grid[0])
    slope_high = (pnl(grid[-1]) - pnl(grid[-2])) / (grid[-1] - grid[-2])
    tol = 1e-6
    inc_high = slope_high > tol
    inc_low = slope_low < -tol
    dec_high = slope_high < -tol
    dec_low = slope_low > tol
    max_profit = None if (inc_high or inc_low) else max(values)
    max_loss = None if (dec_high or dec_low) else min(values)
    bounded = not (inc_high or inc_low or dec_high or dec_low)

    result: dict[str, Any] = {
        "available": True,
        "legs": clean,
        "netPremium": round(net_premium_cost, 6),
        "netPremiumMeaning": "positive = net debit paid, negative = net credit received",
        "strategyType": ("net debit" if net_premium_cost > 0 else
                         "net credit" if net_premium_cost < 0 else "flat"),
        "payoffCurve": curve,
        "breakEvens": [round(b, 6) for b in break_evens],
        "maxProfit": (round(max_profit, 6) if max_profit is not None else None),
        "maxLoss": (round(max_loss, 6) if max_loss is not None else None),
        "bounded": bounded,
        "spotRange": [spot_min, spot_max],
        "model": "expiry payoff (no early exercise) + black-scholes for Greeks",
        "assumptions": _ASSUMPTIONS,
    }
    if valuation_spot is not None and time_to_expiry is not None:
        greeks = _net_greeks(clean, valuation_spot, float(time_to_expiry), iv, risk_free)
        if greeks is not None:
            result["netGreeks"] = greeks
    return result


def _net_greeks(legs, spot, t, iv, risk_free) -> Optional[dict[str, float]]:
    totals = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0, "value": 0.0}
    for leg in legs:
        vol = leg["iv"] if leg["iv"] is not None else iv
        if vol is None or vol <= 0:
            return None
        g = black_scholes(option_type=leg["type"], spot=spot, strike=leg["strike"],
                          time_to_expiry=t, iv=vol, risk_free=risk_free)
        if g is None:
            return None
        scale = leg["quantity"] * leg["multiplier"]
        for key in totals:
            src = "price" if key == "value" else key
            totals[key] += scale * g[src]
    return {k: round(v, 6) for k, v in totals.items()}


__all__ = [
    "OptionError",
    "analyze_option_strategy",
    "implied_volatility",
    "price_option",
]

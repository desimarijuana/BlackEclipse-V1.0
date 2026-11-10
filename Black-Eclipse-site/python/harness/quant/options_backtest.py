"""Historical option-chain strategies — a scoped, honest backtest.

The event engine trades linear instruments. Options need dated chains, an expiry
calendar and an assignment model; those are a different data plane. This module
backtests a multi-leg option position over a supplied chain history, marking each
snapshot with the SAME Black-Scholes model the rest of the app uses.

What it does:
  * enters a multi-leg position on the first snapshot at the quoted/model price;
  * marks it to market on every later snapshot using that snapshot's spot, IV and
    remaining time;
  * settles at expiry with intrinsic value when the chain reaches expiry;
  * subtracts explicit per-contract commission and reports the equity curve.

What it does NOT do (and says so): early exercise/assignment, dividends on the
underlying unless supplied as a yield, or a surface-consistent fill model. The
capability is therefore `partial`, not a claim of institutional option
backtesting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import numpy as np

from .errors import QuantError
from .options import price_option

OPTIONS_BACKTEST_VERSION = "0.1.0"


class OptionsBacktestError(QuantError):
    code = "OPTIONS_BACKTEST_ERROR"


@dataclass
class ChainSnapshot:
    date: str
    spot: float
    legs: list[dict[str, Any]]
    expiry: str
    risk_free: float = 0.05
    dividend_yield: float = 0.0
    # Optional per-leg market premium for the entry fill; otherwise the model.
    commission_per_contract: float = 0.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ChainSnapshot":
        try:
            return cls(
                date=str(raw["date"]),
                spot=float(raw["spot"]),
                legs=list(raw["legs"]),
                expiry=str(raw["expiry"]),
                risk_free=float(raw.get("riskFree", 0.05)),
                dividend_yield=float(raw.get("dividendYield", 0.0)),
                commission_per_contract=float(raw.get("commissionPerContract", 0.0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise OptionsBacktestError("a chain snapshot is malformed", detail={"raw": raw}) from exc


def _days_between(a: str, b: str) -> float:
    try:
        return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days
    except ValueError as exc:
        raise OptionsBacktestError("dates must be ISO YYYY-MM-DD") from exc


def _leg_value(leg: dict[str, Any], *, spot: float, days_to_expiry: float,
               risk_free: float, dividend_yield: float) -> dict[str, Any]:
    otype = str(leg.get("type") or leg.get("optionType") or "").lower()
    strike = float(leg.get("strike"))
    qty = float(leg.get("quantity", leg.get("qty", 0)))
    mult = float(leg.get("multiplier") or 100.0)
    if days_to_expiry <= 0:
        intrinsic = max(spot - strike, 0.0) if otype.startswith("c") else max(strike - spot, 0.0)
        return {"price": intrinsic, "intrinsic": True, "leg": leg,
                "value": intrinsic * qty * mult}
    iv = leg.get("iv")
    if iv is None or float(iv) <= 0:
        raise OptionsBacktestError(
            "every leg needs a positive `iv` before expiry; refusing to invent one",
            detail={"leg": leg},
        )
    priced = price_option(
        option_type=otype, spot=spot, strike=strike,
        time_to_expiry=max(days_to_expiry, 0.0) / 365.0,
        iv=float(iv), risk_free=risk_free, dividend_yield=dividend_yield,
    )
    if not priced.get("available"):
        raise OptionsBacktestError("the option model could not price a leg",
                                   detail={"leg": leg, "result": priced})
    return {"price": float(priced["price"]), "intrinsic": False, "leg": leg,
            "greeks": {k: priced.get(k) for k in ("delta", "gamma", "theta", "vega", "rho")},
            "value": float(priced["price"]) * qty * mult}


def backtest_option_chain(snapshots: list[dict[str, Any]], *,
                          initial_capital: float = 100_000.0,
                          commission_per_contract: Optional[float] = None) -> dict[str, Any]:
    """Run a multi-leg option position over a supplied chain history."""
    if not snapshots:
        raise OptionsBacktestError("at least one chain snapshot is required")
    chain = [ChainSnapshot.from_dict(s) for s in snapshots]
    chain.sort(key=lambda s: s.date)
    if len(chain) < 2:
        raise OptionsBacktestError("at least two snapshots are required to form a P&L")
    if initial_capital <= 0:
        raise OptionsBacktestError("initial capital must be positive")

    expiry = chain[0].expiry
    # Entry: use the first snapshot's model price (or an explicit premium).
    entry = []
    entry_value = 0.0
    entry_commission = 0.0
    for leg in chain[0].legs:
        qty = float(leg.get("quantity", leg.get("qty", 0)))
        mult = float(leg.get("multiplier") or 100.0)
        if leg.get("premium") is not None:
            price = float(leg["premium"])
        else:
            val = _leg_value(leg, spot=chain[0].spot,
                             days_to_expiry=_days_between(chain[0].date, expiry),
                             risk_free=chain[0].risk_free,
                             dividend_yield=chain[0].dividend_yield)
            price = val["price"]
        entry_value += price * qty * mult
        rate = (chain[0].commission_per_contract if commission_per_contract is None
                else float(commission_per_contract))
        entry_commission += abs(qty) * mult / 100.0 * rate
        entry.append({"leg": leg, "entryPrice": price})

    cash = initial_capital - entry_value - entry_commission
    equity = cash + entry_value
    curve: list[dict[str, Any]] = [{
        "date": chain[0].date, "spot": chain[0].spot, "equity": equity,
        "positionValue": entry_value, "pnl": -entry_commission,
        "daysToExpiry": _days_between(chain[0].date, expiry),
    }]
    peak = equity
    drawdown: list[dict[str, Any]] = [{"date": chain[0].date, "drawdown": 0.0}]

    last_greeks: Optional[dict[str, float]] = None
    for snap in chain[1:]:
        days = _days_between(snap.date, expiry)
        position_value = 0.0
        greeks_total = {k: 0.0 for k in ("delta", "gamma", "theta", "vega", "rho")}
        for held in entry:
            leg = held["leg"]
            if days <= 0:
                intrinsic = _leg_value(leg, spot=snap.spot, days_to_expiry=0,
                                       risk_free=snap.risk_free,
                                       dividend_yield=snap.dividend_yield)
                position_value += float(intrinsic["value"])
            else:
                val = _leg_value(leg, spot=snap.spot, days_to_expiry=days,
                                 risk_free=snap.risk_free,
                                 dividend_yield=snap.dividend_yield)
                position_value += float(val["value"])
                for k, v in (val.get("greeks") or {}).items():
                    if v is not None:
                        greeks_total[k] += float(v)
        last_greeks = greeks_total
        equity = cash + position_value
        peak = max(peak, equity)
        dd = (equity / peak - 1.0) * 100.0 if peak else 0.0
        curve.append({
            "date": snap.date, "spot": snap.spot, "equity": equity,
            "positionValue": position_value, "pnl": equity - initial_capital,
            "daysToExpiry": max(0, days),
        })
        drawdown.append({"date": snap.date, "drawdown": dd})

    final = curve[-1]
    total_return = (final["equity"] / initial_capital - 1.0) * 100.0
    max_dd = min((p["drawdown"] for p in drawdown), default=0.0)
    return {
        "status": "OK",
        "engineVersion": OPTIONS_BACKTEST_VERSION,
        "initialCapital": initial_capital,
        "entryDate": chain[0].date,
        "expiry": expiry,
        "exitDate": final["date"],
        "legs": entry,
        "equityCurve": curve,
        "drawdownCurve": drawdown,
        "metrics": {
            "totalReturn": total_return,
            "pnl": final["equity"] - initial_capital,
            "maxDrawdown": max_dd,
            "entryPremium": entry_value,
            "entryCommission": entry_commission,
            "observations": len(curve),
        },
        "greeks": last_greeks,
        "settledAtExpiry": _days_between(final["date"], expiry) <= 0,
        "capability": {
            "historicalOptionChain": "partial",
            "earlyExercise": "unsupported",
            "assignment": "unsupported",
            "surfaceConsistentFills": "unsupported",
        },
        "assumptions": {
            "model": "black-scholes per snapshot (European)",
            "fills": "model premium at entry; no bid/ask surface",
            "exercise": "European, cash-settled at expiry (no early exercise/assignment)",
            "dividends": "continuous yield only",
        },
        "note": "a scoped chain-marked option backtest, not institutional option execution",
    }


__all__ = ["ChainSnapshot", "OPTIONS_BACKTEST_VERSION", "OptionsBacktestError",
           "backtest_option_chain"]

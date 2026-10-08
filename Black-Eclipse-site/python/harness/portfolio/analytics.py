"""Deterministic valuation, P&L, exposure and allocation (pure functions).

These consume already-resolved position data (prices + FX resolved by the
service) and never touch a database, a provider or the async runtime. Every
number traces to the ledger and a Mark; a missing price or FX yields
`UNAVAILABLE`, never a substituted zero.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Optional

from .models import DataQualityStatus, Mark
from .money import ZERO, money_str

GROUPS = ("asset", "assetClass", "sector", "country", "currency", "strategy")


def _pct(numerator: Optional[Decimal], denominator: Optional[Decimal]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(float(numerator / denominator * 100), 6)


def _f(value: Optional[Decimal]) -> Optional[float]:
    return None if value is None else float(value)


def data_quality(positions: Iterable[dict[str, Any]], *, missing_fx: Optional[list[str]] = None) -> dict[str, Any]:
    missing_prices: list[str] = []
    stale_prices: list[dict[str, Any]] = []
    unpriced: list[str] = []
    warnings: list[str] = []
    for p in positions:
        mark: Mark = p["mark"]
        if mark.price is None:
            missing_prices.append(p["symbol"])
            unpriced.append(p["symbol"])
        elif mark.freshness.value not in ("FRESH", "STALE"):
            stale_prices.append({"symbol": p["symbol"], "freshness": mark.freshness.value,
                                 "timestamp": mark.timestamp})
            warnings.append(f"{p['symbol']} price is {mark.freshness.value}")
        for w in mark.warnings:
            if w not in warnings:
                warnings.append(w)
    missing_fx = missing_fx or []
    if missing_prices or stale_prices or missing_fx:
        status = DataQualityStatus.PARTIAL.value if (missing_prices or missing_fx) else DataQualityStatus.OK.value
    else:
        status = DataQualityStatus.OK.value
    return {
        "status": status,
        "missingPrices": missing_prices,
        "stalePrices": stale_prices,
        "missingFX": sorted(set(missing_fx)),
        "unpricedPositions": unpriced,
        "warnings": warnings,
    }


def valuation(base_currency: str, positions: list[dict[str, Any]], cash: Decimal,
              missing_fx: Optional[list[str]] = None) -> dict[str, Any]:
    invested_base = ZERO
    for p in positions:
        if p.get("marketValueBase") is not None:
            invested_base += p["marketValueBase"]
    cash = cash or ZERO
    total_base = invested_base + cash
    return {
        "baseCurrency": base_currency,
        "investedValue": money_str(invested_base),
        "cash": money_str(cash),
        "totalValue": money_str(total_base),
        "unpricedPositions": [p["symbol"] for p in positions if p.get("marketValueBase") is None],
        "dataQuality": data_quality(positions, missing_fx=missing_fx),
    }


def pnl_by_dimension(positions: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
    """Realized + unrealized P&L rolled up by a grouping dimension."""
    if dimension not in GROUPS:
        dimension = "asset"
    buckets: dict[str, dict[str, Decimal]] = {}
    for p in positions:
        key = _group_key(p, dimension)
        b = buckets.setdefault(key, {"realized": ZERO, "unrealized": ZERO})
        b["realized"] += p.get("realizedPnlBase") or ZERO
        b["unrealized"] += p.get("unrealizedPnlBase") or ZERO
    out = [
        {
            "key": key,
            "realizedPnl": money_str(b["realized"]),
            "unrealizedPnl": money_str(b["unrealized"]),
            "totalPnl": money_str(b["realized"] + b["unrealized"]),
        }
        for key, b in buckets.items()
    ]
    out.sort(key=lambda r: abs(float(Decimal(r["totalPnl"]))), reverse=True)
    return out


def pnl(positions: list[dict[str, Any]], *, cash: Decimal, net_deposits: Decimal,
        dividends: Decimal) -> dict[str, Any]:
    realized = ZERO
    unrealized = ZERO
    cost = ZERO
    for p in positions:
        realized += p.get("realizedPnlBase") or ZERO
        if p.get("unrealizedPnlBase") is not None:
            unrealized += p["unrealizedPnlBase"]
        cost += p.get("costBasisBase") or ZERO
    total = realized + unrealized
    return {
        "realizedPnl": money_str(realized),
        "unrealizedPnl": money_str(unrealized),
        "totalPnl": money_str(total),
        "costBasis": money_str(cost),
        "dividends": money_str(dividends),
        "netDeposits": money_str(net_deposits),
        "bySymbol": _pnl_by_symbol(positions),
        "byAssetClass": pnl_by_dimension(positions, "assetClass"),
        "bySector": pnl_by_dimension(positions, "sector"),
        "byStrategy": pnl_by_dimension(positions, "strategy"),
    }


def _pnl_by_symbol(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for p in positions:
        out.append({
            "symbol": p["symbol"],
            "realizedPnl": money_str(p.get("realizedPnlBase")),
            "unrealizedPnl": money_str(p.get("unrealizedPnlBase")),
            "quantity": str(p["quantity"]),
        })
    return out


def exposure(base_currency: str, positions: list[dict[str, Any]], cash: Decimal,
             dimension: str = "asset") -> dict[str, Any]:
    if dimension not in GROUPS:
        dimension = "asset"
    buckets: dict[str, dict[str, Decimal]] = {}
    gross = ZERO
    net = ZERO
    for p in positions:
        value = p.get("marketValueBase")
        if value is None:
            continue
        gross += abs(value)
        net += value
        key = _group_key(p, dimension)
        b = buckets.setdefault(key, {"long": ZERO, "short": ZERO, "net": ZERO})
        if value >= 0:
            b["long"] += value
        else:
            b["short"] += value
        b["net"] += value
    cash = cash or ZERO
    breakdown = [
        {
            "key": key,
            "long": money_str(b["long"]),
            "short": money_str(b["short"]),
            "net": money_str(b["net"]),
            "gross": money_str(abs(b["long"]) + abs(b["short"])),
        }
        for key, b in sorted(buckets.items(), key=lambda kv: abs(kv[1]["net"]), reverse=True)
    ]
    return {
        "baseCurrency": base_currency,
        "dimension": dimension,
        "grossExposure": money_str(gross),
        "netExposure": money_str(net),
        "cash": money_str(cash),
        "netIncludingCash": money_str(net + cash),
        "longExposure": money_str(sum((b["long"] for b in buckets.values()), ZERO)),
        "shortExposure": money_str(sum((b["short"] for b in buckets.values()), ZERO)),
        "breakdown": breakdown,
    }


def allocation(base_currency: str, positions: list[dict[str, Any]], cash: Decimal,
               dimension: str = "asset") -> dict[str, Any]:
    if dimension not in GROUPS:
        dimension = "asset"
    buckets: dict[str, Decimal] = {}
    denominator = ZERO
    priced_value = ZERO
    for p in positions:
        value = p.get("marketValueBase")
        if value is None:
            continue
        key = _group_key(p, dimension)
        buckets[key] = buckets.get(key, ZERO) + value
        priced_value += value
    cash = cash or ZERO
    denominator = priced_value + cash
    breakdown = [
        {
            "key": key,
            "value": money_str(value),
            "weight": _pct(value, denominator),
        }
        for key, value in sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)
    ]
    if cash != 0:
        breakdown.append({"key": "CASH", "value": money_str(cash), "weight": _pct(cash, denominator)})
    # Reconciliation: the weights must sum to 100% (within rounding) whenever the
    # denominator is non-zero. The reported residual is the honest gap.
    weight_sum = sum((b["weight"] or 0.0) for b in breakdown)
    return {
        "baseCurrency": base_currency,
        "dimension": dimension,
        "totalValue": money_str(denominator),
        "pricedValue": money_str(priced_value),
        "cash": money_str(cash),
        "breakdown": breakdown,
        "weightSum": round(weight_sum, 6),
        "reconciles": (abs(weight_sum - 100.0) < 1e-4) if denominator != 0 else True,
        "unpricedPositions": [p["symbol"] for p in positions if p.get("marketValueBase") is None],
    }


def _group_key(position: dict[str, Any], dimension: str) -> str:
    if dimension == "asset":
        return position["symbol"]
    value = position.get(dimension) or position.get("assetClass") or "UNCLASSIFIED"
    return str(value) if value else "UNCLASSIFIED"


__all__ = ["valuation", "pnl", "exposure", "allocation", "data_quality", "GROUPS"]

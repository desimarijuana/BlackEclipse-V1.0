"""Futures continuous-contract construction (splice + back-adjustment).

A futures position is per-contract and rolls before expiry; a backtest needs a
single continuous series. This module builds one from an ordered set of contract
series and a roll schedule, using standard adjustment methods:

  * `none`       — raw splice (keeps the price jumps at each roll),
  * `difference` — shift earlier history by the price gap at each roll so the
    series is continuous (Panama/back-adjusted difference method),
  * `ratio`      — scale earlier history by the price ratio at each roll.

The most recent contract is never adjusted. Every roll (date, contracts, gap,
factor) is recorded so the adjustment is auditable, and the splice is labelled a
*proxy*: the engine trades the continuous series, not deliverable contracts.
"""

from __future__ import annotations

from typing import Any, Optional

from .errors import QuantError


class FuturesError(QuantError):
    code = "FUTURES_ERROR"


def _norm_rows(contract: dict[str, Any]) -> list[dict[str, Any]]:
    rows = contract.get("rows")
    if not isinstance(rows, list) or not rows:
        raise FuturesError(f"contract {contract.get('symbol')!r} has no `rows`")
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            out.append({
                "timestamp": str(row["timestamp"]),
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0)),
            })
        except (KeyError, TypeError, ValueError) as exc:
            raise FuturesError(f"contract {contract.get('symbol')!r} has a malformed row") from exc
    out.sort(key=lambda r: r["timestamp"])
    return out


def _close_at(rows: list[dict[str, Any]], when: str, *, prefer_before: bool) -> Optional[float]:
    """Close of the last bar <= when (before) or first bar >= when (after)."""
    if prefer_before:
        chosen = None
        for r in rows:
            if r["timestamp"] <= when:
                chosen = r
            else:
                break
        if chosen is None and rows:
            chosen = rows[0]
    else:
        chosen = None
        for r in rows:
            if r["timestamp"] >= when:
                chosen = r
                break
        if chosen is None and rows:
            chosen = rows[-1]
    return chosen["close"] if chosen else None


def splice_continuous(
    contracts: list[dict[str, Any]],
    roll_dates: list[str],
    *,
    adjustment: str = "difference",
) -> dict[str, Any]:
    """Splice ordered `contracts` at `roll_dates` into one continuous series.

    `contracts` is near→far (ascending expiry); `roll_dates[i]` is when the series
    switches from `contracts[i]` to `contracts[i+1]` (length = len(contracts) - 1).
    """
    if not contracts:
        raise FuturesError("at least one contract is required")
    if adjustment not in ("none", "difference", "ratio"):
        raise FuturesError(f"unknown adjustment {adjustment!r}")
    if len(contracts) > 1 and len(roll_dates) != len(contracts) - 1:
        raise FuturesError("roll_dates must have exactly one entry per roll")

    series = [_norm_rows(c) for c in contracts]
    for i, (c, rows) in enumerate(zip(contracts, series)):
        if not rows:
            raise FuturesError(f"contract {i} ({c.get('symbol')}) has no bars")
    for i in range(1, len(roll_dates)):
        if roll_dates[i] < roll_dates[i - 1]:
            raise FuturesError("roll_dates must be non-decreasing")

    # Build the raw spliced timeline (each roll_date is exclusive for the old leg).
    timeline: list[tuple[str, int, dict[str, Any]]] = []
    for i, c in enumerate(contracts):
        end = roll_dates[i] if i < len(roll_dates) else None
        for row in series[i]:
            if end is not None and row["timestamp"] >= end:
                continue
            timeline.append((row["timestamp"], i, row))
    timeline.sort(key=lambda t: (t[0], t[1]))
    # De-duplicate timestamps (keep the earlier-listed contract's bar).
    seen: set[str] = set()
    deduped = []
    for ts, idx, row in timeline:
        if ts in seen:
            continue
        seen.add(ts)
        deduped.append((ts, idx, row))
    if not deduped:
        raise FuturesError("the contracts and roll schedule produce no bars")

    # Roll gaps (computed from raw closes) and per-segment offsets.
    rolls: list[dict[str, Any]] = []
    gaps: list[float] = []
    ratios: list[float] = []
    for i in range(len(contracts) - 1):
        when = roll_dates[i]
        old_close = _close_at(series[i], when, prefer_before=True)
        new_close = _close_at(series[i + 1], when, prefer_before=False)
        if old_close is None or new_close is None or old_close == 0 or new_close == 0:
            raise FuturesError(f"cannot determine roll prices at {when!r}")
        gap = new_close - old_close
        gaps.append(gap)
        ratios.append(new_close / old_close)
        rolls.append({
            "at": when, "fromSymbol": contracts[i].get("symbol"),
            "toSymbol": contracts[i + 1].get("symbol"),
            "fromClose": old_close, "toClose": new_close,
            "gap": round(gap, 8), "ratio": round(new_close / old_close, 10),
        })

    # Offsets: newest segment unadjusted; walk backwards.
    k = len(contracts)
    offsets = [0.0] * k
    factors = [1.0] * k
    for i in range(k - 2, -1, -1):
        if adjustment == "difference":
            offsets[i] = offsets[i + 1] + (rolls[i]["toClose"] - rolls[i]["fromClose"])
        elif adjustment == "ratio":
            factors[i] = factors[i + 1] * (rolls[i]["toClose"] / rolls[i]["fromClose"])

    bars: list[dict[str, Any]] = []
    for ts, idx, row in deduped:
        if adjustment == "none":
            adj = {k2: row[k2] for k2 in ("open", "high", "low", "close")}
        elif adjustment == "difference":
            adj = {k2: row[k2] + offsets[idx] for k2 in ("open", "high", "low", "close")}
        else:  # ratio
            adj = {k2: row[k2] * factors[idx] for k2 in ("open", "high", "low", "close")}
        bars.append({
            "timestamp": ts, "open": round(adj["open"], 8), "high": round(adj["high"], 8),
            "low": round(adj["low"], 8), "close": round(adj["close"], 8),
            "volume": row["volume"], "contract": contracts[idx].get("symbol"),
        })

    return {
        "adjustment": adjustment,
        "bars": bars,
        "rolls": rolls,
        "contractSymbols": [c.get("symbol") for c in contracts],
        "barCount": len(bars),
        "note": "the continuous series is a backtest PROXY, not deliverable contracts; "
                "the most recent contract is unadjusted",
    }


def term_structure(points: list[dict[str, Any]], *, spot: Optional[float] = None,
                   risk_free: float = 0.0, storage: float = 0.0) -> dict[str, Any]:
    """Describe a futures curve and its implied carry.

    `points` is ``[{"expiry": "YYYY-MM-DD", "price": 100.0}, ...]``. For each
    point we report the implied annualized carry versus spot (or versus the first
    point when no spot is given). Contango/backwardation are named, not assumed.
    """
    if not points:
        raise FuturesError("term structure needs at least one point")
    rows = []
    base = float(spot) if spot is not None else float(points[0]["price"])
    if base <= 0:
        raise FuturesError("the base price must be positive")
    for point in points:
        try:
            price = float(point["price"])
            expiry = str(point["expiry"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FuturesError("a term-structure point needs expiry and price") from exc
        if price <= 0:
            raise FuturesError("futures prices must be positive")
        years = _years_to(expiry)
        implied = ((price / base) ** (1.0 / years) - 1.0) if years > 0 else None
        rows.append({
            "expiry": expiry, "price": price,
            "yearsToExpiry": round(years, 8),
            "impliedCarry": (None if implied is None else round(implied, 10)),
            "basisVsBase": round(price - base, 8),
            "annualizedCarryAfterConvenience": (
                None if implied is None else round(implied - storage, 10)),
        })
    shape = "flat"
    if len(rows) >= 2:
        shape = ("contango" if rows[-1]["price"] > rows[0]["price"]
                 else "backwardation" if rows[-1]["price"] < rows[0]["price"]
                 else "flat")
    return {
        "basePrice": base, "shape": shape, "points": rows,
        "riskFree": risk_free, "storage": storage,
        "note": "implied carry is a curve-implied number, not a forecast; "
                "convenience yield is not identified separately unless supplied",
    }


def _years_to(expiry: str) -> float:
    from datetime import date  # noqa: PLC0415
    try:
        d = date.fromisoformat(str(expiry)[:10])
    except ValueError as exc:
        raise FuturesError("expiry must be an ISO date") from exc
    days = (d - date.today()).days
    return max(days, 1) / 365.0


def roll_cost(contracts: list[dict[str, Any]], roll_dates: list[str], *,
              adjustment: str = "difference", cost_bps: float = 0.0,
              initial_capital: float = 100_000.0) -> dict[str, Any]:
    """Quantify the cost of rolling a continuous futures position.

    The gap between the outgoing and incoming contract is the *market* roll
    (already reflected in the spliced series under `difference`/`ratio`). The
    `cost_bps` here is the explicit transaction cost of the roll itself.
    """
    spliced = splice_continuous(contracts, roll_dates, adjustment=adjustment)
    rolls = spliced["rolls"]
    costs = []
    total = 0.0
    for roll in rolls:
        notional = abs(float(roll.get("toClose") or 0.0))
        fee = notional * (float(cost_bps) / 10_000.0)
        total += fee
        costs.append({
            "date": roll.get("date"), "fromClose": roll.get("fromClose"),
            "toClose": roll.get("toClose"), "gap": roll.get("gap"),
            "transactionCost": round(fee, 8),
            "costPctOfCapital": round(fee / initial_capital * 100.0, 8) if initial_capital else None,
        })
    return {
        "rolls": costs, "rollCount": len(costs), "totalCost": round(total, 8),
        "costBps": float(cost_bps), "adjustment": adjustment,
        "note": "the price gap is market carry; `transactionCost` is the explicit "
                "roll friction and is never double-counted in the spliced series",
    }


__all__ = ["FuturesError", "roll_cost", "splice_continuous", "term_structure"]

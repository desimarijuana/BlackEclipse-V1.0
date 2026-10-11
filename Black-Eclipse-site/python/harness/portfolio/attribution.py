"""Performance attribution — Brinson single-period decomposition (§25).

Splits active return (portfolio − benchmark) into allocation, selection and
interaction effects by group (sector, asset class, …). Deterministic; inputs are
weights (fractions, summing to ~1) and period returns (fractions).

Two classic forms are supported:
  * Brinson-Fachler (default): allocation = (wp − wb) × (rb − rb_total)
  * Brinson-Hood-Beebower:     allocation = (wp − wb) × rb
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def brinson_attribution(
    segments: Sequence[dict[str, Any]],
    *,
    method: str = "fachler",
    benchmark_total_return: Optional[float] = None,
) -> dict[str, Any]:
    parsed = []
    for seg in segments:
        parsed.append({
            "group": str(seg.get("group") or seg.get("key") or "UNCLASSIFIED"),
            "portfolioWeight": _f(seg.get("portfolioWeight")),
            "benchmarkWeight": _f(seg.get("benchmarkWeight")),
            "portfolioReturn": _f(seg.get("portfolioReturn")),
            "benchmarkReturn": _f(seg.get("benchmarkReturn")),
        })
    if not parsed:
        return {"available": False, "reason": "no segments supplied"}

    rb_total = benchmark_total_return
    if rb_total is None:
        rb_total = sum(s["benchmarkWeight"] * s["benchmarkReturn"] for s in parsed)

    by_group: list[dict[str, Any]] = []
    tot_alloc = tot_select = tot_inter = 0.0
    for s in parsed:
        wp, wb = s["portfolioWeight"], s["benchmarkWeight"]
        rp, rb = s["portfolioReturn"], s["benchmarkReturn"]
        allocation = (wp - wb) * ((rb - rb_total) if method == "fachler" else rb)
        selection = wb * (rp - rb)
        interaction = (wp - wb) * (rp - rb)
        total = allocation + selection + interaction
        tot_alloc += allocation
        tot_select += selection
        tot_inter += interaction
        by_group.append({
            "group": s["group"],
            "portfolioWeight": round(wp, 8),
            "benchmarkWeight": round(wb, 8),
            "portfolioReturn": round(rp, 8),
            "benchmarkReturn": round(rb, 8),
            "allocation": round(allocation, 8),
            "selection": round(selection, 8),
            "interaction": round(interaction, 8),
            "total": round(total, 8),
        })

    portfolio_return = sum(s["portfolioWeight"] * s["portfolioReturn"] for s in parsed)
    return {
        "available": True,
        "method": method,
        "portfolioReturn": round(portfolio_return, 8),
        "benchmarkReturn": round(rb_total, 8),
        "activeReturn": round(portfolio_return - rb_total, 8),
        "effects": {
            "allocation": round(tot_alloc, 8),
            "selection": round(tot_select, 8),
            "interaction": round(tot_inter, 8),
            "total": round(tot_alloc + tot_select + tot_inter, 8),
        },
        "byGroup": by_group,
    }


def multi_period_attribution(
    periods: Sequence[dict[str, Any]], *, method: str = "fachler",
) -> dict[str, Any]:
    """Linked multi-period Brinson attribution (exact proportional linking).

    Each period is a dict with `segments` (as in `brinson_attribution`) and an
    optional `name`. Single-period effects are compounded so that the summed
    multi-period effects reconcile EXACTLY to the geometric active return
    `(1+Rp)/(1+Rb) − 1`. Compounding is by proportional rescaling: every
    single-period effect is multiplied by `G / A`, where `G` is the geometric
    active return and `A = Σ (rpₜ − rbₜ)` the summed arithmetic active return.
    Because each period's effects sum to its active return, the rescaled effects
    sum to `G` by construction. This is deliberately not a naive sum of
    single-period active returns, which would be wrong across periods.
    """
    if not periods:
        return {"available": False, "reason": "no periods supplied"}
    single = []
    for p in periods:
        result = brinson_attribution(p.get("segments") or [], method=method)
        if not result.get("available"):
            return {"available": False, "reason": "a period had no segments"}
        single.append({"name": p.get("name") or f"period{len(single)}", **result})

    cum_p = 1.0
    cum_b = 1.0
    arithmetic_active = 0.0
    for s in single:
        cum_p *= 1.0 + s["portfolioReturn"]
        cum_b *= 1.0 + s["benchmarkReturn"]
        arithmetic_active += s["portfolioReturn"] - s["benchmarkReturn"]
    active = (cum_p / cum_b - 1.0) if cum_b > 0 else (cum_p - 1.0)
    scale = (active / arithmetic_active) if abs(arithmetic_active) > 1e-15 else 0.0

    effects = {"allocation": 0.0, "selection": 0.0, "interaction": 0.0, "total": 0.0}
    linked = []
    for s in single:
        row = {"name": s["name"], "periodActive": round(s["portfolioReturn"] - s["benchmarkReturn"], 8),
               "scale": round(scale, 8), "effects": {}}
        for key in ("allocation", "selection", "interaction", "total"):
            value = s["effects"][key] * scale
            effects[key] += value
            row["effects"][key] = round(value, 8)
        linked.append(row)

    return {
        "available": True,
        "method": f"{method}_proportional_linked",
        "cumulativePortfolioReturn": round(cum_p - 1.0, 8),
        "cumulativeBenchmarkReturn": round(cum_b - 1.0, 8),
        "activeReturn": round(active, 8),
        "periods": linked,
        "effects": {k: round(v, 8) for k, v in effects.items()},
        "reconciles": abs(effects["total"] - active) <= 1e-7 * max(1.0, abs(active)),
    }


__all__ = ["brinson_attribution", "multi_period_attribution"]

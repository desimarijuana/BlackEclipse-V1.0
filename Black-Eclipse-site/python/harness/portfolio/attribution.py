"""Performance attribution — Brinson single-period decomposition (§25).

Splits active return (portfolio − benchmark) into allocation, selection and
interaction effects by group (sector, asset class, …). Deterministic; inputs are
weights (fractions, summing to ~1) and period returns (fractions).

Two classic forms are supported:
  * Brinson-Fachler (default): allocation = (wp − wb) × (rb − rb_total)
  * Brinson-Hood-Beebower:     allocation = (wp − wb) × rb
"""

from __future__ import annotations

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


__all__ = ["brinson_attribution"]

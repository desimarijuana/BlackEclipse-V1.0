"""Deterministic tax-loss harvest candidates (proposal only).

Given a portfolio read (positions with unrealized P&L), identify the positions
whose unrealized loss exceeds a threshold — the raw material a tax-loss-harvest
decision is made from. It is:

  * deterministic — no model call, no market fetch (it consumes the SAME read the
    portfolio tools/UI use);
  * honest — a position with no price is skipped, never treated as a zero loss;
  * proposal-only — it never places a trade.

Wash-sale rules are deliberately NOT modelled: they are jurisdiction-specific and
depend on purchases the ledger may not have (accounts held elsewhere). The result
states this limitation rather than pretending to enforce a rule it cannot see.
"""

from __future__ import annotations

from typing import Any, Optional

_NOTE = (
    "Proposal only — no trades are placed. Wash-sale rules are not modelled; "
    "confirm the 30-day window across ALL accounts before acting."
)


def harvest_candidates(
    positions: list[dict[str, Any]],
    *,
    threshold: float,
    base_currency: str = "USD",
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Positions with an unrealized loss of at least `threshold` (a positive amount).

    `positions` are the serialized rows from `PortfolioService.read` (each carries
    `symbol`, `unrealizedPnlBase`, `weight`, `currency`). A row with no
    `unrealizedPnlBase` is skipped. Candidates are ordered worst-loss-first.
    """
    threshold = abs(float(threshold))
    candidates: list[dict[str, Any]] = []
    for position in positions:
        loss = _float_or_none(position.get("unrealizedPnlBase"))
        if loss is None or loss > -threshold:
            continue
        candidates.append({
            "symbol": position.get("symbol"),
            "unrealizedPnl": loss,
            "weight": position.get("weight"),
            "currency": position.get("currency") or base_currency,
            "quantity": position.get("quantity"),
        })
    candidates.sort(key=lambda c: c["unrealizedPnl"])
    if limit is not None:
        candidates = candidates[: int(limit)]
    return {
        "candidates": candidates,
        "count": len(candidates),
        "threshold": threshold,
        "baseCurrency": base_currency,
        "proposalOnly": True,
        "note": _NOTE,
    }


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["harvest_candidates"]

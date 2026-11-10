"""Corporate actions as explicit events.

Most research data is delivered *adjusted*, in which case dividends and splits
are already reflected in the price series and must NOT be applied again. Some
feeds (and many futures/FX series) are unadjusted, and there a backtest that
ignores a dividend understates total return and a backtest that ignores a split
manufactures a catastrophic loss.

This module makes the choice explicit:

* `CorporateAction` is a plain record with an effective (ex-date) date.
* `parse_actions` validates untrusted input (the same discipline as bundles).
* `apply_to_position` returns the exact quantity/cash change for one action.
* `actions_on` matches by calendar date, not a fragile full timestamp.

The engine applies these only when the caller supplies them
(`BacktestConfig.corporate_actions`); an adjusted series is never double-counted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .errors import QuantError


class CorporateActionError(QuantError):
    code = "CORPORATE_ACTION_ERROR"


@dataclass(frozen=True)
class CorporateAction:
    symbol: str
    ex_date: str                    # YYYY-MM-DD
    kind: str                       # "dividend" | "split"
    amount: float = 0.0             # dividend cash per share
    ratio: float = 1.0              # split: new shares per old share
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "exDate": self.ex_date, "kind": self.kind,
            "amount": self.amount, "ratio": self.ratio, "currency": self.currency,
        }


def _date(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) < 10:
        raise CorporateActionError(
            "an ex-date must be an ISO date (YYYY-MM-DD)",
            detail={"value": text},
        )
    text = text[:10]
    parts = text.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise CorporateActionError(
            "an ex-date must be an ISO date (YYYY-MM-DD)",
            detail={"value": text},
        )
    return text


def parse_actions(raw: Optional[Iterable[Any]]) -> list[CorporateAction]:
    """Validate and normalize caller-supplied actions.

    Unknown kinds are refused rather than silently ignored, because ignoring a
    split is a material accounting error, not a cosmetic one.
    """
    if not raw:
        return []
    out: list[CorporateAction] = []
    for item in raw:
        if isinstance(item, CorporateAction):
            action = item
        elif isinstance(item, dict):
            kind = str(item.get("kind") or item.get("type") or "").strip().lower()
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol:
                raise CorporateActionError("a corporate action needs a symbol")
            if kind not in ("dividend", "split"):
                raise CorporateActionError(
                    f"unsupported corporate action kind {kind!r}",
                    detail={"symbol": symbol, "kind": kind},
                )
            action = CorporateAction(
                symbol=symbol,
                ex_date=_date(item.get("exDate") or item.get("date") or item.get("ex_date")),
                kind=kind,
                amount=float(item.get("amount") or 0.0),
                ratio=float(item.get("ratio") or 1.0),
                currency=str(item.get("currency") or "USD").upper(),
            )
        else:
            raise CorporateActionError(
                "each corporate action must be an object or CorporateAction",
                detail={"type": type(item).__name__},
            )
        if action.kind == "dividend" and action.amount < 0:
            raise CorporateActionError("a dividend amount cannot be negative")
        if action.kind == "split" and action.ratio <= 0:
            raise CorporateActionError("a split ratio must be positive")
        out.append(action)
    return out


def actions_on(actions: Iterable[CorporateAction], symbol: str,
               timestamp: Any) -> list[CorporateAction]:
    if timestamp is None:
        return []
    day = str(timestamp)[:10]
    sym = str(symbol).upper()
    return [a for a in actions if a.symbol == sym and a.ex_date == day]


def apply_to_position(action: CorporateAction, *, quantity: float,
                      avg_entry_price: float) -> dict[str, Any]:
    """Return the accounting effect of one action on a position.

    * dividend: cash = quantity × amount (a short pays it, a long receives it);
    * split: quantity × ratio and avg entry price ÷ ratio, preserving cost basis.

    The caller applies the change; this function only computes it, so the same
    code can be unit-tested without a portfolio.
    """
    if action.kind == "dividend":
        cash = float(quantity) * float(action.amount)
        return {
            "kind": "dividend",
            "cashDelta": cash,
            "quantityDelta": 0.0,
            "newQuantity": float(quantity),
            "newAvgEntryPrice": float(avg_entry_price),
            "amountPerShare": float(action.amount),
        }
    if action.kind == "split":
        new_qty = float(quantity) * float(action.ratio)
        new_avg = (float(avg_entry_price) / float(action.ratio)
                   if action.ratio else float(avg_entry_price))
        return {
            "kind": "split",
            "cashDelta": 0.0,
            "quantityDelta": new_qty - float(quantity),
            "newQuantity": new_qty,
            "newAvgEntryPrice": new_avg,
            "ratio": float(action.ratio),
        }
    raise CorporateActionError(f"unsupported corporate action kind {action.kind!r}")


def events_for(actions: Iterable[CorporateAction]) -> dict[str, list[CorporateAction]]:
    """Group actions by ex-date for an O(1) timeline lookup."""
    grouped: dict[str, list[CorporateAction]] = {}
    for action in actions:
        grouped.setdefault(action.ex_date, []).append(action)
    return grouped


__all__ = [
    "CorporateAction",
    "CorporateActionError",
    "actions_on",
    "apply_to_position",
    "events_for",
    "parse_actions",
]

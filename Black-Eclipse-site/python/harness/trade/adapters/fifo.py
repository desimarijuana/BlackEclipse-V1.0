"""FIFO round-trip normalizer for brokers without a position id.

MT5 reports deals already tied to a `position_id`; Alpaca and IBKR report
executions/orders instead. The journal projection needs round-trips (an entry
and an exit, with costs), so this module turns a chronological execution stream
into synthetic deal legs using FIFO lots.

It is deliberately deterministic and conservative:

* one round-trip per closing execution (a close spanning several lots is
  aggregated into one weighted entry, which is what a trader calls one exit);
* partial fills and scale-ins are supported;
* shorts are supported (sell opens, buy closes);
* fees are allocated pro-rata to the matched quantity;
* an unclosed remainder becomes an `in`-only deal (the journal shows it open);
* no corporate-action or split adjustment — the caller must supply adjusted
  executions or accept the raw accounting.

P&L here is **Eclipse-computed FIFO**, not a broker-reported figure. The caller
should not label it as broker-reported.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass
class Execution:
    id: str
    symbol: str
    side: str  # "buy" | "sell"
    qty: float
    price: float
    time_ms: int
    fee: float = 0.0  # positive = cost


@dataclass
class _Lot:
    qty: float
    price: float
    time_ms: int
    open_id: str
    fee_per_unit: float = 0.0


def _stable_id(*parts: Any) -> int:
    """A positive 31-bit id, stable across runs (Prisma Int is 32-bit)."""
    digest = hashlib.sha1("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def _round(value: float) -> float:
    return float(f"{value:.10f}")


def normalize_fifo(executions: Iterable[Execution]) -> list[dict[str, Any]]:
    """Turn executions into journal-ready synthetic deals.

    The output matches the adapter deal shape (the same shape MT5's
    `deals_since` returns), so the reconciler and journal projection need no
    broker-specific code.
    """
    ordered = sorted(
        (e for e in executions if e.qty > 0 and e.price > 0 and e.symbol),
        key=lambda e: (int(e.time_ms or 0), e.id),
    )

    deals: list[dict[str, Any]] = []
    # symbol -> { direction sign (+1 long, -1 short), FIFO lots }
    state: dict[str, dict[str, Any]] = {}
    seq = 0

    for execution in ordered:
        symbol = execution.symbol.strip().upper()
        book = state.setdefault(symbol, {"sign": 0, "lots": []})
        sign = 1 if execution.side.lower() == "buy" else -1
        remaining = execution.qty
        fee_remaining = max(0.0, execution.fee)
        fee_per_unit = fee_remaining / execution.qty if execution.qty else 0.0

        if not book["lots"]:
            book["sign"] = sign
            book["lots"].append(
                _Lot(
                    qty=remaining,
                    price=execution.price,
                    time_ms=execution.time_ms,
                    open_id=execution.id,
                    fee_per_unit=fee_per_unit,
                )
            )
            continue

        current_sign = int(book["sign"])
        if sign == current_sign:
            book["lots"].append(
                _Lot(
                    qty=remaining,
                    price=execution.price,
                    time_ms=execution.time_ms,
                    open_id=execution.id,
                    fee_per_unit=fee_per_unit,
                )
            )
            continue

        # Opposite side: close FIFO, aggregating this exit into one round-trip.
        matched_qty = 0.0
        matched_notional = 0.0
        open_fees = 0.0
        profit = 0.0
        first_open_id: Optional[str] = None
        first_open_time: Optional[int] = None
        while remaining > 1e-12 and book["lots"]:
            lot: _Lot = book["lots"][0]
            chunk = min(remaining, lot.qty)
            if first_open_id is None:
                first_open_id = lot.open_id
                first_open_time = lot.time_ms
            matched_qty += chunk
            matched_notional += lot.price * chunk
            open_fees += lot.fee_per_unit * chunk
            profit += (execution.price - lot.price) * current_sign * chunk
            lot.qty = _round(lot.qty - chunk)
            remaining = _round(remaining - chunk)
            if lot.qty <= 1e-12:
                book["lots"].pop(0)

        if matched_qty > 0:
            exit_fee = fee_per_unit * matched_qty
            total_fee = open_fees + exit_fee
            weighted_entry = matched_notional / matched_qty
            seq += 1
            position_ticket = _stable_id(
                "rt", first_open_id, execution.id, seq
            )
            entry_ticket = _stable_id("leg", position_ticket, "in")
            exit_ticket = _stable_id("leg", position_ticket, "out")
            deals.append(
                {
                    "dealTicket": entry_ticket,
                    "orderTicket": None,
                    "positionTicket": position_ticket,
                    "symbol": symbol,
                    "side": "buy" if current_sign > 0 else "sell",
                    "entry": "in",
                    "volume": _round(matched_qty),
                    "price": _round(weighted_entry),
                    "commission": _round(-open_fees),
                    "swap": 0.0,
                    "profit": 0.0,
                    "magic": 0,
                    "comment": "fifo",
                    "dealtAt": int(first_open_time or execution.time_ms),
                    "eclipseOwned": False,
                    "pnlBasis": "computed",
                }
            )
            deals.append(
                {
                    "dealTicket": exit_ticket,
                    "orderTicket": None,
                    "positionTicket": position_ticket,
                    "symbol": symbol,
                    "side": "sell" if current_sign > 0 else "buy",
                    "entry": "out",
                    "volume": _round(matched_qty),
                    "price": _round(execution.price),
                    "commission": _round(-exit_fee),
                    "swap": 0.0,
                    "profit": _round(profit),
                    "magic": 0,
                    "comment": f"fifo fees={_round(total_fee)}",
                    "dealtAt": int(execution.time_ms),
                    "eclipseOwned": False,
                    "pnlBasis": "computed",
                }
            )

        if remaining > 1e-12:
            # Position flipped: the remainder opens the new direction.
            book["sign"] = sign
            book["lots"] = [
                _Lot(
                    qty=remaining,
                    price=execution.price,
                    time_ms=execution.time_ms,
                    open_id=execution.id,
                    fee_per_unit=fee_per_unit,
                )
            ]

    # Any still-open lots become an `in`-only round-trip each.
    for symbol, book in state.items():
        for lot in book["lots"]:
            seq += 1
            position_ticket = _stable_id("open", lot.open_id, symbol, seq)
            deals.append(
                {
                    "dealTicket": _stable_id("leg", position_ticket, "in"),
                    "orderTicket": None,
                    "positionTicket": position_ticket,
                    "symbol": symbol,
                    "side": "buy" if int(book["sign"]) > 0 else "sell",
                    "entry": "in",
                    "volume": _round(lot.qty),
                    "price": _round(lot.price),
                    "commission": _round(-(lot.fee_per_unit * lot.qty)),
                    "swap": 0.0,
                    "profit": 0.0,
                    "magic": 0,
                    "comment": "fifo open",
                    "dealtAt": int(lot.time_ms),
                    "eclipseOwned": False,
                    "pnlBasis": "computed",
                }
            )

    return deals


__all__ = ["Execution", "normalize_fifo"]

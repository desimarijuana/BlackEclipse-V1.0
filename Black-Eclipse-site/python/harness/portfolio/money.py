"""Decimal money/quantity arithmetic for the Portfolio Accounting Engine.

Money and accounting quantities are NEVER represented as binary floating point.
`Decimal` is the authoritative type for every price, cost, quantity, fee and
balance. Statistics that are not monetary (returns, volatility, ratios) may use
float — they are dimensionless numbers, not balances.

Precision policy:
  * The raw Decimal context keeps 34 significant digits (IEEE decimal128) so a
    chain of intermediate operations never silently rounds.
  * Money is quantized to 8 decimal places and quantities to 12 only at the
    OUTPUT boundary (`q_money` / `q_qty`), never mid-computation.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, getcontext, localcontext
from typing import Any, Optional

getcontext().prec = 34

QTY_PLACES = Decimal("0.000000000001")
MONEY_PLACES = Decimal("0.00000001")
RATE_PLACES = Decimal("0.0000000001")

ZERO = Decimal("0")
ONE = Decimal("1")


def D(value: Any, default: Optional[Decimal] = None) -> Decimal:
    """Coerce a value to Decimal without going through binary float.

    A float is only accepted as a *lossless-printed* literal (`str(value)`) —
    this is deliberate: callers should pass strings or Decimals for money. A
    float still round-trips through its shortest representation, which is the
    best available recovery for JSON-sourced numbers, but the engine never
    performs arithmetic on the float itself.
    """
    if value is None:
        if default is not None:
            return default
        raise ValueError("cannot convert None to Decimal")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("refusing to treat a bool as a number")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            if default is not None:
                return default
            raise ValueError("empty string is not a number")
        try:
            return Decimal(text)
        except InvalidOperation as exc:  # noqa: PERF203
            raise ValueError(f"invalid decimal literal {value!r}") from exc
    raise ValueError(f"cannot convert {type(value).__name__} to Decimal")


def D_or_none(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return D(value)
    except ValueError:
        return None


def q_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_EVEN)


def q_qty(value: Decimal) -> Decimal:
    return value.quantize(QTY_PLACES, rounding=ROUND_HALF_EVEN)


def q_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE_PLACES, rounding=ROUND_HALF_EVEN)


def money_str(value: Optional[Decimal]) -> Optional[str]:
    """A stable, exact string for persistence (no scientific notation)."""
    if value is None:
        return None
    return format(q_money(value), "f")


def qty_str(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(q_qty(value), "f")


def to_float(value: Optional[Decimal]) -> Optional[float]:
    """Float projection for JSON transport ONLY — never for accounting."""
    if value is None:
        return None
    return float(q_money(value))


__all__ = [
    "D",
    "D_or_none",
    "ZERO",
    "ONE",
    "QTY_PLACES",
    "MONEY_PLACES",
    "RATE_PLACES",
    "q_money",
    "q_qty",
    "q_rate",
    "money_str",
    "qty_str",
    "to_float",
    "localcontext",
]

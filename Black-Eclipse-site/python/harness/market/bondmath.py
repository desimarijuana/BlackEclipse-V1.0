"""Bond analytics — duration, modified duration and convexity (derived).

Computed from coupon, yield and time-to-maturity when a provider supplies them.
A provider-supplied figure always wins; a missing input yields `None` (never a
fabricated duration). Pure math, no I/O.

Convention (documented): `coupon` and `yield` are ANNUAL PERCENT values
(e.g. 4.25 = 4.25%); a value <= 1 is treated as an already-decimal fraction.
Semiannual coupons by default. Face value 100.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from .greeks import years_to_expiry


def _as_rate(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    v = float(value)
    # 4.25 (%) vs 0.0425 (fraction): a small magnitude is already a fraction.
    return v / 100.0 if abs(v) > 1.0 else v


def bond_analytics(
    *,
    coupon: Optional[float],
    yield_: Optional[float],
    years: Optional[float],
    frequency: int = 2,
    face: float = 100.0,
) -> Optional[dict[str, float]]:
    """Macaulay/modified duration + convexity, or None if inputs are unusable."""
    c = _as_rate(coupon)
    y = _as_rate(yield_)
    if y is None or years is None or years <= 0 or frequency <= 0:
        return None
    n = max(1, int(round(years * frequency)))
    per_coupon = (c if c is not None else 0.0) * face / frequency
    y_per = y / frequency
    price = 0.0
    weighted = 0.0
    convex = 0.0
    for t in range(1, n + 1):
        cf = per_coupon + (face if t == n else 0.0)
        disc = (1.0 + y_per) ** t
        pv = cf / disc
        price += pv
        weighted += t * pv
        convex += t * (t + 1) * cf / ((1.0 + y_per) ** (t + 2))
    if price <= 0:
        return None
    macaulay = (weighted / price) / frequency
    modified = macaulay / (1.0 + y_per)
    convexity = convex / price / (frequency * frequency)
    return {
        "price": price,
        "macaulay_duration": macaulay,
        "modified_duration": modified,
        "convexity": convexity,
    }


def enrich_bond(bond: Any, *, frequency: int = 2, now: Optional[_dt.datetime] = None) -> bool:
    """Fill duration/modified_duration/convexity on a BondData in place.

    Returns True when at least one figure was computed. Provider-supplied values
    are never overwritten.
    """
    need = (
        getattr(bond, "duration", None) is None
        or getattr(bond, "modified_duration", None) is None
        or getattr(bond, "convexity", None) is None
    )
    if not need:
        return False
    years: Optional[float] = getattr(bond, "_years_to_maturity", None)
    if years is None:
        years = years_to_expiry(getattr(bond, "maturity", None), now=now)
        try:
            bond._years_to_maturity = years  # noqa: SLF001 - cached on the record
        except Exception:  # noqa: BLE001 - pydantic models allow private attrs too
            pass
    result = bond_analytics(
        coupon=getattr(bond, "coupon", None),
        yield_=getattr(bond, "yield_", None),
        years=years,
        frequency=frequency,
    )
    if result is None:
        return False
    if getattr(bond, "duration", None) is None:
        bond.duration = result["macaulay_duration"]
    if getattr(bond, "modified_duration", None) is None:
        bond.modified_duration = result["modified_duration"]
    if getattr(bond, "convexity", None) is None:
        bond.convexity = result["convexity"]
    return True


__all__ = ["bond_analytics", "enrich_bond"]

"""Cost-of-carry: short borrow, cash financing and maintenance margin.

These are the costs that make a *leveraged* or *short* backtest believable. They
are deliberately separate from `execution.py` (which models the trade itself):
carry accrues while a position is held, not when it is opened.

Every function is pure and deterministic. A missing or undefined input produces
zero **and** a reason in the audit payload, never a silent charge. The engine
calls these once per bar with the actual elapsed calendar time, so a daily bar
and an hourly bar accrue proportionally.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

# A year is a rate convention, not a market fact: 360 (money market) and 365
# (calendar) are both common. The spec records which was used.
DAY_COUNTS = (360, 365)


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            try:
                dt = datetime.fromisoformat(text[:10])
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def elapsed_days(previous_ts: Any, current_ts: Any, *, interval_days: float = 1.0) -> float:
    """Calendar days between two timestamps.

    A missing/unparseable pair falls back to one interval, which is the smallest
    defensible unit the engine knows about (the bar spacing), never zero.
    """
    a = _parse_ts(previous_ts)
    b = _parse_ts(current_ts)
    if a is None or b is None:
        return max(0.0, float(interval_days))
    seconds = (b - a).total_seconds()
    if seconds <= 0:
        return 0.0
    return seconds / 86_400.0


def interest(notional: float, annual_bps: float, days: float, day_count: int = 360) -> float:
    """Simple interest on a signed notional over `days` calendar days."""
    if notional == 0 or annual_bps == 0 or days <= 0 or day_count <= 0:
        return 0.0
    return float(notional) * (float(annual_bps) / 10_000.0) * (float(days) / float(day_count))


def borrow_cost(short_notional: float, annual_bps: float, days: float,
                day_count: int = 360) -> float:
    """Borrow fee for a short position. `short_notional` is positive."""
    return interest(abs(float(short_notional)), annual_bps, days, day_count)


def locate_fee(notional: float, locate_bps: float) -> float:
    """One-off locate fee charged when a short is opened."""
    if not notional or not locate_bps:
        return 0.0
    return abs(float(notional)) * (float(locate_bps) / 10_000.0)


def financing_cost(cash: float, *, debit_rate_bps: float, credit_rate_bps: float,
                   days: float, day_count: int = 360) -> float:
    """Signed cash carry: negative cash charges, positive cash earns.

    The returned value is the *cash delta* (a positive number is a credit, a
    negative number is a debit), so a caller can simply add it to cash.
    """
    if days <= 0:
        return 0.0
    if cash < 0:
        return -interest(abs(cash), debit_rate_bps, days, day_count)
    if cash > 0:
        return interest(cash, credit_rate_bps, days, day_count)
    return 0.0


def funding_payment(notional: float, funding_rate_bps: float, *,
                    side_sign: float = 1.0, periods: float = 1.0) -> float:
    """Perpetual-futures funding cash flow (signed).

    A positive funding rate means longs pay shorts. `side_sign` is +1 for a
    long and -1 for a short, so the returned value is the cash delta for that
    side (negative = paid).
    """
    if not notional or not funding_rate_bps or periods <= 0:
        return 0.0
    magnitude = abs(float(notional)) * (float(funding_rate_bps) / 10_000.0) * float(periods)
    return -float(side_sign) * magnitude


def fx_swap_points(notional: float, *, base_rate_bps: float, quote_rate_bps: float,
                   days: float, day_count: int = 360) -> float:
    """Approximate FX forward points as the interest-rate differential.

    This is a *carry* approximation (covered interest parity), not a quote. The
    result is in quote-currency units per unit of base notional.
    """
    if days <= 0:
        return 0.0
    differential = (float(quote_rate_bps) - float(base_rate_bps)) / 10_000.0
    return float(notional) * differential * (float(days) / float(day_count))


def maintenance_requirement(gross_exposure: float, maintenance_pct: float) -> float:
    if gross_exposure <= 0 or maintenance_pct <= 0:
        return 0.0
    return float(gross_exposure) * float(maintenance_pct)


def margin_status(*, equity: float, gross_exposure: float,
                  maintenance_pct: float, initial_pct: float = 0.0) -> dict[str, Any]:
    """Describe the margin state without deciding anything."""
    maintenance = maintenance_requirement(gross_exposure, maintenance_pct)
    initial = maintenance_requirement(gross_exposure, initial_pct)
    excess = float(equity) - maintenance
    return {
        "enabled": True,
        "equity": float(equity),
        "grossExposure": float(gross_exposure),
        "maintenanceRequirement": maintenance,
        "initialRequirement": initial,
        "excess": excess,
        "breached": maintenance > 0 and equity < maintenance,
        "maintenancePct": float(maintenance_pct),
        "initialPct": float(initial_pct),
    }


def borrow_available(terms: Any, symbol: str) -> tuple[bool, Optional[str]]:
    """Return (available, reason). An empty symbol list means every symbol."""
    if terms is None:
        return True, None
    if not bool(getattr(terms, "available", True)):
        return False, "short borrow is marked unavailable for this strategy"
    symbols = {str(s).upper() for s in (getattr(terms, "symbols", None) or [])}
    if symbols and str(symbol).upper() not in symbols:
        return False, f"no borrow locate for {symbol}"
    return True, None


@dataclass(frozen=True)
class CarryAccrual:
    """One period's carry, with the inputs that produced it (audit-friendly)."""

    days: float
    financing: float
    borrow: float
    cashAfter: float

    @property
    def total(self) -> float:
        return self.financing + self.borrow

    def to_dict(self) -> dict[str, Any]:
        return {
            "days": round(self.days, 8),
            "financing": round(self.financing, 8),
            "borrow": round(self.borrow, 8),
            "total": round(self.total, 8),
            "cashAfter": round(self.cashAfter, 8),
        }


__all__ = [
    "CarryAccrual",
    "DAY_COUNTS",
    "borrow_available",
    "borrow_cost",
    "elapsed_days",
    "financing_cost",
    "funding_payment",
    "fx_swap_points",
    "interest",
    "locate_fee",
    "maintenance_requirement",
    "margin_status",
]

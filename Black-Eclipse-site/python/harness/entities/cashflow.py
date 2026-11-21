"""Irregular dated cash flows — the non-bar half of the asset spine.

Some holdings have no daily bar: a private fund, a structured note, a rental
property, a bond purchased at issue. Their value arrives as **irregular dated
flows** (capital calls, distributions, coupons, fees, a terminal NAV), and the
only honest return for them is money-weighted, not a price series.

Sign convention, stated once and enforced in code
-------------------------------------------------
Every amount is from the **holder's** point of view:

    amount > 0  cash comes IN to the holder   (distribution, coupon, proceeds)
    amount < 0  cash goes OUT from the holder (capital call, purchase, fee)

That is the ordinary IRR/XIRR convention, so a series can be fed straight to a
money-weighted return without a caller-side flip. Because callers reliably get
this backwards when reading a broker or fund statement, the canonical kinds in
`KIND_DIRECTION` are **enforced at construction**: a positive `capital_call` is
rejected, not quietly accepted. A genuinely two-directional movement must be
given its own `kind` — the escape hatch is to name the flow honestly, never to
disable the check.

Valuations are not cash
-----------------------
A NAV mark is a valuation, not a settled movement. It is representable here
because a terminal NAV is required to compute IRR or TVPI, but it is tagged
`is_valuation=True` and **excluded from `total()`**. Mixing the two would count
the same money twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, Optional, Sequence

#: Canonical kinds and the sign the holder's perspective requires.
KIND_DIRECTION: dict[str, int] = {
    "capital_call": -1,
    "purchase": -1,
    "fee": -1,
    "subscription": -1,
    "distribution": +1,
    "dividend": +1,
    "coupon": +1,
    "proceeds": +1,
    "redemption": +1,
}

#: Kinds whose amount may legitimately be either sign (a recallable distribution,
#: a fee rebate). They are listed so an operator can see them, and they carry no
#: sign constraint.
TWO_WAY_KINDS: frozenset[str] = frozenset({
    "flow", "adjustment", "recallable_distribution", "rebate", "fx",
})

_DAY = 86_400.0


def _parse_day(value: object) -> date:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc


@dataclass(frozen=True)
class CashFlow:
    """One dated movement, from the holder's point of view."""

    date: object
    amount: float
    kind: str = "flow"
    is_valuation: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        amount = float(self.amount)
        if amount != amount or amount in (float("inf"), float("-inf")):
            raise ValueError("amount must be finite")
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "_day", _parse_day(self.date))
        required = KIND_DIRECTION.get(self.kind)
        if required is None:
            if self.kind not in TWO_WAY_KINDS:
                raise ValueError(
                    f"unknown kind {self.kind!r}; use a canonical kind "
                    f"({', '.join(sorted(KIND_DIRECTION))}) or a two-way kind "
                    f"({', '.join(sorted(TWO_WAY_KINDS))})"
                )
            return
        if required > 0 and amount < 0:
            raise ValueError(
                f"a {self.kind} is cash IN to the holder; amount {amount} is negative. "
                "Flip the sign or name the flow for what it is."
            )
        if required < 0 and amount > 0:
            raise ValueError(
                f"a {self.kind} is cash OUT of the holder; amount {amount} is positive. "
                "Flip the sign or name the flow for what it is."
            )

    @property
    def day(self) -> date:
        return self._day  # type: ignore[attr-defined]

    def to_dict(self) -> dict:
        return {
            "date": self.day.isoformat(),
            "amount": self.amount,
            "kind": self.kind,
            "isValuation": self.is_valuation,
            "note": self.note,
        }


def _npv(rate: float, flows: Sequence[tuple[date, float]], origin: date) -> float:
    total = 0.0
    base = 1.0 + rate
    for when, amount in flows:
        years = (when - origin).days / 365.0
        total += amount / (base**years)
    return total


def _xirr_entries(entries: Sequence[tuple[date, float]]) -> Optional[float]:
    dated = sorted(entries)
    if len(dated) < 2:
        return None
    if all(amount >= 0 for _day, amount in dated) or all(
        amount <= 0 for _day, amount in dated
    ):
        return None
    origin = dated[0][0]
    lo, hi = -0.9999, 10.0
    f_lo, f_hi = _npv(lo, dated, origin), _npv(hi, dated, origin)
    if f_lo * f_hi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2.0
        f_mid = _npv(mid, dated, origin)
        if abs(f_mid) < 1e-9:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def xirr(flows: Iterable[CashFlow], *, as_of: Optional[object] = None) -> Optional[float]:
    """Annualised money-weighted return of dated flows, or None.

    None means "not well defined": fewer than two flows, or no sign change (a
    series of only contributions has no return). It never returns a fabricated 0.
    """
    entries = [(f.day, f.amount) for f in flows if not f.is_valuation]
    if as_of is not None and entries:
        entries.append((_parse_day(as_of), 0.0))  # anchor only
    return _xirr_entries(entries)


@dataclass
class CashFlowSeries:
    """A holder's dated flows, with the totals a reader expects."""

    flows: list[CashFlow] = field(default_factory=list)

    @classmethod
    def of(cls, *flows: CashFlow) -> "CashFlowSeries":
        return cls(flows=list(flows))

    def add(self, flow: CashFlow) -> "CashFlowSeries":
        self.flows.append(flow)
        return self

    @property
    def cash(self) -> list[CashFlow]:
        """Settled movements only — valuations excluded."""
        return [f for f in self.flows if not f.is_valuation]

    @property
    def valuations(self) -> list[CashFlow]:
        return [f for f in self.flows if f.is_valuation]

    def total(self) -> float:
        """Net settled cash. Valuations are NOT cash and never counted here."""
        return float(sum(f.amount for f in self.cash))

    def invested(self) -> float:
        return float(-sum(f.amount for f in self.cash if f.amount < 0))

    def distributed(self) -> float:
        return float(sum(f.amount for f in self.cash if f.amount > 0))

    def tvpi(self) -> Optional[float]:
        """Total value to paid-in capital: distributed / invested.

        None when nothing has been invested — a ratio with a zero denominator is
        not "infinite", it is undefined.
        """
        paid_in = self.invested()
        if paid_in <= 0:
            return None
        return self.distributed() / paid_in

    def money_weighted_return(
        self, *, terminal_value: Optional[float] = None, as_of: Optional[object] = None,
    ) -> Optional[float]:
        """XIRR of the settled flows, plus an optional terminal NAV as an inflow."""
        entries = [(f.day, f.amount) for f in self.cash]
        if terminal_value is not None:
            if as_of is not None:
                day = _parse_day(as_of)
            elif entries:
                day = max(d for d, _a in entries)
            else:
                return None
            entries.append((day, float(terminal_value)))
        return _xirr_entries(entries)


__all__ = [
    "CashFlow",
    "CashFlowSeries",
    "KIND_DIRECTION",
    "TWO_WAY_KINDS",
    "xirr",
]

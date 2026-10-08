"""Market-data adapter for portfolio valuation.

The portfolio engine NEVER calls a provider directly. It reads prices/FX through
the existing Market Data Gateway, or through caller-injected `marks` (used by the
HTTP front door, which already fetches live quotes, and by tests). Every mark
carries price, timestamp, source and a freshness class — a missing or stale
price is reported, never silently substituted.

Provider independence: this module depends on the gateway interface, not on any
concrete provider. Swapping Yahoo for another source changes nothing here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Optional

from .models import (
    FRESH_MAX_AGE,
    STALE_MAX_AGE,
    VERY_STALE_MAX_AGE,
    DataQualityStatus,
    Freshness,
    Mark,
)
from .money import D


def parse_timestamp(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def classify_freshness(timestamp: Any, now: Optional[datetime] = None) -> Freshness:
    dt = parse_timestamp(timestamp)
    if dt is None:
        return Freshness.MISSING
    now = now or datetime.now(timezone.utc)
    age = (now - dt).total_seconds()
    if age < 0:
        age = 0.0
    if age <= FRESH_MAX_AGE:
        return Freshness.FRESH
    if age <= STALE_MAX_AGE:
        return Freshness.STALE
    if age <= VERY_STALE_MAX_AGE:
        return Freshness.VERY_STALE
    return Freshness.VERY_STALE


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return D(value)
    except ValueError:
        return None


class MarketAdapter:
    """Resolve a Mark and an FX rate, preferring injected marks over the gateway."""

    def __init__(
        self,
        *,
        gateway: Any = None,
        base_currency: str = "USD",
        marks: Optional[dict[str, dict[str, Any]]] = None,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.gateway = gateway
        self.base = (base_currency or "USD").upper()
        self.marks = {k.upper(): v for k, v in (marks or {}).items()}
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._mark_cache: dict[str, Mark] = {}
        self._fx_cache: dict[str, Optional[Decimal]] = {}

    async def mark(self, symbol: str, *, market: Optional[str] = None) -> Mark:
        key = symbol.upper()
        if key in self._mark_cache:
            return self._mark_cache[key]
        mark = await self._resolve_mark(symbol, market)
        self._mark_cache[key] = mark
        return mark

    async def _resolve_mark(self, symbol: str, market: Optional[str]) -> Mark:
        injected = self.marks.get(symbol.upper())
        if injected is not None:
            return self._mark_from_injected(symbol, injected)
        if self.gateway is None:
            return Mark(price=None, symbol=symbol, status=DataQualityStatus.UNAVAILABLE,
                        freshness=Freshness.MISSING,
                        warnings=["no market data source is configured"])
        record = None
        try:
            record = await self.gateway.get_quote(symbol, market, freshness="any")
        except Exception as exc:  # noqa: BLE001 - a fetch failure is a MISSING mark
            return Mark(price=None, symbol=symbol, status=DataQualityStatus.UNAVAILABLE,
                        freshness=Freshness.MISSING, warnings=[f"market fetch failed: {exc}"])
        if record is None or getattr(record, "code", None) is not None:
            reason = getattr(record, "message", None) or "no data"
            return Mark(price=None, symbol=symbol, status=DataQualityStatus.UNAVAILABLE,
                        freshness=Freshness.MISSING, warnings=[f"no quote: {reason}"])
        meta = getattr(record, "meta", None)
        price = _dec(getattr(record, "price", None))
        timestamp = getattr(record, "timestamp", None) or (
            getattr(meta, "event_time", None) if meta else None
        ) or (getattr(meta, "retrieved_at", None) if meta else None)
        currency = (getattr(meta, "currency", None) if meta else None) or self.base
        source = getattr(meta, "provider", None) if meta else None
        fresh = classify_freshness(timestamp, self._now())
        if price is None:
            return Mark(price=None, symbol=symbol, currency=currency, timestamp=timestamp,
                        source=source, freshness=Freshness.MISSING,
                        status=DataQualityStatus.UNAVAILABLE, warnings=["quote carried no price"])
        warnings = [] if fresh in (Freshness.FRESH, Freshness.STALE) else [f"price is {fresh.value}"]
        return Mark(price=price, symbol=symbol, currency=currency, timestamp=timestamp,
                    source=source, freshness=fresh, status=DataQualityStatus.OK, warnings=warnings)

    def _mark_from_injected(self, symbol: str, payload: dict[str, Any]) -> Mark:
        price = _dec(payload.get("price"))
        currency = (payload.get("currency") or self.base).upper()
        timestamp = payload.get("timestamp")
        source = payload.get("source") or "client"
        fresh = payload.get("freshness")
        if fresh:
            try:
                freshness = Freshness(str(fresh).upper())
            except ValueError:
                freshness = classify_freshness(timestamp, self._now())
        else:
            freshness = classify_freshness(timestamp, self._now()) if timestamp else Freshness.FRESH
        if price is None:
            return Mark(price=None, symbol=symbol, currency=currency, timestamp=timestamp,
                        source=source, freshness=Freshness.MISSING,
                        status=DataQualityStatus.UNAVAILABLE, warnings=["no price supplied"])
        warnings = [] if freshness in (Freshness.FRESH, Freshness.STALE) else [f"price is {freshness.value}"]
        return Mark(price=price, symbol=symbol, currency=currency, timestamp=timestamp,
                    source=source, freshness=freshness, status=DataQualityStatus.OK, warnings=warnings)

    async def fx_per_base(self, currency: str) -> Optional[Decimal]:
        """Units of `currency` per ONE unit of the portfolio base currency."""
        cur = (currency or self.base).upper()
        if cur == self.base:
            return Decimal("1")
        if cur in self._fx_cache:
            return self._fx_cache[cur]
        rate = await self._resolve_fx(cur)
        self._fx_cache[cur] = rate
        return rate

    async def _resolve_fx(self, currency: str) -> Optional[Decimal]:
        # Caller may inject an FX rate directly: marks["USD/PKR"] = {rate: ...}.
        for key in (f"{self.base}/{currency}", f"{self.base}{currency}"):
            injected = self.marks.get(key.upper())
            if injected is not None:
                rate = _dec(injected.get("rate") or injected.get("price") or injected.get("mid"))
                if rate is not None and rate > 0:
                    return rate
        if self.gateway is None:
            return None
        try:
            record = await self.gateway.get_fx_rate(base=self.base, quote=currency, freshness="any")
        except Exception:  # noqa: BLE001 - missing FX is reported, never guessed
            return None
        if record is None or getattr(record, "code", None) is not None:
            return None
        rate = _dec(getattr(record, "rate", None)) or _dec(getattr(record, "mid", None))
        if rate is not None and rate > 0:
            return rate
        return None


__all__ = ["MarketAdapter", "classify_freshness", "parse_timestamp"]

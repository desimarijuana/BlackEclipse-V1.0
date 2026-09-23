"""Normalization layer (Milestone 2F).

Providers return different schemas. This module flattens each into the one
`NormalizedFinancialObject` shape while preserving value, unit, currency,
timestamp, period, instrument and provenance.

Nothing is silently converted: any unit/currency transformation is recorded in
`transformations`. A missing field stays None — never a fabricated 0.
"""

from __future__ import annotations

from typing import Any, Optional

from .contract import InstrumentIdentity, NormalizedFinancialObject, SourceReference


def identity_from_payload(payload: dict[str, Any]) -> Optional[InstrumentIdentity]:
    """Extract the canonical instrument identity the bridge attaches.

    The read-only bridge resolves the ticker against the instrument master and
    returns `market`/`currency`/`instrumentId`. When present this identity rides
    on every object so a consumer can prove the payload belongs to the requested
    instrument. Absent metadata yields None — never a fabricated identity.
    """
    symbol = payload.get("symbol")
    market = payload.get("market") or payload.get("country")
    if not symbol or not market:
        return None
    return InstrumentIdentity(
        market=str(market).upper(),
        symbol=str(symbol).upper(),
        currency=payload.get("currency"),
        assetClass=payload.get("assetClass"),
        securityType=payload.get("securityType"),
        name=payload.get("name"),
    )


def _obj(
    name: str,
    value: Any,
    source: SourceReference,
    *,
    unit: Optional[str] = None,
    currency: Optional[str] = None,
    data_timestamp: Optional[str] = None,
    period: Optional[str] = None,
    basis: Optional[str] = None,
    published_at: Optional[str] = None,
    instrument: Optional[str] = None,
    identity: Optional[InstrumentIdentity] = None,
    transformations: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
) -> NormalizedFinancialObject:
    return NormalizedFinancialObject(
        name=name,
        value=value,
        unit=unit,
        currency=currency,
        dataTimestamp=data_timestamp,
        period=period,
        basis=basis,
        publishedAt=published_at,
        instrument=instrument,
        identity=identity,
        source=source,
        transformations=transformations or [],
        warnings=warnings or [],
    )


# ── Quote / snapshot ────────────────────────────────────────────────────────


def normalize_quote(payload: dict[str, Any], source: SourceReference) -> list[NormalizedFinancialObject]:
    """A current/latest quote block.

    Accepts both the bridge shape (`price` nested) and the flat live shape.
    """
    symbol = payload.get("symbol")
    price_block = payload.get("price") if isinstance(payload.get("price"), dict) else payload
    data_ts = payload.get("updatedAt") or payload.get("asOf")
    currency = payload.get("currency")
    identity = identity_from_payload(payload)
    out: list[NormalizedFinancialObject] = []

    def add(name: str, value: Any, unit: Optional[str] = None) -> None:
        if value is None:
            return
        out.append(
            _obj(
                name,
                value,
                source,
                unit=unit,
                currency=currency if name in ("price", "marketCap", "previousClose") else None,
                data_timestamp=data_ts,
                instrument=symbol,
                identity=identity,
            )
        )

    add("price", price_block.get("price"), "currency")
    add("changePct", price_block.get("changePct"), "%")
    add("previousClose", price_block.get("previousClose"), "currency")
    add("open", price_block.get("open"), "currency")
    add("dayHigh", price_block.get("dayHigh"), "currency")
    add("dayLow", price_block.get("dayLow"), "currency")
    add("volume", price_block.get("volume"), "shares")
    add("marketCap", price_block.get("marketCap"), "currency")
    add("peRatio", price_block.get("peRatio"), "ratio")
    add("source", payload.get("priceSource") or payload.get("provider"), None)
    return out


def normalize_snapshot(payload: dict[str, Any], source: SourceReference) -> list[NormalizedFinancialObject]:
    """Company profile / universe metadata."""
    symbol = payload.get("symbol")
    updated = payload.get("updatedAt")
    identity = identity_from_payload(payload)
    fields = {
        "name": payload.get("name"),
        "sector": payload.get("sector"),
        "industry": payload.get("industry"),
        "securityType": payload.get("securityType"),
        "assetClass": payload.get("assetClass"),
        "exchange": payload.get("exchange"),
        "country": payload.get("country"),
        "currency": payload.get("currency"),
        "description": payload.get("description"),
        "employees": payload.get("employees"),
        "website": payload.get("website"),
    }
    return [
        _obj(key, value, source, data_timestamp=updated, instrument=symbol, identity=identity)
        for key, value in fields.items()
        if value is not None
    ]


def normalize_history(payload: dict[str, Any], source: SourceReference) -> list[NormalizedFinancialObject]:
    """OHLCV series. One object per bar, with a per-bar date + period."""
    symbol = payload.get("symbol")
    currency = payload.get("currency")
    series = payload.get("series") or payload.get("history") or payload.get("rows") or []
    interval = payload.get("interval")
    out: list[NormalizedFinancialObject] = []
    if not isinstance(series, list):
        return out
    for bar in series:
        if not isinstance(bar, dict):
            continue
        date = bar.get("date") or bar.get("timestamp")
        for field in ("open", "high", "low", "close", "volume"):
            value = bar.get(field)
            if value is None:
                continue
            out.append(
                _obj(
                    field,
                    value,
                    source,
                    unit="shares" if field == "volume" else "currency",
                    currency=currency if field != "volume" else None,
                    data_timestamp=str(date) if date else None,
                    period=interval,
                    instrument=symbol,
                )
            )
    return out


def normalize_fundamentals(payload: dict[str, Any], source: SourceReference) -> list[NormalizedFinancialObject]:
    """Financial statements: one object per (period, metric) pair.

    Understands the Eclipse `FundamentalsSnapshot` shape (`periods[]`) and a
    flat `statements[]` shape.
    """
    symbol = payload.get("symbol")
    currency = payload.get("currency")
    out: list[NormalizedFinancialObject] = []
    periods = payload.get("periods") or payload.get("statements") or []  # noqa: F841
    if not isinstance(periods, list):
        return out
    for period in periods:
        if not isinstance(period, dict):
            continue
        end = period.get("endDate") or period.get("date")
        label = period.get("fiscalYear") or period.get("period") or end
        # Phase 4: a statement row may carry its consolidation basis and the
        # date it became public (`filed`/`publishedAt`). Both stay None when the
        # source is silent — never inferred from the fiscal period.
        basis = period.get("basis") or period.get("consolidation")
        published = period.get("filed") or period.get("publishedAt")
        for key, value in period.items():
            if key in ("endDate", "date", "fiscalYear", "period", "form", "filed",
                       "publishedAt", "basis", "consolidation"):
                continue
            if value is None or isinstance(value, (dict, list)):
                continue
            unit = "%" if (isinstance(value, (int, float)) and "margin" in key.lower()) else None
            out.append(
                _obj(
                    key,
                    value,
                    source,
                    unit=unit,
                    currency=currency if unit is None else None,
                    data_timestamp=str(end) if end else None,
                    period=str(label) if label else None,
                    basis=str(basis) if basis else None,
                    published_at=str(published) if published else None,
                    instrument=symbol,
                )
            )
    return out


def normalize_macro(payload: dict[str, Any], source: SourceReference) -> list[NormalizedFinancialObject]:
    """A macro/economic series: one object per observation.

    Carries the series identity (as an InstrumentIdentity) plus the series' unit
    and currency, so a rate/level is never a bare number (#3).
    """
    rows = payload.get("rows") or payload.get("series") or payload.get("points") or []
    series_key = payload.get("seriesKey") or payload.get("series") or payload.get("indicator")
    source_name = payload.get("source") or "macro"
    unit = payload.get("units") or payload.get("unit")
    currency = payload.get("currency")
    series_identity = payload.get("seriesIdentity") or {}
    identity = None
    if series_key:
        identity = InstrumentIdentity(
            market=str(series_identity.get("geography") or "GLOBAL"),
            symbol=str(series_key),
            currency=currency,
            assetClass="macro",
            securityType=str(series_identity.get("measure") or "macro_series"),
            name=str(series_key),
        )
    out: list[NormalizedFinancialObject] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        date = row.get("date") or row.get("timestamp")
        value = row.get("value")
        if value is None:
            continue
        out.append(
            _obj(
                str(series_key or "value"),
                value,
                source,
                unit=str(unit) if unit else None,
                currency=currency,
                data_timestamp=str(date) if date else None,
                period=str(date) if date else None,
                instrument=str(series_key) if series_key else None,
                identity=identity,
                transformations=[f"macro source={source_name}"],
            )
        )
    return out


__all__ = [
    "normalize_quote",
    "normalize_snapshot",
    "normalize_history",
    "normalize_fundamentals",
    "normalize_macro",
]

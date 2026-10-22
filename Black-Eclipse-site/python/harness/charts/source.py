"""A chart that NAMES a series instead of carrying it.

The engine can fetch a market series itself: the same market gateway every
price comes from, with the same routing, the same quality checks and the same
provenance. A chart that names its source therefore draws the same numbers a
quote would - and the model never has to type 250 of them into a message,
where a long message gets truncated and the chart is lost.
"""

from __future__ import annotations

from typing import Any, Optional

from .scene import ChartDataSource, ChartMark
from .spec import ChartSpec

#: The value each field takes from a bar.
_FIELDS = ("open", "high", "low", "close", "volume")


class ChartSourceError(Exception):
    """A named source could not be fetched. The chart is refused, not guessed."""

    def __init__(self, message: str, *, code: str = "CHART_SOURCE_UNAVAILABLE") -> None:
        super().__init__(message)
        self.code = code
        self.reason = message


def gateway_for(ctx: Any) -> Any:
    """The run's market-data gateway (built from the context's bridge if needed)."""
    gateway = getattr(ctx, "market_gateway", None)
    if gateway is not None:
        return gateway
    from ..market.gateway import MarketDataGateway  # noqa: PLC0415

    gateway = MarketDataGateway(getattr(ctx, "data_bridge", None))
    try:
        ctx.market_gateway = gateway  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - the context may be frozen in tests
        pass
    return gateway


async def fetch_series(gateway: Any, source: ChartDataSource) -> list[float]:
    """The values of the named series, oldest first."""
    result = await gateway.get_historical_prices(
        source.symbol,
        source.market,
        start=source.start,
        end=source.end,
        interval=source.interval or "1d",
    )
    # A market failure is a `MarketError` (a structured refusal, not an
    # exception) - it must not be mistaken for an empty series.
    if getattr(result, "code", None) is not None and hasattr(result, "message"):
        raise ChartSourceError(
            f"the chart's source ({source.symbol}) could not be fetched: "
            f"{getattr(result, 'message', result)}",
            code=str(getattr(result, "code", "CHART_SOURCE_UNAVAILABLE")),
        )
    if isinstance(result, Exception):
        raise ChartSourceError(
            f"the chart's source ({source.symbol}) could not be fetched: {result}",
        )
    bars = list(getattr(result, "bars", None) or [])
    if not bars:
        raise ChartSourceError(
            f"the chart's source ({source.symbol}) returned no bars"
        )
    field = source.field if source.field in _FIELDS else "close"
    values: list[float] = []
    for bar in bars:
        value = getattr(bar, field, None)
        if value is None:
            continue
        values.append(float(value))
    if not values:
        raise ChartSourceError(
            f"the chart's source ({source.symbol}) returned no {field} values"
        )
    return values


async def resolve_data_sources(spec: ChartSpec, ctx: Any) -> ChartSpec:
    """Fill every mark that names a source with the series it names.

    A mark that carries its own values is left exactly as it is: a named
    source is a convenience, never an override.
    """
    marks: list[ChartMark] = [
        mark for panel in (spec.panels or []) for mark in (panel.marks or [])
    ]
    sourced = [m for m in marks if getattr(m, "data_source", None) is not None]
    if not sourced:
        return spec
    gateway = gateway_for(ctx)
    for mark in sourced:
        source = mark.data_source
        assert source is not None  # noqa: S101 - the list comprehension proved it
        values = await fetch_series(gateway, source)
        # The x axis is the session index (1..n): a regression against a
        # trading-day index is what a reader means by "the trend over the
        # period", and the dates stay in the provenance.
        mark.x = list(range(1, len(values) + 1))
        mark.y = values
        if source.name and not mark.name:
            mark.name = source.name
    return spec

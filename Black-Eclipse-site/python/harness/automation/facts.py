"""Fact providers for condition triggers (§7.5).

A condition trigger (`BTC.price < 90000`) needs a deterministic source of facts.
Facts are supplied by a `FactProvider`; the engine never invents a value. When a
provider cannot resolve a variable, the value is absent and the condition
evaluates UNAVAILABLE — it does NOT fire on fabricated data.

`MarketFactProvider` resolves `<SYMBOL>.<field>` paths through the ONE Market
Data Gateway (the read-only provider path), so a market condition is grounded in
real market data. Any failure yields no facts (honest UNAVAILABLE).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Protocol

# Market fields a condition may reference.
_MARKET_FIELDS = frozenset({
    "price", "change", "change_pct", "changePct", "volume", "average_volume",
    "averageVolume", "day_high", "dayHigh", "day_low", "dayLow", "open",
    "previous_close", "previousClose", "market_cap", "marketCap",
})


class FactProvider(Protocol):
    """Resolve the variables a condition references to current values."""

    async def snapshot(self, variables: Iterable[str]) -> dict[str, Any]:
        ...


class StaticFactProvider:
    """A provider backed by an explicit mapping (tests + injected facts)."""

    def __init__(self, values: dict[str, Any]) -> None:
        self._values = dict(values)

    def set(self, path: str, value: Any) -> None:
        self._values[path] = value

    async def snapshot(self, variables: Iterable[str]) -> dict[str, Any]:
        return {v: self._values[v] for v in variables if v in self._values}


def _extract(quote: Any, field: str) -> Any:
    """Read a field from a quote that may be a dict or an object."""
    candidates = {field, field.replace("_", ""), _snake(field)}
    if isinstance(quote, dict):
        for key in candidates:
            if key in quote:
                return quote[key]
        return None
    for key in candidates:
        if hasattr(quote, key):
            return getattr(quote, key)
    return None


def _snake(text: str) -> str:
    out = []
    for index, ch in enumerate(text):
        if ch.isupper() and index > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


class MarketFactProvider:
    """Resolves market variables through the ONE Market Data Gateway."""

    def __init__(self, service: Any) -> None:
        self._service = service

    async def snapshot(self, variables: Iterable[str]) -> dict[str, Any]:
        gateway = getattr(self._service, "market_gateway", None)
        if gateway is None:
            return {}
        # Bind the server bridge so the gateway can reach providers (the same
        # read-only path a server-initiated run uses).
        try:
            if getattr(gateway, "_bridge", None) is None:
                bridge_factory = getattr(self._service, "server_bridge", None)
                if bridge_factory is not None:
                    gateway._bridge = bridge_factory()  # noqa: SLF001 - deliberate rebind
        except Exception:  # noqa: BLE001 - a missing bridge yields no facts
            return {}

        paths = list(variables)
        symbols: dict[str, list[str]] = {}
        for path in paths:
            head, _, tail = path.partition(".")
            if head and tail:
                symbols.setdefault(head.upper(), []).append(path)

        facts: dict[str, Any] = {}
        for symbol, symbol_paths in symbols.items():
            try:
                quote = await gateway.get_quote(symbol)
            except Exception:  # noqa: BLE001 - a provider failure is no fact, not a crash
                continue
            if quote is None:
                continue
            for path in symbol_paths:
                field = path.partition(".")[2]
                if field in _MARKET_FIELDS or field.replace("_", "") in {
                    f.replace("_", "") for f in _MARKET_FIELDS
                }:
                    value = _extract(quote, field)
                    if value is not None:
                        facts[path] = value
        return facts


def default_fact_provider(service: Any) -> FactProvider:
    return MarketFactProvider(service)


__all__ = [
    "FactProvider",
    "MarketFactProvider",
    "StaticFactProvider",
    "default_fact_provider",
]

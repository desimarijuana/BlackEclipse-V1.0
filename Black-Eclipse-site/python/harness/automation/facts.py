"""Fact providers for condition triggers (§7.5).

A condition trigger (`BTC.price < 90000`) needs a deterministic source of facts.
Facts are supplied by a `FactProvider`; the engine never invents a value. When a
provider cannot resolve a variable, the value is absent and the condition
evaluates UNAVAILABLE — it does NOT fire on fabricated data.

Three providers run behind a `CompositeFactProvider` (the engine's default):

  * `MarketFactProvider` — `<SYMBOL>.<field>` through the ONE Market Data Gateway,
    so a market condition is grounded in real market data.
  * `PortfolioFactProvider` — `pf.<portfolioId>.<field>` through the ONE portfolio
    engine, so a portfolio condition (`weight`, `cash_pct`, `concentration`…) is
    grounded in the user's own ledger.

Any failure yields no facts (honest UNAVAILABLE).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Protocol

# Market fields a condition may reference.
_MARKET_FIELDS = frozenset({
    "price", "change", "change_pct", "changePct", "volume", "average_volume",
    "averageVolume", "day_high", "dayHigh", "day_low", "dayLow", "open",
    "previous_close", "previousClose", "market_cap", "marketCap",
})

# Portfolio fields a `pf.<id>.<field>[.<SYM>]` condition may reference.
_PORTFOLIO_FIELDS = frozenset({
    "total_value", "totalValue", "cash_pct", "cashPct", "position_count",
    "positionCount", "concentration_hhi", "concentrationHhi", "weight", "unrealized",
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


class PortfolioFactProvider:
    """Resolves `pf.<portfolioId>.<field>` variables through the portfolio engine.

    Reads the portfolio's live positions/valuation (the SAME `PortfolioService.read`
    the `portfolio_*` tools and the UI use) and derives the fact. A missing
    portfolio, a failed read, an unpriced position or an unknown field yields NO
    fact — the condition then evaluates UNAVAILABLE, never a fabricated number.
    """

    def __init__(self, service: Any) -> None:
        self._service = service

    async def snapshot(self, variables: Iterable[str]) -> dict[str, Any]:
        portfolio = getattr(self._service, "portfolio", None)
        if portfolio is None:
            return {}
        by_portfolio: dict[str, list[str]] = {}
        for path in variables:
            parts = str(path).split(".")
            if len(parts) >= 3 and parts[0] == "pf" and parts[1]:
                by_portfolio.setdefault(parts[1], []).append(str(path))
        facts: dict[str, Any] = {}
        for portfolio_id, paths in by_portfolio.items():
            try:
                reading = await portfolio.read(
                    portfolio_id, include=["positions", "cash"],
                    gateway=getattr(self._service, "market_gateway", None),
                )
            except Exception:  # noqa: BLE001 - a failed read is no fact, not a crash
                continue
            facts.update(_portfolio_facts(reading, paths))
        return facts


def _portfolio_facts(reading: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    positions = list(reading.get("positions") or [])
    valuation = reading.get("valuation") or {}
    total = _float_or_none(valuation.get("totalValue"))
    cash = _float_or_none((reading.get("cash") or {}).get("balance"))
    by_symbol = {str(p.get("symbol", "")).upper(): p for p in positions}
    weights = [float(p["weight"]) / 100.0 for p in positions
               if isinstance(p.get("weight"), (int, float))]
    hhi = sum(w * w for w in weights)

    facts: dict[str, Any] = {}
    for path in paths:
        parts = path.split(".")
        field = parts[2] if len(parts) > 2 else ""
        symbol = parts[3].upper() if len(parts) > 3 else None
        value = _resolve_portfolio_field(field, symbol, positions, by_symbol, total, cash, hhi)
        if value is not None:
            facts[path] = value
    return facts


def _resolve_portfolio_field(
    field: str, symbol: Optional[str], positions: list[dict[str, Any]],
    by_symbol: dict[str, dict[str, Any]], total: Optional[float], cash: Optional[float],
    hhi: float,
) -> Any:
    lowered = field.lower()
    if lowered in ("total_value", "totalvalue"):
        return total
    if lowered in ("cash_pct", "cashpct"):
        if total and cash is not None and total > 0:
            return cash / total
        return None
    if lowered in ("position_count", "positioncount"):
        return len(positions)
    if lowered in ("concentration_hhi", "concentrationhhi"):
        return hhi
    if lowered == "weight" and symbol:
        position = by_symbol.get(symbol)
        weight = position.get("weight") if position else None
        return float(weight) / 100.0 if isinstance(weight, (int, float)) else None
    if lowered == "unrealized" and symbol:
        position = by_symbol.get(symbol)
        return _float_or_none(position.get("unrealizedPnlBase")) if position else None
    return None


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class CompositeFactProvider:
    """Merges several providers; the first to resolve a variable wins.

    A provider that cannot resolve a variable contributes nothing — the engine
    then sees the variable as missing (UNAVAILABLE). A provider that raises is
    skipped, never allowed to break the tick.
    """

    def __init__(self, providers: Iterable[FactProvider]) -> None:
        self._providers = list(providers)

    async def snapshot(self, variables: Iterable[str]) -> dict[str, Any]:
        remaining = set(variables)
        facts: dict[str, Any] = {}
        for provider in self._providers:
            if not remaining:
                break
            try:
                resolved = await provider.snapshot(remaining)
            except Exception:  # noqa: BLE001 - one provider failing is not fatal
                continue
            for key, value in (resolved or {}).items():
                if key in remaining and value is not None:
                    facts[key] = value
                    remaining.discard(key)
        return facts


def default_fact_provider(service: Any) -> FactProvider:
    return CompositeFactProvider([
        MarketFactProvider(service),
        PortfolioFactProvider(service),
        LedgerFactProvider(service),
    ])


class LedgerFactProvider:
    """Resolves `ledger.<ledgerId>.<field>` variables through the ledger engine.

    Fields: `suspense` (absolute suspense balance), `blockers` / `warnings` (the
    current period's close findings), `ready` (1 when the period has no blocker),
    `open_ar` / `open_ap` (open-item totals) and `entries`. Every value comes from
    the same service the tools and the UI read; a missing ledger, a failed read or
    an unknown field yields NO fact, so the condition evaluates UNAVAILABLE rather
    than firing on a fabricated number.
    """

    _FIELDS = frozenset({"suspense", "blockers", "warnings", "ready",
                         "open_ar", "open_ap", "entries"})  # documented field set

    def __init__(self, service: Any) -> None:
        self._service = service

    async def snapshot(self, variables: Iterable[str]) -> dict[str, Any]:
        ledger = getattr(self._service, "ledger", None)
        if ledger is None:
            return {}
        by_ledger: dict[str, list[str]] = {}
        for path in variables:
            parts = str(path).split(".")
            if len(parts) >= 3 and parts[0] == "ledger" and parts[1]:
                by_ledger.setdefault(parts[1], []).append(str(path))
        facts: dict[str, Any] = {}
        for ledger_id, paths in by_ledger.items():
            try:
                resolved = self._facts_for(ledger, ledger_id)
            except Exception:  # noqa: BLE001 - a failed read is no fact, not a crash
                continue
            for path in paths:
                field = path.split(".")[2]
                if field in resolved:
                    facts[path] = resolved[field]
        return facts

    def _facts_for(self, service: Any, ledger_id: str) -> dict[str, Any]:
        from datetime import date  # noqa: PLC0415

        from ..ledger import statements as ledger_statements  # noqa: PLC0415

        record = service.store.get_ledger(ledger_id)
        if record is None:
            return {}
        today = date.today().isoformat()
        accounts = service.store.list_accounts(ledger_id)
        balances = ledger_statements.build_balances(
            accounts, (), service.store.postings(ledger_id, end=today)
        )
        facts: dict[str, Any] = {}
        suspense = sum((entry.net for entry in balances.values()
                        if entry.account.subtype == "SUSPENSE"), 0)
        facts["suspense"] = float(abs(suspense))
        facts["entries"] = float(service.store.count_entries(ledger_id, end=today))
        try:
            from ..ledger import close as ledger_close  # noqa: PLC0415
            from ..ledger.periods import fiscal_position, period_bounds  # noqa: PLC0415

            fiscal_year, period_no = fiscal_position(record.fiscal_year_start_month,
                                                     date.fromisoformat(today))
            start, end = period_bounds(record.fiscal_year_start_month,
                                       fiscal_year, period_no)
            report = ledger_close.evaluate(service, ledger_id,
                                           start=start.isoformat(), end=end.isoformat())
            facts["blockers"] = float(report["blockerCount"])
            facts["warnings"] = float(report["warningCount"])
            facts["ready"] = 1.0 if report["status"] == "READY" else 0.0
        except Exception:  # noqa: BLE001 - the close fields are simply absent
            pass
        try:
            from ..ledger.documents import aging  # noqa: PLC0415

            for field, kind in (("open_ar", "AR"), ("open_ap", "AP")):
                report = aging(service, ledger_id, kind=kind, as_of=today)
                facts[field] = float(report["openTotal"])
        except Exception:  # noqa: BLE001 - open items are simply absent
            pass
        return facts


__all__ = [
    "CompositeFactProvider",
    "FactProvider",
    "LedgerFactProvider",
    "MarketFactProvider",
    "PortfolioFactProvider",
    "StaticFactProvider",
    "default_fact_provider",
]

"""Declarative provider capability descriptors (Python side).

The runnable adapters live on the TS bridge (one HTTP transport). This module
records what each provider CAN do — capabilities, asset classes, streaming,
credential reference, rate-limit shape, cost tier — so the router can select and
explain without calling the provider.

A descriptor is only `implemented=True` when the TS adapter router actually has
an adapter for it. A catalogued credential with no adapter is recorded honestly
with `implemented=False`; nothing here is a fake adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Capability vocabulary the market layer routes on.
CAPABILITIES: tuple[str, ...] = (
    "quote", "historical", "ohlcv", "volume", "orderbook", "trades",
    "market_cap", "supply", "funding", "open_interest", "options", "fx", "bonds",
)


@dataclass(frozen=True)
class RateLimit:
    requests_per_minute: Optional[int] = None
    requests_per_day: Optional[int] = None
    concurrency: int = 4
    cost_tier: str = "unknown"  # free | freemium | paid | unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "requestsPerMinute": self.requests_per_minute,
            "requestsPerDay": self.requests_per_day,
            "concurrency": self.concurrency,
            "costTier": self.cost_tier,
        }


@dataclass
class ProviderDescriptor:
    id: str
    label: str
    capabilities: tuple[str, ...]
    asset_types: tuple[str, ...] = ()
    realtime: bool = False
    historical: bool = False
    streaming: bool = False
    credential_ref: Optional[str] = None
    configured: Optional[bool] = None  # None = keyless / not applicable
    rate_limit: RateLimit = field(default_factory=RateLimit)
    implemented: bool = True
    notes: Optional[str] = None

    def supports(self, capability: str, asset_type: Optional[str] = None) -> bool:
        if capability not in self.capabilities:
            return False
        if asset_type and self.asset_types and asset_type not in self.asset_types:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "capabilities": list(self.capabilities),
            "assetTypes": list(self.asset_types),
            "realtime": self.realtime,
            "historical": self.historical,
            "streaming": self.streaming,
            "credentialRef": self.credential_ref,
            "configured": self.configured,
            "implemented": self.implemented,
            "rateLimit": self.rate_limit.to_dict(),
        }
        if self.notes:
            out["notes"] = self.notes
        return out


# The provider set. Ordering here is only the *declaration* order; the router
# applies configuration priority on top.
def default_providers() -> list[ProviderDescriptor]:
    return [
        ProviderDescriptor(
            id="yahoo",
            label="Yahoo Finance (keyless yfinance/scraper chain)",
            capabilities=("quote", "historical", "ohlcv", "volume", "market_cap",
                          "options", "fx"),
            asset_types=("equity", "etf", "fund", "index", "commodity", "fx", "crypto", "option"),
            realtime=True, historical=True, streaming=False,
            rate_limit=RateLimit(concurrency=4, cost_tier="free"),
            notes="Keyless; multi-market equities + FX + options (delayed). Subject to upstream terms.",
        ),
        ProviderDescriptor(
            id="binance",
            label="Binance public market data",
            capabilities=("quote", "ohlcv", "historical", "orderbook", "trades",
                          "funding", "open_interest"),
            asset_types=("crypto",),
            realtime=True, historical=True, streaming=True,
            rate_limit=RateLimit(requests_per_minute=1200, concurrency=4, cost_tier="free"),
            notes="Keyless public REST + WebSocket for crypto spot/futures.",
        ),
        ProviderDescriptor(
            id="coingecko",
            label="CoinGecko",
            capabilities=("quote", "market_cap", "supply"),
            asset_types=("crypto",),
            realtime=True, historical=False, streaming=False,
            credential_ref="COINGECKO_API_KEY",
            rate_limit=RateLimit(concurrency=2, cost_tier="freemium"),
            notes="Keyless public tier works; a key raises limits. Used for supply/FDV.",
        ),
        ProviderDescriptor(
            id="stooq",
            label="Stooq (keyless EOD history fallback)",
            capabilities=("historical", "ohlcv", "quote"),
            asset_types=("equity", "etf", "index", "fx", "commodity"),
            realtime=False, historical=True, streaming=False,
            rate_limit=RateLimit(concurrency=2, cost_tier="free"),
            notes="Keyless daily bars; used as a history fallback when Yahoo is unavailable.",
        ),
        ProviderDescriptor(
            id="treasury",
            label="US Treasury / FRED (keyless)",
            capabilities=("bonds",),
            asset_types=("bond", "macro"),
            realtime=False, historical=True, streaming=False,
            credential_ref="FRED_API_KEY",
            rate_limit=RateLimit(concurrency=2, cost_tier="free"),
            notes="Treasury yield curve + government bond data; FRED public CSV is keyless.",
        ),
        ProviderDescriptor(
            id="fx",
            label="European Central Bank FX reference",
            capabilities=("fx",),
            asset_types=("fx",),
            realtime=False, historical=True, streaming=False,
            rate_limit=RateLimit(concurrency=2, cost_tier="free"),
            notes="Keyless daily reference rates; a cross fallback for FX.",
        ),
        # Keyed providers — runnable when their credential is configured. If the
        # key is absent the adapter reports AUTHENTICATION_FAILED (honest), never
        # fake data, and the gateway falls through to the next provider.
        ProviderDescriptor(
            id="polygon", label="Polygon.io",
            capabilities=("quote", "historical", "ohlcv", "orderbook", "trades", "options"),
            asset_types=("equity", "etf", "fund", "index"),
            realtime=True, historical=True, streaming=True,
            credential_ref="POLYGON_API_KEY",
            rate_limit=RateLimit(concurrency=4, cost_tier="paid"),
            notes="Keyed US equities: aggregates, snapshot/NBBO (top-of-book), trades.",
        ),
        ProviderDescriptor(
            id="finnhub", label="Finnhub",
            capabilities=("quote", "historical", "ohlcv", "trades", "options"),
            asset_types=("equity", "etf", "fund", "index"),
            realtime=True, historical=True, streaming=True,
            credential_ref="FINNHUB_API_KEY",
            rate_limit=RateLimit(requests_per_minute=60, concurrency=2, cost_tier="freemium"),
            notes="Keyed equities + real-time trades over WebSocket.",
        ),
    ]


__all__ = ["CAPABILITIES", "ProviderDescriptor", "RateLimit", "default_providers"]

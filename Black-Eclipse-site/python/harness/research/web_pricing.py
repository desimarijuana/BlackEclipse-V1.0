"""Provider cost estimation for research retrieval.

The engine tracks queries, fetches, bytes and time; this module adds an HONEST
dollar estimate. It never invents a price: a provider with no configured rate is
`UNKNOWN` (None), not 0. The keyless connectors/providers are genuinely free (0.0).
An operator sets real list prices via env (`HARNESS_WEB_PRICE_<PROVIDER>`) so the
receipt can show an estimated spend and the budget can be enforced.

This mirrors `model_runtime/usage.py`'s pricing registry: FREE / UNKNOWN / priced.
Nothing here fabricates a billed amount — it is an ESTIMATE the operator opts into.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# Providers that are genuinely free to call (keyless connectors + keyless search
# HTML). Their cost is exactly 0.0 — it is known, not unknown.
FREE_PROVIDERS: frozenset[str] = frozenset(
    {
        "duckduckgo-html",
        "duckduckgo-lite",
        "mojeek",
        "bing-html",
        "openalex",
        "crossref",
        "gdelt",
        "openverse",
        "wikimedia-commons",
        "searxng",
    }
)

# Known PAID providers whose per-call price the operator may configure. The value
# is read from the environment so no price is hard-coded as a "fact"; absent ⇒
# UNKNOWN.
PAID_PROVIDERS: frozenset[str] = frozenset(
    {"tavily", "brave", "exa", "serper", "serpapi", "bing", "google-cse"}
)

_UNKNOWN = None


@dataclass
class ProviderPrice:
    provider: str
    # USD per successful query (search) / per fetch, when known.
    per_query: Optional[float] = None
    per_fetch: Optional[float] = None
    known: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "perQuery": self.per_query,
            "perFetch": self.per_fetch,
            "known": self.known,
            "note": self.note,
        }


def _env_price(provider: str, kind: str) -> Optional[float]:
    key = f"HARNESS_WEB_PRICE_{provider.upper().replace('-', '_')}_{kind.upper()}"
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
        return value if value >= 0 else None
    except ValueError:
        return None


def price_for(provider: str, *, kind: str = "query") -> ProviderPrice:
    """The configured price for a provider, or an UNKNOWN price. Never invents one."""
    key = (provider or "").strip().lower()
    if key in FREE_PROVIDERS:
        return ProviderPrice(provider=key, per_query=0.0, per_fetch=0.0, known=True, note="keyless/free")
    per_query = _env_price(key, "query")
    per_fetch = _env_price(key, "fetch")
    if per_query is None and per_fetch is None:
        return ProviderPrice(provider=key, known=False, note="price not configured (set HARNESS_WEB_PRICE_* to enable cost estimates)")
    return ProviderPrice(provider=key, per_query=per_query, per_fetch=per_fetch, known=True)


@dataclass
class CostLedger:
    """Accumulates an ESTIMATED spend across providers. `unknown` means at least
    one used provider had no configured price, so the total is a FLOOR, not exact."""

    total: float = 0.0
    currency: str = "USD"
    by_provider: dict[str, float] = None  # type: ignore[assignment]
    unknown_providers: set[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.by_provider is None:
            self.by_provider = {}
        if self.unknown_providers is None:
            self.unknown_providers = set()

    def record(self, provider: str, *, kind: str = "query", count: int = 1) -> None:
        price = price_for(provider, kind=kind)
        if not price.known:
            self.unknown_providers.add(price.provider)
            return
        rate = price.per_query if kind == "query" else price.per_fetch
        if rate is None:
            self.unknown_providers.add(price.provider)
            return
        amount = rate * max(0, count)
        self.total += amount
        self.by_provider[price.provider] = round(self.by_provider.get(price.provider, 0.0) + amount, 6)

    @property
    def exact(self) -> bool:
        return not self.unknown_providers

    def snapshot(self) -> dict:
        return {
            "estimatedCost": round(self.total, 6),
            # A total is exact only when EVERY used provider was priced; otherwise
            # it is a lower bound and we say so.
            "exact": self.exact,
            "currency": self.currency,
            "byProvider": {k: round(v, 6) for k, v in self.by_provider.items()},
            "unknownProviders": sorted(self.unknown_providers),
        }


__all__ = ["ProviderPrice", "CostLedger", "price_for", "FREE_PROVIDERS", "PAID_PROVIDERS"]

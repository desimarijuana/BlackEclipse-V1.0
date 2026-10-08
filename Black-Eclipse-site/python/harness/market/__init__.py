"""Market Data Layer — first-class, provider-agnostic market data for Eclipse.

The agent-facing tools (`market/tools.py`) call the `MarketDataGateway`, which
resolves the instrument, routes to a provider via the `ProviderRouter`, fetches
through the read-only TS bridge (one HTTP transport), normalizes into canonical
records, validates data quality, and preserves provenance into the Evidence &
Research Engine. Real-time streaming is a separate WebSocket architecture
(`streaming.py`), not REST polling.

Modules:
    models.py      canonical records (Quote, OHLCV, OrderBook, …)
    errors.py      the closed structured-error vocabulary
    config.py      env-driven configuration with safe defaults
    instruments.py canonical identity + provider symbol mapping
    providers.py   declarative provider capability descriptors
    router.py      capability-aware selection + circuit breaking
    gateway.py     the one market-data entry point
    quality.py     the mandatory data-quality engine
    cache.py       freshness-aware cache
    provenance.py  Evidence Engine bridge + point-in-time
    streaming.py   real-time connection manager + event bus
    analytics.py   derived analytics above normalized data
    store.py       persistence on the one agent-memory connection
    tools.py       the fourteen agent tools
"""

from .config import MarketConfig, get_config, reset_config
from .errors import MarketError
from .gateway import MarketDataGateway
from .models import (
    BondData,
    FXRate,
    FundingRate,
    HistoricalPriceSeries,
    MarketCap,
    MarketDataEvent,
    MarketMeta,
    OpenInterest,
    OptionsChain,
    OrderBook,
    Quote,
    Supply,
    TradeTape,
    VolumeStats,
)
from .router import ProviderRouter, default_router, reset_router
from .store import MarketStore
from .tools import register_market_tools

__all__ = [
    "BondData",
    "FXRate",
    "FundingRate",
    "HistoricalPriceSeries",
    "MarketCap",
    "MarketConfig",
    "MarketDataEvent",
    "MarketDataGateway",
    "MarketError",
    "MarketMeta",
    "MarketStore",
    "OpenInterest",
    "OptionsChain",
    "OrderBook",
    "ProviderRouter",
    "Quote",
    "Supply",
    "TradeTape",
    "VolumeStats",
    "default_router",
    "get_config",
    "register_market_tools",
    "reset_config",
    "reset_router",
]

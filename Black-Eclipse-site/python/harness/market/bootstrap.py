"""Market Data Layer boot wiring.

Constructs and registers the market subsystem on the ONE service, so
`service.py` stays under its size ratchet. Imported and called once from
`AgenticService.__init__`. Every step is best-effort: a failure leaves the market
capability unavailable rather than blocking boot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger("harness.market")


@dataclass
class MarketBundle:
    """The market subsystem handed to a run: gateway + store + stream."""

    gateway: Any
    store: Optional[Any] = None
    stream: Optional[Any] = None


def install_market_layer(service: Any) -> None:
    """Build the market store/router/cache/gateway/stream and register tools.

    Reuses the ONE read-only bridge (bound per run) and the ONE agent-memory
    connection (MarketStore). Adds no second provider, HTTP client or database.
    """
    try:
        from .cache import MarketCache
        from .gateway import MarketDataGateway
        from .history_cache import HistoryCache
        from .series_store import SeriesStore, set_series_store
        from .research_tools import register_research_data_tools
        from .router import default_router
        from .store import MarketStore
        from .tools import register_market_tools

        service.market_store = MarketStore(service.store)
        # The durable half of the cache: the bars the runtime has already paid
        # for, kept on the ONE agent-memory connection so a later run is served
        # from them instead of re-fetching every bar.
        try:
            service.market_series_store = SeriesStore(service.store)
            set_series_store(service.market_series_store)
            service.market_history_cache = HistoryCache(service.market_series_store)
        except Exception:  # noqa: BLE001 - the durable cache is best-effort
            service.market_series_store = None
            service.market_history_cache = None
        service.market_router = default_router()
        service.market_cache = MarketCache()
        # Built without a bridge; bound to the per-run bridge at run time (service.run).
        service.market_gateway = MarketDataGateway(
            None, cache=service.market_cache, router=service.market_router
        )
        # The gateway carries the durable cache, so every consumer of the market
        # layer - the quant engine, the graph nodes, the trade-log analysis -
        # reads the SAME local history.
        if getattr(service, "market_history_cache", None) is not None:
            try:
                service.market_gateway.history_cache = service.market_history_cache
            except Exception:  # noqa: BLE001 - the attribute is best-effort
                pass
        try:
            from .streaming import default_stream_manager

            service.market_stream = default_stream_manager()
        except Exception:  # noqa: BLE001 - streaming is optional
            service.market_stream = None
        register_market_tools(service.registry)
        # The shared quantitative-research tool surface (verification, transforms,
        # versioned datasets) — routed through the same gateway + services.
        register_research_data_tools(service.registry)
    except Exception:  # noqa: BLE001 - market data must never block boot
        service.market_store = None
        service.market_gateway = None
        service.market_series_store = None
        service.market_history_cache = None
        service.market_stream = None
        log.warning("market data layer unavailable", exc_info=True)


__all__ = ["MarketBundle", "install_market_layer"]

"""Portfolio Accounting Engine boot wiring.

Constructs the ONE portfolio service/store and registers its tools on the SAME
registry, reusing the ONE agent-memory connection and the per-run Market Data
Gateway. Imported and called once from `AgenticService.__init__` (mirroring the
market layer) so `service.py` stays under its size ratchet. Best-effort: a
failure leaves the portfolio capability unavailable rather than blocking boot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger("harness.portfolio")


@dataclass
class PortfolioBundle:
    service: Any
    store: Optional[Any] = None


def install_portfolio_layer(service: Any) -> None:
    try:
        from .service import PortfolioService
        from .store import PortfolioStore
        from .tools import register_portfolio_tools

        store = PortfolioStore(service.store)
        portfolio = PortfolioService(store, gateway=getattr(service, "market_gateway", None))
        service.portfolio_store = store
        service.portfolio = portfolio
        register_portfolio_tools(service.registry)
    except Exception:  # noqa: BLE001 - portfolio must never block boot
        service.portfolio = None
        service.portfolio_store = None
        log.warning("portfolio engine unavailable", exc_info=True)


__all__ = ["PortfolioBundle", "install_portfolio_layer"]

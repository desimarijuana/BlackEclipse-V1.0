"""Statistical Analysis Engine boot wiring.

Registers the fourteen statistical tools on the ONE service registry and installs
the persistence + background-runner singletons: a `StatsStore` on the ONE
`agent-memory.db` connection (features, analyses, runs, validations, audit,
artifacts) and the in-process `StatsRunner`. The tool surface itself is pure
computation; installation is best-effort and never blocks boot.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.stats")


def install_stats_layer(service: Any) -> None:
    try:
        from .store import StatsStore
        from .runner import get_runner
        from .service import set_stats_store
        from .tools import register_stats_tools

        register_stats_tools(service.registry)
        store = getattr(service, "store", None)
        if store is not None:
            stats_store = StatsStore(store)
            set_stats_store(stats_store)
            get_runner().set_store(stats_store)
    except Exception:  # noqa: BLE001 - stats must never block boot
        log.warning("statistical analysis engine unavailable", exc_info=True)


__all__ = ["install_stats_layer"]

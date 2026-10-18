"""Boot wiring for the graph runtime.

Best-effort and idempotent: a failure leaves ``service.graphs`` None (the
routes then report the runtime as unavailable) rather than breaking boot. The
service reuses the ONE `agent-memory.db` connection — it introduces no second
store and no second scheduler.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .service import GraphService
from .store import GraphRunStore

log = logging.getLogger("harness.graph_runtime")

_SINGLETON: Optional[GraphService] = None


def get_graph_service() -> Optional[GraphService]:
    """The process-wide graph service, or None before boot wired it."""
    return _SINGLETON


def set_graph_service(service: Optional[GraphService]) -> None:
    global _SINGLETON
    _SINGLETON = service


def install_graph_layer(service: Any) -> bool:
    try:
        store = GraphRunStore(service.store)
        graph_service = GraphService(store)
        # Finance nodes read the runtime's persistent bar series (the SAME vault
        # the research-data tools fill) — no second ingestion path.
        from ..market.series_store import SeriesStore  # noqa: PLC0415

        from .finance_nodes import set_series_store  # noqa: PLC0415

        set_series_store(SeriesStore(service.store))
        service.graphs_store = store
        service.graphs = graph_service
        set_graph_service(graph_service)
        # A run left `running` by the previous process can never finish.
        orphans = store.reconcile_orphans()
        if orphans:
            log.info("marked %d interrupted graph run(s) as failed", orphans)
        return True
    except Exception:  # noqa: BLE001 - never block boot
        log.warning("graph runtime unavailable", exc_info=True)
        service.graphs_store = None
        service.graphs = None
        set_graph_service(None)
        return False


__all__ = ["install_graph_layer", "get_graph_service", "set_graph_service"]

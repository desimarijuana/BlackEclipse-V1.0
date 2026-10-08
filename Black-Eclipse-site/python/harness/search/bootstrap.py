"""Boot wiring for the search layer.

Constructs one process-wide ``SearchService`` (bound to the shared
``agent-memory.db`` for its source adapters, and to the research
``EvidenceStore`` for the evidence bridge) and registers its agent tools on the
shared registry. Best-effort: a failure must never block boot — the runtime then
reports search unavailable rather than crashing.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.search")


def install_search_layer(service: Any) -> Optional[Any]:
    try:
        from .service import SearchService  # noqa: PLC0415
        from .tools import register_search_tools  # noqa: PLC0415

        search = SearchService(
            memory_store=getattr(service, "store", None),
            memory_service=getattr(service, "memory", None),
            evidence_store=getattr(service, "evidence_store", None),
        )
        service.search = search
        register_search_tools(service.registry)
        return search
    except Exception:  # noqa: BLE001 - search must never block boot
        service.search = None
        log.warning("search layer unavailable", exc_info=True)
        return None


__all__ = ["install_search_layer"]

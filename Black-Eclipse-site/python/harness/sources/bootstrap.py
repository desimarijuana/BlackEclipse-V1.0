"""Boot wiring for the source layer.

Builds one process-wide ``SourceService`` (catalog + scan/index threads +
optional semantic index) and registers its tools on the shared registry. Best
effort: a failure must never block boot; the tools then report the layer as
unavailable instead of pretending it works.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("harness.sources")


def install_source_layer(service: Any) -> Optional[Any]:
    try:
        from .service import build_service  # noqa: PLC0415
        from .tools import register_source_tools  # noqa: PLC0415

        sources = build_service()
        service.sources = sources
        register_source_tools(service.registry)
        return sources
    except Exception:  # noqa: BLE001 - sources must never block boot
        service.sources = None
        log.warning("source layer unavailable", exc_info=True)
        return None


__all__ = ["install_source_layer"]

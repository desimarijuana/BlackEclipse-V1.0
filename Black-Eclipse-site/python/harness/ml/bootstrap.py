"""ML Research Lab boot wiring.

Installs the `MLStore` on the ONE `agent-memory.db` connection and registers the
ML agent tools on the ONE service registry. Best-effort: never blocks boot.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.ml")


def install_ml_layer(service: Any) -> None:
    try:
        from .service import set_ml_store
        from .store import MLStore
        from .tools import register_ml_tools

        register_ml_tools(service.registry)
        store = getattr(service, "store", None)
        if store is not None:
            ml_store = MLStore(store)
            service.ml_store = ml_store
            set_ml_store(ml_store)
    except Exception:  # noqa: BLE001 - the ML lab must never block boot
        log.warning("ML research lab unavailable", exc_info=True)


__all__ = ["install_ml_layer"]

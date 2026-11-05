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
        from .tools import register_ml_tools, register_registered_model_tool

        register_ml_tools(service.registry)
        store = getattr(service, "store", None)
        if store is not None:
            ml_store = MLStore(store)
            service.ml_store = ml_store
            set_ml_store(ml_store)
            # Re-register the per-model tools for models that already exist, so a
            # restart does not lose the chat surface of a registered model.
            try:
                for model in ml_store.list_models(limit=200):
                    register_registered_model_tool(
                        service.registry, model_id=str(model["id"]),
                        name=str(model.get("name") or "model"),
                        task=str(model.get("family") or ""))
            except Exception:  # noqa: BLE001 - never block boot
                log.debug("ML per-model tools not restored", exc_info=True)
    except Exception:  # noqa: BLE001 - the ML lab must never block boot
        log.warning("ML research lab unavailable", exc_info=True)


__all__ = ["install_ml_layer"]

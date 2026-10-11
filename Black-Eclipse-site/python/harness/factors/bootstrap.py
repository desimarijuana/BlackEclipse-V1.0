"""Factor & Alpha Research Lab boot wiring.

Installs the `FactorStore` on the ONE `agent-memory.db` connection, registers the
factor agent tools on the ONE service registry, and seeds the evaluable built-in
factor library. Best-effort: never blocks boot.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.factors")


def install_factor_layer(service: Any) -> None:
    try:
        from .store import FactorStore
        from .service import install_builtins, set_factor_store
        from .tools import register_factor_tools

        register_factor_tools(service.registry)
        store = getattr(service, "store", None)
        if store is not None:
            factor_store = FactorStore(store)
            service.factor_store = factor_store
            set_factor_store(factor_store)
            try:
                install_builtins()
            except Exception:  # noqa: BLE001 - seeding is best-effort
                log.warning("built-in factor seeding skipped", exc_info=True)
    except Exception:  # noqa: BLE001 - factors must never block boot
        log.warning("factor research lab unavailable", exc_info=True)


__all__ = ["install_factor_layer"]

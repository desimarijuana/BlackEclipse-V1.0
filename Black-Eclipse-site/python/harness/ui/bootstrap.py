"""Boot wiring for the UI Engineering runtime.

Best-effort and idempotent: a failure leaves `service.ui` None (the routes/tools
then report `UI_UNAVAILABLE`) rather than breaking boot. The service reuses the
ONE `agent-memory.db` connection for its tables and the existing event system for
telemetry; it introduces no second store and no second layout engine.

A module-level singleton lets the agent tools resolve the service even when the
run context was built before the UI layer was attached.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .catalog import UiCatalog
from .service import UiService
from .store import UiStore

log = logging.getLogger("harness.ui")

_SINGLETON: Optional[UiService] = None


def get_ui_service() -> Optional[UiService]:
    return _SINGLETON


def set_ui_service(service: Optional[UiService]) -> None:
    global _SINGLETON
    _SINGLETON = service


def install_ui_layer(service: Any) -> bool:
    """Construct + register the UI runtime on the service. Best-effort."""
    try:
        store = UiStore(service.store)
        ui_service = UiService(store, UiCatalog(), tasks=getattr(service, "tasks", None))
        service.ui_store = store
        service.ui = ui_service
        set_ui_service(ui_service)

        from .tools import register_ui_tools  # noqa: PLC0415

        register_ui_tools(service.registry)
        return True
    except Exception:  # noqa: BLE001 - never block boot
        log.warning("UI runtime unavailable", exc_info=True)
        service.ui_store = None
        service.ui = None
        set_ui_service(None)
        return False


__all__ = ["get_ui_service", "install_ui_layer", "set_ui_service"]

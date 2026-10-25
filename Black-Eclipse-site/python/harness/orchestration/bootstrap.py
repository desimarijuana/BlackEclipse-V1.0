"""Boot wiring for the orchestration layer.

Called from the runtime lifespan so the primary engine exists (for the operator
routes and crash recovery). The engine's model-facing tools are NOT registered:
no built-in agent allowlist names them, so registering them only advertised a
surface the model could never call. `register_orchestration_tools` remains
available for an explicit future surface (and its own tests). Kept out of
`service.py` (which is under a size ratchet).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .service import OrchestrationService

log = logging.getLogger("harness.orchestration.bootstrap")


def install_orchestration_layer(service: Any) -> OrchestrationService:
    """Attach the orchestration service to `service`, idempotently.

    The operator routes (`/orchestration/*`) and the automation dispatcher use
    the engine directly. No agent allowlist names the model-facing tool wrappers,
    so they stay unregistered rather than appearing as dead tools.
    """
    existing = getattr(service, "orchestration", None)
    if existing is not None:
        return existing
    orchestration = OrchestrationService(service)
    service.orchestration = orchestration
    service.orchestration_store = orchestration.store
    return orchestration


async def recover_orchestration(service: Any) -> Optional[list[str]]:
    """Recover interrupted executions. Best-effort: never blocks boot."""
    orchestration = getattr(service, "orchestration", None)
    if orchestration is None:
        return None
    try:
        return await orchestration.primary.recover()
    except Exception:  # noqa: BLE001 - recovery is best-effort
        log.warning("orchestration recovery skipped", exc_info=True)
        return None


__all__ = ["install_orchestration_layer", "recover_orchestration"]

"""Boot wiring for the orchestration layer.

Called from the runtime lifespan so the tool registry carries the orchestration
tools and the primary engine exists for recovery. Kept out of `service.py` (which
is under a size ratchet) and out of the individual subsystems.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .service import OrchestrationService
from .tools import register_orchestration_tools

log = logging.getLogger("harness.orchestration.bootstrap")


def install_orchestration_layer(service: Any) -> OrchestrationService:
    """Attach the orchestration service to `service`, idempotently."""
    existing = getattr(service, "orchestration", None)
    if existing is not None:
        return existing
    orchestration = OrchestrationService(service)
    service.orchestration = orchestration
    service.orchestration_store = orchestration.store
    try:
        register_orchestration_tools(service.registry)
    except ValueError:
        # A tool is already registered (double install) — not fatal.
        log.warning("orchestration tools already registered")
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

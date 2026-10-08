"""Boot wiring for the A2A layer.

`install_a2a_layer(service)` constructs the process-wide `A2AService` (registry +
durable message bus + budgets over the ONE agent-memory connection), seeds the
built-in agent catalogue, and registers the A2A tools on the SAME registry as
every other subsystem. It reuses the existing TaskScheduler (started by the Task
runtime) to execute delegated tasks — it never runs a model itself.

Wiring lives here (not in `service.py`) so the service construction block stays
under its size ratchet, exactly like the orchestration layer.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.a2a.bootstrap")


def install_a2a_layer(service: Any) -> bool:
    """Construct + register the A2A layer. Best-effort; never blocks boot."""
    existing = getattr(service, "a2a", None)
    if existing is not None:
        return True
    try:
        from .service import A2AService  # noqa: PLC0415
        from .tools import register_a2a_tools  # noqa: PLC0415

        a2a = A2AService(service)
        service.a2a = a2a
        service.a2a_store = a2a.store
        service.a2a_registry = a2a.registry
        service.a2a_bus = a2a.bus
        register_a2a_tools(service.registry)
        return True
    except Exception:  # noqa: BLE001 - a failure only leaves a2a absent
        log.warning("[harness-py] A2A layer unavailable", exc_info=True)
        service.a2a = None
        service.a2a_store = None
        service.a2a_registry = None
        service.a2a_bus = None
        return False


def recover_a2a(service: Any) -> list[str]:
    """Re-queue any A2A delegation whose task was left mid-flight by a crash.

    The delegated task itself is recovered by the Task runtime's own recovery;
    here we only re-open the delegation records still marked RUNNING so their
    status reflects reality.
    """
    a2a = getattr(service, "a2a", None)
    if a2a is None:
        return []
    recovered: list[str] = []
    try:
        for record in a2a.store.list_delegations(limit=500):
            if record.status.value == "RUNNING":
                record.status = type(record.status).CREATED
                a2a.store.save_delegation(record)
                recovered.append(record.id)
    except Exception:  # noqa: BLE001
        log.warning("[harness-py] A2A recovery skipped", exc_info=True)
    return recovered


__all__ = ["install_a2a_layer", "recover_a2a"]

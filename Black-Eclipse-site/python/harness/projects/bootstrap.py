"""Project boot wiring.

Creates the `ProjectStore` on the ONE `agent-memory.db` connection and
registers the five project tools on the ONE service registry. Installation is
best-effort: a project layer that cannot boot must never take the runtime with
it, and the tools then report the store as unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.projects")


def install_project_layer(service: Any) -> None:
    try:
        from .store import ProjectStore
        from .tools import register_project_tools

        register_project_tools(service.registry)
        store = getattr(service, "store", None)
        if store is not None:
            service.project_store = ProjectStore(store)
    except Exception:  # noqa: BLE001 - projects must never block boot
        log.warning("project layer unavailable", exc_info=True)


__all__ = ["install_project_layer"]

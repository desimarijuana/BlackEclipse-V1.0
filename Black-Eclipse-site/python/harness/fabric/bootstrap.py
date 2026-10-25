"""Boot wiring for the Execution Fabric.

`install_fabric_layer(service)` constructs the store, the manager, the default
domain workers and the agent tools exactly once and attaches it as
`service.fabric`. `start_fabric`/`stop_fabric`/`recover_fabric` drive the
lifespan. Every step is best-effort: a failure is a diagnostic, never a boot
blocker, so `npm run dev` keeps working.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .builtin_workers import build_default_workers
from .config import FabricConfig
from .integrations import install_event_rules
from .manager import ExecutionManager
from .store import FabricStore
from .tools import register_fabric_tools, set_fabric_manager

log = logging.getLogger("harness.fabric.bootstrap")


def install_fabric_layer(service: Any) -> Optional[ExecutionManager]:
    existing = getattr(service, "fabric", None)
    if existing is not None:
        return existing
    try:
        config = FabricConfig.from_env()
        if not config.enabled:
            service.fabric = None
            service.fabric_store = None
            log.info("execution fabric disabled (HARNESS_FABRIC_ENABLED=0)")
            return None
        store = FabricStore(service.store)
        manager = ExecutionManager(store, config=config, service=service)
        for worker in build_default_workers(service, config):
            if config.runs_worker(worker.kind, worker.queues):
                manager.register_worker(worker)
        # Graph Studio runs on the same durable queue. The worker is registered
        # here because the fabric is installed after the graph layer and owns
        # the single worker pool. A graph-worker failure must not disable the
        # rest of the fabric.
        try:
            from ..graph_runtime.worker import GraphWorker  # noqa: PLC0415

            graph_worker = GraphWorker(service)
            if config.runs_worker(graph_worker.kind, graph_worker.queues):
                manager.register_worker(graph_worker)
            graphs = getattr(service, "graphs", None)
            if graphs is not None:
                graphs.set_fabric(manager)
        except Exception:  # noqa: BLE001 - graph dispatch is optional at boot
            log.warning("graph fabric worker unavailable", exc_info=True)
        service.fabric = manager
        service.fabric_store = store
        service.fabric_config = config
        set_fabric_manager(manager)
        try:
            register_fabric_tools(service.registry)
        except Exception:  # noqa: BLE001 - a tool collision must not block boot
            log.warning("fabric tools already registered", exc_info=True)
        subscription = install_event_rules(manager, service)
        if subscription is not None:
            service._fabric_event_subscription = subscription
        return manager
    except Exception:  # noqa: BLE001 - the fabric must never block boot
        log.warning("execution fabric unavailable", exc_info=True)
        service.fabric = None
        service.fabric_store = None
        return None


async def start_fabric(service: Any) -> None:
    manager = getattr(service, "fabric", None)
    if manager is None:
        return
    try:
        await manager.start()
    except Exception:  # noqa: BLE001 - the fabric must never block boot
        log.warning("execution fabric failed to start", exc_info=True)


async def recover_fabric(service: Any) -> Optional[list[str]]:
    manager = getattr(service, "fabric", None)
    if manager is None:
        return None
    try:
        return await manager.recover()
    except Exception:  # noqa: BLE001
        log.warning("execution fabric recovery skipped", exc_info=True)
        return None


async def stop_fabric(service: Any) -> None:
    manager = getattr(service, "fabric", None)
    if manager is None:
        return
    try:
        await manager.stop()
    except Exception:  # noqa: BLE001
        log.warning("execution fabric shutdown failed", exc_info=True)
    subscription = getattr(service, "_fabric_event_subscription", None)
    if subscription is not None:
        try:
            subscription.unsubscribe()
        except Exception:  # noqa: BLE001
            pass
        service._fabric_event_subscription = None


__all__ = [
    "install_fabric_layer",
    "recover_fabric",
    "start_fabric",
    "stop_fabric",
]

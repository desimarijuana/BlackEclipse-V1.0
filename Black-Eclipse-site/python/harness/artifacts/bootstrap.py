"""Boot wiring for the Artifact Center.

Best-effort, idempotent and non-blocking: a failure leaves `service.artifacts`
None (the routes/tools then report `ARTIFACT_UNAVAILABLE`) rather than breaking
boot. The service reuses the ONE `agent-memory.db` connection and the existing
per-run event bus; it introduces no second store.

A module-level singleton lets non-`ToolContext` producers (analysis, task
scheduler, execution) reach the same service without threading it through every
call site.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from .service import ArtifactService
from .storage import LocalArtifactStorage
from .store import ArtifactStore

log = logging.getLogger("harness.artifacts")

_SINGLETON: Optional[ArtifactService] = None


def get_artifact_service() -> Optional[ArtifactService]:
    """The process-wide artifact service, or None before boot wired it."""
    return _SINGLETON


def set_artifact_service(service: Optional[ArtifactService]) -> None:
    global _SINGLETON
    _SINGLETON = service


class _Reconciler:
    """A bounded background reconciliation loop (opt-in, default 15 min)."""

    def __init__(self, service: ArtifactService, interval: float, retention_days: int = 30) -> None:
        self._service = service
        self._interval = interval
        self._retention_days = retention_days
        self._task: Optional[asyncio.Task] = None

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval)
                await asyncio.to_thread(
                    self._service.reconcile, discover=True,
                    purge_expired=True, retention_days=self._retention_days,
                )
            except asyncio.CancelledError:  # noqa: PERF203
                return
            except Exception:  # noqa: BLE001 - reconciliation must never crash
                log.warning("artifact reconciliation failed", exc_info=True)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None


def install_artifact_layer(service: Any) -> bool:
    """Construct + register the Artifact Center on the service. Best-effort."""
    try:
        store = ArtifactStore(service.store)
        storage = LocalArtifactStorage()
        artifact_service = ArtifactService(store, storage)
        service.artifacts_store = store
        service.artifacts = artifact_service
        set_artifact_service(artifact_service)

        from .tools import register_artifact_tools  # noqa: PLC0415

        register_artifact_tools(service.registry)
        return True
    except Exception:  # noqa: BLE001 - never block boot
        log.warning("artifact layer unavailable", exc_info=True)
        service.artifacts_store = None
        service.artifacts = None
        set_artifact_service(None)
        return False


def start_artifact_reconciler(service: Any) -> Optional[_Reconciler]:
    artifact_service = getattr(service, "artifacts", None)
    if artifact_service is None:
        return None
    if os.environ.get("HARNESS_ARTIFACT_RECONCILE", "1").lower() in ("0", "false", "off"):
        return None
    interval = float(os.environ.get("HARNESS_ARTIFACT_RECONCILE_SECONDS", "900"))
    retention_days = int(os.environ.get("HARNESS_ARTIFACT_RETENTION_DAYS", "30"))
    auto_purge = os.environ.get("HARNESS_ARTIFACT_AUTO_PURGE", "1").lower() not in ("0", "false", "off")
    reconciler = _Reconciler(
        artifact_service, max(60.0, interval),
        retention_days=retention_days if auto_purge else 10_000_000,
    )
    service._artifact_reconciler = reconciler  # noqa: SLF001 - service-owned handle
    try:
        reconciler.start()
    except RuntimeError:
        # No running loop (a sync boot path); reconcile then remains on-demand.
        service._artifact_reconciler = None  # noqa: SLF001
        return None
    return reconciler


async def stop_artifact_reconciler(service: Any) -> None:
    reconciler = getattr(service, "_artifact_reconciler", None)
    if reconciler is not None:
        await reconciler.stop()


__all__ = [
    "get_artifact_service",
    "install_artifact_layer",
    "set_artifact_service",
    "start_artifact_reconciler",
    "stop_artifact_reconciler",
]

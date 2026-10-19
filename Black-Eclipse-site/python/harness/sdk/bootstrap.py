"""Boot wiring for the Eclipse SDK.

Installed after the UI Engineering and Portfolio layers. A failure leaves
`service.sdk` None rather than blocking boot; the `/sdk` routes then report the
runtime unavailable honestly.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .locks import LockService, set_lock_service
from .service import EclipseSdk
from .store import SdkStore

log = logging.getLogger("harness.sdk")

_SINGLETON: Optional[EclipseSdk] = None


def get_sdk_service() -> Optional[EclipseSdk]:
    return _SINGLETON


def set_sdk_service(service: Optional[EclipseSdk]) -> None:
    global _SINGLETON
    _SINGLETON = service


def install_sdk_layer(service: Any) -> bool:
    """Construct + register the SDK on the shared runtime service. Best-effort."""
    try:
        store = SdkStore(service.store)
        locks = LockService(store)
        set_lock_service(locks)
        sdk = EclipseSdk(
            store,
            getattr(service, "ui", None),
            getattr(service, "portfolio", None),
            locks,
        )
        # Attach the lock registry to the already-installed services so their
        # enforcement does not depend on the module singleton (which tests and
        # a re-install may replace).
        ui = getattr(service, "ui", None)
        if ui is not None:
            ui._locks = locks
        portfolio = getattr(service, "portfolio", None)
        if portfolio is not None:
            portfolio._locks = locks
        service.sdk_store = store
        service.sdk_locks = locks
        service.sdk = sdk
        set_sdk_service(sdk)
        registry = getattr(service, "registry", None)
        if registry is not None:
            from .tools import register_sdk_tools  # noqa: PLC0415

            register_sdk_tools(registry)
        return True
    except Exception:  # noqa: BLE001 - never block boot
        log.warning("Eclipse SDK unavailable", exc_info=True)
        service.sdk_store = None
        service.sdk_locks = None
        service.sdk = None
        set_sdk_service(None)
        set_lock_service(None)
        return False


__all__ = ["get_sdk_service", "install_sdk_layer", "set_sdk_service"]

"""Gallery boot wiring."""

from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger("harness.gallery")

#: The process-wide gallery store, so the tools can reach it without a run
#: context carrying it.
_GALLERY_STORE: Optional[Any] = None


def set_gallery_store(store: Optional[Any]) -> None:
    global _GALLERY_STORE
    _GALLERY_STORE = store


def get_gallery_store() -> Optional[Any]:
    return _GALLERY_STORE


def install_gallery_layer(service: Any) -> None:
    """Create the gallery store and register the gallery tools."""
    try:
        from .store import GalleryStore
        from .tools import register_gallery_tools

        register_gallery_tools(service.registry)
        store = getattr(service, "store", None)
        if store is None:
            return
        service.gallery_store = GalleryStore(store)
        set_gallery_store(service.gallery_store)
    except Exception:  # noqa: BLE001 - the gallery must never block boot
        log.warning("gallery layer unavailable", exc_info=True)


__all__ = ["get_gallery_store", "install_gallery_layer", "set_gallery_store"]

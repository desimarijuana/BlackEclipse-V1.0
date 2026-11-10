"""Quant Engine boot wiring.

Constructs the One quant store on the service and registers the `quant_*` tools
on the SAME registry. Best-effort: a failure leaves the capability unavailable
rather than blocking boot (matching the market/portfolio pattern).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger("harness.quant")


@dataclass
class QuantBundle:
    """The quant subsystem handed to a run: stores for strategies/experiments and
    immutable research datasets."""

    store: Optional[Any] = None
    dataset_store: Optional[Any] = None


def install_quant_layer(service: Any) -> None:
    try:
        from .dataset_store import DatasetStore
        from .store import QuantStore
        from .tools import register_quant_tools

        service.quant_store = QuantStore(service.store)
        service.dataset_store = DatasetStore(service.store)
        # The method knowledge base lives on the SAME QuantMethod table. Seeding
        # is idempotent and never overwrites a research registration.
        try:
            from .research_intel.store import ResearchStore

            ResearchStore(service.quant_store).seed_catalog()
        except Exception:  # noqa: BLE001 - research seeding must not block quant boot
            log.debug("quant research catalog seed unavailable", exc_info=True)
        register_quant_tools(service.registry)
        # The unified catalog spans quant/ML/stats/factors. It is registered
        # here but resolves the other stores lazily at call time, so boot order
        # cannot hide an artifact family.
        try:
            from ..model_catalog import register_model_catalog_tool  # noqa: PLC0415

            register_model_catalog_tool(service.registry)
        except Exception:  # noqa: BLE001 - the catalog must not block quant boot
            log.debug("model catalog unavailable", exc_info=True)
    except Exception:  # noqa: BLE001 - quant engine must never block boot
        service.quant_store = None
        service.dataset_store = None
        log.warning("quant engine unavailable", exc_info=True)


__all__ = ["QuantBundle", "install_quant_layer"]

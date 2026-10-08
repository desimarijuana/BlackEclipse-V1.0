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
    """The quant subsystem handed to a run: the strategy/experiment store."""

    store: Optional[Any] = None


def install_quant_layer(service: Any) -> None:
    try:
        from .store import QuantStore
        from .tools import register_quant_tools

        service.quant_store = QuantStore(service.store)
        register_quant_tools(service.registry)
    except Exception:  # noqa: BLE001 - quant engine must never block boot
        service.quant_store = None
        log.warning("quant engine unavailable", exc_info=True)


__all__ = ["QuantBundle", "install_quant_layer"]

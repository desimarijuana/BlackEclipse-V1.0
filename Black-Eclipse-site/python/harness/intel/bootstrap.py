"""Intel layer boot wiring.

Constructs the ONE intelligence service (observation store + collectors) and
registers its tools on the SAME registry, reusing the ONE agent-memory
connection. Called once from `AgenticService.__init__`, mirroring the advisory
and decision layers.

Best-effort: a failure leaves the tools unregistered (the agent simply never
advertises them) rather than blocking boot. No network call happens at boot —
a scan only touches the network when a tool is actually called.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.intel")


def install_intel_layer(service: Any) -> None:
    try:
        from .service import IntelService
        from .tools import register_intel_tools

        intel = IntelService(service.store)
        service.intel = intel
        register_intel_tools(service.registry, intel)
    except Exception:  # noqa: BLE001 - intel must never block boot
        service.intel = None
        log.warning("intel layer unavailable", exc_info=True)


__all__ = ["install_intel_layer"]

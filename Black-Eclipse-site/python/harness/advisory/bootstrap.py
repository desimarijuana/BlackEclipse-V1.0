"""Advisory Ledger boot wiring.

Constructs the ONE advisory service/store and registers its tools on the SAME
registry, reusing the ONE agent-memory connection. Imported and called once from
`AgenticService.__init__` (mirroring the portfolio layer) so `service.py` stays
under its size ratchet. Best-effort: a failure leaves the capability unavailable
rather than blocking boot.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("harness.advisory")


def install_advisory_layer(service: Any) -> None:
    try:
        from .service import AdvisoryService
        from .tools import register_advisory_tools

        advisory = AdvisoryService(service.store)
        service.advisory = advisory
        register_advisory_tools(service.registry)
    except Exception:  # noqa: BLE001 - advisory must never block boot
        service.advisory = None
        log.warning("advisory ledger unavailable", exc_info=True)


__all__ = ["install_advisory_layer"]

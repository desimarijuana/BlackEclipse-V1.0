"""Ledger boot wiring.

Constructs the ONE ledger service/store and registers its tools on the SAME
registry, reusing the ONE agent-memory connection. Called once from
`AgenticService.__init__` (mirroring the portfolio layer).

Best-effort, like every other layer: a failure leaves the accounting capability
unavailable and logs — it never blocks boot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger("harness.ledger")


@dataclass
class LedgerBundle:
    service: Any
    store: Optional[Any] = None


def install_ledger_layer(service: Any) -> None:
    try:
        from .service import LedgerService
        from .store import LedgerStore
        from .tools import register_ledger_tools

        store = LedgerStore(service.store)
        ledger = LedgerService(store)
        service.ledger_store = store
        service.ledger = ledger
        register_ledger_tools(service.registry)
    except Exception:  # noqa: BLE001 - accounting must never block boot
        service.ledger = None
        service.ledger_store = None
        log.warning("general ledger unavailable", exc_info=True)


__all__ = ["LedgerBundle", "install_ledger_layer"]
